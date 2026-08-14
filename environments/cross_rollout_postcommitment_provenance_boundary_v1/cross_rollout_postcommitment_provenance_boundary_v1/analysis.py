"""Frozen, dependency-light analysis for the provenance-boundary assay.

The primary endpoint is the ITT binary indicator ``primary_itt_switch`` for
every randomized primary-eligible trajectory.  Missing R2 behavior is not
silently dropped.  The source comparison is the exact matched-pair McNemar
test; curves and q50 summaries are descriptive secondary analyses.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .constants import ADVISORY_RELIABILITY_LEVELS, SOURCE_CONDITIONS, phase2_prompt
from .evidence import NORMATIVE_CROSSOVER

WILSON_Z = 1.959963984540054
RANDOMIZATION_REPETITIONS = 100_000
RANDOMIZATION_SEED = (
    "cross-rollout-postcommitment-provenance-boundary-v1-q50-randomization-2026-08-14"
)
MIN_Q50_IDENTIFIABLE_FRACTION = 0.5


@dataclass(frozen=True)
class TraceRow:
    """Analysis fields copied from one serialized evaluator trace."""

    trace_id: str
    outer_id: str
    attempt_index: int | None
    phase1_order: str | None
    phase1_policy: str | None
    phase1_success: bool
    phase1_verification_pass: bool
    eligibility: str | None
    primary_eligible: bool
    eligible_index: int | None
    block_index: int | None
    slot: int | None
    pair_id: str | None
    source: str | None
    q: float | None
    phase2_order: str | None
    p_origin: str | None
    phase2_policy: str | None
    primary_choice_observed: bool
    primary_itt_switch: bool
    phase2_missing: bool
    phase2_incomplete: bool
    natural_yield: bool
    r2_activated: bool
    turn2_count: int
    turn2_message: str | None
    interstage_calls: int
    phase2_acquisition_success: bool
    phase2_verification_pass: bool
    stop_reason: str | None
    stop_condition: str | None
    errors: tuple[str, ...]
    model_requests: int
    tool_calls: int
    duration_seconds: float | None
    model_wait_seconds: float | None
    harness_seconds: float | None
    stopped_before_attempt: bool = False
    user_message_count: int = 0
    lifecycle_violations: tuple[str, ...] = ()


@dataclass(frozen=True)
class PairRow:
    pair_id: str
    q: float
    phase2_order: str
    predecessor_switch: bool
    automated_switch: bool
    predecessor_observed: bool
    automated_observed: bool
    predecessor_trace_id: str
    automated_trace_id: str


def _bool(value: Any, default: bool = False) -> bool:
    return default if value is None else bool(value)


def _int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _timing_duration(timing: dict[str, Any]) -> float | None:
    start = timing.get("start")
    if not isinstance(start, (int, float)):
        return None
    ends: list[float] = []
    for value in timing.values():
        if isinstance(value, dict):
            end = value.get("end")
            if isinstance(end, (int, float)):
                ends.append(float(end))
            nested = _timing_duration(value)
            if nested is not None:
                ends.append(float(start) + nested)
    return max(ends, default=float(start)) - float(start)


def _nested_duration(timing: dict[str, Any], section: str) -> float | None:
    value = timing.get(section)
    if not isinstance(value, dict):
        return None
    duration = value.get("duration")
    return float(duration) if isinstance(duration, (int, float)) else None


def _tool_call_count(trace: dict[str, Any]) -> int:
    count = 0
    for node in trace.get("nodes", []) or []:
        message = node.get("message", {}) if isinstance(node, dict) else {}
        if isinstance(message, dict):
            calls = message.get("tool_calls", []) or []
            if isinstance(calls, list):
                count += len(calls)
    return count


def _error_strings(values: Any) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(
        value if isinstance(value, str) else json.dumps(value, sort_keys=True)
        for value in values
    )


def _lifecycle_violations(
    trace: dict[str, Any], assay: dict[str, Any], user_message_count: int
) -> tuple[str, ...]:
    if not assay.get("primary_eligible"):
        return ()
    violations: list[str] = []
    if user_message_count != 2:
        violations.append("user_message_count_not_two")
    if assay.get("turn2_sent_count") != 1:
        violations.append("turn2_count_not_one")
    q = assay.get("advisory_reliability")
    order = assay.get("phase2_presentation_order")
    source = assay.get("source_condition")
    turn2_message = assay.get("turn2_message")
    if q is None or order is None or source is None:
        violations.append("missing_turn2_assignment")
    else:
        expected = phase2_prompt(order, float(q), source)
        if turn2_message != expected:
            violations.append("wrong_turn2_message")
        matching_users = [
            node
            for node in trace.get("nodes", []) or []
            if isinstance(node, dict)
            and isinstance(node.get("message"), dict)
            and node["message"].get("role") == "user"
            and node["message"].get("content") == expected
        ]
        if len(matching_users) != 1:
            violations.append("turn2_user_message_not_exactly_one")
    events = assay.get("events", [])
    if not isinstance(events, list):
        events = []
    by_kind = defaultdict(list)
    for event in events:
        if isinstance(event, dict):
            by_kind[event.get("kind")].append(event)
    eligibility = assay.get("eligibility_event_index")
    assignment_event = assay.get("assignment_event_index")
    if eligibility is None or assignment_event is None or assignment_event <= eligibility:
        violations.append("assignment_not_after_eligibility")
    activation = by_kind.get("env_activate_r2", [])
    turn2 = by_kind.get("env_turn2", [])
    exposure = by_kind.get("exposure", [])
    if len(activation) != 1:
        violations.append("env_activation_count_not_one")
    if len(turn2) != 1:
        violations.append("env_turn2_event_count_not_one")
    if len(exposure) != 1:
        violations.append("exposure_event_count_not_one")
    if activation and turn2 and activation[0].get("index", -1) >= turn2[0].get("index", -1):
        violations.append("turn2_before_activation")
    if exposure and turn2 and exposure[0].get("index", -1) + 1 != turn2[0].get("index", -1):
        violations.append("exposure_turn2_order_invalid")
    if assay.get("interstage_call_count", 0) < 0:
        violations.append("negative_interstage_count")
    if not assay.get("natural_yield_after_r1"):
        violations.append("missing_natural_yield")
    for namespace in ("r2_acquisition", "r2_verification"):
        draw = (assay.get("random_draws") or {}).get(namespace)
        if draw is not None and activation and draw.get("key") and not turn2:
            violations.append("r2_draw_without_turn2")
    return tuple(violations)


def parse_trace(trace: dict[str, Any], outer_id: str = "") -> TraceRow:
    info = trace.get("info", {})
    assay = info.get("provenance_boundary_assay", {}) if isinstance(info, dict) else {}
    if not isinstance(assay, dict):
        assay = {}
    timing = trace.get("timing", {})
    if not isinstance(timing, dict):
        timing = {}
    calls = trace.get("calls", [])
    if not isinstance(calls, list):
        calls = []
    user_message_count = sum(
        1
        for node in trace.get("nodes", []) or []
        if isinstance(node, dict)
        and isinstance(node.get("message"), dict)
        and node["message"].get("role") == "user"
    )
    return TraceRow(
        trace_id=str(trace.get("id", "")),
        outer_id=outer_id,
        attempt_index=_int(assay.get("attempt_index")),
        phase1_order=assay.get("phase1_presentation_order"),
        phase1_policy=assay.get("phase1_policy"),
        phase1_success=_bool(assay.get("phase1_success")),
        phase1_verification_pass=_bool(assay.get("phase1_verification_pass")),
        eligibility=assay.get("eligibility"),
        primary_eligible=_bool(assay.get("primary_eligible")),
        eligible_index=_int(assay.get("eligible_index")),
        block_index=_int(assay.get("assignment_block_index")),
        slot=_int(assay.get("assignment_slot")),
        pair_id=assay.get("source_pair_id"),
        source=assay.get("source_condition"),
        q=_float(assay.get("advisory_reliability")),
        phase2_order=assay.get("phase2_presentation_order"),
        p_origin=assay.get("p_origin"),
        phase2_policy=assay.get("phase2_policy"),
        primary_choice_observed=_bool(assay.get("primary_choice_observed")),
        primary_itt_switch=_bool(assay.get("primary_itt_switch")),
        phase2_missing=_bool(assay.get("phase2_missing")),
        phase2_incomplete=_bool(assay.get("phase2_incomplete_after_choice")),
        natural_yield=_bool(assay.get("natural_yield_after_r1")),
        r2_activated=_bool(assay.get("r2_activated")),
        turn2_count=int(assay.get("turn2_sent_count", 0)),
        turn2_message=assay.get("turn2_message"),
        interstage_calls=int(assay.get("interstage_call_count", 0)),
        phase2_acquisition_success=_bool(assay.get("phase2_acquisition_success")),
        phase2_verification_pass=_bool(assay.get("phase2_verification_pass")),
        stop_reason=assay.get("stop_reason"),
        stop_condition=trace.get("stop_condition"),
        errors=_error_strings(trace.get("errors")),
        model_requests=sum(1 for call in calls if isinstance(call, dict) and call.get("model")),
        tool_calls=_tool_call_count(trace),
        duration_seconds=_timing_duration(timing),
        model_wait_seconds=_nested_duration(timing.get("agent", {}) if isinstance(timing.get("agent", {}), dict) else {}, "model"),
        harness_seconds=_nested_duration(timing.get("agent", {}) if isinstance(timing.get("agent", {}), dict) else {}, "harness"),
        stopped_before_attempt=_bool(assay.get("stopped_before_attempt")),
        user_message_count=user_message_count,
        lifecycle_violations=_lifecycle_violations(trace, assay, user_message_count),
    )


def iter_trace_objects(path: str | Path) -> Iterable[tuple[dict[str, Any], str]]:
    """Yield trace objects from the evaluator's outer JSONL archive."""

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
    return [parse_trace(trace, outer_id) for trace, outer_id in iter_trace_objects(path)]


