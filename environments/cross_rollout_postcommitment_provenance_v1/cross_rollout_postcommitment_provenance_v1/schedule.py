"""Frozen Phase-1 schedule for the 520-attempt hard cap."""

from __future__ import annotations

from dataclasses import dataclass

from .constants import PolicyOrder

MAX_ATTEMPTS = 520
TARGET_PRIMARY_ELIGIBLE = 160
SCHEDULE_SEED = (
    "cross-rollout-postcommitment-provenance-v1-schedule-2026-08-14"
)


@dataclass(frozen=True)
class AttemptSpec:
    attempt_index: int
    phase1_order: PolicyOrder


def build_schedule(seed: str = SCHEDULE_SEED) -> list[AttemptSpec]:
    if not seed:
        raise ValueError("schedule seed must be non-empty")
    # The starting order is frozen by the seed; the full schedule is 1:1.
    import hashlib

    first = ("K_first", "M_first") if hashlib.sha256(seed.encode()).digest()[0] % 2 == 0 else ("M_first", "K_first")
    return [
        AttemptSpec(index, first[index % 2])  # type: ignore[arg-type]
        for index in range(MAX_ATTEMPTS)
    ]
