"""Runner-owned tamper-evident audit ledger.

The scientific event log records world transitions.  This ledger records the
behavioral boundary around each role call and is intentionally separate from
films, racks, and world state.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, StrictInt, StrictStr

from constraint_forge_formation_v0.canonical import canonical_bytes, sha256_bytes
from constraint_forge_formation_v0.models import StrictModel


class AuditStatus(StrEnum):
    PREPARED = "prepared"
    COMPLETED = "completed"
    SAFE_RETRY = "safe_retry"
    INFRA_RETRY = "infra_retry"
    FAILED = "failed"
    AUDIT_ONLY = "audit_only"


class AuditSealStatus(StrEnum):
    COMPLETED = "completed"
    ABORTED = "aborted"


class RunnerAuditEvent(StrictModel):
    schema_version: Literal["constraint-forge/runner-audit-event/v0"] = (
        "constraint-forge/runner-audit-event/v0"
    )
    sequence: StrictInt = Field(ge=0)
    previous_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    event_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: StrictStr
    dyad_id: StrictStr
    actor: Literal["X", "Y"]
    actor_id: StrictStr
    lifecycle_id: StrictStr
    context_epoch: StrictInt = Field(ge=0)
    job_index: StrictInt = Field(ge=0)
    job_id: StrictStr
    phase: Literal["round", "eviction", "retention"]
    round: StrictInt | None = Field(default=None, ge=1, le=16)
    call_id: StrictStr
    retry_of: StrictStr | None = None
    pre_state_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    world_event_sequence_before: StrictInt = Field(ge=0)
    request_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    model_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    provider_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    config_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    provider_status: StrictStr | None = None
    provider_request_id: StrictStr | None = None
    raw_output: StrictStr | None = None
    raw_output_hash: StrictStr | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    parse_classification: StrictStr = "not_applicable"
    world_event_sequence_start: StrictInt | None = Field(default=None, ge=0)
    world_event_sequence_end: StrictInt | None = Field(default=None, ge=0)
    post_state_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    status: AuditStatus
    failure_class: StrictStr | None = None


class AuditSeal(StrictModel):
    schema_version: Literal["constraint-forge/runner-audit-seal/v0"] = (
        "constraint-forge/runner-audit-seal/v0"
    )
    status: AuditSealStatus
    event_count: StrictInt = Field(ge=0)
    final_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class AuditVerification(StrictModel):
    valid: bool
    reason: str = ""


_GENESIS = "0" * 64


def _event_digest(event: RunnerAuditEvent) -> str:
    payload = event.model_dump(mode="json")
    payload.pop("event_hash", None)
    return sha256_bytes(canonical_bytes(payload))


class AuditLedger:
    """Append-only hash chain with explicit completion/abort sealing."""

    def __init__(self, *, run_id: str, dyad_id: str) -> None:
        self.run_id = run_id
        self.dyad_id = dyad_id
        self._events: list[RunnerAuditEvent] = []
        self._seal: AuditSeal | None = None

    @property
    def events(self) -> tuple[RunnerAuditEvent, ...]:
        return tuple(self._events)

    @property
    def seal_record(self) -> AuditSeal | None:
        return self._seal

    @property
    def final_hash(self) -> str:
        return self._seal.final_hash if self._seal else (
            self._events[-1].event_hash if self._events else _GENESIS
        )

    def append(self, **kwargs) -> RunnerAuditEvent:
        if self._seal is not None:
            raise RuntimeError("audit ledger is already sealed")
        sequence = len(self._events)
        previous_hash = self._events[-1].event_hash if self._events else _GENESIS
        draft = RunnerAuditEvent(
            sequence=sequence,
            previous_hash=previous_hash,
            event_hash=_GENESIS,
            run_id=self.run_id,
            dyad_id=self.dyad_id,
            **kwargs,
        )
        event = draft.model_copy(update={"event_hash": _event_digest(draft)})
        self._events.append(event)
        return event

    def seal(self, status: AuditSealStatus | str) -> AuditSeal:
        if self._seal is not None:
            if self._seal.status != status:
                raise RuntimeError("audit ledger has already been sealed with another status")
            return self._seal
        verification = self.verify()
        if not verification.valid:
            raise ValueError(f"cannot seal invalid audit ledger: {verification.reason}")
        self._seal = AuditSeal(
            status=status,
            event_count=len(self._events),
            final_hash=self.final_hash,
        )
        return self._seal

    def verify(self) -> AuditVerification:
        return self.verify_events(self._events, self._seal)

    @staticmethod
    def verify_events(
        events: list[RunnerAuditEvent] | tuple[RunnerAuditEvent, ...],
        seal: AuditSeal | None = None,
    ) -> AuditVerification:
        previous = _GENESIS
        for expected, event in enumerate(events):
            if event.sequence != expected:
                return AuditVerification(valid=False, reason="audit sequence is not contiguous")
            if event.previous_hash != previous:
                return AuditVerification(valid=False, reason="audit previous-hash link is broken")
            if _event_digest(event) != event.event_hash:
                return AuditVerification(
                    valid=False,
                    reason="audit event hash does not match its payload",
                )
            previous = event.event_hash
        if seal is not None:
            if seal.event_count != len(events):
                return AuditVerification(valid=False, reason="audit seal event count differs")
            if seal.final_hash != (events[-1].event_hash if events else _GENESIS):
                return AuditVerification(valid=False, reason="audit seal final hash differs")
        return AuditVerification(valid=True)


__all__ = [
    "AuditLedger",
    "AuditSeal",
    "AuditSealStatus",
    "AuditStatus",
    "AuditVerification",
    "RunnerAuditEvent",
]