def wilson_interval(successes: int, total: int, z: float = WILSON_Z) -> tuple[float, float]:
    if total <= 0:
        return (math.nan, math.nan)
    p = successes / total
    denominator = 1.0 + z * z / total
    center = (p + z * z / (2.0 * total)) / denominator
    half = z * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total)) / denominator
    return center - half, center + half


def _rate(successes: int, total: int) -> dict[str, Any]:
    low, high = wilson_interval(successes, total)
    return {
        "successes": successes,
        "total": total,
        "rate": successes / total if total else None,
        "wilson_95": [low, high] if total else None,
    }


def _q_key(q: float) -> str:
    return f"{q:.4f}"


def _group(rows: Iterable[TraceRow], key_fn) -> dict[Any, list[TraceRow]]:
    grouped: dict[Any, list[TraceRow]] = defaultdict(list)
    for row in rows:
        grouped[key_fn(row)].append(row)
    return dict(grouped)


def raw_q_source_table(rows: Sequence[TraceRow]) -> list[dict[str, Any]]:
    eligible = [row for row in rows if row.primary_eligible]
    result: list[dict[str, Any]] = []
    for q in ADVISORY_RELIABILITY_LEVELS:
        for source in SOURCE_CONDITIONS:
            cell = [row for row in eligible if row.q == q and row.source == source]
            observed = [row for row in cell if row.primary_choice_observed]
            result.append(
                {
                    "q": q,
                    "source": source,
                    "n_itt": len(cell),
                    "itt_switch": _rate(sum(row.primary_itt_switch for row in cell), len(cell)),
                    "choice_observed": len(observed),
                    "observed_switch": _rate(
                        sum(row.primary_itt_switch for row in observed), len(observed)
                    ),
                    "missing_or_incomplete": sum(
                        row.phase2_missing or row.phase2_incomplete for row in cell
                    ),
                }
            )
    return result


