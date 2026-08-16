"""Outcome-blind lifecycle controller for the mechanical runtime boundary.

The orchestrator is deliberately a small control plane.  A frozen schedule is
the only source of actor assignments; starting an actor takes only an opaque
attempt identifier and therefore cannot inject new actor-visible content.  The
controller can launch and reap Bubblewrap actors, verify signatures, and
return already-finalized carrier metadata.  It has no provider/model transport,
output computation, state transformation, action-signing, or session-resume
API.

This module is infrastructure evidence, not an H1 experiment runner.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any, Literal

from pydantic import Field, model_validator

from .attribution import ActionRegistry
from .canonical import canonical_bytes, sha256_bytes, stable_hash
from .carrier import DeclaredCarrierStore, carrier_read_binding
from .isolation import BubblewrapActorFactory, IsolatedActor
from .models import (
    ActorRuntimeRecord,
    ActorSpec,
    CarrierCapability,
    CarrierRecord,
    SignedAction,
    StrictModel,
    TeardownEvidence,
)
from .models import ProviderPolicy
from .provider import ProviderGateway


_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _canonical_json_object(value: str, *, field: str) -> dict[str, Any]:
    """Validate a JSON object is already in the adapter's canonical form."""

    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field} must contain valid JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError(f"{field} must encode a JSON object")
    if canonical_bytes(decoded).decode() != value:
        raise ValueError(f"{field} must be canonical JSON")
    return decoded


def _canonical_json_array(value: str, *, field: str) -> list[Any]:
    """Validate a JSON array is already in the adapter's canonical form."""

    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field} must contain valid JSON") from exc
    if not isinstance(decoded, list):
        raise ValueError(f"{field} must encode a JSON array")
    if canonical_bytes(decoded).decode() != value:
        raise ValueError(f"{field} must be canonical JSON")
    return decoded


class FrozenCommonConfig(StrictModel):
    """An immutable, hash-addressed common prior/configuration blob."""

    config_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    config_version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    content_json: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def from_mapping(
        cls,
        *,
        config_id: str,
        config_version: str,
        content: dict[str, Any],
    ) -> "FrozenCommonConfig":
        content_json = canonical_bytes(content).decode()
        return cls(
            config_id=config_id,
            config_version=config_version,
            content_json=content_json,
            content_hash=sha256_bytes(content_json.encode()),
        )

    @property
    def content_bytes(self) -> bytes:
        """Return the exact predeclared bytes; no reconstruction is performed."""

        return self.content_json.encode()

    @property
    def semantic_payload(self) -> dict[str, str]:
        return {
            "config_id": self.config_id,
            "config_version": self.config_version,
            "content_hash": self.content_hash,
        }

    @model_validator(mode="after")
    def validate_config(self) -> "FrozenCommonConfig":
        _canonical_json_object(self.content_json, field="content_json")
        if self.content_hash != sha256_bytes(self.content_json.encode()):
            raise ValueError("content_hash must be a lowercase SHA-256 digest")
        return self


