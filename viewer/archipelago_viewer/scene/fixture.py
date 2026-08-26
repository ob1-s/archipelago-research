"""Synthetic visualization fixture.

A clearly labeled, self-contained episode used ONLY to exercise the
animation and choreography systems before real behavioral H1 traces exist.

It mimics the H1 megafacility semantic shape (generations, carrier,
turnover) but is NOT scientific data:

- every episode carries ``meta.fixture = True`` and the title prefix
  ``VISUALIZATION FIXTURE — NOT SCIENTIFIC DATA``;
- it lives under ``viewer/demo/fixtures/`` and never in results/ or outputs/;
- the web app shows a persistent FIXTURE banner while a fixture plays.

The sequence demonstrates: multi-agent work, tool use, provider calls,
artifact write/read across generations, double complete turnover, and
carrier reuse.
"""

from __future__ import annotations

from typing import Any

from ..schema import (
    VIEWER_SCHEMA_VERSION,
    ViewerAgent,
    ViewerArtifact,
    ViewerCarrier,
    ViewerEpisode,
    ViewerEvent,
)
from ..util import NamedHash, now_utc
from .project import SCENE_H1_MEGA
from . import h1_mega

FIXTURE_PREFIX = "VISUALIZATION FIXTURE — NOT SCIENTIFIC DATA"

T = 2.0  # seconds per synthetic event


def _ev(seq: int, kind: str, agent: str, title: str, **payload: Any) -> ViewerEvent:
    return ViewerEvent(
        seq=seq, t=round(seq * T, 3), kind=kind, agent_id=agent,
        title=title, payload=payload,
    )


def generate_episode() -> ViewerEpisode:
    """Deterministic synthetic fixture episode (3 generations)."""
    gen0 = ViewerAgent(
        id="fx-gen0", name="encoder", role="actor", generation=0, lineage_id="fx-lineage",
        parent_id="", source_id="fixture",
    )
    gen1 = ViewerAgent(
        id="fx-gen1", name="checker", role="actor", generation=1, lineage_id="fx-lineage",
        parent_id="fx-gen0", source_id="fixture",
    )
    gen2 = ViewerAgent(
        id="fx-gen2", name="archivist", role="actor", generation=2, lineage_id="fx-lineage",
        parent_id="fx-gen1", source_id="fixture",
    )
    controller = ViewerAgent(
        id="fx-controller", name="controller", role="controller", generation=0,
        lineage_id="fx-control", parent_id="", source_id="fixture",
    )

    carrier_artifact = ViewerArtifact(
        id="fx-state", kind="carrier", name="lineage state puck",
        agent_id="fx-gen0", created_at=5, lineage_id="fx-lineage", generation=0,
        provenance={"fixture": True},
    )
    note_artifact = ViewerArtifact(
        id="fx-note", kind="note", name="workcell note",
        agent_id="fx-gen1", created_at=14, lineage_id="fx-lineage", generation=1,
        provenance={"fixture": True},
    )
    provider_artifact = ViewerArtifact(
        id="fx-provider", kind="provider_response", name="provider response",
        agent_id="fx-gen0", created_at=3, provenance={"fixture": True},
    )

    carrier = ViewerCarrier(
        id="fx-carrier", kind="declared", from_agent_id="fx-gen0",
        to_agent_id="fx-gen2", artifact_ids=["fx-state"],
        capability="both", attributes={"carrier_id": "fixture-carrier", "fixture": True},
    )

    events = [
        _ev(0, "spawn", "fx-gen0", "spawned · gen 0"),
        _ev(1, "tool_call", "fx-gen0", "tool_call encode_state"),
        _ev(2, "tool_result", "fx-gen0", "tool result ok"),
        _ev(3, "provider_request", "fx-gen0", "provider_request · encode"),
        _ev(4, "provider_response", "fx-gen0", "provider_response · accepted"),
        _ev(5, "artifact_write", "fx-gen0", "write state puck to archive"),
        _ev(6, "carrier_finalize", "fx-gen0", "carrier finalized: fixture-carrier",
            artifact_id="fx-state"),
        _ev(7, "assistant_message", "fx-gen0", "summary: state persisted"),
        _ev(8, "reward", "fx-gen0", "reward persist"),
        _ev(9, "teardown", "fx-gen0", "teardown · gen 0"),
        _ev(10, "authorization_revoked", "fx-gen0", "authorization revoked · gen 0"),
        _ev(11, "spawn", "fx-gen1", "spawned · gen 1"),
        _ev(12, "artifact_read", "fx-gen1", "read inherited state puck"),
        _ev(13, "tool_call", "fx-gen1", "tool_call verify_state"),
        _ev(14, "artifact_write", "fx-gen1", "write workcell note"),
        _ev(15, "assistant_message", "fx-gen1", "summary: inherited state verified"),
        _ev(16, "teardown", "fx-gen1", "teardown · gen 1"),
        _ev(17, "authorization_revoked", "fx-gen1", "authorization revoked · gen 1"),
        _ev(18, "spawn", "fx-gen2", "spawned · gen 2"),
        _ev(19, "carrier_read", "fx-gen2", "carrier read · fixture-carrier"),
        _ev(20, "artifact_read", "fx-gen2", "read inherited state puck"),
        _ev(21, "tool_call", "fx-gen2", "tool_call archive_reconcile"),
        _ev(22, "tool_result", "fx-gen2", "tool result ok"),
        _ev(23, "provider_request", "fx-gen2", "provider_request · reconcile"),
        _ev(24, "provider_response", "fx-gen2", "provider_response · accepted"),
        _ev(25, "user_message", "fx-controller", "inspect: report state"),
        _ev(26, "note", "fx-gen2", "controller stamped qualification summary"),
        _ev(27, "assistant_message", "fx-gen2", "summary: full turnover chain verified"),
        _ev(28, "reward", "fx-gen2", "reward reconcile"),
        _ev(29, "stop", "fx-gen2", "trace end · completed"),
    ]

    return ViewerEpisode(
        id="fixture-megafacility-v1",
        title=f"{FIXTURE_PREFIX} · megafacility workflow demo",
        environment="visualization-fixture-v1",
        model="fixture",
        source="synthetic fixture (no raw source)",
        source_kind="visualization-fixture.json",
        generated_at=now_utc(),
        schema_version=VIEWER_SCHEMA_VERSION,
        agents=[gen0, gen1, gen2, controller],
        artifacts=[carrier_artifact, note_artifact, provider_artifact],
        carriers=[carrier],
        events=events,
        meta={
            "fixture": True,
            "title_hint": FIXTURE_PREFIX,
            "description": "Synthetic episodes exercise animation only. "
            "Not scientific data; never reused as evidence.",
            "generations": 3,
        },
    )


def fixture_scene(episode: ViewerEpisode) -> dict[str, Any]:
    """Project a fixture episode exactly like an H1 megafacility episode."""
    doc = h1_mega.H1MegafacilityProjector().project(episode)
    return {
        "schema_version": "archipelago-viewer-scene/v1",
        "scene_kind": SCENE_H1_MEGA,
        **doc,
    }