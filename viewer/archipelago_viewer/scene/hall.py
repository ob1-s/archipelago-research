"""Conversation hall scene projection.

Pre-framework corpus turn trees are a single conversation: two speakers at
a table with a shared screen.  The parent/children tree is preserved in the
event payload; the scene shows speaker bubbles and, while a message is
current, the child thread arcs dimmed on the screen.  No walk choreography:
speakers stay seated and "lean" (a deterministic sway) while talking.
"""

from __future__ import annotations

from typing import Any

from ..schema import ViewerEpisode
from .project import (
    PHASE_BUBBLE,
    PHASE_GLOW,
    SceneProjection,
    Station,
    action,
    actor_hue,
    building_block,
)

WORLD = {"w": 900.0, "h": 520.0}

ROOMS: list[dict[str, Any]] = [
    {"id": "studio", "label": "Conversation Studio",
     "x": 60, "y": 60, "w": 780, "h": 400, "kind": "studio"},
]

STATIONS: list[Station] = [
    Station("table", "table", "Shared table", 450, 300, 220, 90),
    Station("screen", "screen", "Thread screen", 450, 130, 300, 120),
    Station("seat_user", "seat", "User", 230, 300, 54, 54),
    Station("seat_assistant", "seat", "Assistant", 670, 300, 54, 54),
    Station("door", "door", "Studio door", 60, 300, 22, 60),
]


class HallProjector(SceneProjection):
    scene_kind = "conversation_hall"

    def project(self, episode: ViewerEpisode) -> dict[str, Any]:
        actors: dict[str, dict[str, Any]] = {}
        for agent in episode.agents:
            actor = building_block(agent)
            if agent.role == "user":
                seat = "seat_user"
            else:
                seat = "seat_assistant"
            actor["home"] = seat
            actor["spawn"] = seat
            actor["exit"] = "door"
            actor["hue"] = actor_hue(agent.lineage_id or agent.id)
            actors[agent.id] = actor

        script = [
            self.action_for(ev, actors, {}, {})
            for ev in episode.events
        ]
        stations = {s.id: s.to_dict() for s in STATIONS}
        return {
            "bounds": WORLD,
            "rooms": ROOMS,
            "stations": stations,
            "actors": actors,
            "artifacts": {},
            "carriers": {},
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
        home = actor["home"] if actor else "table"
        if event.kind == "spawn":
            return action(event, aid, interact=home, via=[home], phase="enter", fx="spawn_ring")
        if event.kind == "teardown":
            return action(event, aid, interact="door", via=[home, "door"], phase="exit", fx="dissolve")
        if event.kind in ("reward", "metric"):
            return action(event, aid, interact=home, phase=PHASE_GLOW, fx="score_glow")
        if event.kind == "stop":
            return action(event, aid, interact=home, phase=PHASE_GLOW, fx="done_light")
        return action(event, aid or "", interact=home, phase=PHASE_BUBBLE, fx="bubble")