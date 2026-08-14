"""Frozen primary, q50, bootstrap, and net-evidence analysis."""

from __future__ import annotations

import json
import math
import random
import statistics
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import (
    BOOTSTRAP_REPETITIONS,
    BOOTSTRAP_SEED,
    PHASE1_ORDERS,
    Q_GRIDS,
    STRENGTHS,
)
from .evidence import strength_math

WILSON_Z = 1.959963984540054


@dataclass(frozen=True)
class TraceRow:
    trace_id: str
    attempt_index: int
    strength: str
    q: float
    phase1_order: str
    phase2_order: str
    primary_eligible: bool
    evidence_eligible: bool
    over_quota_guard: bool
    primary_itt_switch: bool
    primary_choice_observed: bool
    phase2_missing: bool
    phase2_incomplete: bool
    stopped_before_attempt: bool
    natural_yield: bool
    r2_activated: bool
    turn2_sent_count: int
    interstage_call_count: int
    user_message_count: int
    duration_seconds: float | None
    model_requests: int
    tool_calls: int
    errors: tuple[str, ...]


def _as_bool(value: Any) -> bool:
    return bool(value)


def _error_strings(trace: dict[str, Any]) -> tuple[str, ...]:
    errors = trace.get("errors") or []
    if not isinstance(errors, list):
        return (str(errors),)
    return tuple(str(error) for error in errors)


def _duration_seconds(trace: dict[str, Any]) -> float | None:
    timing = trace.get("timing")
    if not isinstance(timing, dict):
        return None
    start = timing.get("start")
    end = timing.get("end")
    if not isinstance(end, (int, float)):
        for phase in ("scoring", "finalize", "agent", "setup"):
            interval = timing.get(phase)
            if isinstance(interval, dict) and isinstance(
                interval.get("end"), (int, float)
            ):
                end = interval["end"]
                break
    if isinstance(start, (int, float)) and isinstance(end, (int, float)):
        return float(end - start)
    return None


def parse_trace(trace: dict[str, Any], outer_id: str = "") -> TraceRow:
    info = trace.get("info", {}).get("evidence_threshold_transport_assay", {})
    if not isinstance(info, dict):
        raise TypeError("trace is missing transport assay info")
    calls = trace.get("calls") or []
    model_requests = sum(
        1 for call in calls if isinstance(call, dict) and call.get("model")
    )
    tool_calls = 0
    for node in trace.get("nodes") or []:
        message = node.get("message", {}) if isinstance(node, dict) else {}
        if isinstance(message, dict):
            tool_calls += len(message.get("tool_calls") or [])
    user_message_count = sum(
        1
        for node in trace.get("nodes") or []
        if isinstance(node, dict)
        and isinstance(node.get("message"), dict)
        and node["message"].get("role") == "user"
    )
    return TraceRow(
        trace_id=str(trace.get("id") or outer_id),
        attempt_index=int(info.get("attempt_index", -1)),
        strength=str(info.get("strength_internal")),
        q=float(info.get("advisory_reliability_internal")),
        phase1_order=str(info.get("phase1_presentation_order")),
        phase2_order=str(info.get("phase2_presentation_order_internal")),
        primary_eligible=_as_bool(info.get("primary_eligible")),
        evidence_eligible=_as_bool(info.get("evidence_eligible")),
        over_quota_guard=_as_bool(info.get("over_quota_guard")),
        primary_itt_switch=_as_bool(info.get("primary_itt_switch")),
        primary_choice_observed=_as_bool(info.get("primary_choice_observed")),
        phase2_missing=_as_bool(info.get("phase2_missing")),
        phase2_incomplete=_as_bool(info.get("phase2_incomplete_after_choice")),
        stopped_before_attempt=_as_bool(info.get("stopped_before_attempt")),
        natural_yield=_as_bool(info.get("natural_yield_after_r1")),
        r2_activated=_as_bool(info.get("r2_activated")),
        turn2_sent_count=int(info.get("turn2_sent_count", 0)),
        interstage_call_count=int(info.get("interstage_call_count", 0)),
        user_message_count=user_message_count,
        duration_seconds=_duration_seconds(trace),
        model_requests=model_requests,
        tool_calls=tool_calls,
        errors=_error_strings(trace),
    )


