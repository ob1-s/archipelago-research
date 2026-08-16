"""Durable, append-only lifecycle event journal for the runtime controller.

The orchestrator commits every ``spawned``, ``teardown_complete``, and
``authorization_revoked`` transition to this SQLite journal *before* the
controller proceeds past that transition, so quantities a successor actor may
observe (a predecessor's teardown, its revoked authorization) are decided by
state that survives a controller restart.  The journal is a narrow audit
surface: rows are immutable once committed, the sequence is global and
strictly increasing, restart merely reopens the same file, and the journal
holds no secrets.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

from .models import LifecycleEvent

_EVENT_NAMES = ("spawned", "teardown_complete", "authorization_revoked")


class LifecycleJournal:
    """Append-only SQLite lifecycle event journal with FULL synchronous durability."""

    def __init__(self, path: Path | None = None) -> None:
        self._owned = path is None
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
    ) -> LifecycleEvent:
        """Append and durably commit one immutable event row.

        The row is committed before this method returns, so callers can
        proceed only after the transition is durable.  Returns the exact
        committed row as the typed model the evidence layer consumes.
        """
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


__all__ = ["LifecycleJournal"]