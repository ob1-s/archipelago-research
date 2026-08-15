"""Auditable deterministic actor lifecycle and authority invalidation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .canonical import stable_hash


class InvalidHandleError(RuntimeError):
    """Raised when terminated actor state or authority is reused."""


@dataclass
class ActorHandle:
    actor_id: str
    lifecycle_id: str
    process_id: str
    session_id: str
    write_authority_id: str
    lineage_id: str
    generation: int
    position: str
    _active: bool = True
    _authority_active: bool = True
    reactivation_attempted: bool = False
    authority_reactivation_attempted: bool = False
    local_memory: dict[str, Any] = field(default_factory=dict)
    _action_secret: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._action_secret = stable_hash(
            {
                "domain": "model-free-actor-action-attestation/v1",
                "actor_id": self.actor_id,
                "lifecycle_id": self.lifecycle_id,
                "process_id": self.process_id,
                "session_id": self.session_id,
            }
        )

    @property
    def active(self) -> bool:
        return self._active

    @active.setter
    def active(self, value: bool) -> None:
        if value and not self._active:
            self.reactivation_attempted = True
        self._active = value

    @property
    def authority_active(self) -> bool:
        return self._authority_active

    @authority_active.setter
    def authority_active(self, value: bool) -> None:
        if value and not self._authority_active:
            self.authority_reactivation_attempted = True
        self._authority_active = value

    def assert_active(self) -> None:
        if not self.active:
            raise InvalidHandleError(f"actor handle {self.lifecycle_id} is terminated")

    def assert_can_write(self) -> None:
        self.assert_active()
        if not self.authority_active:
            raise InvalidHandleError(
                f"write authority {self.write_authority_id} is revoked"
            )

    def remember(self, key: str, value: Any) -> None:
        self.assert_active()
        self.local_memory[key] = value

    def recall(self, key: str) -> Any:
        self.assert_active()
        return self.local_memory[key]

    def terminate(self) -> None:
        self.assert_active()
        self.local_memory.clear()
        self._authority_active = False
        self._active = False

    def attest_action(
        self,
        *,
        stage: int,
        artifact_id: str,
        content_hash: str,
        component: str,
        parent_ids: tuple[str, ...],
    ) -> str:
        self.assert_active()
        return stable_hash(
            {
                "secret": self._action_secret,
                "actor_id": self.actor_id,
                "stage": stage,
                "artifact_id": artifact_id,
                "content_hash": content_hash,
                "component": component,
                "parent_ids": parent_ids,
            }
        )

    def verify_action_attestation(
        self,
        *,
        attestation: str,
        stage: int,
        artifact_id: str,
        content_hash: str,
        component: str,
        parent_ids: tuple[str, ...],
    ) -> bool:
        expected = stable_hash(
            {
                "secret": self._action_secret,
                "actor_id": self.actor_id,
                "stage": stage,
                "artifact_id": artifact_id,
                "content_hash": content_hash,
                "component": component,
                "parent_ids": parent_ids,
            }
        )
        return attestation == expected


class LifecycleRegistry:
    """Generates stable IDs and keeps old handles invalid after turnover."""

    def __init__(self, population_id: str) -> None:
        self.population_id = population_id
        self._counter = 0
        self._actors: dict[str, ActorHandle] = {}

    def spawn(self, *, lineage_id: str, generation: int, position: str) -> ActorHandle:
        self._counter += 1
        stem = f"{self.population_id}-g{generation}-{position}-{self._counter}"
        actor = ActorHandle(
            actor_id=f"actor-{stem}",
            lifecycle_id=f"life-{stem}",
            process_id=f"proc-{stem}",
            session_id=f"session-{stem}",
            write_authority_id=f"write-{stem}",
            lineage_id=lineage_id,
            generation=generation,
            position=position,
        )
        self._actors[actor.actor_id] = actor
        return actor

    def terminate(self, actor: ActorHandle) -> None:
        if self._actors.get(actor.actor_id) is not actor:
            raise InvalidHandleError(f"unknown actor {actor.actor_id}")
        actor.terminate()

    @property
    def actors(self) -> tuple[ActorHandle, ...]:
        return tuple(self._actors.values())

    @property
    def active(self) -> tuple[ActorHandle, ...]:
        return tuple(actor for actor in self._actors.values() if actor.active)

    def assert_complete_turnover(self, predecessor_generation: int = 0) -> bool:
        predecessors = [
            actor
            for actor in self._actors.values()
            if actor.generation == predecessor_generation
        ]
        return bool(predecessors) and all(
            not actor.active
            and not actor.authority_active
            and not actor.local_memory
            and not actor.reactivation_attempted
            and not actor.authority_reactivation_attempted
            for actor in predecessors
        )
