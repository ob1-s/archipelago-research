"""Reducer tests: determinism and derived-flag semantics."""

from __future__ import annotations

import json

from archipelago_viewer.reduce import reduce, replay_json
from archipelago_viewer.schema import (
    ViewerAgent,
    ViewerArtifact,
    ViewerCarrier,
    ViewerEpisode,
    ViewerEvent,
)


def _turnover_episode() -> ViewerEpisode:
    episode = ViewerEpisode(id="turn", title="turnover", source_kind="test")
    episode.agents = [
        ViewerAgent(id="pred", name="predecessor", role="actor", lineage_id="L", generation=0),
        ViewerAgent(id="succ", name="successor", role="actor", lineage_id="L", generation=1),
    ]
    episode.artifacts = [
        ViewerArtifact(id="car1", kind="carrier", name="c-1", created_at=-1),
        ViewerArtifact(id="note1", kind="note", name="notes.txt", created_at=-1),
    ]
    episode.carriers = [
        ViewerCarrier(id="car", from_agent_id="pred", artifact_ids=["car1"],
                      attributes={"carrier_id": "c-1"}),
    ]
    episode.events = [
        ViewerEvent(seq=0, t=0.0, kind="spawn", agent_id="pred", title="spawn pred"),
        ViewerEvent(seq=1, t=1.0, kind="artifact_write", agent_id="pred",
                    title="write", payload={"artifact_id": "note1"}),
        ViewerEvent(seq=2, t=2.0, kind="teardown", agent_id="pred", title="teardown"),
        ViewerEvent(seq=3, t=3.0, kind="authorization_revoked", agent_id="pred"),
        ViewerEvent(seq=4, t=4.0, kind="spawn", agent_id="succ", title="spawn succ"),
        ViewerEvent(seq=5, t=5.0, kind="carrier_finalize",
                    payload={"carrier_record": {"carrier_id": "c-1"}}),
    ]
    return episode


def test_reduce_is_deterministic() -> None:
    episode = _turnover_episode()
    first = json.loads(replay_json(episode, reduce(episode)))
    second = json.loads(replay_json(episode, reduce(episode)))
    assert first == second


def test_reduce_positions_are_stable_across_processes() -> None:
    episode = _turnover_episode()
    doc_a = reduce(episode)
    doc_b = reduce(ViewerEpisode.from_json(episode.to_json()))
    assert doc_a["sequences"][-1]["agents"]["pred"]["x"] == doc_b["sequences"][-1]["agents"]["pred"]["x"]
    assert doc_a["sequences"][-1]["agents"]["pred"]["y"] == doc_b["sequences"][-1]["agents"]["pred"]["y"]


def test_turnover_flag_requires_predecessor_teardown() -> None:
    doc = reduce(_turnover_episode())
    states = {s["seq"]: s for s in doc["sequences"]}
    spawn_state = states[4]
    assert spawn_state["agents"]["succ"]["turnover_seq"] == 4
    assert states[1]["agents"]["pred"]["artifact_writes"] == 1
    assert states[4]["agents"]["pred"]["alive"] is False


def test_artifact_created_flag_from_write() -> None:
    episode = _turnover_episode()
    doc = reduce(episode)
    final = doc["sequences"][-1]
    assert final["artifacts"]["note1"]["created_seq"] == 1
    assert final["artifacts"]["note1"]["owner_agent"] == "pred"
    assert final["artifacts"]["car1"]["created_seq"] == -1  # pre-existing


def test_carrier_activation_from_finalize() -> None:
    doc = reduce(_turnover_episode())
    final = doc["sequences"][-1]
    assert final["carriers"]["car"]["active"] is True
    assert final["carriers"]["car"]["activated_seq"] == 5


def test_snapshot_count_matches_events() -> None:
    episode = _turnover_episode()
    doc = reduce(episode)
    assert len(doc["sequences"]) == len(episode.events) + 1


def test_scrubber_event_markers_align_with_snapshots() -> None:
    episode = _turnover_episode()
    doc = reduce(episode)
    # sequences[i] is the state AFTER events[0..i]
    for i, state in enumerate(doc["sequences"][1:], start=0):
        assert state["seq"] == i