class FrozenAssignment(StrictModel):
    """One predeclared, output-blind actor assignment."""

    attempt_id: str
    actor_spec: ActorSpec
    input_json: str
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    instructions: str | None = None
    common_config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    declared_carrier_ids: tuple[str, ...] = ()
    carrier_capabilities: tuple[CarrierCapability, ...] = ()
    assignment_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def from_input(
        cls,
        *,
        attempt_id: str,
        actor_spec: ActorSpec,
        input: tuple[dict[str, Any], ...],
        common_config_hash: str,
        instructions: str | None = None,
        declared_carrier_ids: tuple[str, ...] = (),
        carrier_capabilities: tuple[CarrierCapability, ...] = (),
    ) -> "FrozenAssignment":
        if carrier_capabilities:
            normalized_capabilities = tuple(carrier_capabilities)
            capability_ids = tuple(
                sorted({item.carrier_id for item in normalized_capabilities})
            )
            if declared_carrier_ids and tuple(declared_carrier_ids) != capability_ids:
                raise ValueError(
                    "declared carrier identifiers must equal capability identifiers"
                )
            normalized_carrier_ids = capability_ids
        else:
            if declared_carrier_ids:
                raise ValueError(
                    "carrier declarations require explicit per-assignment capabilities"
                )
            normalized_carrier_ids = ()
            normalized_capabilities = ()
        input_json = canonical_bytes(list(input)).decode()
        payload = {
            "attempt_id": attempt_id,
            "actor_spec": actor_spec.model_dump(mode="json"),
            "input_json": input_json,
            "input_hash": sha256_bytes(input_json.encode()),
            "instructions": instructions,
            "common_config_hash": common_config_hash,
            "declared_carrier_ids": list(normalized_carrier_ids),
            "carrier_capabilities": [
                item.model_dump(mode="json") for item in normalized_capabilities
            ],
        }
        return cls(**payload, assignment_hash=stable_hash(payload))

    @property
    def semantic_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude={"assignment_hash"}, mode="json")

    @property
    def input_bytes(self) -> bytes:
        """Return the exact predeclared input bytes without modifying them."""

        return self.input_json.encode()

    @model_validator(mode="after")
    def validate_assignment(self) -> "FrozenAssignment":
        if not _SAFE_ID.fullmatch(self.attempt_id):
            raise ValueError("attempt_id is not safe")
        _canonical_json_array(self.input_json, field="input_json")
        if self.input_hash != sha256_bytes(self.input_json.encode()):
            raise ValueError("input_hash does not match input_json")
        if len(set(self.declared_carrier_ids)) != len(self.declared_carrier_ids):
            raise ValueError("declared carrier identifiers must be unique")
        if tuple(sorted(self.declared_carrier_ids)) != self.declared_carrier_ids:
            raise ValueError("declared carrier identifiers must be sorted")
        if any(not _SAFE_ID.fullmatch(value) for value in self.declared_carrier_ids):
            raise ValueError("declared carrier identifier is not safe")
        capability_ids = tuple(sorted(item.carrier_id for item in self.carrier_capabilities))
        if capability_ids != self.declared_carrier_ids:
            raise ValueError(
                "assignment carrier declarations do not match capability identifiers"
            )
        if len(capability_ids) != len(set(capability_ids)):
            raise ValueError("carrier capabilities must identify unique carrier IDs")
        for capability in self.carrier_capabilities:
            if (
                capability.attempt_id != self.attempt_id
                or capability.actor_id != self.actor_spec.actor_id
                or capability.lifecycle_id != self.actor_spec.lifecycle_id
                or capability.lineage_id != self.actor_spec.lineage_id
                or capability.generation != self.actor_spec.generation
            ):
                raise ValueError("carrier capability is not bound to this assignment")
        if self.assignment_hash != stable_hash(self.semantic_payload):
            raise ValueError("assignment_hash does not match the frozen assignment")
        return self

    def carrier_capability(
        self,
        carrier_id: str,
        *,
        operation: Literal["read", "write"] | None = None,
    ) -> CarrierCapability:
        """Return the exact immutable capability for this assignment."""

        matches = [
            capability
            for capability in self.carrier_capabilities
            if capability.carrier_id == carrier_id
            and (operation is None or capability.permits(operation))
        ]
        if len(matches) != 1:
            raise KeyError(
                f"carrier {carrier_id!r} has no {operation or 'declared'} capability"
            )
        return matches[0]


