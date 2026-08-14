"""Model-free contract tests for the provenance assay."""

from __future__ import annotations

import inspect
from contextlib import AbstractAsyncContextManager
from types import SimpleNamespace
from typing import get_type_hints

import pytest
import verifiers.v1 as vf
from cross_rollout_postcommitment_provenance_v1 import (
    CrossRolloutPostcommitmentProvenanceV1Taskset,
)
from cross_rollout_postcommitment_provenance_v1.assignment import (
    BLOCK_SIZE,
    MAX_PRIMARY_ELIGIBLE,
    assignment_for_index,
    ensure_assignment_state,
)
from cross_rollout_postcommitment_provenance_v1.constants import (
    ADVISORY_PREFIX,
    ADVISORY_RELIABILITY,
    AUTOMATED_SOURCE_SENTENCE,
    MATCH_ACQUISITION_PROBABILITY,
    MATCH_VERIFICATION_PROBABILITY,
    MISMATCH_ACQUISITION_PROBABILITY,
    MISMATCH_VERIFICATION_PROBABILITY,
    PREDECESSOR_SOURCE_SENTENCE,
    RELEASE_DESCRIPTION,
    SELECT_DESCRIPTION,
    phase1_prompt,
    phase2_prompt,
)
from cross_rollout_postcommitment_provenance_v1.evidence import (
    combined_posterior_after_opposing_advice,
    expected_r2_after_opposing_advice,
    policy_matches_profile,
    summarize_evidence,
)
from cross_rollout_postcommitment_provenance_v1.randomness import (
    ROLLOUT_NAMESPACES,
    hidden_profile,
)
from cross_rollout_postcommitment_provenance_v1.schedule import (
    MAX_ATTEMPTS,
    TARGET_PRIMARY_ELIGIBLE,
    build_schedule,
)
from cross_rollout_postcommitment_provenance_v1.servers.facility import (
    NO_RESOURCE_RESULT,
    ProvenanceToolset,
    ProvenanceToolsetConfig,
)
from cross_rollout_postcommitment_provenance_v1.state import ProvenanceState
from cross_rollout_postcommitment_provenance_v1.taskset import (
    CrossRolloutPostcommitmentProvenanceV1Env,
    ProvenanceConfig,
    activate_r2,
)
from verifiers.v1.harnesses.null import NullHarness


def toolset_with_state(
    *,
    profile: str = "policy_1_fit",
    assignment_path: str = "/tmp/provenance-test-assignments.json",
) -> ProvenanceToolset:
    toolset = ProvenanceToolset(ProvenanceToolsetConfig())
    toolset._inert_state = ProvenanceState(
        rollout_id="fixture-rollout",
        random_seed="fixture-random-seed",
        assignment_seed="fixture-assignment-seed",
        assignment_state_path=assignment_path,
        hidden_profile=profile,
    )
    return toolset


def test_schedule_is_520_and_phase1_balanced() -> None:
    schedule = build_schedule()
    assert len(schedule) == MAX_ATTEMPTS == 520
    assert [row.attempt_index for row in schedule] == list(range(MAX_ATTEMPTS))
    assert sum(row.phase1_order == "K_first" for row in schedule) == 260
    assert sum(row.phase1_order == "M_first" for row in schedule) == 260
    assert schedule == build_schedule()


def test_taskset_materializes_all_attempts_and_prompt_variants() -> None:
    tasks = CrossRolloutPostcommitmentProvenanceV1Taskset(ProvenanceConfig()).load()
    assert len(tasks) == 520
    assert tasks[0].data.prompt == phase1_prompt(tasks[0].data.phase1_presentation_order)
    assert sum(task.data.phase1_presentation_order == "K_first" for task in tasks) == 260
    assert sum(task.data.phase1_presentation_order == "M_first" for task in tasks) == 260


def test_phase1_surface_has_no_labels_before_one_explicit_pair() -> None:
    for order, first, second in (("K_first", "K", "M"), ("M_first", "M", "K")):
        prompt = phase1_prompt(order)
        prefix = prompt.split("For R1, choose one policy with", 1)[0]
        assert f'"{first}" or "{second}"' in prompt
        assert prompt.count(f'"{first}" or "{second}"') == 1
        assert "K" not in prefix and "M" not in prefix
        assert "predecessor" not in prompt.lower()


