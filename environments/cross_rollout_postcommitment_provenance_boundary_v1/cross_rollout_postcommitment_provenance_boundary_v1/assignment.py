"""Frozen 36-slot macro-block assignment with matched source pairs."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .constants import ADVISORY_RELIABILITY_LEVELS, PolicyOrder, SourceCondition

BLOCK_SIZE = 36
MAX_PRIMARY_ELIGIBLE = 432
MACRO_BLOCK_COUNT = MAX_PRIMARY_ELIGIBLE // BLOCK_SIZE
ASSIGNMENT_NAMESPACES = ("source_pair", "macro_block_shuffle")


@dataclass(frozen=True)
class PrimaryAssignment:
    eligible_index: int
    block_index: int
    slot: int
    advisory_reliability: float
    source_condition: SourceCondition
    phase2_order: PolicyOrder
    pair_id: str
    source_pair_key: str
    assignment_order_key: str


def _pair_cells() -> list[tuple[float, PolicyOrder]]:
    return [
        (q, order)
        for q in ADVISORY_RELIABILITY_LEVELS
        for order in ("K_first", "M_first")
    ]


def _source_bit(seed: str, block_index: int, pair_index: int) -> bool:
    digest = hashlib.sha256(
        f"{seed}:block:{block_index}:pair:{pair_index}:source_pair".encode()
    ).digest()
    return bool(digest[0] & 1)


def _block_assignments(seed: str, block_index: int) -> list[dict[str, object]]:
    if not 0 <= block_index < MACRO_BLOCK_COUNT:
        raise ValueError("block index is outside the frozen macro-block range")
    paired: list[dict[str, object]] = []
    for pair_index, (q, order) in enumerate(_pair_cells()):
        pair_id = f"block-{block_index:02d}-q-{q:.4f}-{order}"
        sources = (
            ("PredecessorSource", "AutomatedSource")
            if not _source_bit(seed, block_index, pair_index)
            else ("AutomatedSource", "PredecessorSource")
        )
        source_pair_key = (
            f"sha256({seed}:block:{block_index}:pair:{pair_index}:source_pair)"
        )
        for source in sources:
            paired.append(
                {
                    "q": q,
                    "order": order,
                    "source": source,
                    "pair_id": pair_id,
                    "source_pair_key": source_pair_key,
                }
            )
    keyed = [
        (
            hashlib.sha256(
                f"{seed}:block:{block_index}:position:{position}:macro_block_shuffle".encode()
            ).digest(),
            entry,
        )
        for position, entry in enumerate(paired)
    ]
    keyed.sort(key=lambda item: item[0])
    return [entry for _, entry in keyed]


def assignment_for_index(seed: str, eligible_index: int) -> PrimaryAssignment:
    if not 0 <= eligible_index < MAX_PRIMARY_ELIGIBLE:
        raise ValueError("eligible index is outside the preregistered 0..431 range")
    block_index, slot = divmod(eligible_index, BLOCK_SIZE)
    entry = _block_assignments(seed, block_index)[slot]
    return PrimaryAssignment(
        eligible_index=eligible_index,
        block_index=block_index,
        slot=slot,
        advisory_reliability=float(entry["q"]),
        source_condition=entry["source"],  # type: ignore[arg-type]
        phase2_order=entry["order"],  # type: ignore[arg-type]
        pair_id=str(entry["pair_id"]),
        source_pair_key=str(entry["source_pair_key"]),
        assignment_order_key=(
            f"sha256({seed}:block:{block_index}:macro_block_shuffle)"
        ),
    )


def build_assignment_plan(seed: str) -> list[PrimaryAssignment]:
    return [assignment_for_index(seed, index) for index in range(MAX_PRIMARY_ELIGIBLE)]


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
        claims = state.setdefault("claims", [])
        if len(claims) != eligible_index:
            raise RuntimeError("assignment ledger has a repeated or skipped slot")
        if eligible_index >= MAX_PRIMARY_ELIGIBLE:
            raise RuntimeError("primary eligible stopping threshold exceeded")
        assignment = assignment_for_index(seed, eligible_index)
        state["next_eligible_index"] = eligible_index + 1
        claims.append(
            {
                "eligible_index": assignment.eligible_index,
                "block_index": assignment.block_index,
                "slot": assignment.slot,
                "advisory_reliability": assignment.advisory_reliability,
                "source_condition": assignment.source_condition,
                "phase2_order": assignment.phase2_order,
                "pair_id": assignment.pair_id,
                "source_pair_key": assignment.source_pair_key,
                "assignment_order_key": assignment.assignment_order_key,
            }
        )
        stream.seek(0)
        stream.truncate()
        json.dump(state, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        return assignment
