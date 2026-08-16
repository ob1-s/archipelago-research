"""Scene projection: episode -> experiment-specific visual scene.

Pipeline:

    raw trace -> normalized episode -> scene projection -> choreographed replay

The episode schema is generic.  A *projection* decides, per environment,
where things live and what every event *means visually*:

- rooms/stations (layout)
- actor home/spawn/exit points
- artifact storage slots
- event -> choreographed action (routes, interaction station, effect)

The projection is a pure, deterministic function of the episode.  It never
invents scientific facts: actions are presentational conventions
(``walk to archive``, ``deposit puck``) that represent an event; the raw
event payload stays canonical and inspectable in the inspector.

Renderer contract: every action is a small deterministic script:

    actor walks the ``via`` stations (straight-waypoint tween)
    -> performs ``phase`` interaction at ``interact`` station
    -> if ``return_home``, walks back to its home station

Scene kinds:

- ``h1_megafacility``  H1 runtime boundary state (mechanical or behavioral)
- ``parallel_cells``   independent verifiers rollouts, each in its own cell
- ``conversation_hall`` pre-framework corpus turn trees as a conversation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..schema import ViewerEpisode
from ..util import NamedHash

SCENE_H1_MEGA = "h1_megafacility"
SCENE_CELLS = "parallel_cells"
SCENE_HALL = "conversation_hall"

SCENE_VERSION = "archipelago-viewer-scene/v1"

# event kinds grouped into coarse choreography families
PHASE_ENTER = "enter"       # walk in from spawn point, take post
PHASE_EXIT = "exit"         # leave/disappear at exit point
PHASE_DEPOSIT = "deposit"   # put object at station
PHASE_RETRIEVE = "retrieve" # take/inspect object at station
PHASE_USE = "use"           # operate a terminal/bench
PHASE_FLASH = "flash"       # alert effect at a control station
PHASE_LINK = "link"         # relationship/archive pulse (no walk)
PHASE_BUBBLE = "bubble"     # message / note in place
PHASE_STAMP = "stamp"       # controller action at desk
PHASE_GLOW = "glow"         # reward/metric/stop state change

_TYPICAL: dict[str, tuple[str, str]] = {  # kind -> (phase, fx)
    "spawn": (PHASE_ENTER, "spawn_ring"),
    "teardown": (PHASE_EXIT, "dissolve"),
    "authorization_revoked": (PHASE_FLASH, "auth_flash"),
    "carrier_finalize": (PHASE_LINK, "puck_finalize"),
    "artifact_write": (PHASE_DEPOSIT, "deposit"),
    "artifact_read": (PHASE_RETRIEVE, "retrieve"),
    "carrier_read": (PHASE_LINK, "archive_link"),
    "provider_request": (PHASE_USE, "terminal_activity"),
    "provider_response": (PHASE_USE, "gateway_glow"),
    "network_probe": (PHASE_USE, "probe_arc"),
    "tool_call": (PHASE_USE, "tool_activity"),
    "tool_result": (PHASE_USE, "tool_done"),
    "user_message": (PHASE_BUBBLE, "bubble"),
    "assistant_message": (PHASE_BUBBLE, "bubble"),
    "system_message": (PHASE_BUBBLE, "bubble"),
    "note": (PHASE_STAMP, "stamp"),
    "phase": (PHASE_FLASH, "phase_banner"),
    "reward": (PHASE_GLOW, "score_glow"),
    "metric": (PHASE_GLOW, "score_glow"),
    "stop": (PHASE_GLOW, "done_light"),
    "info": (PHASE_BUBBLE, "info_tag"),
}


@dataclass
class Station:
    id: str
    kind: str
    label: str
    x: float
    y: float
    w: float = 60.0
    h: float = 48.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "label": self.label,
            "x": round(self.x, 2), "y": round(self.y, 2),
            "w": round(self.w, 2), "h": round(self.h, 2),
        }


class SceneProjection:
    """Base class for environment-specific projections.

    Subclasses implement ``scene_kind``, ``project`` (layout + actor/artifact
    homes) and ``action_for`` (event -> action).  Everything must be a pure
    deterministic function of the episode.
    """

    scene_kind: str = ""

    def project(self, episode: ViewerEpisode) -> dict[str, Any]:
        raise NotImplementedError

    def action_for(
        self,
        event: Any,
        actors: dict[str, Any],
        artifacts: dict[str, Any],
        carriers: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError


def actor_hue(seed: str) -> int:
    if not seed:
        return 0
    h = NamedHash(seed)
    return h.int() % 360


def building_block(actor: Any) -> dict[str, Any]:
    """Common actor record fields (enriched by subclass layout)."""
    return {
        "id": actor.id,
        "role": actor.role,
        "generation": actor.generation,
        "lineage": actor.lineage_id,
        "parent": actor.parent_id,
        "label": actor.name or actor.role,
        "hue": actor_hue(actor.lineage_id or actor.id),
    }


def stats(action: dict[str, Any], event: Any) -> dict[str, Any]:
    """Attach event facts to an action for the inspector/tooltip."""
    action["i"] = event.seq
    action["kind"] = event.kind
    action["title"] = event.title
    action["t"] = round(event.t, 3)
    return action


def action(
    event: Any,
    actor_id: str = "",
    interact: str = "",
    via: list[str] | None = None,
    phase: str = "",
    fx: str = "",
    obj: str = "",
    return_home: bool = False,
    label: str = "",
) -> dict[str, Any]:
    """Build a choreographed action for one event (deterministic)."""
    if not phase and event.kind in _TYPICAL:
        phase, default_fx = _TYPICAL[event.kind]
        fx = fx or default_fx
    return stats(
        {
            "actor": actor_id,
            "phase": phase or PHASE_BUBBLE,
            "fx": fx or "bubble",
            "interact": interact,
            "via": list(via or []),
            "object": obj,
            "return_home": bool(return_home),
            "label": label or event.title,
        },
        event,
    )


def pick_scene(episode: ViewerEpisode) -> str:
    """Deterministic scene selection per source kind."""
    kind = episode.source_kind
    if episode.meta.get("fixture") is True:
        return SCENE_H1_MEGA
    if kind == "h1-runtime-boundary-state.json":
        return SCENE_H1_MEGA
    if kind == "pre-framework-corpus.jsonl":
        return SCENE_HALL
    return SCENE_CELLS  # verifiers traces + unknown sources


def project(episode: ViewerEpisode) -> dict[str, Any]:
    """Project an episode into its environment-specific scene document."""
    from . import cells, h1_mega, hall

    scene_kind = pick_scene(episode)
    projector = {
        SCENE_H1_MEGA: h1_mega.H1MegafacilityProjector(),
        SCENE_CELLS: cells.CellsProjector(),
        SCENE_HALL: hall.HallProjector(),
    }[scene_kind]
    doc = projector.project(episode)
    return {
        "schema_version": SCENE_VERSION,
        "scene_kind": scene_kind,
        **doc,
    }


def scene_doc(projector: SceneProjection, episode: ViewerEpisode) -> dict[str, Any]:
    return {
        "schema_version": SCENE_VERSION,
        "scene_kind": projector.scene_kind,
        **projector.project(episode),
    }