def iter_trace_objects(path: str | Path) -> Iterable[tuple[dict[str, Any], str]]:
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            outer = json.loads(line)
            if isinstance(outer, dict) and isinstance(outer.get("traces"), list):
                outer_id = str(outer.get("id", ""))
                for trace in outer["traces"]:
                    if isinstance(trace, dict):
                        yield trace, outer_id
            elif isinstance(outer, dict):
                yield outer, ""


def load_rows(path: str | Path) -> list[TraceRow]:
    return [
        parse_trace(trace, outer_id) for trace, outer_id in iter_trace_objects(path)
    ]


def wilson_interval(
    successes: int, total: int, z: float = WILSON_Z
) -> tuple[float, float]:
    if total <= 0:
        return (math.nan, math.nan)
    p = successes / total
    denominator = 1.0 + z * z / total
    center = (p + z * z / (2.0 * total)) / denominator
    half = (
        z
        * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total))
        / denominator
    )
    return center - half, center + half


def _rate(successes: int, total: int) -> dict[str, Any]:
    low, high = wilson_interval(successes, total)
    return {
        "successes": successes,
        "total": total,
        "rate": successes / total if total else None,
        "wilson_95": [low, high] if total else None,
    }


def _pava(values: Sequence[float], weights: Sequence[int]) -> list[float]:
    blocks: list[list[float]] = []
    for index, (value, weight) in enumerate(zip(values, weights)):
        if weight <= 0:
            continue
        blocks.append(
            [float(weight), float(value) * float(weight), float(index), float(index)]
        )
        while len(blocks) >= 2:
            left, right = blocks[-2], blocks[-1]
            if left[1] / left[0] <= right[1] / right[0]:
                break
            blocks[-2:] = [[left[0] + right[0], left[1] + right[1], left[2], right[3]]]
    fitted: list[float] = []
    for weight, weighted_sum, start, end in blocks:
        del weight
        total_weight = sum(weights[int(start) : int(end) + 1])
        fitted.extend([weighted_sum / total_weight] * (int(end) - int(start) + 1))
    return fitted


def isotonic_q50(
    q_values: Sequence[float], rates: Sequence[float], weights: Sequence[int]
) -> dict[str, Any]:
    if not (len(q_values) == len(rates) == len(weights)):
        raise ValueError("q, rates, and weights must have equal lengths")
    valid = [
        (q, rate, weight)
        for q, rate, weight in zip(q_values, rates, weights)
        if weight > 0
    ]
    if not valid:
        return {"q50": None, "fitted": [], "identified": False}
    valid_q = [row[0] for row in valid]
    valid_rates = [row[1] for row in valid]
    valid_weights = [row[2] for row in valid]
    fitted = _pava(valid_rates, valid_weights)
    for index, value in enumerate(fitted):
        if math.isclose(value, 0.5, abs_tol=1e-15):
            return {"q50": valid_q[index], "fitted": fitted, "identified": True}
    for index in range(len(fitted) - 1):
        left, right = fitted[index], fitted[index + 1]
        if left < 0.5 < right:
            fraction = (0.5 - left) / (right - left)
            return {
                "q50": valid_q[index]
                + fraction * (valid_q[index + 1] - valid_q[index]),
                "fitted": fitted,
                "identified": True,
            }
    return {"q50": None, "fitted": fitted, "identified": False}


def _group(rows: Iterable[TraceRow], key_fn) -> dict[Any, list[TraceRow]]:
    grouped: dict[Any, list[TraceRow]] = defaultdict(list)
    for row in rows:
        grouped[key_fn(row)].append(row)
    return dict(grouped)


def strength_q_table(rows: Sequence[TraceRow]) -> list[dict[str, Any]]:
    eligible = [row for row in rows if row.primary_eligible]
    result: list[dict[str, Any]] = []
    for strength in STRENGTHS:
        for q in Q_GRIDS[strength]:
            cell = [row for row in eligible if row.strength == strength and row.q == q]
            result.append(
                {
                    "strength": strength,
                    "q": q,
                    "n": len(cell),
                    "switch": _rate(
                        sum(row.primary_itt_switch for row in cell), len(cell)
                    ),
                    "phase1_orders": {
                        order: len([row for row in cell if row.phase1_order == order])
                        for order in PHASE1_ORDERS
                    },
                    "phase2_orders": {
                        order: len([row for row in cell if row.phase2_order == order])
                        for order in PHASE1_ORDERS
                    },
                    "missing_or_incomplete": sum(
                        row.phase2_missing or row.phase2_incomplete for row in cell
                    ),
                }
            )
    return result


