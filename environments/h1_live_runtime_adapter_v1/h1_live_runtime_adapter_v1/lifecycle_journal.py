"""Durable, append-only lifecycle event journal and lifecycle-validity predicates.

The orchestrator commits every ``spawned``, ``teardown_complete``, and
``authorization_revoked`` transition to this SQLite journal *before* the
controller proceeds past that transition, so quantities a successor actor may
observe (a predecessor's teardown, its revoked authorization) are decided by
state that survives a controller restart.  The journal is a narrow audit
surface: rows are immutable once committed, the sequence is global and
strictly increasing, restart merely reopens the same file, and the journal
holds no secrets.

This module is also the single home of the lifecycle-validity predicates the
runtime and the L0 verifier share.  ``lifecycle_chain_outcome`` decides whether
one frozen assignment's lifecycle chain is complete and exact, and
``teardown_evidence_complete`` decides whether returned teardown evidence
satisfies the qualified turnover conditions.  Successor admission, journal
validation, and boundary/L0 assessment all use these, so the runtime never
exposes a successor for state the verifier will later reject.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Literal

from .models import LifecycleEvent, TeardownEvidence

_EVENT_NAMES = ("spawned", "teardown_complete", "authorization_revoked")


LifecycleChainOutcome = Literal[
    "complete",
    "journal_sequence_invalid",
    "missing_spawn",
    "missing_teardown",
    "missing_revocation",
    "duplicate_event",
    "out_of_order",
    "mismatched_metadata",
]

_REQUIRED_EVENTS = {
    "spawned": "missing_spawn",
    "teardown_complete": "missing_teardown",
    "authorization_revoked": "missing_revocation",
}


def journal_events_match_assignments(
    events: tuple[LifecycleEvent, ...],
    assignments: tuple[tuple[str, str, str, str, int], ...],
) -> bool:
    """Reject journal rows outside the frozen schedule or repeated transitions."""

    sequences = [event.sequence for event in events]
    if len(sequences) != len(set(sequences)) or any(
        sequence != index for index, sequence in enumerate(sequences)
    ):
        return False
    expected = set(assignments)
    seen: set[tuple[str, str]] = set()
    events_by_lifecycle: dict[str, list[str]] = {}
    for event in events:
        identity = (
            event.lifecycle_id,
            event.attempt_id,
            event.actor_id,
            event.lineage_id,
            event.generation,
        )
        if identity not in expected:
            return False
        transition = (event.lifecycle_id, event.event)
        if transition in seen:
            return False
        seen.add(transition)
        events_by_lifecycle.setdefault(event.lifecycle_id, []).append(event.event)
    if any(
        event_names != list(_EVENT_NAMES[: len(event_names)])
        for event_names in events_by_lifecycle.values()
    ):
        return False
    return True


def lifecycle_chain_outcome(
    events: tuple[LifecycleEvent, ...],
    *,
    lifecycle_id: str,
    attempt_id: str,
    actor_id: str,
    lineage_id: str,
    generation: int,
) -> LifecycleChainOutcome:
    """Return the exact lifecycle-validity verdict for one frozen assignment.

    This is the shared authority for successor admission, journal validation,
    and L0 evidence assessment.  A complete chain for the frozen assignment is
    exactly one ``spawned`` row before one ``teardown_complete`` row before
    one ``authorization_revoked`` row, with every row bound to the frozen
    assignment's attempt/lifecycle/actor/lineage/generation identifiers and
    the global journal sequence contiguous.  Missing, duplicate, reordered,
    or mismatched rows yield a non-complete outcome (fail closed).
    """

    sequences = [event.sequence for event in events]
    if len(sequences) != len(set(sequences)) or any(
        sequence != index for index, sequence in enumerate(sequences)
    ):
        return "journal_sequence_invalid"
    rows = [event for event in events if event.lifecycle_id == lifecycle_id]
    if any(
        event.attempt_id != attempt_id
        or event.actor_id != actor_id
        or event.lineage_id != lineage_id
        or event.generation != generation
        for event in rows
    ):
        return "mismatched_metadata"
    by_event: dict[str, int] = {}
    for row in rows:
        if row.event in by_event:
            return "duplicate_event"
        by_event[row.event] = row.sequence
    for required, outcome in _REQUIRED_EVENTS.items():
        if required not in by_event:
            return outcome
    if not (
        by_event["spawned"]
        < by_event["teardown_complete"]
        < by_event["authorization_revoked"]
    ):
        return "out_of_order"
    return "complete"


def teardown_evidence_complete(
    evidence: TeardownEvidence,
    *,
    actor_id: str,
    lifecycle_id: str,
    expected_launcher_pid: int | None = None,
    expected_runtime_process_id: int | None = None,
) -> bool:
    """Whether teardown evidence satisfies the qualified turnover predicate.

    Mirrors exactly the conditions the boundary assessor already requires of
    every teardown record: identity correspondence with the frozen
    assignment, reaped process and process group, removed private root,
    invalidated actor-private signing key, and the qualified clean-return
    semantics.  The controller persists ``teardown_complete`` only when this
    predicate holds.
    """

    return (
        evidence.actor_id == actor_id
        and evidence.lifecycle_id == lifecycle_id
        and evidence.process_absent
        and evidence.process_group_absent
        and evidence.private_root_removed
        and evidence.key_invalidated
        and evidence.return_code == 0
        and (
            expected_launcher_pid is None
            or evidence.launcher_pid == expected_launcher_pid
        )
        and (
            expected_runtime_process_id is None
            or evidence.runtime_process_id == expected_runtime_process_id
        )
    )


class LifecycleJournal:
    """Append-only SQLite lifecycle journal with controller-only writes."""

    def __init__(self, path: Path | None = None) -> None:
        self._owned = path is None
        self._append_authority = object()
        if path is None:
            descriptor, raw_path = tempfile.mkstemp(
                prefix="h1-lifecycle-journal-", suffix=".sqlite", dir="/tmp"
            )
            os.close(descriptor)
            path = Path(raw_path)
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS lifecycle_events (
                sequence INTEGER PRIMARY KEY,
                lifecycle_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                lineage_id TEXT NOT NULL,
                generation INTEGER NOT NULL,
                event TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def append(
        self,
        *,
        lifecycle_id: str,
        actor_id: str,
        attempt_id: str,
        lineage_id: str,
        generation: int,
        event: str,
        _authority: object | None = None,
    ) -> LifecycleEvent:
        """Append and durably commit one immutable event row.

        The row is committed before this method returns, so callers can
        proceed only after the transition is durable.  Returns the exact
        committed row as the typed model the evidence layer consumes.  The
        append authority is intentionally not part of the public API.
        """
        if _authority is not self._append_authority:
            raise PermissionError(
                "lifecycle events can only be appended by the controller"
            )
        if event not in _EVENT_NAMES:
            raise ValueError(f"unknown lifecycle event: {event!r}")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row = self.connection.execute(
                "SELECT COALESCE(MAX(sequence), -1) FROM lifecycle_events"
            ).fetchone()
            sequence = int(row[0]) + 1
            self.connection.execute(
                """
                INSERT INTO lifecycle_events (
                    sequence, lifecycle_id, actor_id, attempt_id,
                    lineage_id, generation, event
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sequence,
                    lifecycle_id,
                    actor_id,
                    attempt_id,
                    lineage_id,
                    generation,
                    event,
                ),
            )
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise
        return LifecycleEvent(
            sequence=sequence,
            lifecycle_id=lifecycle_id,
            actor_id=actor_id,
            attempt_id=attempt_id,
            lineage_id=lineage_id,
            generation=generation,
            event=event,
        )

    def _append_controller_event(self, **kwargs: object) -> LifecycleEvent:
        """Append one event through the controller-owned authority."""

        return self.append(**kwargs, _authority=self._append_authority)

    def events(self) -> tuple[LifecycleEvent, ...]:
        """Return every committed row in global sequence order."""

        rows = self.connection.execute(
            """
            SELECT sequence, lifecycle_id, actor_id, attempt_id,
                   lineage_id, generation, event
            FROM lifecycle_events
            ORDER BY sequence
            """
        ).fetchall()
        return tuple(
            LifecycleEvent(
                sequence=int(row[0]),
                lifecycle_id=row[1],
                actor_id=row[2],
                attempt_id=row[3],
                lineage_id=row[4],
                generation=int(row[5]),
                event=row[6],
            )
            for row in rows
        )

    def close(self) -> None:
        self.connection.close()


__all__ = [
    "LifecycleJournal",
    "LifecycleChainOutcome",
    "journal_events_match_assignments",
    "lifecycle_chain_outcome",
    "teardown_evidence_complete",
]
