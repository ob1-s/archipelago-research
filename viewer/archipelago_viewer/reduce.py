"""Deterministic reducer: ViewerEpisode -> ordered replay state snapshots.

The reducer is a pure function of the episode: same episode in, identical
JSON out.  It never invents trajectory facts — positions are purely
presentational (agents stand on a ring around the plaza, artifacts sit in
facility lots keyed by kind and stable hash), and every derived flag
(``spawn_after_teardown``, alive, counts) is computed from real events.

``reduce(episode) -> ReplayDocument`` where ``sequences[i]`` is the world
state after applying events ``0..i``.  The renderer draws only from these
snapshots, so rendering is deterministic from the normalized event stream.
"""

from __future__ import annotations

import json
import math
from typing import Any

from .schema import ViewerEpisode
from .util import NamedHash

# ----------------------------------------------------------------- layout

PLAZA = {"x": 500.0, "y": 350.0}
AGENT_RING_RADIUS = 205.0

FACILITIES: list[tuple[str, str, float, float]] = [
    ("note", "notes hall", 250.0, 205.0),
    ("resource", "resource depot", 750.0, 205.0),
    ("carrier", "carrier hub", 500.0, 115.0),
    ("provider_response", "provider gateway", 750.0, 495.0),
    ("artifact", "artifact workshop", 500.0, 585.0),
    ("seed", "seed archive", 250.0, 495.0),
    ("file", "file library", 335.0, 150.0),
    ("generic", "generic workshop", 665.0, 150.0),
]
_GENERIC = (500.0, 350.0)


def facility_position(kind: str, name: str) -> tuple[str, float, float]:
    """Deterministic facility slot for an artifact of ``kind`` (presentational)."""
    for slot_kind, label, x, y in FACILITIES:
        if slot_kind == kind:
            return label, x, y
    return "generic workshop", _GENERIC[0], _GENERIC[1]


def artifact_offset(kind: str, name: str) -> tuple[float, float]:
    h = NamedHash(kind or "artifact", name or "")
    return (h.unit() * 60.0 - 30.0, (h.int() % 1000) / 1000.0 * 60.0 - 30.0)


def agent_position(agent_ids: list[str], index: int, hue: float) -> tuple[float, float]:
    """Stable ring position for one agent (presentational)."""
    count = max(1, len(agent_ids))
    angle = (index / count) * math.tau + (hue / 360.0) * 0.35
    jitter = (NamedHash(agent_ids[index]).int() % 40) - 20
    return (
        PLAZA["x"] + (AGENT_RING_RADIUS + jitter) * math.cos(angle),
        PLAZA["y"] + (AGENT_RING_RADIUS + jitter) * math.sin(angle),
    )


# ----------------------------------------------------------------- state

def _snapshot(
    seq: int,
    t: float,
    agents: dict[str, dict[str, Any]],
    artifacts: dict[str, dict[str, Any]],
    carriers: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "seq": seq,
        "t": round(t, 3),
        "agents": {aid: dict(v) for aid, v in sorted(agents.items())},
        "artifacts": {aid: dict(v) for aid, v in sorted(artifacts.items())},
        "carriers": {cid: dict(v) for cid, v in sorted(carriers.items())},
    }