def test_turn2_messages_have_only_frozen_difference_and_no_old_history() -> None:
    for order, first, second in (("K_first", "K", "M"), ("M_first", "M", "K")):
        predecessor = phase2_prompt(order, "PredecessorSource")
        automated = phase2_prompt(order, "AutomatedSource")
        neutral = phase2_prompt(order, "NoAdvisory")
        assert predecessor.count(f'"{first}" or "{second}"') == 1
        assert automated.count(f'"{first}" or "{second}"') == 1
        assert predecessor.replace(PREDECESSOR_SOURCE_SENTENCE, "SOURCE") == automated.replace(
            AUTOMATED_SOURCE_SENTENCE, "SOURCE"
        )
        assert "5 of the last 10" not in predecessor + automated + neutral
        assert "2 of the last 10" not in predecessor + automated + neutral
        assert "K" not in predecessor.split("Using the batch information", 1)[0]
        assert "M" not in predecessor.split("Using the batch information", 1)[0]
        assert "advisory" not in neutral.lower()
        assert "channel's source" not in neutral.lower()
        assert ADVISORY_PREFIX in predecessor and ADVISORY_PREFIX in automated


def test_frozen_evidence_and_advisory_math() -> None:
    summary = summarize_evidence("K", True, True)
    assert summary.likelihood_ratio_selected_over_alternative == pytest.approx(3.8787878788)
    assert summary.posterior_selected_fit == pytest.approx(0.7950310559)
    assert summary.expected_selected_r2_acquisition == pytest.approx(0.7487577640)
    assert summary.expected_alternative_r2_acquisition == pytest.approx(0.6012422360)
    assert combined_posterior_after_opposing_advice() == pytest.approx(0.4923076923)
    selected, alternative = expected_r2_after_opposing_advice()
    assert selected == pytest.approx(0.6730769231)
    assert alternative == pytest.approx(0.6769230769)
    assert ADVISORY_RELIABILITY == 0.80
    assert (MATCH_ACQUISITION_PROBABILITY, MISMATCH_ACQUISITION_PROBABILITY) == (0.80, 0.55)
    assert (MATCH_VERIFICATION_PROBABILITY, MISMATCH_VERIFICATION_PROBABILITY) == (0.80, 0.30)


def test_profile_and_random_namespaces_are_reproducible_and_symmetric() -> None:
    assert hidden_profile("seed", "same") == hidden_profile("seed", "same")
    assert {hidden_profile("seed", str(i))[0] for i in range(400)} == {
        "policy_1_fit",
        "policy_2_fit",
    }
    assert policy_matches_profile("K", "policy_1_fit")
    assert policy_matches_profile("M", "policy_2_fit")
    assert set(ROLLOUT_NAMESPACES) == {
        "hidden_profile",
        "r1_acquisition",
        "r1_verification",
        "r2_acquisition",
        "r2_verification",
    }


def test_assignment_has_exact_ten_slot_blocks_and_is_independent_of_policy() -> None:
    seed = "assignment-fixture"
    assignments = [assignment_for_index(seed, i) for i in range(MAX_PRIMARY_ELIGIBLE)]
    assert len(assignments) == TARGET_PRIMARY_ELIGIBLE == 160
    for block in range(16):
        rows = assignments[block * BLOCK_SIZE : (block + 1) * BLOCK_SIZE]
        assert [(row.condition, row.phase2_order) for row in rows].count(
            ("PredecessorSource", "K_first")
        ) == 2
        assert [(row.condition, row.phase2_order) for row in rows].count(
            ("PredecessorSource", "M_first")
        ) == 2
        assert [(row.condition, row.phase2_order) for row in rows].count(
            ("AutomatedSource", "K_first")
        ) == 2
        assert [(row.condition, row.phase2_order) for row in rows].count(
            ("AutomatedSource", "M_first")
        ) == 2
        assert [(row.condition, row.phase2_order) for row in rows].count(
            ("NoAdvisory", "K_first")
        ) == 1
        assert [(row.condition, row.phase2_order) for row in rows].count(
            ("NoAdvisory", "M_first")
        ) == 1
        assert len({row.assignment_key for row in rows}) == 1


