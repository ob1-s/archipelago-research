"""Deterministic, outcome-blind qualification calculations."""

from __future__ import annotations

import math
from typing import Any

from .assignment import MAX_ATTEMPTS, QUOTA_CELL_COUNT, build_attempt_plan
from .constants import Q_GRIDS, STRENGTHS, TARGET_PRIMARY_PER_QUOTA_CELL
from .evidence import strength_math, validate_frozen_math


def expected_attempts_by_strength() -> dict[str, float]:
    validate_frozen_math()
    return {
        strength: (len(Q_GRIDS[strength]) * 2 * TARGET_PRIMARY_PER_QUOTA_CELL)
        * 2
        / strength_math(strength).eligibility_rate
        for strength in STRENGTHS
    }


def expected_attempts_total() -> float:
    return sum(expected_attempts_by_strength().values())


def binomial_probability_below_target(
    strength: str,
    attempts_per_quota_cell: int,
) -> float:
    """Probability a frozen quota cell has fewer than six eligible rows."""

    p = strength_math(strength).eligibility_rate  # type: ignore[arg-type]
    target = TARGET_PRIMARY_PER_QUOTA_CELL
    return sum(
        math.comb(attempts_per_quota_cell, successes)
        * p**successes
        * (1.0 - p) ** (attempts_per_quota_cell - successes)
        for successes in range(target)
    )


def all_cells_completion_failure_bound(attempts_per_quota_cell: int) -> float:
    """Union bound across the 28 Phase-1/Phase-2 quota cells per strength."""

    return sum(
        4
        * len(Q_GRIDS[strength])
        * binomial_probability_below_target(strength, attempts_per_quota_cell)
        for strength in STRENGTHS
    )


def assignment_audit(seed: str) -> dict[str, Any]:
    plan = build_attempt_plan(seed)
    signatures = {
        row.attempt_index: (
            row.strength,
            row.advisory_reliability,
            row.phase1_order,
            row.phase2_order,
            row.quota_cell_key,
        )
        for row in plan
    }
    return {
        "max_attempts": MAX_ATTEMPTS,
        "quota_cell_count": QUOTA_CELL_COUNT,
        "unique_attempt_indices": len(signatures) == MAX_ATTEMPTS,
        "first_signature": signatures[0],
        "last_signature": signatures[MAX_ATTEMPTS - 1],
        "assignment_signature_digest_input_count": len(signatures),
        "completion_order_independent": True,
    }
