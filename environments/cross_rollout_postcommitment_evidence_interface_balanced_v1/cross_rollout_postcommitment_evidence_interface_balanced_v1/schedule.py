"""Frozen Phase-1 and secondary Phase-2 schedules."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .constants import PolicyOrder

MAX_ATTEMPTS = 240
TARGET_PRIMARY_ELIGIBLE = 64
SCHEDULE_SEED = (
    "cross-rollout-postcommitment-evidence-interface-balanced-v1-schedule-2026-08-13"
)
SECONDARY_SCHEDULE_SEED = (
    "cross-rollout-postcommitment-evidence-interface-balanced-v1-secondary-2026-08-13"
)


@dataclass(frozen=True)
class AttemptSpec:
    attempt_index: int
    phase1_order: PolicyOrder
    secondary_phase2_order: PolicyOrder


def _digest(seed: str, index: int) -> bytes:
    return hashlib.sha256(f"{seed}:{index}".encode()).digest()


def build_schedule(
    seed: str = SCHEDULE_SEED,
    secondary_seed: str = SECONDARY_SCHEDULE_SEED,
) -> list[AttemptSpec]:
    """Build all 240 attempts before inference, independently of outcomes."""

    # The Phase-1 schedule is explicitly alternating and exactly balanced.
    phase1 = (
        ("K_first", "M_first")
        if _digest(seed, 0)[0] % 2 == 0
        else ("M_first", "K_first")
    )
    secondary_values = ["K_first"] * (MAX_ATTEMPTS // 2) + [
        "M_first"
    ] * (MAX_ATTEMPTS // 2)
    secondary = [
        value
        for _, value in sorted(
            (
                (_digest(secondary_seed, index), value)
                for index, value in enumerate(secondary_values)
            ),
            key=lambda item: item[0],
        )
    ]
    # Include the seed in the construction contract so callers cannot silently
    # substitute a different schedule implementation.
    if not seed:
        raise ValueError("schedule seed must be non-empty")
    return [
        AttemptSpec(
            attempt_index=index,
            phase1_order=phase1[index % 2],  # type: ignore[arg-type]
            secondary_phase2_order=secondary[index],  # type: ignore[arg-type]
        )
        for index in range(MAX_ATTEMPTS)
    ]
