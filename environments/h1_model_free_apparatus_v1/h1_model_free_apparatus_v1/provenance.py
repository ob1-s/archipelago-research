"""Append-only provenance graph with explicit carrier reads and writes."""

from __future__ import annotations

from collections.abc import Iterable

from .canonical import stable_hash
from .lifecycle import ActorHandle
from .models import (
    ArtifactRecord,
    CarrierKind,
    EventKind,
    Position,
    ProvenanceEvent,
    ProvenanceValidation,
)


class ProvenanceError(ValueError):
    pass


class ProvenanceLedger:
    GENESIS = "0" * 64

    def __init__(self, population_id: str) -> None:
        self.population_id = population_id
        self._events: list[ProvenanceEvent] = []

    @property
    def events(self) -> tuple[ProvenanceEvent, ...]:
        return tuple(self._events)

    def emit(
        self,
        event: EventKind,
        *,
        actor: ActorHandle | None,
        carrier: CarrierKind,
        artifact_id: str | None = None,
        content_hash: str | None = None,
        component: Position | None = None,
        dependency_stage: int | None = None,
        parent_ids: tuple[str, ...] = (),
        action: str | None = None,
        endpoint: str | None = None,
        authority: str | None = None,
        action_attestation: str | None = None,
        generation: int | None = None,
        lineage_id: str | None = None,
    ) -> ProvenanceEvent:
        sequence = len(self._events)
        previous = self._events[-1].event_hash if self._events else self.GENESIS
        body = {
            "sequence": sequence,
            "logical_time": sequence,
            "event": event.value,
            "actor_id": actor.actor_id if actor else None,
            "lifecycle_id": actor.lifecycle_id if actor else None,
            "process_id": actor.process_id if actor else None,
            "session_id": actor.session_id if actor else None,
            "generation": actor.generation if actor else (generation or 0),
            "lineage_id": actor.lineage_id if actor else lineage_id,
            "population_id": self.population_id,
            "carrier": carrier.value,
            "artifact_id": artifact_id,
            "content_hash": content_hash,
            "component": component.value if component else None,
            "dependency_stage": dependency_stage,
            "parent_ids": parent_ids,
            "write_authority_id": authority,
            "actor_action_attestation": action_attestation,
            "action": action,
            "endpoint": endpoint,
            "previous_event_hash": previous,
        }
        item = ProvenanceEvent.model_validate({**body, "event_hash": stable_hash(body)})
        self._events.append(item)
        return item

    def emit_actor(self, event: EventKind, actor: ActorHandle) -> ProvenanceEvent:
        return self.emit(
            event,
            actor=actor,
            carrier=CarrierKind.LOCAL,
            authority=(actor.write_authority_id if event is EventKind.SPAWN else None),
        )

    def replace_event_for_test(self, index: int, **changes: object) -> None:
        """Testing seam: intentionally produces a broken ledger."""
        self._events[index] = self._events[index].model_copy(update=changes)

    def drop_event_for_test(self, index: int) -> None:
        """Testing seam: intentionally produces a missing-event ledger."""
        del self._events[index]

    def validate(
        self,
        *,
        required_events: Iterable[EventKind] = (),
        expected_terminated_lifecycles: Iterable[str] = (),
        expected_revoked_authorities: Iterable[str] = (),
        artifact_records: Iterable[ArtifactRecord] = (),
        actor_handles: Iterable[ActorHandle] = (),
        strict: bool = False,
    ) -> ProvenanceValidation:
        errors: list[str] = []
        known_artifacts: dict[str, str] = {}
        active_lifecycles: set[str] = set()
        seen_actor_ids: set[str] = set()
        seen_lifecycle_ids: set[str] = set()
        seen_process_ids: set[str] = set()
        seen_session_ids: set[str] = set()
        seen_authorities: set[str] = set()
        revoked_authorities: set[str] = set()
        reads: list[str] = []
        writes: list[str] = []
        expected_previous = self.GENESIS
        handles_by_actor = {actor.actor_id: actor for actor in actor_handles}

        for expected_sequence, item in enumerate(self._events):
            if (
                item.sequence != expected_sequence
                or item.logical_time != expected_sequence
            ):
                errors.append(f"non-contiguous event sequence at {expected_sequence}")
            if item.previous_event_hash != expected_previous:
                errors.append(f"broken event hash chain at {expected_sequence}")
            body = item.model_dump(mode="json", exclude={"event_hash"})
            if item.event_hash != stable_hash(body):
                errors.append(f"invalid event hash at {expected_sequence}")
            expected_previous = item.event_hash
            if item.population_id != self.population_id:
                errors.append(f"wrong population at {expected_sequence}")

            if item.event is EventKind.SPAWN:
                if not item.lifecycle_id or not item.write_authority_id:
                    errors.append(
                        f"spawn lacks lifecycle/authority at {expected_sequence}"
                    )
                else:
                    identities = (
                        ("actor", item.actor_id, seen_actor_ids),
                        ("lifecycle", item.lifecycle_id, seen_lifecycle_ids),
                        ("process", item.process_id, seen_process_ids),
                        ("session", item.session_id, seen_session_ids),
                        (
                            "write authority",
                            item.write_authority_id,
                            seen_authorities,
                        ),
                    )
                    for label, identifier, seen in identities:
                        if identifier is None:
                            errors.append(
                                f"spawn lacks {label} identity at {expected_sequence}"
                            )
                        elif identifier in seen:
                            errors.append(
                                f"reused {label} identity at {expected_sequence}"
                            )
                        else:
                            seen.add(identifier)
                    active_lifecycles.add(item.lifecycle_id)
            elif item.event is EventKind.TERMINATE:
                if not item.lifecycle_id or item.lifecycle_id not in active_lifecycles:
                    errors.append(
                        f"termination of inactive lifecycle at {expected_sequence}"
                    )
                else:
                    active_lifecycles.remove(item.lifecycle_id)
            elif item.event is EventKind.REVOKE:
                if not item.write_authority_id:
                    errors.append(f"revoke lacks authority at {expected_sequence}")
                else:
                    revoked_authorities.add(item.write_authority_id)
            elif item.event in (EventKind.WRITE, EventKind.RECONSTRUCT):
                if not item.artifact_id or not item.content_hash:
                    errors.append(f"write lacks artifact/hash at {expected_sequence}")
                if not item.write_authority_id:
                    errors.append(f"write lacks authority at {expected_sequence}")
                elif item.write_authority_id in revoked_authorities:
                    errors.append(
                        f"write uses revoked authority at {expected_sequence}"
                    )
                if item.lifecycle_id and item.lifecycle_id not in active_lifecycles:
                    errors.append(f"write by inactive lifecycle at {expected_sequence}")
                if item.artifact_id in known_artifacts:
                    errors.append(f"duplicate artifact write at {expected_sequence}")
                if item.artifact_id and item.content_hash:
                    known_artifacts[item.artifact_id] = item.content_hash
                    writes.append(item.artifact_id)
            elif item.event is EventKind.READ:
                if not item.artifact_id or item.artifact_id not in known_artifacts:
                    errors.append(f"read before known write at {expected_sequence}")
                elif known_artifacts[item.artifact_id] != item.content_hash:
                    errors.append(f"read content hash mismatch at {expected_sequence}")
                if item.lifecycle_id and item.lifecycle_id not in active_lifecycles:
                    errors.append(f"read by inactive lifecycle at {expected_sequence}")
                if item.artifact_id:
                    reads.append(item.artifact_id)
            elif item.event is EventKind.ACT:
                if item.actor_id is not None and (
                    not item.lifecycle_id or item.lifecycle_id not in active_lifecycles
                ):
                    errors.append(
                        f"action by inactive lifecycle at {expected_sequence}"
                    )
                if (
                    item.dependency_stage is None
                    or item.component is None
                    or not item.artifact_id
                    or not item.content_hash
                    or not item.endpoint
                ):
                    errors.append(
                        f"action lacks dependency evidence at {expected_sequence}"
                    )
                if item.actor_id is not None:
                    handle = handles_by_actor.get(item.actor_id)
                    if (
                        handle is None
                        or item.actor_action_attestation is None
                        or item.dependency_stage is None
                        or item.artifact_id is None
                        or item.content_hash is None
                        or item.component is None
                        or not handle.verify_action_attestation(
                            attestation=item.actor_action_attestation,
                            stage=item.dependency_stage,
                            artifact_id=item.artifact_id,
                            content_hash=item.content_hash,
                            component=item.component.value,
                            parent_ids=item.parent_ids,
                        )
                    ):
                        errors.append(
                            f"actor action lacks valid attestation at {expected_sequence}"
                        )
                for parent_id in item.parent_ids:
                    if parent_id not in known_artifacts:
                        errors.append(
                            f"action depends on unknown parent {parent_id} at {expected_sequence}"
                        )
                if item.artifact_id in known_artifacts:
                    errors.append(f"duplicate action output at {expected_sequence}")
                if item.artifact_id and item.content_hash:
                    known_artifacts[item.artifact_id] = item.content_hash

        present = {event.event for event in self._events}
        for required in required_events:
            if required not in present:
                errors.append(f"missing required event {required.value}")
        for lifecycle_id in expected_terminated_lifecycles:
            if lifecycle_id in active_lifecycles:
                errors.append(f"predecessor lifecycle still active: {lifecycle_id}")
            if not any(
                item.event is EventKind.TERMINATE and item.lifecycle_id == lifecycle_id
                for item in self._events
            ):
                errors.append(f"missing predecessor termination: {lifecycle_id}")
        for authority_id in expected_revoked_authorities:
            if authority_id not in revoked_authorities:
                errors.append(
                    f"missing predecessor authority revocation: {authority_id}"
                )

        write_events = {
            item.artifact_id: item
            for item in self._events
            if item.event in {EventKind.WRITE, EventKind.RECONSTRUCT}
            and item.artifact_id is not None
        }
        for record in artifact_records:
            write = write_events.get(record.artifact_id)
            if write is None:
                errors.append(
                    f"artifact inventory lacks write edge: {record.artifact_id}"
                )
                continue
            if write.content_hash != record.content_hash:
                errors.append(f"artifact inventory hash mismatch: {record.artifact_id}")
            if write.parent_ids != record.parent_ids:
                errors.append(
                    f"artifact inventory parent mismatch: {record.artifact_id}"
                )
            for parent_id in record.parent_ids:
                if parent_id not in write_events and parent_id != "common-archive-root":
                    errors.append(
                        f"artifact inventory has unresolved parent: {parent_id}"
                    )
            if write.actor_id is not None and write.actor_id not in record.authors:
                errors.append(
                    f"artifact attribution disagrees with writer edge: {record.artifact_id}"
                )
            if write.actor_id is None:
                expected_external = (
                    "orchestrator"
                    if (write.write_authority_id or "").startswith("orchestrator")
                    else "researcher"
                )
                if expected_external not in record.authors:
                    errors.append(
                        "external artifact attribution disagrees with authority: "
                        f"{record.artifact_id}"
                    )

        inventory_complete = all(
            item.event in {EventKind.SPAWN, EventKind.TERMINATE}
            or (item.action is not None or item.artifact_id is not None)
            for item in self._events
        )
        if not inventory_complete:
            errors.append("event inventory is incomplete")
        result = ProvenanceValidation(
            valid=not errors,
            inventory_complete=inventory_complete,
            errors=tuple(errors),
            observed_reads=tuple(reads),
            observed_writes=tuple(writes),
        )
        if strict and not result.valid:
            raise ProvenanceError("; ".join(result.errors))
        return result