def _pava(values: Sequence[float], weights: Sequence[float]) -> list[float]:
    spans: list[list[float]] = []
    for index, (value, weight) in enumerate(zip(values, weights)):
        if weight <= 0:
            continue
        spans.append([float(weight), float(value) * float(weight), float(index), float(index)])
        while len(spans) >= 2:
            left, right = spans[-2], spans[-1]
            left_mean = left[1] / left[0]
            right_mean = right[1] / right[0]
            if left_mean <= right_mean:
                break
            spans[-2:] = [[
                left[0] + right[0],
                left[1] + right[1],
                left[2],
                right[3],
            ]]
    expanded: list[float] = []
    for weight, weighted_sum, start, end in spans:
        del weight
        weight_sum = sum(weights[int(start) : int(end) + 1])
        expanded.extend(
            [weighted_sum / weight_sum] * (int(end) - int(start) + 1)
        )
    return expanded


def isotonic_q50(q_values: Sequence[float], rates: Sequence[float], weights: Sequence[int]) -> dict[str, Any]:
    if not (len(q_values) == len(rates) == len(weights)):
        raise ValueError("q, rates, and weights must have equal lengths")
    valid = [
        (q, rate, weight)
        for q, rate, weight in zip(q_values, rates, weights)
        if weight > 0
    ]
    if not valid:
        return {"q50": None, "fitted": [], "identified": False}
    valid_q = [entry[0] for entry in valid]
    valid_rates = [entry[1] for entry in valid]
    valid_weights = [entry[2] for entry in valid]
    fitted = _pava(valid_rates, valid_weights)
    for index, value in enumerate(fitted):
        if math.isclose(value, 0.5, abs_tol=1e-15):
            return {"q50": valid_q[index], "fitted": fitted, "identified": True}
    for index in range(len(fitted) - 1):
        left, right = fitted[index], fitted[index + 1]
        if left < 0.5 < right:
            fraction = (0.5 - left) / (right - left)
            return {
                "q50": valid_q[index] + fraction * (valid_q[index + 1] - valid_q[index]),
                "fitted": fitted,
                "identified": True,
            }
    return {"q50": None, "fitted": fitted, "identified": False}