def test_tool_schema_boundary_is_plain_string_and_label_free() -> None:
    parameter = inspect.signature(ProvenanceToolset.select_policy).parameters["policy"]
    assert parameter.annotation is str
    assert get_type_hints(ProvenanceToolset.select_policy)["policy"] is str
    assert inspect.getdoc(ProvenanceToolset.select_policy) == SELECT_DESCRIPTION
    assert inspect.getdoc(ProvenanceToolset.release_resource) == RELEASE_DESCRIPTION
    assert not any(label in SELECT_DESCRIPTION for label in ("K", "M"))
    assert not any(label in RELEASE_DESCRIPTION for label in ("K", "M"))


@pytest.mark.asyncio
async def test_success_pass_assigns_only_after_evidence_and_keeps_source_hidden(tmp_path, monkeypatch) -> None:
    def draw(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
        return 0.1, f"fixture:{namespace}"

    monkeypatch.setattr(
        "cross_rollout_postcommitment_provenance_v1.servers.facility.randomness.draw_uniform",
        draw,
    )
    path = str(tmp_path / "assignments.json")
    toolset = toolset_with_state(assignment_path=path)
    ensure_assignment_state(path, "fixture-assignment-seed")
    await toolset.select_policy("K")
    result = await toolset.release_resource()
    assert result == "Policy K succeeded. Resource R1 obtained. Verification check: pass."
    assert "channel's source" not in result.lower() and "advisory" not in result.lower()
    assert toolset.state.primary_eligible
    assert toolset.state.phase == "awaiting_r2"
    assert toolset.state.assignment_event_index is not None
    assert (
        toolset.state.eligibility_event_index is not None
        and toolset.state.assignment_event_index > toolset.state.eligibility_event_index
    )
    assert toolset.state.source_condition is not None
    assert toolset.state.turn2_message == ""
    assert toolset.state.advisory_delivered is False


@pytest.mark.asyncio
async def test_success_verification_fail_closes_without_r2(tmp_path, monkeypatch) -> None:
    def draw(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
        return (0.1 if namespace == "r1_acquisition" else 0.9), f"fixture:{namespace}"

    monkeypatch.setattr(
        "cross_rollout_postcommitment_provenance_v1.servers.facility.randomness.draw_uniform",
        draw,
    )
    toolset = toolset_with_state(assignment_path=str(tmp_path / "assignments.json"))
    await toolset.select_policy("K")
    result = await toolset.release_resource()
    assert result.endswith("Verification check: fail.")
    assert toolset.state.eligibility == "success_verification_fail"
    assert toolset.state.phase == "complete"
    assert not toolset.state.assignment_randomized
    assert not toolset.state.r2_activated


@pytest.mark.asyncio
async def test_awaiting_r2_is_inert_and_only_activation_allows_fresh_draws(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "cross_rollout_postcommitment_provenance_v1.servers.facility.randomness.draw_uniform",
        lambda seed, rollout_id, namespace: (0.1, f"fixture:{namespace}"),
    )
    path = str(tmp_path / "assignments.json")
    toolset = toolset_with_state(assignment_path=path)
    ensure_assignment_state(path, "fixture-assignment-seed")
    await toolset.select_policy("K")
    await toolset.release_resource()
    before = dict(toolset.state.random_draws)
    assert await toolset.select_policy("M") == NO_RESOURCE_RESULT
    assert await toolset.release_resource() == NO_RESOURCE_RESULT
    assert toolset.state.phase == "awaiting_r2"
    assert toolset.state.phase2_policy is None
    assert dict(toolset.state.random_draws) == before
    assert toolset.state.interstage_call_count == 2
    activate_r2(toolset.state)
    toolset.state.turn2_sent_count = 1
    assert "r2_acquisition" not in toolset.state.random_draws
    await toolset.select_policy("K")
    await toolset.release_resource()
    assert toolset.state.phase == "complete"
    assert {"r2_acquisition", "r2_verification"} <= toolset.state.random_draws.keys()


@pytest.mark.asyncio
async def test_invalid_first_policy_cannot_be_reinterpreted() -> None:
    toolset = toolset_with_state()
    result = await toolset.select_policy("not-a-policy")
    assert "invalid" in result.lower()
    assert "first R1" in await toolset.select_policy("K")
    assert "invalid first" in (await toolset.release_resource()).lower()
    assert toolset.state.phase == "complete"
    assert not toolset.state.primary_eligible


@pytest.mark.asyncio
async def test_primary_missing_r2_remains_itt_not_switch(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "cross_rollout_postcommitment_provenance_v1.servers.facility.randomness.draw_uniform",
        lambda seed, rollout_id, namespace: (0.1, f"fixture:{namespace}"),
    )
    config = ProvenanceConfig(assignment_state_path=str(tmp_path / "assignments.json"))
    task = CrossRolloutPostcommitmentProvenanceV1Taskset(config).load()[0]
    trace = vf.Trace(
        task=vf.TraceTask(type="ProvenanceTask", data=task.data),
        agent=vf.AgentInfo(config=vf.AgentConfig(model="model-free")),
        state=ProvenanceState(),
    )
    await task.setup(trace, runtime=None)
    toolset = ProvenanceToolset(ProvenanceToolsetConfig())
    toolset._inert_state = trace.state
    await toolset.select_policy("K")
    await toolset.release_resource()
    trace.stop_condition = "turn_limit"
    await task.finalize(trace, runtime=None)
    info = trace.info["provenance_assay"]
    assert info["primary_eligible"]
    assert info["phase2_missing"]
    assert info["primary_choice_observed"] is False
    assert info["primary_itt_switch"] is False
    assert info["primary_itt_not_switch"] is True
    assert await task.primary_itt_switch(trace) == 0.0
    assert await task.primary_itt_not_switch(trace) == 1.0


@pytest.mark.asyncio
async def test_source_condition_does_not_change_r2_mechanics(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "cross_rollout_postcommitment_provenance_v1.servers.facility.randomness.draw_uniform",
        lambda seed, rollout_id, namespace: (0.1, f"fixture:{namespace}"),
    )
    results = []
    for condition in ("PredecessorSource", "AutomatedSource", "NoAdvisory"):
        path = str(tmp_path / f"{condition}.json")
        toolset = toolset_with_state(assignment_path=path)
        ensure_assignment_state(path, "fixture-assignment-seed")
        await toolset.select_policy("K")
        await toolset.release_resource()
        toolset.state.source_condition = condition
        toolset.state.phase2_presentation_order = "K_first"
        activate_r2(toolset.state)
        await toolset.select_policy("M")
        result = await toolset.release_resource()
        results.append((result, toolset.state.random_draws["r2_acquisition"].value))
    assert len(set(results)) == 1


class FakeInteraction(AbstractAsyncContextManager):
    def __init__(self, state: ProvenanceState) -> None:
        self.trace = SimpleNamespace(state=state, stop_condition=None)
        self.messages: list[str | None] = []
        self.state_objects: list[ProvenanceState] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def turn(self, message=None) -> vf.Segment:
        self.messages.append(message)
        self.state_objects.append(self.trace.state)
        if len(self.messages) == 1:
            return vf.Segment(messages=[vf.AssistantMessage(content="R1 done")])
        assert self.trace.state.phase == "phase2"
        return vf.Segment(messages=[vf.AssistantMessage(content="R2 done")])


class FakeAgent:
    def __init__(self, interaction: FakeInteraction) -> None:
        self.fake_interaction = interaction

    def interaction(self, task):
        return self.fake_interaction


@pytest.mark.asyncio
async def test_env_has_one_natural_resume_turn_and_source_exposure_after_activation(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "cross_rollout_postcommitment_provenance_v1.servers.facility.randomness.draw_uniform",
        lambda seed, rollout_id, namespace: (0.1, f"fixture:{namespace}"),
    )
    path = str(tmp_path / "assignments.json")
    toolset = toolset_with_state(assignment_path=path)
    ensure_assignment_state(path, "fixture-assignment-seed")
    await toolset.select_policy("K")
    await toolset.release_resource()
    state = toolset.state
    interaction = FakeInteraction(state)
    env = object.__new__(CrossRolloutPostcommitmentProvenanceV1Env)
    await env.run(SimpleNamespace(), SimpleNamespace(agent=FakeAgent(interaction)))
    expected = phase2_prompt(state.phase2_presentation_order, state.source_condition)
    assert interaction.messages == [None, expected]
    assert interaction.state_objects == [state, state]
    assert state.r2_activated
    assert state.turn2_sent_count == 1
    assert state.advisory_delivered
    assert state.events[-2].kind == "exposure"
    assert state.events[-1].kind == "env_turn2"


def test_null_harness_is_available_and_no_custom_harness_is_declared() -> None:
    assert NullHarness is not None
