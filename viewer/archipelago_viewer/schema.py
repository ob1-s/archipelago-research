"""Generic, read-only replay schema for Archipelago trajectory visualization.

Everything in this module is *derived* data.  The raw trace/archive remains
canonical evidence and the visual replay is never scientific evidence.  The
viewer never invents trajectory information: every payload attached to an
event is copied verbatim from the source, and every derived number is produced
by a documented, deterministic rule in an adapter or the reducer (see
``viewer/docs/ARCHITECTURE.md``).

The schema is deliberately small and extensible: it models agents, artifacts,
carriers, and a flat, globally ordered event stream with a seconds clock.
H1 runtime records (lifecycle events, carriers, signed actions, provider
traffic) map onto the same primitives as verifiers.v1 traces and
pre-framework conversation trees.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from typing import Any

VIEWER_SCHEMA_VERSION = "archipelago-viewer-episode/v1"

# Semantic groups for the UI (event log filters / coloring / icons).
EVENT_KINDS: dict[str, str] = {
    # messages
    "user_message": "message",
    "assistant_message": "message",
    "system_message": "message",
    "tool_message": "message",
    "reasoning_message": "message",
    # tool activity
    "tool_call": "tool",
    "tool_result": "tool",
    # runtime lifecycle / society dynamics
    "spawn": "lifecycle",
    "teardown": "lifecycle",
    "authorization_revoked": "lifecycle",
    "turnover": "lifecycle",
    "phase": "lifecycle",
    "provider_request": "provider",
    "provider_response": "provider",
    "network_probe": "provider",
    # artifacts
    "artifact_create": "artifact",
    "artifact_write": "artifact",
    "artifact_read": "artifact",
    "artifact_delete": "artifact",
    # carriers / state transfer
    "carrier_authorize": "carrier",
    "carrier_finalize": "carrier",
    "carrier_read": "carrier",
    "carrier_transfer": "carrier",
    # outcomes
    "reward": "outcome",
    "metric": "outcome",
    "stop": "outcome",
    "failure": "outcome",
    # generic
    "info": "info",
    "note": "info",
}


@dataclass
class ViewerAgent:
    """One agent-like participant in a replay (model actor, controller,
    runtime actor, or a backdrop role such as ``user``/``system``)."""

    id: str
    name: str = ""
    role: str = "assistant"  # assistant|controller|actor|user|system|backdrop
    lineage_id: str = ""
    generation: int = 0
    color: str = ""  # "" = reducer assigns deterministically from lineage
    source_id: str = ""  # id in the raw source (trace id, lifecycle id, ...)
    parent_id: str = ""  # lineage parent (previous generation agent id)
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ViewerAgent":
        return cls(**{k: v for k, v in data.items() if k in {f.name for f in dataclasses.fields(cls)}})


@dataclass
class ViewerArtifact:
    """A durable object agents read/write: notes, resources, provider
    responses, declared carriers, seeds, ..."""

    id: str
    kind: str = "artifact"  # note|resource|provider_response|carrier|seed|file|...
    name: str = ""
    agent_id: str = ""  # owning agent (creator / last writer), "" if none
    created_at: int = -1  # event seq of creation; -1 = already present
    content_preview: str = ""
    lineage_id: str = ""
    generation: int = 0
    provenance: dict[str, Any] = field(default_factory=dict)  # writer/parents/raw
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ViewerArtifact":
        return cls(**{k: v for k, v in data.items() if k in {f.name for f in dataclasses.fields(cls)}})


@dataclass
class ViewerCarrier:
    """A state-transfer relationship between agents and artifacts (declared
    carriers, backups, transmissions, provider transport)."""

    id: str
    kind: str = "declared"  # declared|backup|transmission|provider
    from_agent_id: str = ""
    to_agent_id: str = ""
    artifact_ids: list[str] = field(default_factory=list)
    capability: str = ""  # read|write|both|transport
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ViewerCarrier":
        return cls(**{k: v for k, v in data.items() if k in {f.name for f in dataclasses.fields(cls)}})


@dataclass
class ViewerEvent:
    """One atomic replay event in the global deterministic order.

    ``seq`` is the event index (0..n-1).  ``t`` is seconds since episode
    start; it comes from real source timestamps when the source has them,
    otherwise from a documented deterministic rule.  ``payload`` carries
    verbatim source data (never synthesized facts).
    """

    seq: int
    t: float
    kind: str
    agent_id: str = ""
    title: str = ""
    detail: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def group(self) -> str:
        return EVENT_KINDS.get(self.kind, "info")

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ViewerEvent":
        return cls(**{k: v for k, v in data.items() if k in {f.name for f in dataclasses.fields(cls)}})


@dataclass
class ViewerEpisode:
    """A complete replay: the normalized event stream plus entities."""

    id: str
    title: str
    environment: str = ""
    model: str = ""
    source: str = ""  # human description of the raw input
    source_kind: str = ""  # adapter name
    generated_at: str = ""  # UTC iso of conversion
    schema_version: str = VIEWER_SCHEMA_VERSION
    agents: list[ViewerAgent] = field(default_factory=list)
    artifacts: list[ViewerArtifact] = field(default_factory=list)
    carriers: list[ViewerCarrier] = field(default_factory=list)
    events: list[ViewerEvent] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------ serialization

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        return data

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ViewerEpisode":
        return cls(
            id=data["id"],
            title=data.get("title", data.get("id", "")),
            environment=data.get("environment", ""),
            model=data.get("model", ""),
            source=data.get("source", ""),
            source_kind=data.get("source_kind", ""),
            generated_at=data.get("generated_at", ""),
            schema_version=data.get("schema_version", VIEWER_SCHEMA_VERSION),
            agents=[ViewerAgent.from_dict(a) for a in data.get("agents", [])],
            artifacts=[
                ViewerArtifact.from_dict(a) for a in data.get("artifacts", [])
            ],
            carriers=[ViewerCarrier.from_dict(c) for c in data.get("carriers", [])],
            events=[ViewerEvent.from_dict(e) for e in data.get("events", [])],
            meta=data.get("meta", {}),
        )

    @classmethod
    def from_json(cls, text: str) -> "ViewerEpisode":
        return cls.from_dict(json.loads(text))

    # ---------------------------------------------------------------- helpers

    def agent(self, agent_id: str) -> ViewerAgent | None:
        for agent in self.agents:
            if agent.id == agent_id:
                return agent
        return None

    def artifact(self, artifact_id: str) -> ViewerArtifact | None:
        for artifact in self.artifacts:
            if artifact.id == artifact_id:
                return artifact
        return None

    def validate(self) -> list[str]:
        """Structural checks a viewer may rely on.  Returns problem strings."""
        problems: list[str] = []
        seqs = [e.seq for e in self.events]
        if seqs != list(range(len(seqs))):
            problems.append("events.seq must be contiguous 0..n-1")
        ids = [a.id for a in self.agents]
        if len(ids) != len(set(ids)):
            problems.append("duplicate agent id")
        ids = [a.id for a in self.artifacts]
        if len(ids) != len(set(ids)):
            problems.append("duplicate artifact id")
        for event in self.events:
            if event.kind not in EVENT_KINDS:
                problems.append(f"unknown event kind {event.kind!r}")
            if event.agent_id and not any(
                a.id == event.agent_id for a in self.agents
            ):
                problems.append(f"event references unknown agent {event.agent_id!r}")
        return problems