def _curve(
    rows: Sequence[TraceRow], source: str, *, observed_only: bool = False
) -> dict[str, Any]:
    rates: list[float] = []
    weights: list[int] = []
    raw: list[dict[str, Any]] = []
    for q in ADVISORY_RELIABILITY_LEVELS:
        cell = [
            row
            for row in rows
            if row.primary_eligible
            and row.source == source
            and row.q == q
            and (not observed_only or row.primary_choice_observed)
        ]
        successes = sum(row.primary_itt_switch for row in cell)
        rates.append(successes / len(cell) if cell else 0.0)
        weights.append(len(cell))
        raw.append({"q": q, "source": source, "n": len(cell), **_rate(successes, len(cell))})
    return {
        "source": source,
        "endpoint": "observed_only" if observed_only else "itt",
        "raw": raw,
        "isotonic_q50": isotonic_q50(
            ADVISORY_RELIABILITY_LEVELS, rates, weights
        ),
    }


def _normal_interval(mean: float, standard_error: float) -> list[float]:
    return [mean - WILSON_Z * standard_error, mean + WILSON_Z * standard_error]


def pair_rows(rows: Sequence[TraceRow]) -> tuple[list[PairRow], dict[str, Any]]:
    grouped = _group((row for row in rows if row.primary_eligible and row.pair_id), lambda row: row.pair_id)
    pairs: list[PairRow] = []
    incomplete: list[dict[str, Any]] = []
    for pair_id, members in sorted(grouped.items()):
        sources = {row.source for row in members}
        if len(members) != 2 or sources != set(SOURCE_CONDITIONS):
            incomplete.append({"pair_id": pair_id, "member_count": len(members), "sources": sorted(sources)})
            continue
        by_source = {row.source: row for row in members}
        predecessor = by_source["PredecessorSource"]
        automated = by_source["AutomatedSource"]
        if predecessor.q is None or predecessor.phase2_order is None:
            incomplete.append({"pair_id": pair_id, "reason": "missing_q_or_order"})
            continue
        pairs.append(PairRow(
            pair_id=str(pair_id),
            q=predecessor.q,
            phase2_order=predecessor.phase2_order,
            predecessor_switch=predecessor.primary_itt_switch,
            automated_switch=automated.primary_itt_switch,
            predecessor_observed=predecessor.primary_choice_observed,
            automated_observed=automated.primary_choice_observed,
            predecessor_trace_id=predecessor.trace_id,
            automated_trace_id=automated.trace_id,
        ))
    return pairs, {"complete_pairs": len(pairs), "incomplete_pairs": incomplete}


def exact_mcnemar(b: int, c: int) -> float:
    discordant = b + c
    if discordant == 0:
        return 1.0
    probabilities = [math.comb(discordant, k) / (2.0**discordant) for k in range(discordant + 1)]
    lower = sum(probabilities[: min(b, c) + 1])
    upper = sum(probabilities[max(b, c) :])
    return min(1.0, 2.0 * min(lower, upper))


