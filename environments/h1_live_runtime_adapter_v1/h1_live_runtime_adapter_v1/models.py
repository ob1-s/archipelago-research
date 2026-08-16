"""Strict wire models for the live-runtime mechanical boundary."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


Sha256Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
SafeIdentifier = Annotated[
    str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
]
NonEmptyString = Annotated[str, Field(min_length=1)]


class StateClass(StrEnum):
    TRANSIENT_ACTOR_STATE = "TRANSIENT_ACTOR_STATE"
    IMMUTABLE_COMMON_PRIOR = "IMMUTABLE_COMMON_PRIOR"
    DECLARED_ASSIGNMENT = "DECLARED_ASSIGNMENT"
    DECLARED_LINEAGE_CARRIER = "DECLARED_LINEAGE_CARRIER"
    DECLARED_BACKUP = "DECLARED_BACKUP"
    ORCHESTRATOR_ONLY = "ORCHESTRATOR_ONLY"
    PROVIDER_OPAQUE = "PROVIDER_OPAQUE"
    FORBIDDEN = "FORBIDDEN"


class CarrierCapability(StrictModel):
    """One immutable schedule grant for one carrier and actor lifecycle."""

    attempt_id: SafeIdentifier
    actor_id: SafeIdentifier
    lifecycle_id: SafeIdentifier
    lineage_id: SafeIdentifier
    generation: int = Field(ge=0)
    carrier_id: SafeIdentifier
    carrier_class: StateClass
    can_read: bool = False
    can_write: bool = False
    capability_hash: Sha256Digest

    @classmethod
    def from_fields(
        cls,
        *,
        attempt_id: str,
        actor_id: str,
        lifecycle_id: str,
        lineage_id: str,
        generation: int,
        carrier_id: str,
        carrier_class: StateClass,
        can_read: bool = False,
        can_write: bool = False,
    ) -> "CarrierCapability":
        from .canonical import stable_hash

        payload = {
            "attempt_id": attempt_id,
            "actor_id": actor_id,
            "lifecycle_id": lifecycle_id,
            "lineage_id": lineage_id,
            "generation": generation,
            "carrier_id": carrier_id,
            "carrier_class": StateClass(carrier_class).value,
            "can_read": can_read,
            "can_write": can_write,
        }
        return cls(**payload, capability_hash=stable_hash(payload))

    @property
    def semantic_payload(self) -> dict[str, object]:
        return self.model_dump(exclude={"capability_hash"}, mode="json")

    def permits(self, operation: str) -> bool:
        if operation == "read":
            return self.can_read
        if operation == "write":
            return self.can_write
        raise ValueError(f"unknown carrier capability operation: {operation}")

    @model_validator(mode="after")
    def validate_capability(self) -> "CarrierCapability":
        from .canonical import stable_hash

        if self.carrier_class not in {
            StateClass.DECLARED_LINEAGE_CARRIER,
            StateClass.DECLARED_BACKUP,
        }:
            raise ValueError("carrier capability class is undeclared")
        if self.can_read == self.can_write:
            raise ValueError("carrier capability must grant exactly one operation")
        if self.capability_hash != stable_hash(self.semantic_payload):
            raise ValueError("carrier capability hash does not match its fields")
        return self


class AssignmentContractPin(StrictModel):
    """Nonsecret audit pin for one member of the frozen runtime schedule."""

    attempt_id: SafeIdentifier
    assignment_hash: Sha256Digest
    actor_spec_hash: Sha256Digest
    request_hash: Sha256Digest | None = None
    capability_hashes: tuple[Sha256Digest, ...] = ()

    @model_validator(mode="after")
    def validate_capability_hashes(self) -> "AssignmentContractPin":
        if len(self.capability_hashes) != len(set(self.capability_hashes)):
            raise ValueError("assignment capability hashes must be unique")
        return self


class ScheduleContractPin(StrictModel):
    """Hash-validated public audit view of the frozen schedule contract."""

    version: Literal["h1-runtime-schedule-pin/v1"] = "h1-runtime-schedule-pin/v1"
    provider_policy_hash: Sha256Digest
    common_prior_hashes: dict[str, Sha256Digest]
    gateway_public_key_b64: NonEmptyString
    assignments: tuple[AssignmentContractPin, ...] = Field(min_length=1)
    schedule_hash: Sha256Digest

    @classmethod
    def from_fields(
        cls,
        *,
        provider_policy_hash: str,
        common_prior_hashes: dict[str, str],
        gateway_public_key_b64: str,
        assignments: tuple[AssignmentContractPin, ...],
    ) -> "ScheduleContractPin":
        from .canonical import stable_hash

        payload = {
            "version": "h1-runtime-schedule-pin/v1",
            "provider_policy_hash": provider_policy_hash,
            "common_prior_hashes": common_prior_hashes,
            "gateway_public_key_b64": gateway_public_key_b64,
            "assignments": [item.model_dump(mode="json") for item in assignments],
        }
        return cls(**payload, schedule_hash=stable_hash(payload))

    @property
    def semantic_payload(self) -> dict[str, object]:
        return self.model_dump(exclude={"schedule_hash"}, mode="json")

    @model_validator(mode="after")
    def validate_schedule_pin(self) -> "ScheduleContractPin":
        from .canonical import stable_hash

        attempt_ids = tuple(item.attempt_id for item in self.assignments)
        if len(attempt_ids) != len(set(attempt_ids)):
            raise ValueError("schedule-pin attempt identifiers must be unique")
        if not self.common_prior_hashes:
            raise ValueError("schedule pin requires common-prior hashes")
        if self.schedule_hash != stable_hash(self.semantic_payload):
            raise ValueError("schedule pin hash does not match its fields")
        return self


class EvidenceClass(StrEnum):
    MECHANICALLY_CONTROLLED = "MECHANICALLY CONTROLLED"
    DOCUMENTATION_SUPPORTED = "CONTRACTUALLY/DOCUMENTATION-SUPPORTED"
    EMPIRICALLY_PROBED = "EMPIRICALLY PROBED"
    OPAQUE_UNVERIFIED = "OPAQUE/UNVERIFIED"


class Readiness(StrEnum):
    PASS = "PASS"
    PASS_WITH_REPAIRS = "PASS WITH REPAIRS"
    FAIL = "FAIL"


class StateLayer(StrictModel):
    name: str
    owner: str
    scope: str
    lifetime: str
    model_visible: Literal["yes", "no", "unknown"]
    mutable: bool
    predecessor_write: bool
    successor_read: bool
    classification: StateClass
    reset_or_isolation: str
    verification: str
    evidence_class: EvidenceClass
    residual_uncertainty: str | None = None


class ActorSpec(StrictModel):
    actor_id: SafeIdentifier
    lifecycle_id: SafeIdentifier
    generation: int = Field(ge=0)
    lineage_id: SafeIdentifier
    position: SafeIdentifier
    gateway_public_key_b64: str | None = None


class ActorIdentity(ActorSpec):
    session_id: SafeIdentifier
    public_key_b64: str
    registration_signature_b64: str
    namespace_pid: int
    namespace_process_start_ticks: int
    environment_fingerprint: str
    environment_names: tuple[str, ...]
    namespace_ids: dict[str, str]
    effective_capabilities_hex: str
    no_new_privileges: bool
    open_extra_fd_count: int
    open_extra_fd_targets: dict[str, str]

    @model_validator(mode="after")
    def validate_fd_inventory(self) -> "ActorIdentity":
        if self.open_extra_fd_count != len(self.open_extra_fd_targets):
            raise ValueError("open descriptor count differs from descriptor inventory")
        return self


class SignedAction(StrictModel):
    actor_id: SafeIdentifier
    lifecycle_id: SafeIdentifier
    session_id: SafeIdentifier
    generation: int = Field(ge=0)
    lineage_id: SafeIdentifier
    public_key_b64: str
    sequence: int = Field(ge=1)
    action_id: SafeIdentifier
    action: SafeIdentifier
    payload_hash: Sha256Digest
    parent_hashes: tuple[Sha256Digest, ...] = ()
    signature_b64: str

    def unsigned_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude={"signature_b64"}, mode="json")


class CanaryEvidence(StrictModel):
    actor_id: SafeIdentifier
    path_hashes: dict[str, Sha256Digest]
    environment_value_hash: Sha256Digest
    paths: tuple[str, ...] = Field(min_length=1)
    history_length: int = Field(ge=1)
    action: SignedAction


class TeardownEvidence(StrictModel):
    actor_id: SafeIdentifier
    lifecycle_id: SafeIdentifier
    launcher_pid: int = Field(ge=1)
    runtime_process_id: int = Field(ge=1)
    return_code: int
    process_absent: bool
    process_group_absent: bool
    private_root_removed: bool
    key_invalidated: bool


class ProviderPolicy(StrictModel):
    adapter: Literal["openai_responses_stateless_v1"] = "openai_responses_stateless_v1"
    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    store: Literal[False] = False
    previous_response_id: None = None
    conversation: None = None
    tools: tuple[Any, ...] = ()
    background: Literal[False] = False
    stream: Literal[False] = False
    include: tuple[Any, ...] = ()
    max_retries: Literal[0] = 0

    @model_validator(mode="after")
    def validate_stateless_policy(self) -> "ProviderPolicy":
        if self.tools or self.include:
            raise ValueError("qualified provider policy permits no tools or hidden state")
        if not self.base_url.startswith("https://"):
            raise ValueError("provider base URL must use HTTPS")
        return self


class ProviderRequest(StrictModel):
    action: SignedAction
    policy: ProviderPolicy
    input: tuple[dict[str, Any], ...]
    instructions: str | None = None
    attempt_id: SafeIdentifier
    assignment_hash: Sha256Digest
    common_prior_hashes: dict[str, Sha256Digest]

    @model_validator(mode="after")
    def validate_signed_request(self) -> "ProviderRequest":
        if self.action.action != "provider_request":
            raise ValueError("provider request requires provider_request action")
        if self.action.payload_hash != self.semantic_hash():
            raise ValueError("signed provider request hash mismatch")
        return self

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "policy": self.policy.model_dump(mode="json"),
            "input": list(self.input),
            "instructions": self.instructions,
            "attempt_id": self.attempt_id,
            "assignment_hash": self.assignment_hash,
            "common_prior_hashes": self.common_prior_hashes,
        }

    def semantic_hash(self) -> str:
        from .canonical import stable_hash

        return stable_hash(self.semantic_payload())


class GatewayReceipt(StrictModel):
    gateway_id: SafeIdentifier
    public_key_b64: str
    logical_attempt_id: SafeIdentifier
    assignment_hash: Sha256Digest
    request_hash: Sha256Digest
    response_id: str = Field(min_length=1)
    provider_request_id: NonEmptyString | None = None
    output_hash: Sha256Digest
    signature_b64: str

    def unsigned_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude={"signature_b64"}, mode="json")


class ProviderResponse(StrictModel):
    provider: str
    model: str
    status: Literal["completed"] = "completed"
    response_id: str = Field(min_length=1)
    request_id: NonEmptyString | None
    output_text: str
    output_hash: Sha256Digest
    request_hash: Sha256Digest
    store_requested: Literal[False] = False
    provider_storage_observed: bool | None = None
    previous_response_id: None = None
    conversation_id: None = None
    tool_calls: Literal[0] = 0
    gateway_receipt: GatewayReceipt | None = None

    @model_validator(mode="after")
    def validate_completed_response(self) -> "ProviderResponse":
        from .canonical import sha256_bytes

        if self.output_hash != sha256_bytes(self.output_text.encode()):
            raise ValueError("provider output hash mismatch")
        if self.gateway_receipt is not None and (
            self.gateway_receipt.request_hash != self.request_hash
            or self.gateway_receipt.output_hash != self.output_hash
            or self.gateway_receipt.response_id != self.response_id
            or self.gateway_receipt.provider_request_id != self.request_id
        ):
            raise ValueError("gateway receipt differs from provider response")
        return self


class RetryAttempt(StrictModel):
    actor_id: SafeIdentifier
    lifecycle_id: SafeIdentifier
    logical_attempt_id: SafeIdentifier
    transport_attempt: int = Field(ge=1)
    wire_attempt_id: SafeIdentifier
    request_hash: Sha256Digest
    outcome: NonEmptyString
    dispatch_phase: Literal[
        "not_sent", "sent", "response_received", "unknown"
    ]
    provider_request_id: NonEmptyString | None = None
    provider_response_id: NonEmptyString | None = None
    retryable: bool


class CarrierDraft(StrictModel):
    carrier_id: SafeIdentifier
    carrier_class: StateClass
    lineage_id: SafeIdentifier
    generation: int = Field(ge=0)
    writer: SignedAction
    content_hash: Sha256Digest
    parent_hashes: tuple[Sha256Digest, ...] = ()


class CarrierRecord(CarrierDraft):
    logical_time: int = Field(ge=1)
    finalized: Literal[True] = True
    write_authority: Sha256Digest
    write_capability_hash: Sha256Digest | None = None
    read_by: tuple[SafeIdentifier, ...] = ()
    read_actions: tuple[SignedAction, ...] = ()
    read_capability_hashes: tuple[Sha256Digest, ...] = ()

    @model_validator(mode="after")
    def validate_durable_read_provenance(self) -> "CarrierRecord":
        from .canonical import stable_hash
        from .crypto import verify_action

        write_binding = stable_hash(
            {
                "carrier_id": self.carrier_id,
                "carrier_class": self.carrier_class.value,
                "lineage_id": self.lineage_id,
                "generation": self.generation,
                "content_hash": self.content_hash,
                "parent_hashes": list(self.parent_hashes),
            }
        )
        write_authority = stable_hash(
            {
                "lifecycle_id": self.writer.lifecycle_id,
                "public_key": self.writer.public_key_b64,
            }
        )
        if (
            self.writer.action != "carrier_write"
            or self.writer.payload_hash != self.content_hash
            or self.writer.lineage_id != self.lineage_id
            or self.writer.generation != self.generation
            or self.writer.parent_hashes != (*self.parent_hashes, write_binding)
            or self.write_authority != write_authority
            or not verify_action(self.writer)
        ):
            raise ValueError("carrier has invalid durable write provenance")
        read_binding = stable_hash(
            {
                "carrier_id": self.carrier_id,
                "carrier_class": self.carrier_class.value,
                "lineage_id": self.lineage_id,
                "generation": self.generation,
                "content_hash": self.content_hash,
                "parent_hashes": list(self.parent_hashes),
                "write_authority": self.write_authority,
            }
        )
        if self.read_by != tuple(action.actor_id for action in self.read_actions):
            raise ValueError("carrier read index differs from signed read actions")
        if self.write_capability_hash is None:
            if self.read_capability_hashes:
                raise ValueError("unbound carrier cannot contain capability attribution")
        elif len(self.read_capability_hashes) != len(self.read_actions):
            raise ValueError("carrier capability attribution differs from read actions")
        for action in self.read_actions:
            if (
                action.action != "carrier_read"
                or action.payload_hash != self.content_hash
                or action.lineage_id != self.lineage_id
                or action.generation <= self.generation
                or action.parent_hashes != (self.content_hash, read_binding)
                or not verify_action(action)
            ):
                raise ValueError("carrier has invalid durable read provenance")
        return self


class BoundaryAssessment(StrictModel):
    clean: bool
    l0_supported: bool
    l0_claim: str | None
    violations: tuple[str, ...]
    predecessor_actor_ids: tuple[str, ...]
    successor_actor_ids: tuple[str, ...]


class ClaimBoundary(StrictModel):
    level: Literal["L0", "L1", "L2", "L3", "L4", "L5"]
    supported: bool
    scientific_evidence: Literal[False] = False
    basis: str


class ReadinessQuestion(StrictModel):
    question_id: str = Field(pattern=r"^Q(0[1-9]|1[0-9])$")
    question: str
    status: Readiness
    answer: str
    evidence: tuple[str, ...]


class ActorRuntimeRecord(StrictModel):
    identity: ActorIdentity
    runtime_process_id: int = Field(ge=1)


class RuntimeBoundaryEvidence(StrictModel):
    adapter_version: str
    backend: str
    backend_version: str
    provider: str
    model: str
    runtime: str
    runtime_versions: dict[str, str]
    schedule_contract: ScheduleContractPin
    predecessors: tuple[ActorRuntimeRecord, ...]
    successors: tuple[ActorRuntimeRecord, ...]
    teardowns: tuple[TeardownEvidence, ...]
    predecessor_attempt_id: SafeIdentifier
    predecessor_canary: CanaryEvidence
    successor_path_probes: dict[str, bool]
    successor_path_probe_action: SignedAction
    successor_history_length_at_spawn: int = Field(ge=0)
    successor_environment_value_hash: Sha256Digest
    network_probe_action: SignedAction
    carrier_capabilities: tuple[CarrierCapability, ...]
    carrier_records: tuple[CarrierRecord, ...]
    carrier_positive_read: bool
    provider_policy: ProviderPolicy
    provider_assignment_hash: Sha256Digest
    provider_request_hash: Sha256Digest
    provider_request_action: SignedAction
    provider_output_hash: Sha256Digest
    provider_gateway_receipt: GatewayReceipt
    provider_response_acceptance: SignedAction
    provider_response_id: NonEmptyString
    provider_request_id: NonEmptyString | None
    provider_status: Literal["completed"]
    provider_store_requested: Literal[False]
    provider_storage_observed: bool | None
    provider_continuation_present: bool
    network_probe: dict[str, bool | str]
    process_namespace_fresh: bool
    private_mount_reused: bool
    env_or_cache_reused: bool
    stale_worker_reused: bool
    signing_key_reused: bool
    undeclared_external_carrier: bool
    actor_network_mode: Literal["unshared-deny"]
    actor_tools: tuple[str, ...]
    registry_private_key_count: Literal[0]
    common_prior_hashes: dict[str, Sha256Digest]
    retry_attempts: tuple[RetryAttempt, ...]
    live_model_calls: int = 0
    scientific_result: Literal[False] = False
    residual_opaque_state: tuple[str, ...]


L0_CLAIM = (
    "complete turnover within the controlled and documented model-visible state boundary"
)
