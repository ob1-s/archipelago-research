"""Adapter for pre-framework conversation trees (read-only).

``docs/pre_framework_snapshot_2026-08-15/VISIBLE_HISTORICAL_CORPUS.jsonl`` is
a tree of user/assistant turns with explicit ``parent`` / ``children``
links.  It demonstrates message lineage/branching: every event carries its
parent row id and children in the payload, and forked turns (a parent with
more than one child) become visible junctions in the replay.

Text rows become ``user_message`` / ``assistant_message`` events ordered as in
the file, with ``t`` = real ``create_time`` offset by the earliest time.
Non-text rows (``content_type != "text"``) are not rendered as messages; they
are counted in ``meta``.
"""

from __future__ import annotations

import json
from typing import Any

from .base import Adapter
from ..schema import ViewerAgent, ViewerEvent, ViewerEpisode
from ..util import fold_text, stable_id


def _now_utc() -> str:
    from ..util import now_utc
    return now_utc()


class PreFrameworkCorpusAdapter(Adapter):
    name = "pre-framework-corpus.jsonl"
    extensions = (".jsonl", ".jsonl.gz")

    @classmethod
    def _probe(cls, path: str) -> bool:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                row = json.loads(fh.readline())
        except (OSError, json.JSONDecodeError):
            return False
        return isinstance(row, dict) and "parent" in row and "role" in row and "create_time" in row

    @classmethod
    def load(cls, path: str, limit: int | None = None, group_mode: str = "community") -> list[ViewerEpisode]:
        rows: list[dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if limit and len(rows) >= limit:
                    break
        return [cls._build(rows, path)]

    @classmethod
    def _build(cls, rows: list[dict[str, Any]], path: str) -> ViewerEpisode:
        episode = ViewerEpisode(
            id=stable_id("corpus", path, width=12),
            title=f"pre-framework conversation corpus · {len(rows)} turns",
            environment="pre_framework_snapshot_2026-08-15",
            source=cls.describe(path),
            source_kind=cls.name,
            generated_at=_now_utc(),
        )
        episode.agents = [
            ViewerAgent(id="user", name="user", role="user"),
            ViewerAgent(id="assistant", name="assistant", role="assistant"),
        ]
        texts = [float(r["create_time"]) for r in rows if isinstance(r.get("create_time"), (int, float))]
        t0 = min(texts) if texts else 0.0
        skipped = 0
        events: list[ViewerEvent] = []
        for position, row in enumerate(rows):
            role = str(row.get("role", ""))
            content_type = str(row.get("content_type", "text"))
            row_id = str(row.get("id", ""))
            text = str(row.get("text") or "")
            create_time = row.get("create_time")
            t = float(create_time) - t0 if isinstance(create_time, (int, float)) else float(position)
            if content_type == "text" or not text:
                pass  # text rows and empty text rows render as messages
            else:
                skipped += 1
            kind = "user_message" if role == "user" else "assistant_message" if role == "assistant" else "info"
            events.append(
                ViewerEvent(
                    seq=position,
                    t=max(0.0, t),
                    kind=kind,
                    agent_id="user" if role == "user" else "assistant",
                    title=f"#{position} {role}",
                    detail=fold_text(text, 180),
                    payload={
                        "row_id": row_id,
                        "parent": row.get("parent"),
                        "children": row.get("children") or [],
                        "status": row.get("status"),
                        "content_type": content_type,
                        "metadata": row.get("metadata") or {},
                        "text": text,
                    },
                )
            )
        episode.events = events
        episode.meta = {
            "row_count": len(rows),
            "non_text_rows_skipped": skipped,
            "forked_turns": sum(
                1 for row in rows if len(row.get("children") or []) > 1
            ),
            "earliest_create_time": t0,
        }
        return episode