def mcnemar_summary(pairs: Sequence[PairRow]) -> dict[str, Any]:
    both_switch = sum(pair.predecessor_switch and pair.automated_switch for pair in pairs)
    both_retain = sum(not pair.predecessor_switch and not pair.automated_switch for pair in pairs)
    predecessor_switch_automated_retain = sum(
        pair.predecessor_switch and not pair.automated_switch for pair in pairs
    )
    predecessor_retain_automated_switch = sum(
        not pair.predecessor_switch and pair.automated_switch for pair in pairs
    )
    return {
        "pairs": len(pairs),
        "both_switch": both_switch,
        "both_retain": both_retain,
        "predecessor_switch_automated_retain": predecessor_switch_automated_retain,
        "predecessor_retain_automated_switch": predecessor_retain_automated_switch,
        "discordant_total": predecessor_switch_automated_retain + predecessor_retain_automated_switch,
        "exact_two_sided_p": exact_mcnemar(
            predecessor_switch_automated_retain,
            predecessor_retain_automated_switch,
        ),
    }


def source_risk_difference(
    pairs: Sequence[PairRow], *, observed_only: bool = False
) -> dict[str, Any]:
    usable_pairs = [
        pair
        for pair in pairs
        if not observed_only or (pair.predecessor_observed and pair.automated_observed)
    ]
    by_q = _group(usable_pairs, lambda pair: pair.q)
    q_differences: list[dict[str, Any]] = []
    for q in ADVISORY_RELIABILITY_LEVELS:
        cell = by_q.get(q, [])
        differences = [int(pair.predecessor_switch) - int(pair.automated_switch) for pair in cell]
        mean = statistics.fmean(differences) if differences else math.nan
        variance = statistics.variance(differences) if len(differences) > 1 else 0.0
        q_differences.append({"q": q, "n_pairs": len(cell), "risk_difference": mean if differences else None})
        if differences:
            q_differences[-1]["pair_difference_variance"] = variance
    usable = [entry for entry in q_differences if entry["risk_difference"] is not None]
    estimate = statistics.fmean([entry["risk_difference"] for entry in usable]) if usable else math.nan
    variance_terms = []
    for entry in usable:
        n = int(entry["n_pairs"])
        variance_terms.append(float(entry.get("pair_difference_variance", 0.0)) / n if n else 0.0)
    se = math.sqrt(sum(variance_terms)) / len(usable) if usable else math.nan
    return {
        "estimand": (
            "equal-weight mean over q of PredecessorSource minus AutomatedSource "
            + ("observed-only" if observed_only else "ITT")
            + " switch risk"
        ),
        "endpoint": "observed_only" if observed_only else "itt",
        "q_strata": q_differences,
        "estimate": estimate if usable else None,
        "normal_95_interval": _normal_interval(estimate, se) if usable else None,
        "standard_error": se if usable else None,
    }


def _q50_from_pair_labels(
    pairs: Sequence[PairRow],
    flips: Sequence[bool],
    *,
    observed_only: bool = False,
) -> tuple[float | None, float | None]:
    pred_counts = [0] * len(ADVISORY_RELIABILITY_LEVELS)
    auto_counts = [0] * len(ADVISORY_RELIABILITY_LEVELS)
    totals = [0] * len(ADVISORY_RELIABILITY_LEVELS)
    q_to_index = {q: index for index, q in enumerate(ADVISORY_RELIABILITY_LEVELS)}
    for pair, flip in zip(pairs, flips):
        if observed_only and not (pair.predecessor_observed and pair.automated_observed):
            continue
        index = q_to_index[pair.q]
        pred = pair.automated_switch if flip else pair.predecessor_switch
        auto = pair.predecessor_switch if flip else pair.automated_switch
        pred_counts[index] += int(pred)
        auto_counts[index] += int(auto)
        totals[index] += 1
    pred_curve = isotonic_q50(
        ADVISORY_RELIABILITY_LEVELS,
        [count / total if total else 0.0 for count, total in zip(pred_counts, totals)],
        totals,
    )
    auto_curve = isotonic_q50(
        ADVISORY_RELIABILITY_LEVELS,
        [count / total if total else 0.0 for count, total in zip(auto_counts, totals)],
        totals,
    )
    return pred_curve["q50"], auto_curve["q50"]


