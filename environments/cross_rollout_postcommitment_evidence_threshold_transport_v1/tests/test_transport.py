"""Model-free implementation and concurrency contract tests."""

from __future__ import annotations

import inspect
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import get_type_hints

import pytest
from cross_rollout_postcommitment_evidence_threshold_transport_v1 import (
    CrossRolloutPostcommitmentEvidenceThresholdTransportV1Taskset,
    TransportConfig,
)
from cross_rollout_postcommitment_evidence_threshold_transport_v1.assignment import (
    MAX_ATTEMPTS,
    QUOTA_CELL_COUNT,
    accept_primary_quota,
    build_attempt_plan,
    ensure_quota_state,
)
from cross_rollout_postcommitment_evidence_threshold_transport_v1.constants import (
    MISMATCH_VERIFICATION_BY_STRENGTH,
    PHASE1_ORDERS,
    Q_GRIDS,
    STRENGTHS,
    phase1_prompt,
    phase2_prompt,
)
from cross_rollout_postcommitment_evidence_threshold_transport_v1.evidence import (
    combined_posterior_selected_fit,
    validate_frozen_math,
)
from cross_rollout_postcommitment_evidence_threshold_transport_v1.qualification import (
    all_cells_completion_failure_bound,
    expected_attempts_by_strength,
    expected_attempts_total,
)
from cross_rollout_postcommitment_evidence_threshold_transport_v1.servers.facility import (
    NO_RESOURCE_RESULT,
    TransportToolset,
    TransportToolsetConfig,
)
from cross_rollout_postcommitment_evidence_threshold_transport_v1.state import (
    TransportState,
)
from cross_rollout_postcommitment_evidence_threshold_transport_v1.taskset import (
    activate_r2,
)


def test_frozen_strength_math_and_expected_rates() -> None:
    values = validate_frozen_math()
    assert values["LOW"].private_likelihood_ratio == pytest.approx(7 / 3)
    assert values["LOW"].normative_crossover == pytest.approx(0.7)
    assert values["ANCHOR"].private_likelihood_ratio == pytest.approx(0.64 / 0.165)
    assert values["ANCHOR"].normative_crossover == pytest.approx(0.7950310559006212)
    assert values["HIGH"].private_likelihood_ratio == pytest.approx(9.0)
    assert values["HIGH"].normative_crossover == pytest.approx(0.9)
    assert values["LOW"].eligibility_rate == pytest.approx(0.45714285714285724)
    assert values["ANCHOR"].eligibility_rate == pytest.approx(0.4025)
    assert values["HIGH"].eligibility_rate == pytest.approx(0.3555555555555556)
    assert combined_posterior_selected_fit("LOW", 0.7) == pytest.approx(0.5)
    assert expected_attempts_by_strength() == pytest.approx(
        {"LOW": 367.5, "ANCHOR": 417.391304347826, "HIGH": 472.5}
    )
    assert expected_attempts_total() == pytest.approx(1257.391304347826)
    assert all_cells_completion_failure_bound(60) < 0.001


def test_preassignment_is_fixed_before_phase1_and_balanced() -> None:
    plan = build_attempt_plan("fixture-schedule")
    assert len(plan) == MAX_ATTEMPTS == 5040
    assert len({row.attempt_index for row in plan}) == MAX_ATTEMPTS
    assert len({row.quota_cell_key for row in plan}) == QUOTA_CELL_COUNT == 84
    for strength in STRENGTHS:
        for q in Q_GRIDS[strength]:
            aggregate = [
                row
                for row in plan
                if row.strength == strength and row.advisory_reliability == q
            ]
            assert len(aggregate) == 4 * 60
            assert {row.phase1_order for row in aggregate} == set(PHASE1_ORDERS)
            assert {row.phase2_order for row in aggregate} == set(PHASE1_ORDERS)
            primary_shape = [row for row in aggregate if row.quota_round < 6]
            assert sum(row.phase1_order == "K_first" for row in primary_shape) == 12
            assert sum(row.phase1_order == "M_first" for row in primary_shape) == 12
            assert sum(row.phase2_order == "K_first" for row in primary_shape) == 12
            assert sum(row.phase2_order == "M_first" for row in primary_shape) == 12
            for phase1_order in PHASE1_ORDERS:
                for phase2_order in PHASE1_ORDERS:
                    cell = [
                        row
                        for row in aggregate
                        if row.phase1_order == phase1_order
                        and row.phase2_order == phase2_order
                    ]
                    assert len(cell) == 60
                    assert sum(row.quota_round < 6 for row in cell) == 6

    forward = {
        row.attempt_index: (
            row.strength,
            row.advisory_reliability,
            row.phase1_order,
            row.phase2_order,
            row.quota_cell_key,
        )
        for row in plan
    }
    reverse = {
        row.attempt_index: (
            row.strength,
            row.advisory_reliability,
            row.phase1_order,
            row.phase2_order,
            row.quota_cell_key,
        )
        for row in reversed(plan)
    }
    assert forward == reverse


