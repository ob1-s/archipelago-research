"""Run-level deterministic blocked assignment for primary eligible rollouts."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from dataclasses import dataclass
from itertools import permutations
from pathlib import Path
from typing import Literal

Condition = Literal["neutral", "opposing_convention"]
Order = Literal["A_first", "B_first"]

MAX_PRIMARY_ELIGIBLE = 64
BLOCK_SIZE = 4
ASSIGNMENT_NAMESPACES = (
    "treatment_assignment",
    "phase2_assignment_block",
)


@dataclass(frozen=True)
class RelativeAssignment:
    eligible_index: int
    block_index: int
    slot: int
    condition: Condition
    phase2_order: Order
    treatment_value: float
    treatment_key: str
    phase2_value: float
    phase2_key: str


def _block_digest(seed: str, block_index: int, namespace: str) -> bytes:
    if namespace not in ASSIGNMENT_NAMESPACES:
        raise ValueError(f"unknown assignment namespace: {namespace}")
    return hashlib.sha256(
        f"{seed}:block:{block_index}:{namespace}".encode()
    ).digest()


def _uniform(digest: bytes) -> float:
    return int.from_bytes(digest[:8], "big") / float(2**64)


def assignment_for_index(seed: str, eligible_index: int) -> RelativeAssignment:
    """Return one deterministic, balanced cell from an eligible-index block."""

    if eligible_index < 0 or eligible_index >= MAX_PRIMARY_ELIGIBLE:
        raise ValueError("eligible index is outside the preregistered 0..63 range")

    block_index, slot = divmod(eligible_index, BLOCK_SIZE)
    treatment_digest = _block_digest(
        seed, block_index, "treatment_assignment"
    )
    phase2_digest = _block_digest(
        seed, block_index, "phase2_assignment_block"
    )
    treatment_value = _uniform(treatment_digest)
    phase2_value = _uniform(phase2_digest)

    condition_sequences = sorted(
        set(
            permutations(
                ("neutral", "neutral", "opposing_convention", "opposing_convention")
            )
        )
    )
    condition_sequence = condition_sequences[min(int(treatment_value * 6), 5)]
    phase2_orders: list[Order | None] = [None] * BLOCK_SIZE
    for condition, bit in (
        ("neutral", phase2_digest[0] % 2),
        ("opposing_convention", phase2_digest[1] % 2),
    ):
        positions = [
            index
            for index, value in enumerate(condition_sequence)
            if value == condition
        ]
        first: Order = "A_first" if bit == 0 else "B_first"
        second: Order = "B_first" if first == "A_first" else "A_first"
        phase2_orders[positions[0]] = first
        phase2_orders[positions[1]] = second

    condition = condition_sequence[slot]
    phase2_order = phase2_orders[slot]
    assert phase2_order is not None
    return RelativeAssignment(
        eligible_index=eligible_index,
        block_index=block_index,
        slot=slot,
        condition=condition,
        phase2_order=phase2_order,
        treatment_value=treatment_value,
        treatment_key=(
            f"sha256({seed}:block:{block_index}:treatment_assignment)[:8]"
        ),
        phase2_value=phase2_value,
        phase2_key=(
            f"sha256({seed}:block:{block_index}:phase2_assignment_block)[:8]"
        ),
    )


def ensure_assignment_state(path: str, seed: str) -> None:
    """Create the run allocator state without resetting an existing run."""

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
            )
            stream.flush()
            os.fsync(stream.fileno())
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def claim_assignment(path: str, seed: str) -> RelativeAssignment:
    """Atomically claim the next eligible index and persist its assignment."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.seek(0)
        raw = stream.read().strip()
        state = (
            json.loads(raw)
            if raw
            else {
                "assignment_seed": seed,
                "next_eligible_index": 0,
                "claims": [],
            }
        )
        if state.get("assignment_seed") != seed:
            raise RuntimeError("assignment state seed does not match task seed")
        eligible_index = int(state["next_eligible_index"])
        if eligible_index >= MAX_PRIMARY_ELIGIBLE:
            raise RuntimeError(
                "the preregistered 64-eligible stopping threshold was exceeded"
            )
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