def randomization_inference_q50(
    pairs: Sequence[PairRow],
    *,
    repetitions: int = RANDOMIZATION_REPETITIONS,
    seed: str = RANDOMIZATION_SEED,
) -> dict[str, Any]:
    observed_pred, observed_auto = _q50_from_pair_labels(pairs, [False] * len(pairs))
    observed_delta = (
        observed_pred - observed_auto
        if observed_pred is not None and observed_auto is not None
        else None
    )
    rng = random.Random(seed)
    deltas: list[float] = []
    for _ in range(repetitions):
        pred_q50, auto_q50 = _q50_from_pair_labels(
            pairs, [bool(rng.getrandbits(1)) for _ in pairs]
        )
        if pred_q50 is not None and auto_q50 is not None:
            deltas.append(pred_q50 - auto_q50)
    result: dict[str, Any] = {
        "repetitions": repetitions,
        "seed": seed,
        "minimum_identifiable_fraction_for_p": MIN_Q50_IDENTIFIABLE_FRACTION,
        "observed_predecessor_q50": observed_pred,
        "observed_automated_q50": observed_auto,
        "observed_delta_q50": observed_delta,
        "identifiable_repetitions": len(deltas),
        "identifiable_fraction": len(deltas) / repetitions if repetitions else None,
    }
    identifiable_fraction = len(deltas) / repetitions if repetitions else 0.0
    if observed_delta is None or not deltas:
        result["two_sided_p"] = None
        result["quantiles"] = None
        return result
    if identifiable_fraction < MIN_Q50_IDENTIFIABLE_FRACTION:
        result["two_sided_p"] = None
        result["p_suppressed_reason"] = (
            "identifiable fraction below the frozen 0.50 threshold"
        )
    else:
        absolute = abs(observed_delta)
        result["two_sided_p"] = (1 + sum(abs(delta) >= absolute for delta in deltas)) / (1 + len(deltas))
    result["quantiles"] = {
        str(level): statistics.quantiles(deltas, n=100, method="inclusive")[int(level * 100) - 1]
        for level in (0.025, 0.5, 0.975)
    }
    return result


def _simple_group_summary(rows: Sequence[TraceRow], key: str) -> list[dict[str, Any]]:
    grouped = _group((row for row in rows if row.primary_eligible), lambda row: getattr(row, key))
    result = []
    for value in sorted(grouped, key=lambda item: "" if item is None else str(item)):
        cell = grouped[value]
        observed = [row for row in cell if row.primary_choice_observed]
        result.append({
            key: value,
            "n": len(cell),
            "itt_switch": _rate(sum(row.primary_itt_switch for row in cell), len(cell)),
            "choice_observed": len(observed),
            "observed_switch": _rate(sum(row.primary_itt_switch for row in observed), len(observed)),
        })
    return result


def lifecycle_summary(rows: Sequence[TraceRow]) -> dict[str, Any]:
    eligible = [row for row in rows if row.primary_eligible]
    violations: list[dict[str, Any]] = []
    for row in eligible:
        row_violations: list[str] = []
        row_violations.extend(row.lifecycle_violations)
        if not row.r2_activated:
            row_violations.append("r2_not_activated")
        if row.errors:
            row_violations.append("runtime_or_provider_error")
        if row_violations:
            violations.append({"trace_id": row.trace_id, "violations": row_violations})
    return {
        "eligible": len(eligible),
        "natural_yield": _rate(sum(row.natural_yield for row in eligible), len(eligible)),
        "r2_activation": _rate(sum(row.r2_activated for row in eligible), len(eligible)),
        "turn2_exactly_one": _rate(sum(row.turn2_count == 1 for row in eligible), len(eligible)),
        "choice_observed": _rate(sum(row.primary_choice_observed for row in eligible), len(eligible)),
        "missing_phase2": sum(row.phase2_missing for row in eligible),
        "incomplete_after_choice": sum(row.phase2_incomplete for row in eligible),
        "interstage_call_total": sum(row.interstage_calls for row in eligible),
        "interstage_call_frequency": _rate(sum(row.interstage_calls > 0 for row in eligible), len(eligible)),
        "user_message_count": {
            "expected": 2,
            "observed": {str(count): sum(row.user_message_count == count for row in eligible) for count in sorted({row.user_message_count for row in eligible})},
        },
        "violations": violations,
    }