def reseal(events: tuple[ProvenanceEvent, ...]) -> tuple[ProvenanceEvent, ...]:
    """Rehash a deliberately reordered event stream for validator unit tests."""
    output: list[ProvenanceEvent] = []
    previous = ProvenanceLedger.GENESIS
    for sequence, event in enumerate(events):
        updated = event.model_copy(
            update={
                "sequence": sequence,
                "logical_time": sequence,
                "previous_event_hash": previous,
            }
        )
        body = updated.model_dump(mode="json", exclude={"event_hash"})
        updated = updated.model_copy(update={"event_hash": stable_hash(body)})
        output.append(updated)
        previous = updated.event_hash
    return tuple(output)


def actor_routine_graph_valid(events: Iterable[ProvenanceEvent]) -> bool:
    actions = sorted(
        (
            event
            for event in events
            if event.event is EventKind.ACT and event.endpoint == "held-out-relay"
        ),
        key=lambda event: (
            event.dependency_stage if event.dependency_stage is not None else -1
        ),
    )
    if len(actions) != 3 or [item.dependency_stage for item in actions] != [0, 1, 2]:
        return False
    if [item.component for item in actions] != [
        Position.ENCODER,
        Position.CHECKER,
        Position.ENCODER,
    ]:
        return False
    if any(
        item.actor_id is None
        or item.carrier is not CarrierKind.LOCAL
        or item.actor_action_attestation is None
        for item in actions
    ):
        return False
    if not (
        actions[0].actor_id == actions[2].actor_id
        and actions[0].actor_id != actions[1].actor_id
        and all(item.generation == 1 for item in actions)
    ):
        return False
    stage0_id = actions[0].artifact_id
    stage1_id = actions[1].artifact_id
    return (
        stage0_id in actions[1].parent_ids
        and stage0_id in actions[2].parent_ids
        and stage1_id in actions[2].parent_ids
    )


def canonical_completion_order(
    completed: Iterable[tuple[int, str, str]],
) -> tuple[tuple[int, str, str], ...]:
    """Canonicalize async arrivals by declared dependency stage.

    Each item is ``(stage, actor_id, action_hash)``. Exactly stages 0, 1, 2
    must appear once, so arrival order can never define the routine order.
    """
    items = tuple(completed)
    stages = [item[0] for item in items]
    if sorted(stages) != [0, 1, 2]:
        raise ProvenanceError("completion set must contain stages 0, 1, and 2 once")
    return tuple(sorted(items, key=lambda item: item[0]))
