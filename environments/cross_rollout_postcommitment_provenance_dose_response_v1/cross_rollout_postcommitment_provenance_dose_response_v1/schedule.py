"""Frozen Phase-1 schedule and stopping rule."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .constants import PolicyOrder

MAX_ATTEMPTS = 900
TARGET_PRIMARY_ELIGIBLE = 280
SCHEDULE_SEED = (
    "cross-rollout-postcommitment-provenance-dose-response-v1-schedule-2026-08-14"
)


@dataclass(frozen=True)
class AttemptSpec:
    attempt_index: int
    phase1_order: PolicyOrder


def _digest(seed: str, index: int) -> bytes:
    return hashlib.sha256(f"{seed}:{index}".encode()).digest()


def build_schedule(seed: str = SCHEDULE_SEED) -> list[AttemptSpec]:
    if not seed:
        raise ValueError("schedule seed must be non-empty")
    first = ("K_first", "M_first") if _digest(seed, 0)[0] % 2 == 0 else ("M_first", "K_first")
    return [
        AttemptSpec(index, first[index % 2])  # type: ignore[arg-type]
        for index in range(MAX_ATTEMPTS)
    ]