def reduce(episode: ViewerEpisode) -> dict[str, Any]:
    sorted_agents = sorted(episode.agents, key=lambda a: a.id)
    agents: dict[str, dict[str, Any]] = {}
    for index, agent in enumerate(sorted_agents):
        seed = agent.lineage_id or agent.id
        hue = (sum(ord(c) for c in seed) if seed else index * 53) % 360
        x, y = agent_position(
            [a.id for a in sorted_agents], index, hue
        )
        agents[agent.id] = {
            "x": round(x, 2),
            "y": round(y, 2),
            "hue": hue,
            "alive": agent.role in ("assistant", "actor", "controller"),
            "generation": agent.generation,
            "lineage_id": agent.lineage_id,
            "role": agent.role,
            "name": agent.name,
            "spawn_seq": -1,
            "death_seq": -1,
            "turnover_seq": -1,
            "tool_calls": 0,
            "artifact_reads": 0,
            "artifact_writes": 0,
            "carrier_events": 0,
            "last_kind": "",
            "last_title": "",
            "last_detail": "",
        }

    artifacts: dict[str, dict[str, Any]] = {}
    for artifact in episode.artifacts:
        label, fx, fy = facility_position(artifact.kind, artifact.name)
        dx, dy = artifact_offset(artifact.kind, artifact.name)
        artifacts[artifact.id] = {
            "x": round(fx + dx, 2),
            "y": round(fy + dy, 2),
            "kind": artifact.kind,
            "name": artifact.name,
            "live": artifact.created_at == -1,
            "created_seq": artifact.created_at,
            "owner_agent": artifact.agent_id,
            "facility": label,
        }

    carriers: dict[str, dict[str, Any]] = {}
    for carrier in episode.carriers:
        carriers[carrier.id] = {
            "active": False,
            "activated_seq": -1,
            "from": carrier.from_agent_id,
            "to": carrier.to_agent_id,
            "artifact_ids": list(carrier.artifact_ids),
            "kind": carrier.kind,
            "carrier_id": str(carrier.attributes.get("carrier_id", "")),
        }

    teardown_seqs: list[tuple[str, int]] = []
    sequences: list[dict[str, Any]] = []
    sequences.append(_snapshot(-1, 0.0, agents, artifacts, carriers))
    for event in episode.events:
        aid = event.agent_id
        if aid and aid in agents:
            state = agents[aid]
            state["last_kind"] = event.kind
            state["last_title"] = event.title
            state["last_detail"] = event.detail
            if event.kind == "tool_call":
                state["tool_calls"] += 1
            if event.kind in ("artifact_read", "carrier_read"):
                state["artifact_reads"] += 1
            if event.kind in ("artifact_write", "carrier_finalize"):
                state["artifact_writes"] += 1
            if event.kind.startswith("carrier_"):
                state["carrier_events"] += 1
        if event.kind == "spawn":
            target = agents.get(aid)
            if target is not None:
                target["alive"] = True
                target["spawn_seq"] = event.seq
                lineage = target.get("lineage_id", "")
                if lineage and any(
                    lc == lineage and s < event.seq for lc, s in teardown_seqs
                ):
                    target["turnover_seq"] = event.seq
        elif event.kind == "teardown":
            target = agents.get(aid)
            if target is not None:
                target["alive"] = False
                target["death_seq"] = event.seq
            teardown_seqs.append(
                (target.get("lineage_id", "") if target else "", event.seq)
            )
        elif event.kind in (
            "artifact_read",
            "artifact_write",
            "artifact_create",
            "artifact_delete",
        ):
            artifact = _match_artifact(event, artifacts)
            if artifact is not None:
                artifact["live"] = True
                if event.kind == "artifact_write" and artifact["created_seq"] == -1:
                    artifact["created_seq"] = event.seq
                    artifact["owner_agent"] = aid
                if event.kind == "artifact_delete":
                    artifact["live"] = False
        elif event.kind in ("carrier_finalize", "carrier_read"):
            record = event.payload.get("carrier_record") or {}
            carrier_id = record.get("carrier_id")
            for carrier in carriers.values():
                if carrier["carrier_id"] == carrier_id:
                    carrier["active"] = True
                    carrier["activated_seq"] = event.seq
        sequences.append(_snapshot(event.seq, event.t, agents, artifacts, carriers))

    if not episode.events:
        sequences = sequences[:1]
    duration = episode.events[-1].t if episode.events else 0.0
    return {
        "schema_version": "archipelago-viewer-replay/v1",
        "episode_id": episode.id,
        "duration": round(duration, 3),
        "event_count": len(episode.events),
        "plaza": PLAZA,
        "agent_ring_radius": AGENT_RING_RADIUS,
        "facilities": {
            label: {"kind": kind, "x": x, "y": y}
            for kind, label, x, y in FACILITIES
        },
        "sequences": sequences,
    }


def _match_artifact(
    event: Any, artifacts: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    """Resolve the artifact an event touches (payload id, else name key)."""
    artifact_id = event.payload.get("artifact_id")
    if artifact_id and artifact_id in artifacts:
        return artifacts[artifact_id]
    record = event.payload.get("record") or {}
    argument = str(record.get("argument") or "")
    if not argument:
        return None
    for candidate in artifacts.values():
        if candidate["name"] == argument:
            return candidate
    return None


def replay_json(episode: ViewerEpisode, document: dict[str, Any]) -> str:
    """Bundle episode + replay into one deterministic JSON document."""
    return json.dumps(
        {
            "schema_version": "archipelago-viewer-bundle/v1",
            "episode": episode.to_dict(),
            "replay": document,
        },
        sort_keys=True,
        separators=(",", ":"),
    )