def test_quota_lock_accepts_exactly_six_under_arbitrary_completion_order(
    tmp_path: Path,
) -> None:
    seed = "fixture-schedule"
    path = str(tmp_path / "quota.json")
    ensure_quota_state(path, seed)
    cell = build_attempt_plan(seed)[0].quota_cell_key
    attempt_indices = [
        row.attempt_index
        for row in build_attempt_plan(seed)
        if row.quota_cell_key == cell
    ]
    completion_order = list(reversed(attempt_indices[:30]))
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(
            pool.map(
                lambda index: accept_primary_quota(path, seed, cell, index),
                completion_order,
            )
        )
    accepted = [result for result in results if result[0]]
    assert len(accepted) == 6
    assert sorted(rank for _, rank in accepted if rank is not None) == list(range(6))
    state = json.loads(Path(path).read_text())
    assert state["accepted_by_cell"][cell] == 6


def test_model_visible_surfaces_are_clean_and_strength_is_probability_only() -> None:
    for strength in STRENGTHS:
        for order in PHASE1_ORDERS:
            prompt = phase1_prompt(order, strength)
            assert (
                MISMATCH_VERIFICATION_BY_STRENGTH[strength].__format__(".17f") in prompt
            )
            assert (
                "LOW" not in prompt and "ANCHOR" not in prompt and "HIGH" not in prompt
            )
            assert "advisory" not in prompt.lower()
            assert (
                prompt.count('select_policy(policy="K" or "M")') == 1
                or prompt.count('select_policy(policy="M" or "K")') == 1
            )
            for q in Q_GRIDS[strength]:
                turn2 = phase2_prompt(order, q)
                assert "automated facility diagnostic" in turn2
                assert "predecessor" not in turn2.lower()
                assert all(label not in turn2 for label in ("LOW", "ANCHOR", "HIGH"))
    signature = inspect.signature(TransportToolset.select_policy)
    assert signature.parameters["policy"].annotation is str
    assert get_type_hints(TransportToolset.select_policy)["policy"] is str


def _toolset(tmp_path: Path) -> TransportToolset:
    toolset = TransportToolset(TransportToolsetConfig())
    schedule_seed = "fixture-schedule"
    path = str(tmp_path / "quota.json")
    spec = build_attempt_plan(schedule_seed)[0]
    ensure_quota_state(path, schedule_seed)
    toolset._inert_state = TransportState(
        rollout_id="fixture-rollout",
        random_seed="fixture-random",
        schedule_seed=schedule_seed,
        quota_state_path=path,
        assignment_key=spec.assignment_key,
        quota_cell_key=spec.quota_cell_key,
        quota_cell_target=spec.quota_cell_target,
        quota_round=spec.quota_round,
        strength=spec.strength,
        advisory_reliability=spec.advisory_reliability,
        phase1_presentation_order=spec.phase1_order,
        phase2_presentation_order=spec.phase2_order,
        hidden_profile="policy_1_fit",
    )
    return toolset


@pytest.mark.asyncio
async def test_native_two_turn_gate_and_inert_interstage(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "cross_rollout_postcommitment_evidence_threshold_transport_v1.servers.facility.randomness.draw_uniform",
        lambda seed, rollout_id, namespace: (0.1, f"fixture:{namespace}"),
    )
    toolset = _toolset(tmp_path)
    await toolset.select_policy("K")
    r1 = await toolset.release_resource()
    assert r1.endswith("Verification check: pass.")
    assert toolset.state.primary_eligible
    assert toolset.state.phase == "awaiting_r2"
    before = dict(toolset.state.random_draws)
    assert await toolset.select_policy("M") == NO_RESOURCE_RESULT
    assert await toolset.release_resource() == NO_RESOURCE_RESULT
    assert toolset.state.phase2_policy is None
    assert dict(toolset.state.random_draws) == before
    assert toolset.state.interstage_call_count == 2
    activate_r2(toolset.state)
    await toolset.select_policy("M")
    await toolset.release_resource()
    assert toolset.state.phase == "complete"
    assert toolset.state.primary_switch is True
    assert {"r2_acquisition", "r2_verification"} <= toolset.state.random_draws.keys()


def test_taskset_materializes_the_frozen_plan() -> None:
    tasks = CrossRolloutPostcommitmentEvidenceThresholdTransportV1Taskset(
        TransportConfig()
    ).load()
    assert len(tasks) == MAX_ATTEMPTS
    assert {task.data.strength for task in tasks} == set(STRENGTHS)
    assert {task.data.phase1_presentation_order for task in tasks} == set(PHASE1_ORDERS)
    assert {task.data.phase2_presentation_order for task in tasks} == set(PHASE1_ORDERS)


def test_attempt_duration_parser_uses_nested_native_timing_end() -> None:
    from cross_rollout_postcommitment_evidence_threshold_transport_v1.analysis import (
        parse_trace,
    )

    parsed = parse_trace(
        {
            "id": "trace",
            "info": {
                "evidence_threshold_transport_assay": {
                    "attempt_index": 0,
                    "strength_internal": "LOW",
                    "advisory_reliability_internal": 0.68,
                    "phase1_presentation_order": "K_first",
                    "phase2_presentation_order_internal": "K_first",
                }
            },
            "timing": {
                "start": 10.0,
                "finalize": {"start": 12.0, "end": 12.5},
                "scoring": {"start": 12.5, "end": 13.0},
            },
        }
    )
    assert parsed.duration_seconds == 3.0
