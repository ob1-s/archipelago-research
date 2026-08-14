"""Frozen-analysis unit tests."""

from __future__ import annotations

from cross_rollout_postcommitment_evidence_threshold_transport_v1.analysis import (
    TraceRow,
    analyze_rows,
    isotonic_q50,
)


def row(strength: str, q: float, switch: bool, index: int) -> TraceRow:
    return TraceRow(
        trace_id=f"trace-{index}",
        attempt_index=index,
        strength=strength,
        q=q,
        phase1_order="K_first",
        phase2_order="K_first",
        primary_eligible=True,
        evidence_eligible=True,
        over_quota_guard=False,
        primary_itt_switch=switch,
        primary_choice_observed=True,
        phase2_missing=False,
        phase2_incomplete=False,
        natural_yield=True,
        r2_activated=True,
        turn2_sent_count=1,
        interstage_call_count=0,
        user_message_count=2,
        duration_seconds=1.0,
        model_requests=2,
        tool_calls=2,
        errors=(),
        stopped_before_attempt=False,
    )


def test_q50_interpolates_without_extrapolation() -> None:
    result = isotonic_q50([0.7, 0.8, 0.9], [0.1, 0.9, 1.0], [10, 10, 10])
    assert result["identified"] is True
    assert result["q50"] == 0.75
    assert isotonic_q50([0.7, 0.8], [0.1, 0.2], [10, 10])["identified"] is False


def test_analysis_has_three_curves_and_net_evidence() -> None:
    rows = []
    index = 0
    for strength, q_values in {
        "LOW": (0.6800, 0.6900, 0.6950, 0.7000, 0.7050, 0.7100, 0.7200),
        "ANCHOR": (0.7800, 0.7900, 0.7925, 0.7950, 0.7975, 0.8000, 0.8100),
        "HIGH": (0.8800, 0.8900, 0.8950, 0.9000, 0.9050, 0.9100, 0.9200),
    }.items():
        for q in q_values:
            for repeat in range(4):
                rows.append(row(strength, q, q >= q_values[3], index))
                index += 1
    result = analyze_rows(rows, bootstrap_repetitions=20, bootstrap_seed="fixture")
    assert set(result["curves"]) == {"LOW", "ANCHOR", "HIGH"}
    assert len(result["strength_q_table"]) == 21
    assert result["bootstrap"]["repetitions"] == 20
    assert len(result["secondary_net_evidence"]) == 21
