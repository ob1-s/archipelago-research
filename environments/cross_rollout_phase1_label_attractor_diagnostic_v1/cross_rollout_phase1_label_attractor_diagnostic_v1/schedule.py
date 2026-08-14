"""Deterministic complete schedule for the 16-cell diagnostic."""

from __future__ import annotations

import random

from .constants import CellSpec, cell_specs

TOTAL_CELLS = 16
ROLLOUTS_PER_CELL = 10
TOTAL_ROLLOUTS = TOTAL_CELLS * ROLLOUTS_PER_CELL
SCHEDULE_SEED = "cross-rollout-phase1-label-attractor-diagnostic-v1-schedule-2026-08-13"


def build_schedule(seed: str = SCHEDULE_SEED) -> list[CellSpec]:
    cells = [cell for cell in cell_specs() for _ in range(ROLLOUTS_PER_CELL)]
    random.Random(seed).shuffle(cells)
    return cells
