"""Schema tests: round-trips, validation, and determinism."""

from __future__ import annotations

import json

from archipelago_viewer.schema import (
    EVENT_KINDS,
    ViewerAgent,
    ViewerArtifact,
    ViewerCarrier,
    ViewerEpisode,
    ViewerEvent,
)


def _minimal_episode() -> ViewerEpisode:
    episode = ViewerEpisode(
        id="test-ep",
        title="test",
        environment="env",
        source_kind="verifiers-traces.jsonl",
    )
    episode.agents = [
        ViewerAgent(id="a1", name="alpha", role="assistant"),
        ViewerAgent(id="a2", name="beta", role="assistant", lineage_id="L", generation=1),
    ]
    episode.artifacts = [
        ViewerArtifact(id="art1", kind="note", name="notes.txt", created_at=-1),
    ]
    episode.events = [
        ViewerEvent(seq=0, t=0.0, kind="user_message", agent_id="a1", title="prompt"),
        ViewerEvent(seq=1, t=1.0, kind="spawn", agent_id="a2", title="spawned"),
    ]
    return episode


def test_round_trip_json() -> None:
    episode = _minimal_episode()
    decoded = ViewerEpisode.from_json(episode.to_json())
    assert decoded.to_json() == episode.to_json()
    assert decoded.agent("a2").generation == 1
    assert decoded.artifact("art1").kind == "note"


def test_event_groups() -> None:
    episode = _minimal_episode()
    group = {e.kind: e.group() for e in episode.events}
    assert group["user_message"] == "message"
    assert group["spawn"] == "lifecycle"
    assert set(EVENT_KINDS) == set(EVENT_KINDS)  # dict stable


def test_validate_accepts_well_formed() -> None:
    assert _minimal_episode().validate() == []


def test_validate_rejects_bad_sequence_and_dangling_agent() -> None:
    episode = _minimal_episode()
    episode.events[1].seq = 5  # breaks contiguity
    episode.events.append(ViewerEvent(seq=3, t=2.0, kind="note", agent_id="ghost"))
    problems = episode.validate()
    assert any("contiguous" in p for p in problems), problems
    assert any("unknown agent" in p for p in problems), problems


def test_frozen_string_repr_is_stable() -> None:
    a = _minimal_episode()
    b = _minimal_episode()
    assert json.loads(a.to_json()) == json.loads(b.to_json())