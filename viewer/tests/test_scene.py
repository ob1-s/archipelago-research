"""Scene projection tests: selection, determinism, topology honesty,
event->choreography mapping, turnover, fixture labeling, playback timing."""

from __future__ import annotations

import json
import os

import pytest

from archipelago_viewer.adapters import load_episodes
from archipelago_viewer.reduce import reduce, replay_json
from archipelago_viewer.scene import (
    SCENE_CELLS,
    SCENE_H1_MEGA,
    SCENE_HALL,
    pick_scene,
    project,
)
from archipelago_viewer.scene.fixture import FIXTURE_PREFIX, generate_episode
from archipelago_viewer.schema import (
    ViewerAgent,
    ViewerEpisode,
    ViewerEvent,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
POLICY_BASELINE = os.path.join(
    REPO_ROOT,
    "results/cross-rollout-policy-v1-luna-qualification-2026-08-12/baseline/traces.jsonl",
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


def _episode(source_kind: str, **extra: object) -> ViewerEpisode:
    return ViewerEpisode(
        id="test-ep", title="t", source_kind=source_kind,
        agents=[ViewerAgent(id="a", role="assistant")],
        events=[ViewerEvent(seq=0, t=0.0, kind="stop")],
        meta={},
        **extra,
    )


# ------------------------------------------------ scene selection


def test_pick_scene_kind_mapping() -> None:
    assert pick_scene(_episode("h1-runtime-boundary-state.json")) == SCENE_H1_MEGA
    assert pick_scene(_episode("verifiers-traces.jsonl")) == SCENE_CELLS
    assert pick_scene(_episode("pre-framework-corpus.jsonl")) == SCENE_HALL
    assert pick_scene(_episode("unknown-format.jsonl")) == SCENE_CELLS


def test_fixture_always_projects_to_megafacility() -> None:
    episode = generate_episode()
    assert pick_scene(episode) == SCENE_H1_MEGA
    assert episode.meta.get("fixture") is True


# ------------------------------------------------ determinism


@pytest.mark.skipif(
    not os.path.isfile(RUNTIME_STATE), reason="source absent"
)
def test_h1_scene_projection_is_deterministic() -> None:
    episode = load_episodes(RUNTIME_STATE)[0]
    a = project(episode)
    b = project(episode)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


@pytest.mark.skipif(
    not os.path.isfile(POLICY_BASELINE), reason="source absent"
)
def test_cells_scene_projection_is_deterministic() -> None:
    episode = load_episodes(POLICY_BASELINE, limit=12, group_mode="community")[0]
    a = project(episode)
    b = project(episode)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_fixture_scene_projection_is_deterministic() -> None:
    a = project(generate_episode())
    b = project(generate_episode())
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ------------------------------------------------ no topology conflation


def _cell_of(station_id: str) -> str:
    return station_id.split(".")[0] if "." in station_id else station_id


@pytest.mark.skipif(
    not os.path.isfile(POLICY_BASELINE), reason="source absent"
)
def test_cells_never_conflate_independent_rollouts() -> None:
    """Actions of one rollout must never reference another cell."""
    episode = load_episodes(POLICY_BASELINE, limit=12, group_mode="community")[0]
    scene = project(episode)
    assert scene["scene_kind"] == SCENE_CELLS
    cells = {a["cell"] for a in scene["actors"].values()}
    assert len(cells) == len(episode.agents)  # one isolated cell per rollout
    for act in scene["script"]:
        actor_cell = scene["actors"].get(act["actor"], {}).get("cell")
        for sid in [act["interact"]] + act["via"]:
            if not sid:
                continue
            assert _cell_of(sid) == (actor_cell or _cell_of(sid)), (
                f"{act['i']} {act['kind']} escapes its cell via {sid}"
            )


@pytest.mark.skipif(
    not os.path.isfile(POLICY_BASELINE), reason="source absent"
)
def test_cells_artifacts_stay_in_owner_cell() -> None:
    episode = load_episodes(POLICY_BASELINE, limit=6, group_mode="community")[0]
    scene = project(episode)
    for art in scene["artifacts"].values():
        owner = scene["actors"].get(art.get("owner", ""), {}).get("cell")
        if owner:
            assert _cell_of(art["station"]) == owner


def test_single_rollout_is_single_cell() -> None:
    episode = _episode("verifiers-traces.jsonl")
    scene = project(episode)
    assert scene["scene_kind"] == SCENE_CELLS
    assert len(scene["actors"]) == 1


# ------------------------------------------------ h1 choreography


@pytest.mark.skipif(
    not os.path.isfile(RUNTIME_STATE), reason="source absent"
)
def test_h1_event_to_choreography_mapping() -> None:
    episode = load_episodes(RUNTIME_STATE)[0]
    scene = project(episode)
    by_kind: dict[str, list[dict]] = {}
    for act in scene["script"]:
        by_kind.setdefault(act["kind"], []).append(act)
    assert by_kind["spawn"][0]["phase"] == "enter"
    assert by_kind["teardown"][0]["phase"] == "exit"
    assert by_kind["authorization_revoked"][0]["fx"] == "auth_flash"
    assert by_kind["carrier_finalize"][0]["phase"] == "link"
    assert by_kind["artifact_write"][0]["phase"] == "deposit"
    assert by_kind["artifact_read"][0]["phase"] == "retrieve"
    assert by_kind["carrier_read"][0]["fx"] == "archive_link"
    assert by_kind["provider_request"][0]["interact"] == "provider_gateway"
    # every event got a script entry in order
    assert [a["i"] for a in scene["script"]] == list(range(len(episode.events)))
    # no unknown choreography family silently
    known = {"enter", "exit", "deposit", "retrieve", "use", "flash",
             "link", "bubble", "stamp", "glow"}
    for act in scene["script"]:
        assert act["phase"] in known, act


@pytest.mark.skipif(
    not os.path.isfile(RUNTIME_STATE), reason="source absent"
)
def test_h1_turnover_sequence_and_workcell_swap() -> None:
    episode = load_episodes(RUNTIME_STATE)[0]
    scene = project(episode)
    gen0 = "b56c4ccf70"
    gen1 = "8965191b7a"
    assert scene["actors"][gen0]["home"] == "workcell_a_post"
    assert scene["actors"][gen1]["home"] == "workcell_b_post"
    spawns = [a for a in scene["script"] if a["kind"] == "spawn"]
    teardowns = [a for a in scene["script"] if a["kind"] == "teardown"]
    assert [spawns[0]["actor"], teardowns[0]["actor"]] == [gen0, gen0]
    assert [teardowns[1]["actor"], spawns[1]["actor"]] == [gen1, gen1]
    # carrier artifact lives in the archive for the whole run
    for art in scene["artifacts"].values():
        if art["kind"] == "carrier":
            assert art["station"] == "archive_shelf"


def test_fixture_double_turnover_is_visible() -> None:
    episode = generate_episode()
    scene = project(episode)
    gen_sequence = [
        a["actor"] for a in scene["script"]
        if a["kind"] in ("teardown", "spawn")
    ]
    assert "fx-gen0" in gen_sequence and "fx-gen1" in gen_sequence
    assert "fx-gen2" in gen_sequence
    i = gen_sequence.index("fx-gen0")
    assert gen_sequence[i + 1] == "fx-gen0"  # spawn, teardown
    # carrier read after gen-2 spawn: keeper event present
    kinds = [a["kind"] for a in scene["script"]]
    assert kinds.index("carrier_read") > kinds.index("artifact_read")


# ------------------------------------------------ fixture labeling


def test_fixture_is_unmistakably_labeled() -> None:
    episode = generate_episode()
    assert episode.title.startswith(FIXTURE_PREFIX)
    assert episode.meta["fixture"] is True
    assert episode.source_kind == "visualization-fixture.json"


def test_bundle_scene_is_embedded_and_deterministic() -> None:
    episode = generate_episode()
    scene = project(episode)
    doc_a = json.loads(replay_json(episode, reduce(episode), scene))
    doc_b = json.loads(replay_json(episode, reduce(episode), project(episode)))
    assert doc_a["schema_version"] == "archipelago-viewer-bundle/v2"
    assert len(doc_a["scene"]["script"]) == len(episode.events)
    assert doc_a == doc_b


# ------------------------------------------------ playback timing regression


def advance(pos: float, dt: float, rate: float, n_events: int) -> float:
    """Fixed playback advance (mirrors the JS renderer logic)."""
    pos += dt * rate
    return max(0.0, min(float(n_events - 1), pos))


def test_playback_advance_is_linear_not_quadratic() -> None:
    """v1 bug: dt accumulated since start on every tick -> quadratic speedup.

    Equal wall-time windows must produce equal event-index advances."""
    pos = 0.0
    first = advance(pos, 0.1, 9.0, 500) - pos
    pos = first
    second = advance(pos, 0.1, 9.0, 500) - pos
    assert first == pytest.approx(0.9)
    assert second == pytest.approx(0.9)  # == first, not growing


def test_playback_advance_clamps_at_bounds() -> None:
    assert advance(0.0, -1.0, 9.0, 500) == 0.0
    assert advance(499.5, 1.0, 9.0, 500) == 499.0


# ------------------------------------------------- corpus scene


@pytest.mark.skipif(
    not os.path.isfile(CORPUS), reason="source absent"
)
def test_corpus_projects_to_hall_with_seats() -> None:
    episode = load_episodes(CORPUS, limit=60)[0]
    scene = project(episode)
    assert scene["scene_kind"] == SCENE_HALL
    seats = {s["id"] for s in scene["stations"].values()}
    assert "seat_user" in seats and "seat_assistant" in seats
    for act in scene["script"]:
        if act["actor"]:
            assert act["phase"] in ("enter", "bubble", "glow", "exit")