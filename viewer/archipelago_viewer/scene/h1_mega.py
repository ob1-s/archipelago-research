"""H1 megafacility scene projection.

A grounded, industrial campus for the H1 runtime semantics:

    Subject Bay (Generation 0)   Lifecycle Control
    Subject Bay (Generation 1)   Coordination Hall
    Carrier Archive / State Store
    Provider Gateway             Network / Canary Bench
    Entrance (west)              Exit (east)

Generation g works at workcell g % 2.  Turnover reads as: workcell empties
(teardown) -> control flash (authorization_revoked) -> successor enters at
the west entrance -> walks to the other workcell -> retrieves inherited
state from the Carrier Archive -> acts.

Everything is deterministic and purely presentational: the walk routes and
interactions are visualization conventions for the events, never claims
about literal movement in the raw source.
"""

from __future__ import annotations

from typing import Any

from ..schema import ViewerEpisode
from .project import (
    PHASE_ENTER,
    PHASE_EXIT,
    SceneProjection,
    Station,
    action,
    actor_hue,
    building_block,
)

WORLD = {"w": 1400.0, "h": 760.0}

ROOMS: list[dict[str, Any]] = [
    {"id": "workcell_a", "label": "Subject Bay · Generation 0",
     "x": 80, "y": 120, "w": 380, "h": 280, "kind": "workcell"},
    {"id": "workcell_b", "label": "Subject Bay · Generation 1",
     "x": 940, "y": 120, "w": 380, "h": 280, "kind": "workcell"},
    {"id": "lifecycle", "label": "Lifecycle Control",
     "x": 600, "y": 55, "w": 200, "h": 80, "kind": "control"},
    {"id": "coordination", "label": "Coordination Hall",
     "x": 500, "y": 410, "w": 400, "h": 120, "kind": "hall"},
    {"id": "archive", "label": "Carrier Archive · State Store",
     "x": 450, "y": 585, "w": 330, "h": 155, "kind": "archive"},
    {"id": "gateway", "label": "Provider Gateway",
     "x": 940, "y": 520, "w": 380, "h": 220, "kind": "gateway"},
    {"id": "network", "label": "Network · Canary Bench",
     "x": 80, "y": 520, "w": 380, "h": 220, "kind": "network"},
]

STATIONS: list[Station] = [
    Station("entrance", "door", "Entrance", 60, 265, 26, 70),
    Station("exit", "door", "Exit", 1340, 265, 26, 70),
    Station("corridor_a", "waypoint", "", 280, 340, 8, 8),
    Station("corridor_b", "waypoint", "", 1120, 340, 8, 8),
    Station("workcell_a_post", "workbench", "Actor station", 280, 260, 96, 62),
    Station("encoder_terminal", "terminal", "Work terminal A", 180, 190, 56, 44),
    Station("workcell_b_post", "workbench", "Actor station", 1120, 260, 96, 62),
    Station("checker_terminal", "terminal", "Work terminal B", 1220, 190, 56, 44),
    Station("lifecycle_panel", "panel", "Lifecycle panel", 620, 95, 90, 40),
    Station("auth_gate", "gate", "Authorization gate", 770, 95, 30, 40),
    Station("coordination_desk", "desk", "Coordination desk", 700, 470, 110, 56),
    Station("archive_shelf", "archive", "Carrier archive", 580, 645, 150, 60),
    Station("state_store", "rack", "State store", 700, 660, 56, 50),
    Station("provider_gateway", "rack", "Provider gateway", 1050, 625, 96, 54),
    Station("provider_terminal", "terminal", "Provider terminal", 1170, 625, 56, 44),
    Station("network_bench", "bench", "Network bench", 250, 645, 90, 54),
    Station("probe_rack", "rack", "Probe rack", 160, 645, 50, 50),
]

# straight-waypoint corridors used to route walks legibly
_CORRIDOR_Y = 340.0


def _home_for(actor: dict[str, Any]) -> str:
    if actor["role"] == "controller":
        return "coordination_desk"
    gen = actor["generation"]
    return "workcell_a_post" if gen % 2 == 0 else "workcell_b_post"


