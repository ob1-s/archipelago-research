"""Parallel cells scene projection.

Independent verifiers rollouts never coexisted in one shared world, so they
must not be drawn as characters standing together in one facility.  Each
rollout gets its own isolated laboratory cell with a door, a bench, a
terminal and a notes shelf.  An agent works only inside its own cell; no
choreography ever references another cell (enforced by tests).

``group_mode="one"`` yields a single cell.  Community mode with N rollouts
yields an N-cell grid (columns bounded, rows grow downward).
"""

from __future__ import annotations

from typing import Any

from ..schema import ViewerEpisode
from .project import (
    PHASE_BUBBLE,
    PHASE_USE,
    SceneProjection,
    Station,
    action,
    actor_hue,
    building_block,
    stats,
)

CELL_W = 300.0
CELL_H = 300.0
GAP = 26.0
PAD = 30.0
MAX_COLS = 4


def _grid(n: int) -> tuple[int, int]:
    cols = min(MAX_COLS, n)
    rows = (n + cols - 1) // cols
    return cols, rows


def _cell_origin(index: int, cols: int) -> tuple[float, float]:
    col = index % cols
    row = index // cols
    return PAD + col * (CELL_W + GAP), PAD + 60 + row * (CELL_H + GAP)


class CellsProjector(SceneProjection):
    scene_kind = "parallel_cells"

    def project(self, episode: ViewerEpisode) -> dict[str, Any]:
        agents = sorted(episode.agents, key=lambda a: (a.generation, a.id))
        cols, _rows = _grid(max(1, len(agents)))

        rooms: list[dict[str, Any]] = []
        stations: dict[str, dict[str, Any]] = {}
        actors: dict[str, dict[str, Any]] = {}
        artifacts: dict[str, dict[str, Any]] = {}
        carriers: dict[str, dict[str, Any]] = {}

        for index, agent in enumerate(agents):
            ox, oy = _cell_origin(index, cols)
            cell_id = f"cell_{index}"
            rooms.append({
                "id": cell_id, "label": f"Cell {index + 1}",
                "x": ox, "y": oy, "w": CELL_W, "h": CELL_H, "kind": "cell",
            })

            def sid(name: str) -> str:
                return f"{cell_id}.{name}"

            door = Station(sid("door"), "door", f"rollout {index + 1}", ox + CELL_W / 2, oy - 12, 44, 16)
            bench = Station(sid("bench"), "workbench", "Rollout bench", ox + CELL_W * 0.42, oy + CELL_H * 0.42, 86, 56)
            terminal = Station(sid("terminal"), "terminal", "Terminal", ox + CELL_W * 0.80, oy + CELL_H * 0.30, 46, 34)
            shelf = Station(sid("notes_shelf"), "shelf", "Notes", ox + CELL_W * 0.18, oy + CELL_H * 0.72, 62, 40)
            lamp = Station(sid("lamp"), "lamp", "Status light", ox + CELL_W * 0.88, oy + CELL_H * 0.88, 16, 16)
            for s in (door, bench, terminal, shelf, lamp):
                stations[s.id] = s.to_dict()

            actor = building_block(agent)
            actor["home"] = bench.id
            actor["spawn"] = door.id
            actor["exit"] = door.id
            actor["cell"] = cell_id
            actor["hue"] = actor_hue(agent.lineage_id or agent.id)
            actors[agent.id] = actor

            cell_counts: dict[str, int] = {}
            for art in episode.artifacts:
                if art.agent_id == agent.id:
                    slot = cell_counts.get(cell_id, 0)
                    cell_counts[cell_id] = slot + 1
                    artifacts[art.id] = {
                        "station": shelf.id,
                        "kind": art.kind,
                        "label": art.name or art.kind,
                        "slot": slot,
                        "cell": cell_id,
                    }

        for carrier in episode.carriers:
            carriers[carrier.id] = {
                "station": "",
                "kind": carrier.kind,
                "artifact": carrier.artifact_ids[0] if carrier.artifact_ids else "",
                "from": carrier.from_agent_id,
                "to": carrier.to_agent_id,
            }

        script = [
            self.action_for(ev, actors, artifacts, carriers)
            for ev in episode.events
        ]

        n = max(1, len(agents))
        cols_n, rows_n = _grid(n)
        return {
            "bounds": {
                "w": PAD * 2 + cols_n * CELL_W + (cols_n - 1) * GAP,
                "h": PAD + 60 + rows_n * CELL_H + (rows_n - 1) * GAP + PAD,
            },
            "rooms": rooms,
            "stations": stations,
            "actors": actors,
            "artifacts": artifacts,
            "carriers": carriers,
            "script": script,
        }

    def action_for(
        self,
        event: Any,
        actors: dict[str, Any],
        artifacts: dict[str, Any],
        carriers: dict[str, Any],
    ) -> dict[str, Any]:
        aid = event.agent_id
        actor = actors.get(aid) if aid else None
        if not actor:
            return action(event, "", phase=PHASE_BUBBLE, fx="bubble")
        home = actor["home"]
        cell = actor["cell"]
        ns = f"{cell}.notes_shelf"
        term = f"{cell}.terminal"
        door = f"{cell}.door"
        kind = event.kind

        if kind == "spawn":
            return action(event, aid, interact=home, via=[door, home],
                          phase="enter", fx="spawn_ring")
        if kind == "teardown":
            return action(event, aid, interact=door, via=[home, door],
                          phase="exit", fx="dissolve")
        if kind == "authorization_revoked":
            return action(event, aid, interact=home,
                          phase="flash", fx="auth_flash")
        if kind == "artifact_write":
            return action(event, aid, interact=ns, via=[home, ns],
                          phase="deposit", fx="deposit", return_home=True,
                          obj=event.payload.get("artifact_id", ""))
        if kind == "artifact_read":
            return action(event, aid, interact=ns, via=[home, ns],
                          phase="retrieve", fx="retrieve", return_home=True,
                          obj=event.payload.get("artifact_id", ""))
        if kind in ("provider_request", "provider_response"):
            return action(event, aid, interact=term, via=[home, term],
                          phase=PHASE_USE, fx="terminal_activity" if kind == "provider_request" else "gateway_glow",
                          return_home=True)
        if kind == "tool_call":
            return action(event, aid, interact=term, via=[home, term],
                          phase=PHASE_USE, fx="tool_activity", return_home=True)
        if kind == "tool_result":
            return action(event, aid, interact=home, phase=PHASE_USE, fx="tool_done")
        if kind in ("user_message", "assistant_message", "system_message"):
            return action(event, aid, interact=home, phase="bubble", fx="bubble")
        if kind == "carrier_finalize":
            return action(event, aid, interact=ns, phase="link", fx="puck_finalize",
                          obj=event.payload.get("artifact_id", ""))
        if kind == "carrier_read":
            return action(event, aid, interact=ns, phase="link", fx="archive_link")
        if kind in ("reward", "metric"):
            return action(event, aid, interact=home, phase="glow", fx="score_glow")
        if kind == "stop":
            return action(event, aid, interact=home, phase="glow", fx="done_light")
        return action(event, aid, interact=home, phase="bubble", fx="info_tag")