def strength_curves(rows: Sequence[TraceRow]) -> dict[str, dict[str, Any]]:
    eligible = [row for row in rows if row.primary_eligible]
    curves: dict[str, dict[str, Any]] = {}
    for strength in STRENGTHS:
        q_values = list(Q_GRIDS[strength])
        rates: list[float] = []
        weights: list[int] = []
        raw: list[dict[str, Any]] = []
        for q in q_values:
            cell = [row for row in eligible if row.strength == strength and row.q == q]
            successes = sum(row.primary_itt_switch for row in cell)
            rates.append(successes / len(cell) if cell else 0.0)
            weights.append(len(cell))
            raw.append(
                {
                    "strength": strength,
                    "q": q,
                    "n": len(cell),
                    **_rate(successes, len(cell)),
                }
            )
        curves[strength] = {
            "strength": strength,
            "normative_q_star": strength_math(strength).normative_crossover,
            "raw": raw,
            "isotonic_q50": isotonic_q50(q_values, rates, weights),
        }
    return curves


def _percentile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def bootstrap_summary(
    rows: Sequence[TraceRow],
    *,
    repetitions: int = BOOTSTRAP_REPETITIONS,
    seed: str = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    eligible = [row for row in rows if row.primary_eligible]
    strata = _group(
        eligible,
        lambda row: (row.strength, row.q, row.phase1_order, row.phase2_order),
    )
    rng = random.Random(seed)
    q50_values: dict[str, list[float]] = {strength: [] for strength in STRENGTHS}
    shifts: dict[str, list[float]] = {
        "LOW_to_ANCHOR": [],
        "ANCHOR_to_HIGH": [],
        "LOW_to_HIGH": [],
    }
    for _ in range(repetitions):
        sample: list[TraceRow] = []
        for stratum in strata.values():
            sample.extend(rng.choice(stratum) for _ in stratum)
        curves = strength_curves(sample)
        q50 = {
            strength: curves[strength]["isotonic_q50"]["q50"] for strength in STRENGTHS
        }
        for strength, value in q50.items():
            if value is not None:
                q50_values[strength].append(float(value))
        if q50["LOW"] is not None and q50["ANCHOR"] is not None:
            shifts["LOW_to_ANCHOR"].append(q50["ANCHOR"] - q50["LOW"])
        if q50["ANCHOR"] is not None and q50["HIGH"] is not None:
            shifts["ANCHOR_to_HIGH"].append(q50["HIGH"] - q50["ANCHOR"])
        if q50["LOW"] is not None and q50["HIGH"] is not None:
            shifts["LOW_to_HIGH"].append(q50["HIGH"] - q50["LOW"])

    def summarize(values: list[float]) -> dict[str, Any]:
        return {
            "identifiable_fraction": len(values) / repetitions,
            "n_identifiable": len(values),
            "interval_95": [_percentile(values, 0.025), _percentile(values, 0.975)],
            "median": _percentile(values, 0.5),
        }

    return {
        "repetitions": repetitions,
        "seed": seed,
        "stratification": "strength × q × Phase-1 order × Phase-2 order",
        "failed_replicate_rule": "retain replicate only for q50/contrast quantities whose required q50 values are identifiable; report fraction",
        "q50": {strength: summarize(values) for strength, values in q50_values.items()},
        "shifts": {name: summarize(values) for name, values in shifts.items()},
    }


def secondary_net_evidence(rows: Sequence[TraceRow]) -> list[dict[str, Any]]:
    eligible = [row for row in rows if row.primary_eligible]
    points: list[dict[str, Any]] = []
    for strength in STRENGTHS:
        private_lr = strength_math(strength).private_likelihood_ratio
        for q in Q_GRIDS[strength]:
            cell = [row for row in eligible if row.strength == strength and row.q == q]
            points.append(
                {
                    "strength": strength,
                    "q": q,
                    "net_evidence_log_odds": math.log(q / (1.0 - q))
                    - math.log(private_lr),
                    "n": len(cell),
                    "switch": _rate(
                        sum(row.primary_itt_switch for row in cell), len(cell)
                    ),
                }
            )
    return points


def lifecycle_summary(rows: Sequence[TraceRow]) -> dict[str, Any]:
    eligible = [row for row in rows if row.primary_eligible]
    violations: list[dict[str, Any]] = []
    for row in eligible:
        if not row.natural_yield:
            violations.append(
                {"attempt_index": row.attempt_index, "violation": "no_natural_yield"}
            )
        if not row.r2_activated:
            violations.append(
                {"attempt_index": row.attempt_index, "violation": "r2_not_activated"}
            )
        if row.turn2_sent_count != 1:
            violations.append(
                {"attempt_index": row.attempt_index, "violation": "turn2_count"}
            )
        if row.user_message_count != 2:
            violations.append(
                {"attempt_index": row.attempt_index, "violation": "user_message_count"}
            )
    return {
        "primary_eligible": len(eligible),
        "natural_yield": _rate(
            sum(row.natural_yield for row in eligible), len(eligible)
        ),
        "r2_activation": _rate(
            sum(row.r2_activated for row in eligible), len(eligible)
        ),
        "choice_observed": _rate(
            sum(row.primary_choice_observed for row in eligible), len(eligible)
        ),
        "missing_phase2": sum(row.phase2_missing for row in eligible),
        "incomplete_after_choice": sum(row.phase2_incomplete for row in eligible),
        "interstage_calls": sum(row.interstage_call_count for row in eligible),
        "violations": violations,
    }


def runtime_summary(rows: Sequence[TraceRow]) -> dict[str, Any]:
    durations = [
        row.duration_seconds for row in rows if row.duration_seconds is not None
    ]
    eligible_durations = [
        row.duration_seconds
        for row in rows
        if row.primary_eligible and row.duration_seconds is not None
    ]

    def summarize(values: list[float]) -> dict[str, Any]:
        return {
            "n": len(values),
            "mean_seconds": statistics.fmean(values) if values else None,
            "median_seconds": statistics.median(values) if values else None,
            "min_seconds": min(values) if values else None,
            "max_seconds": max(values) if values else None,
        }

    return {
        "trace_rows": len(rows),
        "phase1_attempt_rows": sum(not row.stopped_before_attempt for row in rows),
        "all_rows": summarize(durations),
        "primary_eligible_rows": summarize(eligible_durations),
        "model_requests": sum(row.model_requests for row in rows),
        "tool_calls": sum(row.tool_calls for row in rows),
    }


def analyze_rows(
    rows: Sequence[TraceRow],
    *,
    bootstrap_repetitions: int = BOOTSTRAP_REPETITIONS,
    bootstrap_seed: str = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    primary = [row for row in rows if row.primary_eligible]
    curves = strength_curves(rows)
    q50 = {strength: curves[strength]["isotonic_q50"]["q50"] for strength in STRENGTHS}
    shifts = {
        "LOW_to_ANCHOR": q50["ANCHOR"] - q50["LOW"]
        if q50["LOW"] is not None and q50["ANCHOR"] is not None
        else None,
        "ANCHOR_to_HIGH": q50["HIGH"] - q50["ANCHOR"]
        if q50["ANCHOR"] is not None and q50["HIGH"] is not None
        else None,
        "LOW_to_HIGH": q50["HIGH"] - q50["LOW"]
        if q50["LOW"] is not None and q50["HIGH"] is not None
        else None,
    }
    calibration = {
        strength: (
            q50[strength] - strength_math(strength).normative_crossover
            if q50[strength] is not None
            else None
        )
        for strength in STRENGTHS
    }
    return {
        "schema_version": "evidence_threshold_transport_v1.analysis_results.v1",
        "primary_eligible_count": len(primary),
        "primary_choice_observed_count": sum(
            row.primary_choice_observed for row in primary
        ),
        "strength_q_table": strength_q_table(rows),
        "curves": curves,
        "q50": q50,
        "normative_q_star": {
            strength: strength_math(strength).normative_crossover
            for strength in STRENGTHS
        },
        "calibration_error": calibration,
        "shift_contrasts": shifts,
        "predicted_shift_contrasts": {
            "LOW_to_ANCHOR": 0.7950310559006212 - 0.7,
            "ANCHOR_to_HIGH": 0.9 - 0.7950310559006212,
            "LOW_to_HIGH": 0.2,
        },
        "bootstrap": bootstrap_summary(
            rows,
            repetitions=bootstrap_repetitions,
            seed=bootstrap_seed,
        ),
        "secondary_net_evidence": secondary_net_evidence(rows),
        "lifecycle": lifecycle_summary(rows),
        "optional_logistic": "not run; no post-hoc regularization or alternate model",
    }