class PredeclaredSchedule(StrictModel):
    """Hash-pinned schedule whose assignments cannot depend on outcomes."""

    schedule_version: Literal["h1-runtime-schedule/v1"] = "h1-runtime-schedule/v1"
    common_config: FrozenCommonConfig
    assignments: tuple[FrozenAssignment, ...]
    schedule_hash: str

    @classmethod
    def from_assignments(
        cls,
        *,
        common_config: FrozenCommonConfig,
        assignments: tuple[FrozenAssignment, ...],
    ) -> "PredeclaredSchedule":
        payload = {
            "schedule_version": "h1-runtime-schedule/v1",
            "common_config_hash": common_config.content_hash,
            "assignments": [item.semantic_payload for item in assignments],
        }
        return cls(
            common_config=common_config,
            assignments=assignments,
            schedule_hash=stable_hash(payload),
        )

    @property
    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schedule_version": self.schedule_version,
            "common_config_hash": self.common_config.content_hash,
            "assignments": [item.semantic_payload for item in self.assignments],
        }

    @model_validator(mode="after")
    def validate_schedule(self) -> "PredeclaredSchedule":
        if not self.assignments:
            raise ValueError("schedule must contain at least one assignment")
        attempt_ids = [item.attempt_id for item in self.assignments]
        actor_ids = [item.actor_spec.actor_id for item in self.assignments]
        lifecycle_ids = [item.actor_spec.lifecycle_id for item in self.assignments]
        if len(set(attempt_ids)) != len(attempt_ids):
            raise ValueError("attempt identifiers must be unique")
        if len(set(actor_ids)) != len(actor_ids):
            raise ValueError("actor identifiers must be unique")
        if len(set(lifecycle_ids)) != len(lifecycle_ids):
            raise ValueError("lifecycle identifiers must be unique")
        if any(
            item.common_config_hash != self.common_config.content_hash
            for item in self.assignments
        ):
            raise ValueError("assignment is pinned to a different common config")
        writers: dict[str, CarrierCapability] = {}
        carrier_classes: dict[str, str] = {}
        readers: list[CarrierCapability] = []
        for assignment in self.assignments:
            for capability in assignment.carrier_capabilities:
                carrier_id = capability.carrier_id
                carrier_class = capability.carrier_class.value
                prior_class = carrier_classes.setdefault(carrier_id, carrier_class)
                if prior_class != carrier_class:
                    raise ValueError("carrier class changes across frozen assignments")
                if capability.can_read and capability.can_write:
                    raise ValueError(
                        "carrier capability must separate writer and reader permissions"
                    )
                if capability.can_write:
                    if carrier_id in writers:
                        raise ValueError("carrier has more than one frozen writer")
                    writers[carrier_id] = capability
                if capability.can_read:
                    readers.append(capability)
        for reader in readers:
            writer = writers.get(reader.carrier_id)
            if writer is None:
                raise ValueError("carrier reader has no frozen writer")
            if (
                reader.lineage_id != writer.lineage_id
                or reader.carrier_class != writer.carrier_class
                or reader.generation <= writer.generation
            ):
                raise ValueError(
                    "carrier reader must match writer lineage/class and be a later generation"
                )
        if self.schedule_hash != stable_hash(self.semantic_payload):
            raise ValueError("schedule_hash does not match the frozen schedule")
        return self


class OrchestratorPolicy(StrictModel):
    """The only runtime policy an orchestrator may expose."""

    network_mode: Literal["unshared-deny"] = "unshared-deny"
    tools: tuple[str, ...] = ()
    model_calls: Literal[False] = False
    session_resume: Literal[False] = False
    outcome_dependent_assignment: Literal[False] = False
    orchestrator_signing: Literal[False] = False

    @model_validator(mode="after")
    def validate_policy(self) -> "OrchestratorPolicy":
        if self.tools:
            raise ValueError("orchestrator tools are permanently disabled")
        return self


class VerifiedActionMetadata(StrictModel):
    """Non-secret audit metadata for one accepted actor signature."""

    actor_id: str
    lifecycle_id: str
    session_id: str
    generation: int
    action_id: str
    sequence: int
    action: str
    payload_hash: str
    parent_hashes: tuple[str, ...]

    @classmethod
    def from_action(cls, action: SignedAction) -> "VerifiedActionMetadata":
        return cls(
            actor_id=action.actor_id,
            lifecycle_id=action.lifecycle_id,
            session_id=action.session_id,
            generation=action.generation,
            action_id=action.action_id,
            sequence=action.sequence,
            action=action.action,
            payload_hash=action.payload_hash,
            parent_hashes=action.parent_hashes,
        )


