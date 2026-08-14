"""Pre-Phase-1 condition assignment and concurrency-safe quota bookkeeping.

Experimental conditions are deterministic functions of attempt identity. No
condition is assigned when an eligible trajectory completes.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import (
    PHASE1_ORDERS,
    Q_GRIDS,
    QUOTA_SEED,
    ROUNDS_PER_QUOTA_CELL,
    STRENGTHS,
    TARGET_PRIMARY_PER_PHASE2_CELL,
    TARGET_PRIMARY_PER_QUOTA_CELL,
    PolicyOrder,
    Strength,
)

QUOTA_CELL_COUNT = sum(len(Q_GRIDS[s]) for s in STRENGTHS) * 2 * 2
MAX_ATTEMPTS = QUOTA_CELL_COUNT * ROUNDS_PER_QUOTA_CELL
TARGET_PRIMARY_ELIGIBLE = (
    sum(len(Q_GRIDS[s]) for s in STRENGTHS) * 2 * TARGET_PRIMARY_PER_PHASE2_CELL
)
ASSIGNMENT_NAMESPACES = ("condition_assignment", "quota_acceptance")


@dataclass(frozen=True)
class AttemptAssignment:
    attempt_index: int
    strength: Strength
    advisory_reliability: float
    phase1_order: PolicyOrder
    phase2_order: PolicyOrder
    quota_cell_key: str
    quota_cell_target: int
    quota_round: int
    assignment_key: str


def quota_cell_key(
    strength: Strength,
    advisory_reliability: float,
    phase1_order: PolicyOrder,
    phase2_order: PolicyOrder,
) -> str:
    return f"{strength}|{advisory_reliability:.4f}|{phase1_order}|{phase2_order}"


def _cells() -> list[tuple[Strength, float, PolicyOrder, PolicyOrder]]:
    return [
        (strength, q, phase1_order, phase2_order)
        for strength in STRENGTHS
        for q in Q_GRIDS[strength]
        for phase2_order in PHASE1_ORDERS
        for phase1_order in PHASE1_ORDERS
    ]


def build_attempt_plan(seed: str) -> list[AttemptAssignment]:
    if not seed:
        raise ValueError("schedule seed must be non-empty")
    cells = _cells()
    plan: list[AttemptAssignment] = []
    for round_index in range(ROUNDS_PER_QUOTA_CELL):
        for cell_index, (strength, q, phase1_order, phase2_order) in enumerate(cells):
            attempt_index = round_index * len(cells) + cell_index
            key = hashlib.sha256(
                f"{seed}:attempt:{attempt_index}:condition_assignment".encode()
            ).hexdigest()
            plan.append(
                AttemptAssignment(
                    attempt_index=attempt_index,
                    strength=strength,
                    advisory_reliability=q,
                    phase1_order=phase1_order,
                    phase2_order=phase2_order,
                    quota_cell_key=quota_cell_key(
                        strength, q, phase1_order, phase2_order
                    ),
                    quota_cell_target=TARGET_PRIMARY_PER_QUOTA_CELL,
                    quota_round=round_index,
                    assignment_key=f"sha256({key})",
                )
            )
    return plan


def assignment_for_index(seed: str, attempt_index: int) -> AttemptAssignment:
    if not 0 <= attempt_index < MAX_ATTEMPTS:
        raise ValueError("attempt index is outside the frozen schedule")
    return build_attempt_plan(seed)[attempt_index]


def _lock_path(target: Path) -> Path:
    return target.with_name(target.name + ".lock")


def _initial_state(seed: str) -> dict[str, Any]:
    cells = [quota_cell_key(strength, q, p1, p2) for strength, q, p1, p2 in _cells()]
    return {
        "quota_seed": QUOTA_SEED,
        "schedule_seed": seed,
        "target_per_quota_cell": TARGET_PRIMARY_PER_QUOTA_CELL,
        "accepted_by_cell": {cell: 0 for cell in cells},
        "accepted_attempts": [],
    }


def _read_state(target: Path) -> dict[str, Any]:
    raw = target.read_text(encoding="utf-8").strip()
    if not raw:
        raise RuntimeError("quota state is empty or was interrupted")
    state = json.loads(raw)
    if not isinstance(state, dict):
        raise TypeError("quota state is not a JSON object")
    return state


def _write_state_atomic(target: Path, state: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", dir=target.parent, text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(state, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, target)
        directory_descriptor = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def ensure_quota_state(path: str, schedule_seed: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _lock_path(target).open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if target.exists():
            state = _read_state(target)
            if state.get("schedule_seed") != schedule_seed:
                raise RuntimeError("quota state schedule seed does not match")
            if state.get("target_per_quota_cell") != TARGET_PRIMARY_PER_QUOTA_CELL:
                raise RuntimeError("quota state target does not match")
        else:
            _write_state_atomic(target, _initial_state(schedule_seed))
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def quota_snapshot(path: str, schedule_seed: str) -> dict[str, Any]:
    target = Path(path)
    with _lock_path(target).open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
        state = _read_state(target)
        if state.get("schedule_seed") != schedule_seed:
            raise RuntimeError("quota state schedule seed does not match")
        snapshot = json.loads(json.dumps(state))
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return snapshot


def cell_is_complete(path: str, schedule_seed: str, cell: str) -> bool:
    state = quota_snapshot(path, schedule_seed)
    counts = state.get("accepted_by_cell", {})
    return int(counts.get(cell, 0)) >= TARGET_PRIMARY_PER_QUOTA_CELL


def accept_primary_quota(
    path: str,
    schedule_seed: str,
    cell: str,
    attempt_index: int,
) -> tuple[bool, int | None]:
    """Atomically accept an eligible row into its already assigned cell quota.

    This operation never chooses a condition. It only records whether an
    attempt whose condition was fixed before Phase 1 fits its own cell quota.
    """

    target = Path(path)
    with _lock_path(target).open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        state = _read_state(target)
        if state.get("schedule_seed") != schedule_seed:
            raise RuntimeError("quota state schedule seed does not match")
        counts = state.get("accepted_by_cell")
        attempts = state.get("accepted_attempts")
        if not isinstance(counts, dict) or not isinstance(attempts, list):
            raise TypeError("quota state has invalid shape")
        if attempt_index in attempts:
            raise RuntimeError("attempt was accepted more than once")
        current = int(counts.get(cell, 0))
        if current >= TARGET_PRIMARY_PER_QUOTA_CELL:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            return False, None
        counts[cell] = current + 1
        attempts.append(attempt_index)
        _write_state_atomic(target, state)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        return True, current