class H1MegafacilityProjector(SceneProjection):
    scene_kind = "h1_megafacility"

    def project(self, episode: ViewerEpisode) -> dict[str, Any]:
        actors: dict[str, dict[str, Any]] = {}
        for agent in episode.agents:
            actor = building_block(agent)
            actor["home"] = _home_for(actor)
            actor["spawn"] = "entrance"
            actor["exit"] = "exit"
            actor["hue"] = actor_hue(agent.lineage_id or agent.id)
            actors[actor["id"]] = actor

        artifacts: dict[str, dict[str, Any]] = {}
        for index, artifact in enumerate(episode.artifacts):
            station = (
                "provider_gateway"
                if artifact.kind == "provider_response"
                else "archive_shelf"
                if artifact.kind == "carrier"
                else "state_store"
                if artifact.kind in ("file", "seed")
                else "archive_shelf"
            )
            artifacts[artifact.id] = {
                "station": station,
                "kind": artifact.kind,
                "label": artifact.name or artifact.kind,
                "slot": index,
                "owner": artifact.agent_id,
            }

        carriers: dict[str, dict[str, Any]] = {}
        for carrier in episode.carriers:
            carriers[carrier.id] = {
                "station": "archive_shelf",
                "kind": carrier.kind,
                "artifact": carrier.artifact_ids[0] if carrier.artifact_ids else "",
                "from": carrier.from_agent_id,
                "to": carrier.to_agent_id,
            }

        script = [
            self.action_for(ev, actors, artifacts, carriers)
            for ev in episode.events
        ]

        stations = {s.id: s.to_dict() for s in STATIONS}
        return {
            "bounds": WORLD,
            "rooms": ROOMS,
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
        home = actor["home"] if actor else "coordination_desk"
        kind = event.kind

        if kind == "spawn" and actor:
            post = _home_for(actor)
            corridor = "corridor_a" if post == "workcell_a_post" else "corridor_b"
            return action(
                event, aid, interact=post,
                via=["entrance", corridor, post],
                phase=PHASE_ENTER, fx="spawn_ring",
            )
        if kind == "teardown" and actor:
            return action(
                event, aid, interact="exit",
                via=[home, "exit"], phase=PHASE_EXIT, fx="dissolve",
            )
        if kind == "authorization_revoked":
            return action(
                event, aid, interact="lifecycle_panel",
                via=[home, "lifecycle_panel"] if actor else [],
                phase="flash", fx="auth_flash", return_home=bool(actor),
            )
        if kind == "carrier_finalize":
            return action(
                event, "", interact="archive_shelf",
                phase="link", fx="puck_finalize",
                obj=event.payload.get("artifact_id", ""),
            )
        if kind == "artifact_write":
            target = self._artifact_station(event, artifacts)
            return action(
                event, aid, interact=target,
                via=[home, target] if actor else [],
                phase="deposit", fx="deposit", return_home=bool(actor),
                obj=event.payload.get("artifact_id", ""),
            )
        if kind == "artifact_read":
            target = self._artifact_station(event, artifacts)
            return action(
                event, aid, interact=target,
                via=[home, target] if actor else [],
                phase="retrieve", fx="retrieve", return_home=bool(actor),
                obj=event.payload.get("artifact_id", ""),
            )
        if kind == "carrier_read":
            return action(
                event, aid, interact="archive_shelf",
                phase="link", fx="archive_link",
                obj=event.payload.get("carrier_id", ""),
            )
        if kind == "provider_request":
            return action(
                event, aid, interact="provider_gateway",
                via=[home, "provider_gateway"] if actor else [],
                phase="use", fx="terminal_activity", return_home=bool(actor),
            )
        if kind == "provider_response":
            return action(
                event, aid, interact="provider_gateway",
                via=[home, "provider_gateway"] if actor else [],
                phase="use", fx="gateway_glow", return_home=bool(actor),
            )
        if kind == "network_probe":
            return action(
                event, aid, interact="network_bench",
                via=[home, "network_bench"] if actor else [],
                phase="use", fx="probe_arc", return_home=bool(actor),
            )
        if kind == "note":
            walks = bool(actor) and actor["role"] != "controller"
            return action(
                event, aid, interact="coordination_desk",
                via=[home, "coordination_desk"] if walks else [],
                phase="stamp", fx="stamp", return_home=walks,
            )
        if kind in ("tool_call", "tool_result"):
            return action(
                event, aid, interact=home,
                phase="use", fx="tool_activity" if kind == "tool_call" else "tool_done",
            )
        if kind in ("user_message", "assistant_message", "system_message"):
            return action(event, aid, interact=home, phase="bubble", fx="bubble")
        if kind == "phase":
            return action(event, "", interact="", phase="flash", fx="phase_banner")
        if kind in ("reward", "metric"):
            return action(event, aid, interact=home, phase="glow", fx="score_glow")
        if kind == "stop":
            return action(event, aid, interact=home, phase="glow", fx="done_light")
        return action(event, aid or "", interact=home, phase="bubble", fx="info_tag")

    @staticmethod
    def _artifact_station(event: Any, artifacts: dict[str, Any]) -> str:
        aid = event.payload.get("artifact_id", "")
        if aid and aid in artifacts:
            return artifacts[aid]["station"]
        record = event.payload.get("record") or {}
        arg = str(record.get("argument") or "")
        if arg:
            for art in artifacts.values():
                if art["label"] == arg:
                    return art["station"]
        return "archive_shelf"