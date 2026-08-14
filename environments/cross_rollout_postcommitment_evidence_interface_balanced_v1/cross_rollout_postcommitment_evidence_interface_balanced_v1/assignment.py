"""Locked deterministic four-cell blocked assignment for primary eligibility."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Condition = Literal["neutral", "opposing_convention"]
PolicyOrder = Literal["K_first", "M_first"]
BLOCK_SIZE = 4
MAX_PRIMARY_ELIGIBLE = 64
ASSIGNMENT_NAMESPACES = ("treatment_assignment", "phase2_assignment_block")


@dataclass(frozen=True)
class PrimaryAssignment:
    eligible_index: int
    block_index: int
    slot: int
    condition: Condition
    phase2_order: PolicyOrder
    assignment_key: str
    order_key: str


def _digest(seed: str, block_index: int, namespace: str) -> bytes:
    if namespace not in ASSIGNMENT_NAMESPACES:
        raise ValueError(f"unknown assignment namespace: {namespace}")
    return hashlib.sha256(
        f"{seed}:block:{block_index}:{namespace}".encode()
    ).digest()


def _permutation(seed: str, block_index: int) -> list[tuple[Condition, PolicyOrder]]:
    cells: list[tuple[Condition, PolicyOrder]] = [
        ("neutral", "K_first"),
        ("neutral", "M_first"),
        ("opposing_convention", "K_first"),
        ("opposing_convention", "M_first"),
    ]
    keyed = [
        (hashlib.sha256(f"{seed}:block:{block_index}:slot:{slot}".encode()).digest(), cell)
        for slot, cell in enumerate(cells)
    ]
    keyed.sort(key=lambda item: item[0])
    return [cell for _, cell in keyed]


def assignment_for_index(seed: str, eligible_index: int) -> PrimaryAssignment:
    if not 0 <= eligible_index < MAX_PRIMARY_ELIGIBLE:
        raise ValueError("eligible index is outside the preregistered 0..63 range")
    block_index, slot = divmod(eligible_index, BLOCK_SIZE)
    condition, order = _permutation(seed, block_index)[slot]
    treatment_key = f"sha256({seed}:block:{block_index}:treatment_assignment)"
    order_key = f"sha256({seed}:block:{block_index}:phase2_assignment_block)"
    return PrimaryAssignment(
        eligible_index=eligible_index,
        block_index=block_index,
        slot=slot,
        condition=condition,
        phase2_order=order,
        assignment_key=treatment_key,
        order_key=order_key,
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
                {
                    "assignment_seed": seed,
                    "next_eligible_index": 0,
                    "claims": [],
                },
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

