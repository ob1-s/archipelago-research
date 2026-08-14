"""Model-free contract tests for the provenance-boundary assay."""

from __future__ import annotations

import inspect
import subprocess
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from types import SimpleNamespace
from typing import get_type_hints

import pytest
import verifiers.v1 as vf
from verifiers.v1.harnesses.null import NullHarness, NullHarnessConfig
from verifiers.v1.runtimes import ProgramResult

from cross_rollout_postcommitment_provenance_boundary_v1 import (
    CrossRolloutPostcommitmentProvenanceBoundaryV1Env,
    CrossRolloutPostcommitmentProvenanceBoundaryV1Taskset,
)
from cross_rollout_postcommitment_provenance_boundary_v1.assignment import (
    BLOCK_SIZE,
    MAX_PRIMARY_ELIGIBLE,
    build_assignment_plan,
    claim_assignment,
    current_eligible_count,
    ensure_assignment_state,
)
from cross_rollout_postcommitment_provenance_boundary_v1.constants import (
    ADVISORY_RELIABILITY_LEVELS,
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
from cross_rollout_postcommitment_provenance_boundary_v1.evidence import (
    NORMATIVE_CROSSOVER,
    PRIVATE_LR_SUCCESS_PASS,
    combined_posterior_selected_fit,
    policy_matches_profile,
    summarize_evidence,
)
from cross_rollout_postcommitment_provenance_boundary_v1.randomness import (
    ROLLOUT_NAMESPACES,
    hidden_profile,
)
from cross_rollout_postcommitment_provenance_boundary_v1.schedule import (
    MAX_ATTEMPTS,
    TARGET_PRIMARY_ELIGIBLE,
    build_schedule,
)
from cross_rollout_postcommitment_provenance_boundary_v1.servers.facility import (
    NO_RESOURCE_RESULT,
    BoundaryToolset,
    BoundaryToolsetConfig,
)
from cross_rollout_postcommitment_provenance_boundary_v1.state import BoundaryState
from cross_rollout_postcommitment_provenance_boundary_v1.taskset import (
    BoundaryConfig,
    activate_r2,
)


def toolset_with_state(
    *,
    profile: str = "policy_1_fit",
    assignment_path: str = "/tmp/provenance-boundary-test-assignments.json",
) -> BoundaryToolset:
    toolset = BoundaryToolset(BoundaryToolsetConfig())
    toolset._inert_state = BoundaryState(
        rollout_id="fixture-rollout",
        random_seed="fixture-random-seed",
        assignment_seed="fixture-assignment-seed",
        assignment_state_path=assignment_path,
        hidden_profile=profile,
    )
    return toolset


def test_schedule_is_1400_and_phase1_balanced() -> None:
    schedule = build_schedule()
    assert len(schedule) == MAX_ATTEMPTS == 1400
    assert [row.attempt_index for row in schedule] == list(range(MAX_ATTEMPTS))
    assert sum(row.phase1_order == "K_first" for row in schedule) == 700
    assert sum(row.phase1_order == "M_first" for row in schedule) == 700
    assert schedule == build_schedule()


def test_taskset_materializes_the_frozen_attempt_cap() -> None:
    tasks = CrossRolloutPostcommitmentProvenanceBoundaryV1Taskset(
        BoundaryConfig()
    ).load()
    assert len(tasks) == MAX_ATTEMPTS
    assert tasks[0].data.prompt == phase1_prompt(tasks[0].data.phase1_presentation_order)
    assert sum(task.data.phase1_presentation_order == "K_first" for task in tasks) == 700
    assert sum(task.data.phase1_presentation_order == "M_first" for task in tasks) == 700


def test_phase1_surface_has_no_source_or_q_before_one_explicit_pair() -> None:
    for order, first, second in (("K_first", "K", "M"), ("M_first", "M", "K")):
        prompt = phase1_prompt(order)
        prefix = prompt.split("For R1, choose one policy with", 1)[0]
        assert f'"{first}" or "{second}"' in prompt
        assert prompt.count(f'"{first}" or "{second}"') == 1
        assert "K" not in prefix and "M" not in prefix
        assert "predecessor" not in prompt.lower()
        assert "advisory" not in prompt.lower()
        assert "%" not in prefix


def test_exact_q_grid_and_frozen_turn2_surface() -> None:
    expected_percentages = [
        "78.00%",
        "78.50%",
        "79.00%",
        "79.25%",
        "79.50%",
        "79.75%",
        "80.00%",
        "80.50%",
        "81.00%",
    ]
    assert ADVISORY_RELIABILITY_LEVELS == (
        0.7800,
        0.7850,
        0.7900,
        0.7925,
        0.7950,
        0.7975,
        0.8000,
        0.8050,
        0.8100,
    )
    for q, percentage in zip(ADVISORY_RELIABILITY_LEVELS, expected_percentages):
        predecessor = phase2_prompt("K_first", q, "PredecessorSource")
        automated = phase2_prompt("K_first", q, "AutomatedSource")
        assert percentage in predecessor and percentage in automated
        assert predecessor.count('select_policy(policy="K" or "M")') == 1
        assert automated.count('select_policy(policy="K" or "M")') == 1
        assert (
            predecessor.replace(PREDECESSOR_SOURCE_SENTENCE, "SOURCE")
            == automated.replace(AUTOMATED_SOURCE_SENTENCE, "SOURCE")
        )
        assert "5 of the last 10" not in predecessor
        assert "2 of the last 10" not in predecessor
        assert "NoAdvisory" not in predecessor + automated
        assert "recommend" not in (predecessor + automated).lower()
        assert "consensus" not in (predecessor + automated).lower()

    for order, first, second in (("K_first", "K", "M"), ("M_first", "M", "K")):
        for q in ADVISORY_RELIABILITY_LEVELS:
            for source in ("PredecessorSource", "AutomatedSource"):
                message = phase2_prompt(order, q, source)
                assert message.count(f'"{first}" or "{second}"') == 1
                assert message.endswith("and then call release_resource().")


def test_frozen_evidence_math_and_normative_table() -> None:
    summary = summarize_evidence("K", True, True)
    assert PRIVATE_LR_SUCCESS_PASS == pytest.approx(3.8787878788)
    assert summary.likelihood_ratio_selected_over_alternative == pytest.approx(
        3.8787878788
    )
    assert summary.posterior_selected_fit == pytest.approx(0.7950311)
    assert NORMATIVE_CROSSOVER == pytest.approx(0.7950311)
    expected = [0.52245, 0.51511, 0.50765, 0.50387, 0.50005, 0.49620, 0.49231, 0.48443, 0.47640]
    assert [combined_posterior_selected_fit(q) for q in ADVISORY_RELIABILITY_LEVELS] == pytest.approx(expected, abs=0.00002)
    assert (MATCH_ACQUISITION_PROBABILITY, MISMATCH_ACQUISITION_PROBABILITY) == (0.80, 0.55)
    assert (MATCH_VERIFICATION_PROBABILITY, MISMATCH_VERIFICATION_PROBABILITY) == (0.80, 0.30)


def test_randomness_is_reproducible_and_namespaced() -> None:
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


def test_assignment_has_216_matched_pairs_and_exact_36_slot_blocks() -> None:
    seed = "assignment-fixture"
    assignments = build_assignment_plan(seed)
    assert len(assignments) == MAX_PRIMARY_ELIGIBLE == TARGET_PRIMARY_ELIGIBLE == 432
    assert [row.eligible_index for row in assignments] == list(range(432))
    assert len({row.pair_id for row in assignments}) == 216
    for block in range(12):
        rows = assignments[block * BLOCK_SIZE : (block + 1) * BLOCK_SIZE]
        assert len(rows) == 36
        for q in ADVISORY_RELIABILITY_LEVELS:
            for order in ("K_first", "M_first"):
                cell = [
                    row for row in rows
                    if row.advisory_reliability == q and row.phase2_order == order
                ]
                assert len(cell) == 2
                assert {row.source_condition for row in cell} == {
                    "PredecessorSource",
                    "AutomatedSource",
                }
                assert len({row.pair_id for row in cell}) == 1
        assert len({row.assignment_order_key for row in rows}) == 1

    by_cell = {}
    for row in assignments:
        by_cell.setdefault((row.advisory_reliability, row.source_condition), []).append(row)
    assert {len(rows) for rows in by_cell.values()} == {24}


def test_assignment_ledger_is_atomic_and_does_not_reset_an_empty_file(tmp_path) -> None:
    path = str(tmp_path / "assignments.json")
    seed = "atomic-fixture"
    ensure_assignment_state(path, seed)
    first = claim_assignment(path, seed)
    assert first.eligible_index == 0
    assert current_eligible_count(path, seed) == 1

    Path(path).write_text("", encoding="utf-8")
    with pytest.raises(RuntimeError, match="empty or was interrupted"):
        ensure_assignment_state(path, seed)
    with pytest.raises(RuntimeError, match="empty or was interrupted"):
        claim_assignment(path, seed)


def test_tool_schema_boundary_is_plain_string_and_label_free() -> None:
    parameter = inspect.signature(BoundaryToolset.select_policy).parameters["policy"]
    assert parameter.annotation is str
    assert get_type_hints(BoundaryToolset.select_policy)["policy"] is str
    assert inspect.getdoc(BoundaryToolset.select_policy) == SELECT_DESCRIPTION
    assert inspect.getdoc(BoundaryToolset.release_resource) == RELEASE_DESCRIPTION
    assert not any(label in SELECT_DESCRIPTION for label in ("K", "M"))
    assert not any(label in RELEASE_DESCRIPTION for label in ("K", "M"))


@pytest.mark.asyncio
async def test_success_pass_assigns_only_after_evidence_and_keeps_advice_hidden(tmp_path, monkeypatch) -> None:
    def draw(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
        return 0.1, f"fixture:{namespace}"

    monkeypatch.setattr(
        "cross_rollout_postcommitment_provenance_boundary_v1.servers.facility.randomness.draw_uniform",
        draw,
    )
    path = str(tmp_path / "assignments.json")
    toolset = toolset_with_state(assignment_path=path)
    ensure_assignment_state(path, "fixture-assignment-seed")
    await toolset.select_policy("K")
    result = await toolset.release_resource()
    assert result == "Policy K succeeded. Resource R1 obtained. Verification check: pass."
    assert PREDECESSOR_SOURCE_SENTENCE not in result
    assert AUTOMATED_SOURCE_SENTENCE not in result
    assert "advisory" not in result.lower()
    assert toolset.state.primary_eligible
    assert toolset.state.phase == "awaiting_r2"
    assert toolset.state.assignment_event_index > toolset.state.eligibility_event_index
    assert toolset.state.source_condition is not None
    assert toolset.state.advisory_reliability in ADVISORY_RELIABILITY_LEVELS
    assert toolset.state.turn2_message == ""
    assert toolset.state.advisory_delivered is False


@pytest.mark.asyncio
async def test_success_verification_fail_closes_without_assignment_or_r2(tmp_path, monkeypatch) -> None:
    def draw(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
        return (0.1 if namespace == "r1_acquisition" else 0.99), f"fixture:{namespace}"

    monkeypatch.setattr(
        "cross_rollout_postcommitment_provenance_boundary_v1.servers.facility.randomness.draw_uniform",
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
async def test_awaiting_r2_is_inert_and_activation_is_the_only_r2_gate(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "cross_rollout_postcommitment_provenance_boundary_v1.servers.facility.randomness.draw_uniform",
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
    assert "r2_acquisition" not in toolset.state.random_draws
    await toolset.select_policy("M")
    assert toolset.state.phase2_policy == "M"
    assert "r2_acquisition" not in toolset.state.random_draws
    await toolset.release_resource()
    assert toolset.state.phase == "complete"
    assert {"r2_acquisition", "r2_verification"} <= toolset.state.random_draws.keys()


@pytest.mark.asyncio
async def test_invalid_first_policy_cannot_be_reinterpreted() -> None:
    toolset = toolset_with_state()
    result = await toolset.select_policy("not-a-policy")
    assert "invalid" in result.lower()
    assert "invalid first" in (await toolset.release_resource()).lower()
    assert toolset.state.phase == "complete"
    assert not toolset.state.primary_eligible


class FakeInteraction(AbstractAsyncContextManager):
    def __init__(self, state: BoundaryState) -> None:
        self.trace = SimpleNamespace(state=state, stop_condition=None)
        self.messages: list[str | None] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def turn(self, message=None) -> vf.Segment:
        self.messages.append(message)
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
async def test_env_has_one_natural_resume_turn_and_exposes_source_only_on_turn2(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "cross_rollout_postcommitment_provenance_boundary_v1.servers.facility.randomness.draw_uniform",
        lambda seed, rollout_id, namespace: (0.1, f"fixture:{namespace}"),
    )
    path = str(tmp_path / "assignments.json")
    toolset = toolset_with_state(assignment_path=path)
    ensure_assignment_state(path, "fixture-assignment-seed")
    await toolset.select_policy("K")
    await toolset.release_resource()
    state = toolset.state
    interaction = FakeInteraction(state)
    env = object.__new__(CrossRolloutPostcommitmentProvenanceBoundaryV1Env)
    await env.run(SimpleNamespace(), SimpleNamespace(agent=FakeAgent(interaction)))
    expected = phase2_prompt(
        state.phase2_presentation_order,
        state.advisory_reliability,
        state.source_condition,
    )
    assert interaction.messages == [None, expected]
    assert state.r2_activated
    assert state.turn2_sent_count == 1
    assert state.advisory_delivered
    assert state.events[-2].kind == "exposure"
    assert state.events[-1].kind == "env_turn2"


@pytest.mark.asyncio
async def test_native_null_resume_preserves_the_existing_transcript() -> None:
    harness = NullHarness(NullHarnessConfig(id="null"))
    captured: dict[str, object] = {}

    async def capture_launch(*args, **kwargs) -> ProgramResult:
        del kwargs
        captured["prompt"] = args[-1].prompt
        return ProgramResult(exit_code=0, stdout="", stderr="")

    harness.launch = capture_launch
    trace = SimpleNamespace(
        branches=[
            SimpleNamespace(
                messages=[
                    vf.UserMessage(content="Phase 1"),
                    vf.AssistantMessage(content="R1 complete"),
                ]
            )
        ]
    )
    await harness.resume(
        SimpleNamespace(),
        trace,
        SimpleNamespace(),
        "http://example/v1",
        "secret",
        {},
        vf.TaskData(prompt=None),
        [vf.UserMessage(content="Turn 2")],
    )
    assert harness.SUPPORTS_RESUME
    assert captured["prompt"] == [
        vf.UserMessage(content="Phase 1"),
        vf.AssistantMessage(content="R1 complete"),
        vf.UserMessage(content="Turn 2"),
    ]


def test_recorded_predecessor_manifests_are_unchanged() -> None:
    manifests = [
        Path("/tmp/archipelago-dose-predecessor-manifest.sha256"),
        Path("/tmp/native-v2-hashes-before-diagnostic.txt"),
    ]
    for manifest in manifests:
        assert manifest.exists(), manifest
        result = subprocess.run(
            ["sha256sum", "-c", str(manifest)],
            capture_output=True,
            text=True,
            check=False,
            cwd=Path(__file__).resolve().parents[3],
        )
        assert result.returncode == 0, result.stdout + result.stderr


def test_persistent_package_manifest_matches_current_files() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "PRELIVE_MANIFEST.sha256"
    assert manifest.exists()
    result = subprocess.run(
        ["sha256sum", "-c", str(manifest)],
        capture_output=True,
        text=True,
        check=False,
        cwd=root.parents[1],
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_no_custom_harness_or_continuation_nudge_is_declared() -> None:
    source = inspect.getsource(CrossRolloutPostcommitmentProvenanceBoundaryV1Env)
    assert "Harness(" not in source
    assert "continuation" not in source.lower()
    assert NullHarness is not None