def runtime_summary(rows: Sequence[TraceRow]) -> dict[str, Any]:
    def values(field: str, subset: Sequence[TraceRow]) -> list[float]:
        return [float(getattr(row, field)) for row in subset if getattr(row, field) is not None]

    def describe(field: str, subset: Sequence[TraceRow], label: str) -> dict[str, Any]:
        observed = values(field, subset)
        return {
            "n": len(observed),
            f"mean_{label}": statistics.fmean(observed) if observed else None,
            f"median_{label}": statistics.median(observed) if observed else None,
            f"min_{label}": min(observed) if observed else None,
            f"max_{label}": max(observed) if observed else None,
        }

    durations = values("duration_seconds", rows)
    eligible = [row for row in rows if row.primary_eligible]
    model_wait = values("model_wait_seconds", rows)
    harness = values("harness_seconds", rows)
    total = sum(durations) if durations else None
    return {
        "rollouts": len(rows),
        "total_wall_seconds": total,
        "total_wall_hours": total / 3600.0 if total is not None else None,
        "rollout_duration": describe("duration_seconds", rows, "seconds"),
        "all_rollouts": describe("duration_seconds", rows, "seconds"),
        "eligible_rollouts": describe("duration_seconds", eligible, "seconds"),
        "model_requests": describe("model_requests", rows, "requests"),
        "tool_calls": describe("tool_calls", rows, "calls"),
        "model_wait_seconds_total": sum(model_wait) if model_wait else None,
        "harness_seconds_total": sum(harness) if harness else None,
        "local_overhead_approx_seconds": (
            total - sum(model_wait) if total is not None and model_wait else None
        ),
        "eligible_per_hour": (
            len(eligible) / (total / 3600.0)
            if total and total > 0
            else None
        ),
    }


def analyze_rows(rows: Sequence[TraceRow], *, randomization_repetitions: int = RANDOMIZATION_REPETITIONS) -> dict[str, Any]:
    eligible = [row for row in rows if row.primary_eligible]
    pairs, pair_integrity = pair_rows(rows)
    mcnemar = mcnemar_summary(pairs)
    return {
        "trace_count": len(rows),
        "phase1_attempt_count": sum(not row.stopped_before_attempt for row in rows),
        "guard_record_count": sum(row.stopped_before_attempt for row in rows),
        "primary_eligible_count": len(eligible),
        "phase1_policy": _simple_group_summary(rows, "phase1_policy"),
        "phase1_order": _simple_group_summary(rows, "phase1_order"),
        "q_source_table": raw_q_source_table(rows),
        "curves": {source: _curve(rows, source) for source in SOURCE_CONDITIONS},
        "observed_only_curves": {
            source: _curve(rows, source, observed_only=True)
            for source in SOURCE_CONDITIONS
        },
        "matched_pairs": pair_integrity,
        "mcnemar": mcnemar,
        "source_risk_difference": {
            "itt": source_risk_difference(pairs),
            "observed_only": source_risk_difference(pairs, observed_only=True),
        },
        "q50_randomization": randomization_inference_q50(
            pairs, repetitions=randomization_repetitions
        ),
        "phase2_order": _simple_group_summary(rows, "phase2_order"),
        "p_origin": _simple_group_summary(rows, "p_origin"),
        "r2_secondary": {
            "acquisition": _rate(
                sum(row.phase2_acquisition_success for row in eligible), len(eligible)
            ),
            "verification": _rate(
                sum(row.phase2_verification_pass for row in eligible), len(eligible)
            ),
            "policy_k": sum(row.phase2_policy == "K" for row in eligible),
            "policy_m": sum(row.phase2_policy == "M" for row in eligible),
        },
        "lifecycle": lifecycle_summary(rows),
        "runtime": runtime_summary(rows),
        "normative_crossover": NORMATIVE_CROSSOVER,
        "optional_logistic": "not run; frozen analysis uses raw and isotonic curves",
        "trace_rows": [asdict(row) for row in rows],
    }


def analyze_jsonl(path: str | Path, *, randomization_repetitions: int = RANDOMIZATION_REPETITIONS) -> dict[str, Any]:
    return analyze_rows(load_rows(path), randomization_repetitions=randomization_repetitions)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("traces", type=Path)
    parser.add_argument("--randomization-repetitions", type=int, default=RANDOMIZATION_REPETITIONS)
    args = parser.parse_args()
    print(json.dumps(analyze_jsonl(args.traces, randomization_repetitions=args.randomization_repetitions), indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