class OrchestratorMetadata(StrictModel):
    """Outcome-blind control-plane record."""

    schedule_hash: str
    common_config_hash: str
    policy: OrchestratorPolicy
    started_attempt_ids: tuple[str, ...]
    stopped_attempt_ids: tuple[str, ...]
    actors: tuple[ActorRuntimeRecord, ...]
    teardowns: tuple[TeardownEvidence, ...]
    verified_actions: tuple[VerifiedActionMetadata, ...]
    declared_carrier_records: tuple[CarrierRecord, ...]


class Orchestrator:
    """A frozen-schedule lifecycle controller with no model-facing authority."""

    def __init__(
        self,
        schedule: PredeclaredSchedule,
        *,
        factory: BubblewrapActorFactory | None = None,
        carrier_store: DeclaredCarrierStore | None = None,
    ) -> None:
        self._schedule = PredeclaredSchedule.model_validate(
            schedule.model_dump(mode="python")
        )
        self.policy = OrchestratorPolicy()
        self._factory = factory or BubblewrapActorFactory()
        self._registry = ActionRegistry()
        if carrier_store is None:
            self._carrier_store = DeclaredCarrierStore(
                self._registry,
                capabilities=tuple(
                    capability
                    for assignment in self._schedule.assignments
                    for capability in assignment.carrier_capabilities
                ),
            )
        else:
            if carrier_store.registry is not self._registry:
                raise ValueError("carrier store must use the orchestrator's action registry")
            carrier_store.bind_capabilities(
                tuple(
                    capability
                    for assignment in self._schedule.assignments
                    for capability in assignment.carrier_capabilities
                )
            )
            self._carrier_store = carrier_store
        self._actors: dict[str, IsolatedActor] = {}
        self._runtime_records: dict[str, ActorRuntimeRecord] = {}
        self._teardowns: dict[str, TeardownEvidence] = {}
        self._verified_actions: list[VerifiedActionMetadata] = []

    @property
    def schedule(self) -> PredeclaredSchedule:
        """Return the immutable schedule snapshot used by every lookup."""

        return self._schedule

    @property
    def common_config_hash(self) -> str:
        return self.schedule.common_config.content_hash

    @property
    def common_config_bytes(self) -> bytes:
        return self.schedule.common_config.content_bytes

    @property
    def schedule_hash(self) -> str:
        return self.schedule.schedule_hash

    def predeclared_assignment(self, attempt_id: str) -> FrozenAssignment:
        """Return only the assignment already frozen into the schedule."""

        for assignment in self.schedule.assignments:
            if assignment.attempt_id == attempt_id:
                return assignment
        raise KeyError(f"attempt is not in the frozen schedule: {attempt_id}")

    def carrier_capability(
        self,
        attempt_id: str,
        carrier_id: str,
        *,
        operation: Literal["read", "write"] | None = None,
    ) -> CarrierCapability:
        """Look up a carrier grant only through the frozen schedule."""

        return self.predeclared_assignment(attempt_id).carrier_capability(
            carrier_id, operation=operation
        )

    def provider_gateway_for_attempt(
        self,
        attempt_id: str,
        *,
        policy: ProviderPolicy,
        common_prior_hashes: dict[str, str],
        ledger_path: Any | None = None,
        receipt_private_key: Any | None = None,
    ) -> ProviderGateway:
        """Build provider pins directly from one frozen assignment.

        Callers provide the provider policy and prior *values* for the
        experiment design; they cannot provide expected hashes, actor specs,
        or request contracts.  Every expected value is derived here from the
        private schedule snapshot and the orchestrator's registry.
        """

        assignment = self.predeclared_assignment(attempt_id)
        input_value = tuple(json.loads(assignment.input_json))
        priors = dict(common_prior_hashes)
        request_payload = {
            "policy": policy.model_dump(mode="json"),
            "input": list(input_value),
            "instructions": assignment.instructions,
            "attempt_id": assignment.attempt_id,
            "assignment_hash": assignment.assignment_hash,
            "common_prior_hashes": priors,
        }
        return ProviderGateway(
            self._registry,
            expected_policy=policy,
            expected_common_prior_hashes=priors,
            expected_assignment_hashes={
                assignment.attempt_id: assignment.assignment_hash
            },
            expected_request_hashes={
                assignment.attempt_id: stable_hash(request_payload)
            },
            expected_actor_specs={assignment.attempt_id: assignment.actor_spec},
            ledger_path=ledger_path,
            receipt_private_key=receipt_private_key,
        )

    async def start_actor(self, attempt_id: str) -> ActorRuntimeRecord:
        """Start the exact scheduled actor; no actor-visible argument is accepted."""

        assignment = self.predeclared_assignment(attempt_id)
        if attempt_id in self._actors:
            raise ValueError("attempt already has a live actor")
        # A successor cannot start until every earlier generation in its
        # lineage has been stopped.  This is a schedule/lifecycle rule, never
        # a reaction to a behavioral or provider outcome.
        for other in self.schedule.assignments:
            other_id = other.attempt_id
            if (
                other.actor_spec.lineage_id == assignment.actor_spec.lineage_id
                and other.actor_spec.generation < assignment.actor_spec.generation
                and other_id in self._actors
            ):
                raise RuntimeError("predecessor lifecycle is still active")
        actor = await self._factory.spawn(assignment.actor_spec)
        try:
            self._registry.register(actor.identity)
        except BaseException:
            await self._factory.stop(actor)
            raise
        record = ActorRuntimeRecord(
            identity=actor.identity,
            runtime_process_id=actor.launcher_pid,
        )
        self._actors[attempt_id] = actor
        self._runtime_records[attempt_id] = record
        return record

    async def stop_actor(self, attempt_id: str) -> TeardownEvidence:
        """Stop and revoke one scheduled actor, recording the teardown evidence."""

        try:
            actor = self._actors[attempt_id]
        except KeyError as exc:
            raise KeyError(f"attempt has no live actor: {attempt_id}") from exc
        evidence = await self._factory.stop(actor)
        self._registry.revoke(actor.identity.lifecycle_id)
        del self._actors[attempt_id]
        self._teardowns[attempt_id] = evidence
        return evidence

    async def stop_all(self) -> tuple[TeardownEvidence, ...]:
        """Stop active actors in reverse schedule order without inspecting outcomes."""

        order = [item.attempt_id for item in reversed(self.schedule.assignments)]
        evidence: list[TeardownEvidence] = []
        for attempt_id in order:
            if attempt_id in self._actors:
                evidence.append(await self.stop_actor(attempt_id))
        return tuple(evidence)

    async def create_and_finalize_carrier(
        self,
        attempt_id: str,
        carrier_id: str,
    ) -> CarrierRecord:
        """Create one scheduled carrier through the live actor and finalize it.

        The actor chooses the bytes inside its isolated process.  The
        controller receives only the actor-signed action and uses the exact
        schedule capability for write/finalize authorization.
        """

        assignment = self.predeclared_assignment(attempt_id)
        actor = self._actors.get(attempt_id)
        if actor is None:
            raise RuntimeError("carrier writer lifecycle is not active")
        capability = assignment.carrier_capability(carrier_id, operation="write")
        if capability.carrier_class.value not in {
            "DECLARED_LINEAGE_CARRIER",
            "DECLARED_BACKUP",
        }:
            raise ValueError("carrier capability class is not writable")
        raw = await actor.command(
            "create_mechanical_carrier",
            carrier_id=carrier_id,
            carrier_class=capability.carrier_class.value,
            parent_hashes=[],
        )
        action = actor.validate_action(raw["action"])
        content = base64.b64decode(raw["content_b64"])
        self._carrier_store.write(
            carrier_id=carrier_id,
            carrier_class=capability.carrier_class,
            content=content,
            writer=action,
            parent_hashes=tuple(raw["parent_hashes"]),
            capability=capability,
        )
        return self._carrier_store.finalize_and_hash(
            carrier_id, capability=capability
        )

    async def deliver_carrier(
        self,
        attempt_id: str,
        carrier_id: str,
    ) -> CarrierRecord:
        """Authorize and deliver carrier bytes to one scheduled live actor.

        Raw bytes never cross this normal orchestrator API.  They are opened
        only after the exact recipient identity and read capability have been
        checked, sent directly to that actor's narrow command, and then
        discarded after the actor-signed read is durably attributed.
        """

        assignment = self.predeclared_assignment(attempt_id)
        actor = self._actors.get(attempt_id)
        if actor is None:
            raise RuntimeError("carrier reader lifecycle is not active")
        capability = assignment.carrier_capability(carrier_id, operation="read")
        record, content = self._carrier_store.read(
            carrier_id,
            capability=capability,
            recipient=actor.identity,
        )
        raw = await actor.command(
            "carrier_read",
            carrier_id=record.carrier_id,
            content_b64=base64.b64encode(content).decode(),
            content_hash=record.content_hash,
            provenance_hash=carrier_read_binding(record),
        )
        reader = actor.validate_action(raw["action"])
        updated = self._carrier_store.record_read(
            carrier_id,
            reader,
            capability=capability,
        )
        self._verified_actions.append(VerifiedActionMetadata.from_action(reader))
        return updated

    def verify_signed_action(self, action: SignedAction | dict[str, Any]) -> VerifiedActionMetadata:
        """Verify and consume an active actor signature; the controller cannot sign."""

        parsed = SignedAction.model_validate(action)
        if not self._registry.verify(parsed):
            raise ValueError("signed action is not authorized by a live scheduled actor")
        metadata = VerifiedActionMetadata.from_action(parsed)
        self._verified_actions.append(metadata)
        return metadata

    def enumerate_declared_carrier_records(
        self, attempt_id: str | None = None
    ) -> tuple[CarrierRecord, ...]:
        """Expose records through one assignment's read capabilities.

        A no-argument call intentionally returns no records: there is no
        schedule-wide carrier union API.  Metadata collection performs the
        same per-assignment lookups internally and deduplicates only after
        authorization has succeeded for each source assignment.
        """

        if attempt_id is None:
            return ()
        assignment = self.predeclared_assignment(attempt_id)
        records: list[CarrierRecord] = []
        for capability in assignment.carrier_capabilities:
            if not capability.can_read:
                continue
            records.extend(self._carrier_store.enumerate(capability=capability))
        return tuple(
            record
            for index, record in enumerate(records)
            if record.carrier_id not in {prior.carrier_id for prior in records[:index]}
        )

    def _collect_authorized_carrier_records(self) -> tuple[CarrierRecord, ...]:
        records: list[CarrierRecord] = []
        for assignment in self.schedule.assignments:
            records.extend(self.enumerate_declared_carrier_records(assignment.attempt_id))
        return tuple(
            record
            for index, record in enumerate(records)
            if record.carrier_id not in {prior.carrier_id for prior in records[:index]}
        )

    def collect_metadata(self) -> OrchestratorMetadata:
        """Collect hashes, identities, signatures, and teardown records only."""

        return OrchestratorMetadata(
            schedule_hash=self.schedule_hash,
            common_config_hash=self.common_config_hash,
            policy=self.policy,
            started_attempt_ids=tuple(
                item.attempt_id for item in self.schedule.assignments if item.attempt_id in self._runtime_records
            ),
            stopped_attempt_ids=tuple(
                item.attempt_id for item in self.schedule.assignments if item.attempt_id in self._teardowns
            ),
            actors=tuple(
                self._runtime_records[item.attempt_id]
                for item in self.schedule.assignments
                if item.attempt_id in self._runtime_records
            ),
            teardowns=tuple(
                self._teardowns[item.attempt_id]
                for item in self.schedule.assignments
                if item.attempt_id in self._teardowns
            ),
            verified_actions=tuple(self._verified_actions),
            declared_carrier_records=self._collect_authorized_carrier_records(),
        )


__all__ = [
    "CarrierCapability",
    "FrozenAssignment",
    "FrozenCommonConfig",
    "Orchestrator",
    "OrchestratorMetadata",
    "OrchestratorPolicy",
    "PredeclaredSchedule",
    "VerifiedActionMetadata",
]
