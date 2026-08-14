"""Model-free tests for the frozen dose-response contract."""

from __future__ import annotations

import inspect

import pytest

from cross_rollout_postcommitment_provenance_dose_response_v1.assignment import (
    BLOCK_SIZE,
    assignment_for_index,
    ensure_assignment_state,
)
from cross_rollout_postcommitment_provenance_dose_response_v1.constants import (
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
from cross_rollout_postcommitment_provenance_dose_response_v1.evidence import (
    PRIVATE_LR_SUCCESS_PASS,
    combined_posterior_selected_fit,
    policy_matches_profile,
    summarize_evidence,
)
from cross_rollout_postcommitment_provenance_dose_response_v1.randomness import (
    ROLLOUT_NAMESPACES,
    hidden_profile,
)
from cross_rollout_postcommitment_provenance_dose_response_v1.schedule import (
    MAX_ATTEMPTS,
    build_schedule,
)
from cross_rollout_postcommitment_provenance_dose_response_v1.servers.facility import (
    NO_RESOURCE_RESULT,
    DoseResponseToolset,
    DoseResponseToolsetConfig,
)
from cross_rollout_postcommitment_provenance_dose_response_v1.state import (
    DoseResponseState,
)
from cross_rollout_postcommitment_provenance_dose_response_v1.taskset import (
    CrossRolloutPostcommitmentProvenanceDoseResponseV1Taskset,
    DoseResponseConfig,
    activate_r2,
)


def toolset_with_state(*, profile: str = "policy_1_fit", path: str = "/tmp/dose-test.json"):
    toolset = DoseResponseToolset(DoseResponseToolsetConfig())
    toolset._inert_state = DoseResponseState(
        rollout_id="fixture-rollout",
        random_seed="fixture-random",
        assignment_seed="fixture-assignment",
        assignment_state_path=path,
        hidden_profile=profile,
    )
    return toolset


def test_frozen_grid_and_schedule_are_exact() -> None:
    assert ADVISORY_RELIABILITY_LEVELS == (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80)
    schedule = build_schedule()
    assert len(schedule) == MAX_ATTEMPTS == 900
    assert [row.attempt_index for row in schedule] == list(range(900))
    assert sum(row.phase1_order == "K_first" for row in schedule) == 450
    assert sum(row.phase1_order == "M_first" for row in schedule) == 450
    assert all(schedule[i].phase1_order != schedule[i + 1].phase1_order for i in range(899))


def test_taskset_materializes_900_attempts_and_balanced_phase1() -> None:
    tasks = CrossRolloutPostcommitmentProvenanceDoseResponseV1Taskset(
        DoseResponseConfig()
    ).load()
    assert len(tasks) == MAX_ATTEMPTS
    assert sum(task.data.phase1_presentation_order == "K_first" for task in tasks) == 450
    assert sum(task.data.phase1_presentation_order == "M_first" for task in tasks) == 450
    assert tasks[0].data.prompt == phase1_prompt("K_first")
    assert tasks[1].data.prompt == phase1_prompt("M_first")


def test_phase1_surface_is_label_neutral_except_explicit_choice_pair() -> None:
    for order, first, second in (("K_first", "K", "M"), ("M_first", "M", "K")):
        prompt = phase1_prompt(order)
        assert prompt.count(f'"{first}" or "{second}"') == 1
        assert "K" not in prompt.split("For R1, choose one policy with", 1)[0]
        assert "M" not in prompt.split("For R1, choose one policy with", 1)[0]
        assert "R2" not in prompt
        assert "advisory" not in prompt.lower()


def test_all_14_advisory_templates_differ_only_by_q_and_source_clause() -> None:
    for q in ADVISORY_RELIABILITY_LEVELS:
        for order in ("K_first", "M_first"):
            predecessor = phase2_prompt(order, q, "PredecessorSource")
            automated = phase2_prompt(order, q, "AutomatedSource")
            assert predecessor.replace(PREDECESSOR_SOURCE_SENTENCE, "SOURCE") == automated.replace(
                AUTOMATED_SOURCE_SENTENCE, "SOURCE"
            )
            assert predecessor.count('"K" or "M"') + predecessor.count('"M" or "K"') == 1
            assert "not use on R1" in predecessor
            assert "recommend" not in predecessor.lower()
            assert "trust" not in predecessor.lower()
            assert "follow" not in predecessor.lower()


def test_private_evidence_and_advisory_math_is_frozen() -> None:
    summary = summarize_evidence("K", True, True)
    assert PRIVATE_LR_SUCCESS_PASS == pytest.approx(3.8787878788, abs=1e-9)
    assert summary.posterior_selected_fit == pytest.approx(0.7950310559, abs=1e-9)
    assert summary.expected_selected_r2_acquisition == pytest.approx(0.7487577640, abs=1e-9)
    assert summary.expected_alternative_r2_acquisition == pytest.approx(0.6012422360, abs=1e-9)
    expected = (0.7950, 0.7604, 0.7211, 0.6762, 0.6244, 0.5639, 0.4923)
    for q, value in zip(ADVISORY_RELIABILITY_LEVELS, expected):
        assert combined_posterior_selected_fit(q) == pytest.approx(value, abs=2e-4)
    assert combined_posterior_selected_fit(0.50) == pytest.approx(summary.posterior_selected_fit)
    assert combined_posterior_selected_fit(0.80) == pytest.approx(0.4923076923, abs=1e-9)


def test_profile_and_draw_namespaces_are_symmetric_and_reproducible() -> None:
    assert set(ROLLOUT_NAMESPACES) == {
        "hidden_profile",
        "r1_acquisition",
        "r1_verification",
        "r2_acquisition",
        "r2_verification",
    }
    assert hidden_profile("seed", "same") == hidden_profile("seed", "same")
    assert policy_matches_profile("K", "policy_1_fit")
    assert policy_matches_profile("M", "policy_2_fit")
    assert not policy_matches_profile("K", "policy_2_fit")
    assert not policy_matches_profile("M", "policy_1_fit")


def test_assignment_has_280_slots_140_pairs_and_10_per_cell() -> None:
    assignments = [assignment_for_index("fixture", index) for index in range(280)]
    assert len({item.pair_id for item in assignments}) == 140
    assert all(sum(item.pair_id == pair for item in assignments) == 2 for pair in {item.pair_id for item in assignments})
    for q in ADVISORY_RELIABILITY_LEVELS:
        for source in ("PredecessorSource", "AutomatedSource"):
            for order in ("K_first", "M_first"):
                assert sum(
                    item.advisory_reliability == q
                    and item.source_condition == source
                    and item.phase2_order == order
                    for item in assignments
                ) == 10
    assert {item.slot for item in assignments[:BLOCK_SIZE]} == set(range(BLOCK_SIZE))
    assert {item.slot for item in assignments[BLOCK_SIZE:2 * BLOCK_SIZE]} == set(range(BLOCK_SIZE))


@pytest.mark.asyncio
async def test_success_pass_assigns_after_r1_and_enters_inert_barrier(tmp_path, monkeypatch):
    def draw(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
        return 0.1, f"fixture:{namespace}"

    monkeypatch.setattr(
        "cross_rollout_postcommitment_provenance_dose_response_v1.servers.facility.randomness.draw_uniform",
        draw,
    )
    path = str(tmp_path / "assignments.json")
    ensure_assignment_state(path, "fixture-assignment")
    toolset = toolset_with_state(path=path)
    await toolset.select_policy("K")
    result = await toolset.release_resource()
    assert result == "Policy K succeeded. Resource R1 obtained. Verification check: pass."
    assert toolset.state.primary_eligible
    assert toolset.state.phase == "awaiting_r2"
    assert not toolset.state.r2_activated
    assert toolset.state.advisory_reliability in ADVISORY_RELIABILITY_LEVELS
    assert await toolset.select_policy("M") == NO_RESOURCE_RESULT
    assert await toolset.release_resource() == NO_RESOURCE_RESULT
    assert toolset.state.phase2_policy is None
    assert toolset.state.interstage_call_count == 2


@pytest.mark.asyncio
async def test_success_verification_fail_closes_without_phase2(tmp_path, monkeypatch):
    def draw(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
        return (0.1 if namespace == "r1_acquisition" else 0.9), f"fixture:{namespace}"

    monkeypatch.setattr(
        "cross_rollout_postcommitment_provenance_dose_response_v1.servers.facility.randomness.draw_uniform",
        draw,
    )
    path = str(tmp_path / "assignments.json")
    ensure_assignment_state(path, "fixture-assignment")
    toolset = toolset_with_state(path=path)
    await toolset.select_policy("K")
    await toolset.release_resource()
    assert toolset.state.eligibility == "success_verification_fail"
    assert toolset.state.phase == "complete"
    assert not toolset.state.primary_eligible
    assert toolset.state.advisory_reliability is None


@pytest.mark.asyncio
async def test_activation_turn2_uses_one_frozen_message_and_fresh_draws(tmp_path, monkeypatch):
    def draw(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
        return 0.1, f"fixture:{namespace}"

    monkeypatch.setattr(
        "cross_rollout_postcommitment_provenance_dose_response_v1.servers.facility.randomness.draw_uniform",
        draw,
    )
    path = str(tmp_path / "assignments.json")
    ensure_assignment_state(path, "fixture-assignment")
    toolset = toolset_with_state(path=path)
    await toolset.select_policy("K")
    await toolset.release_resource()
    assert "r2_acquisition" not in toolset.state.random_draws
    activate_r2(toolset.state)
    assert toolset.state.phase == "phase2"
    assert toolset.state.turn2_sent_count == 0
    assert toolset.state.phase2_presentation_order in ("K_first", "M_first")
    await toolset.select_policy("M")
    await toolset.release_resource()
    assert toolset.state.phase == "complete"
    assert {"r2_acquisition", "r2_verification"} <= toolset.state.random_draws.keys()


def test_tool_schema_boundary_is_plain_string_and_label_free() -> None:
    parameter = inspect.signature(DoseResponseToolset.select_policy).parameters["policy"]
    assert parameter.annotation is str
    assert inspect.getdoc(DoseResponseToolset.select_policy) == SELECT_DESCRIPTION
    assert inspect.getdoc(DoseResponseToolset.release_resource) == RELEASE_DESCRIPTION
    assert not any(label in SELECT_DESCRIPTION for label in ("K", "M"))
    assert not any(label in RELEASE_DESCRIPTION for label in ("K", "M"))


def test_frozen_probabilities_are_exact() -> None:
    assert MATCH_ACQUISITION_PROBABILITY == 0.80
    assert MISMATCH_ACQUISITION_PROBABILITY == 0.55
    assert MATCH_VERIFICATION_PROBABILITY == 0.80
    assert MISMATCH_VERIFICATION_PROBABILITY == 0.30
