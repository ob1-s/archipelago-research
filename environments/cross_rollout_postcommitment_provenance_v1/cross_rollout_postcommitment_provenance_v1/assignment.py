"""Locked deterministic ten-slot assignment blocks."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .constants import PolicyOrder, SourceCondition

BLOCK_SIZE = 10
MAX_PRIMARY_ELIGIBLE = 160
ASSIGNMENT_NAMESPACE = "provenance_assignment"


@dataclass(frozen=True)
class PrimaryAssignment:
    eligible_index: int
    block_index: int
    slot: int
    condition: SourceCondition
    phase2_order: PolicyOrder
    assignment_key: str


def _cells() -> list[tuple[SourceCondition, PolicyOrder]]:
    return [
        ("PredecessorSource", "K_first"),
        ("PredecessorSource", "K_first"),
        ("PredecessorSource", "M_first"),
        ("PredecessorSource", "M_first"),
        ("AutomatedSource", "K_first"),
        ("AutomatedSource", "K_first"),
        ("AutomatedSource", "M_first"),
        ("AutomatedSource", "M_first"),
        ("NoAdvisory", "K_first"),
        ("NoAdvisory", "M_first"),
    ]


def assignment_for_index(seed: str, eligible_index: int) -> PrimaryAssignment:
    if not 0 <= eligible_index < MAX_PRIMARY_ELIGIBLE:
        raise ValueError("eligible index is outside the preregistered 0..159 range")
    block_index, slot = divmod(eligible_index, BLOCK_SIZE)
    keyed = [
        (
            hashlib.sha256(
                f"{seed}:block:{block_index}:slot:{position}:{ASSIGNMENT_NAMESPACE}".encode()
            ).digest(),
            cell,
        )
        for position, cell in enumerate(_cells())
    ]
    keyed.sort(key=lambda item: item[0])
    condition, order = keyed[slot][1]
    return PrimaryAssignment(
        eligible_index=eligible_index,
        block_index=block_index,
        slot=slot,
        condition=condition,
        phase2_order=order,
        assignment_key=(
            f"sha256({seed}:block:{block_index}:{ASSIGNMENT_NAMESPACE})"
        ),
    )


def ensure_assignment_state(path: str, seed: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.seek(0)
        raw = stream.read().strip()
        if raw:
            state = json.loads(raw)
            if state.get("assignment_seed") != seed:
                raise RuntimeError("assignment state seed does not match task seed")
        else:
            stream.seek(0)
            stream.truncate()
            json.dump(
                {"assignment_seed": seed, "next_eligible_index": 0, "claims": []},
                stream,
                sort_keys=True,
            )
            stream.flush()
            os.fsync(stream.fileno())
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def current_eligible_count(path: str, seed: str) -> int:
    target = Path(path)
    if not target.exists():
        return 0
    with target.open("r", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_SH)
        raw = stream.read().strip()
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    if not raw:
        return 0
    state = json.loads(raw)
    if state.get("assignment_seed") != seed:
        raise RuntimeError("assignment state seed does not match task seed")
    return int(state.get("next_eligible_index", 0))


def claim_assignment(path: str, seed: str) -> PrimaryAssignment:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.seek(0)
        raw = stream.read().strip()
        state = json.loads(raw) if raw else {
            "assignment_seed": seed,
            "next_eligible_index": 0,
            "claims": [],
        }
        if state.get("assignment_seed") != seed:
            raise RuntimeError("assignment state seed does not match task seed")
        eligible_index = int(state.get("next_eligible_index", 0))
        if eligible_index >= MAX_PRIMARY_ELIGIBLE:
            raise RuntimeError("primary eligible stopping threshold exceeded")
        assignment = assignment_for_index(seed, eligible_index)
        state["next_eligible_index"] = eligible_index + 1
        state.setdefault("claims", []).append(
            {
                "eligible_index": assignment.eligible_index,
                "block_index": assignment.block_index,
                "slot": assignment.slot,
                "condition": assignment.condition,
                "phase2_order": assignment.phase2_order,
            }
        )
        stream.seek(0)
        stream.truncate()
        json.dump(state, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        return assignment
