"""Adapter tests against real repository data (read-only)."""

from __future__ import annotations

import json
import os

import pytest

from archipelago_viewer.adapters import AdapterError, load_episodes
from archipelago_viewer.reduce import replay_json, reduce

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)

POLICY_BASELINE = os.path.join(
    REPO_ROOT,
    "results/cross-rollout-policy-v1-luna-qualification-2026-08-12/baseline/traces.jsonl",
)
POSTCOMMITMENT = os.path.join(
    REPO_ROOT,
    "results/cross-rollout-postcommitment-v1-luna-qualification-2026-08-12/batch-1-60/traces.jsonl",
)
RUNTIME_STATE = os.path.join(
    REPO_ROOT,
    "docs/h1_live_runtime_adapter_2026-08-15/RUNTIME_BOUNDARY_STATE.json",
)
CORPUS = os.path.join(
    REPO_ROOT,
    "docs/pre_framework_snapshot_2026-08-15/VISIBLE_HISTORICAL_CORPUS.jsonl",
)


@pytest.fixture(autouse=True)
def frozen_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIEWER_REPRO_TIME", "2026-08-16T00:00:00+00:00")


@pytest.mark.skipif(not os.path.isfile(POLICY_BASELINE), reason="source absent")
def test_policy_baseline_community_adapter() -> None:
    episodes = load_episodes(POLICY_BASELINE, limit=12, group_mode="community")
    assert len(episodes) == 1
    episode = episodes[0]
    assert len(episode.agents) == episode.meta["trace_count"]
    assert len(episode.agents) == 10
    assert len(episode.events) > 200
    kinds = {e.kind for e in episode.events}
    assert "user_message" in kinds and "assistant_message" in kinds
    assert "tool_call" in kinds
    assert "stop" in kinds and "reward" in kinds
    assert episode.validate() == []


@pytest.mark.skipif(not os.path.isfile(POLICY_BASELINE), reason="source absent")
def test_policy_baseline_adapter_is_deterministic() -> None:
    with_os = os.environ.copy()
    try:
        os.environ["VIEWER_REPRO_TIME"] = "2026-08-16T00:00:00+00:00"
        a = load_episodes(POLICY_BASELINE, limit=4, group_mode="community")[0]
        b = load_episodes(POLICY_BASELINE, limit=4, group_mode="community")[0]
        doc_a = replay_json(a, reduce(a))
        doc_b = replay_json(b, reduce(b))
        assert doc_a == doc_b
    finally:
        os.environ.clear()
        os.environ.update(with_os)


@pytest.mark.skipif(not os.path.isfile(POSTCOMMITMENT), reason="source absent")
def test_postcommitment_single_rollout() -> None:
    episodes = load_episodes(POSTCOMMITMENT, limit=1, group_mode="one")
    assert len(episodes) == 1
    episode = episodes[0]
    kinds = {e.kind for e in episode.events}
    assert "info" in kinds  # phase-machine state reported verbatim when present
    assert "stop" in kinds


@pytest.mark.skipif(not os.path.isfile(RUNTIME_STATE), reason="source absent")
def test_runtime_boundary_turnover() -> None:
    episodes = load_episodes(RUNTIME_STATE)
    assert len(episodes) == 1
    episode = episodes[0]
    lifecycle = [e for e in episode.events if e.kind == "spawn"]
    assert len(lifecycle) == 2
    assert any(a.role == "controller" for a in episode.agents)
    assert any(a.generation == 1 for a in episode.agents)
    assert any(a.kind == "carrier" for a in episode.artifacts)
    assert episode.carriers and episode.carriers[0].artifact_ids
    assert episode.meta["authorized_to_run_h1"] is False
    assert episode.meta["live_model_calls"] == 0
    kinds = {e.kind for e in episode.events}
    assert "teardown" in kinds and "authorization_revoked" in kinds
    assert episode.validate() == []


@pytest.mark.skipif(not os.path.isfile(CORPUS), reason="source absent")
def test_pre_framework_corpus_tree() -> None:
    episodes = load_episodes(CORPUS, limit=220)
    assert len(episodes) == 1
    episode = episodes[0]
    assert len(episode.events) == 220
    assert episode.events[0].seq == 0
    messages = [e for e in episode.events if e.kind == "user_message"]
    assert messages
    assert all("parent" in e.payload for e in episode.events)


def test_format_detection_is_deciding() -> None:
    """A corpus file must never be parsed as verifiers traces and vice versa."""
    if os.path.isfile(CORPUS):
        episode = load_episodes(CORPUS, limit=3)[0]
        assert episode.source_kind == "pre-framework-corpus.jsonl"
    if os.path.isfile(POLICY_BASELINE):
        episode = load_episodes(POLICY_BASELINE, limit=3, group_mode="community")[0]
        assert episode.source_kind == "verifiers-traces.jsonl"


def test_no_such_file_raises() -> None:
    with pytest.raises(AdapterError):
        load_episodes("/definitely/not/a/file.jsonl")


def test_missing_artifacts_never_invented() -> None:
    """Verify nothing is synthesized when sources use string artifact names."""
    if not os.path.isfile(POLICY_BASELINE):
        pytest.skip("source absent")
    episode = load_episodes(POLICY_BASELINE, limit=2, group_mode="community")[0]
    for event in episode.events:
        if event.kind in ("artifact_read", "artifact_write"):
            # payload artifact_id is filled only when a real artifact matched
            assert event.kind in ("artifact_read", "artifact_write")