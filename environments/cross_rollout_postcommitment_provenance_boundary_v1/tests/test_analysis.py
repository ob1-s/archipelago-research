"""Model-free tests for the frozen analysis contract."""

from __future__ import annotations

import pytest

from cross_rollout_postcommitment_provenance_boundary_v1.analysis import (
    PairRow,
    TraceRow,
    analyze_rows,
    exact_mcnemar,
    isotonic_q50,
    randomization_inference_q50,
    wilson_interval,
)
from cross_rollout_postcommitment_provenance_boundary_v1.audit import (
    build_surface_audit,
)


def row(
    *,
    trace_id: str = "trace",
    q: float | None = None,
    source: str | None = None,
    pair_id: str | None = None,
    primary_eligible: bool = False,
    primary_itt_switch: bool = False,
    primary_choice_observed: bool = True,
    phase2_order: str | None = None,
    p_origin: str | None = "K",
) -> TraceRow:
    return TraceRow(
        trace_id=trace_id,
        outer_id="outer",
        attempt_index=0,
        phase1_order="K_first",
        phase1_policy="K",
        phase1_success=True,
        phase1_verification_pass=True,
        eligibility="primary_eligible" if primary_eligible else "phase1_not_successful",
        primary_eligible=primary_eligible,
        eligible_index=0 if primary_eligible else None,
        block_index=0 if primary_eligible else None,
        slot=0 if primary_eligible else None,
        pair_id=pair_id,
        source=source,
        q=q,
        phase2_order=phase2_order,
        p_origin=p_origin,
        phase2_policy="M" if primary_itt_switch else "K",
        primary_choice_observed=primary_choice_observed,
        primary_itt_switch=primary_itt_switch,
        phase2_missing=not primary_choice_observed,
        phase2_incomplete=False,
        natural_yield=primary_eligible,
        r2_activated=primary_eligible,
        turn2_count=1 if primary_eligible else 0,
        turn2_message="Turn 2" if primary_eligible else None,
        interstage_calls=0,
        phase2_acquisition_success=False,
        phase2_verification_pass=False,
        stop_reason="r2_released" if primary_eligible else "phase1_closed",
        stop_condition="user_closed",
        errors=(),
        model_requests=2 if primary_eligible else 1,
        tool_calls=4 if primary_eligible else 2,
        duration_seconds=2.0,
        model_wait_seconds=1.0,
        harness_seconds=0.2,
    )


def test_wilson_and_exact_mcnemar_are_frozen_descriptive_calculations() -> None:
    low, high = wilson_interval(0, 10)
    assert low == pytest.approx(0.0)
    assert high == pytest.approx(0.2775327999)
    assert exact_mcnemar(1, 1) == 1.0
    assert exact_mcnemar(2, 0) == pytest.approx(0.5)


def test_isotonic_q50_interpolates_only_between_tested_grid_points() -> None:
    result = isotonic_q50((0.78, 0.80), (0.25, 0.75), (4, 4))
    assert result["identified"] is True
    assert result["q50"] == pytest.approx(0.79)
    assert isotonic_q50((0.78, 0.80), (0.1, 0.2), (4, 4))["q50"] is None


def test_surface_audit_is_machine_readable_and_passes() -> None:
    audit = build_surface_audit()
    assert audit["all_pass"] is True
    assert all(row["normalized_equal"] for row in audit["source_diffs"])
    assert all(row["normalized_equal"] for row in audit["q_diffs"])
    assert audit["mcp_schema"]["serialized_schema"]["properties"]["policy"] == {
        "title": "Policy",
        "type": "string",
    }


def test_analysis_keeps_itt_missingness_and_pair_direction() -> None:
    first = row(
        trace_id="pred",
        q=0.78,
        source="PredecessorSource",
        pair_id="pair-1",
        primary_eligible=True,
        primary_itt_switch=True,
        phase2_order="K_first",
    )
    second = row(
        trace_id="auto",
        q=0.78,
        source="AutomatedSource",
        pair_id="pair-1",
        primary_eligible=True,
        primary_itt_switch=False,
        phase2_order="K_first",
    )
    missing = row(
        trace_id="missing",
        q=0.785,
        source="PredecessorSource",
        pair_id="pair-2",
        primary_eligible=True,
        primary_itt_switch=False,
        primary_choice_observed=False,
        phase2_order="M_first",
    )
    result = analyze_rows([first, second, missing], randomization_repetitions=20)
    assert result["primary_eligible_count"] == 3
    assert result["mcnemar"]["pairs"] == 1
    assert result["mcnemar"]["predecessor_switch_automated_retain"] == 1
    assert result["lifecycle"]["missing_phase2"] == 1
    assert result["q_source_table"][0]["n_itt"] == 1
    assert result["q50_randomization"]["repetitions"] == 20


def test_randomization_inference_is_reproducible() -> None:
    pairs = [
        PairRow("p1", 0.78, "K_first", True, False, True, True, "a", "b"),
        PairRow("p2", 0.78, "M_first", False, True, True, True, "c", "d"),
    ]
    left = randomization_inference_q50(pairs, repetitions=30, seed="fixture")
    right = randomization_inference_q50(pairs, repetitions=30, seed="fixture")
    assert left == right
