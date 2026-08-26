"""Typed canonical event log and offline serialization helpers."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr, field_validator

from ._config import event_round_cap
from .canonical import canonical_bytes, sha256_bytes
from .models import (
    DeliveryStatus,
    EffectStatus,
    Phase,
    Seed,
    Station,
    StrictModel,
    TriggerStatus,
)


class EventKind(StrEnum):
    JOB_START = "JOB_START"
    CONTEXT_RESET = "CONTEXT_RESET"
    OBSERVATION = "OBSERVATION"
    ACTION_SUBMITTED = "ACTION_SUBMITTED"
    ACTION_REJECTED = "ACTION_REJECTED"
    WRITE_DELIVERED = "WRITE_DELIVERED"
    WRITE_DROPPED = "WRITE_DROPPED"
    WRITE_DELAYED = "WRITE_DELAYED"
    WRITE_CANCELLED = "WRITE_CANCELLED"
    LAYER_SET = "LAYER_SET"
    LAYER_UNSET = "LAYER_UNSET"
    LAYER_VISIBILITY_DELAYED = "LAYER_VISIBILITY_DELAYED"
    LAYER_VISIBILITY_EXPIRED = "LAYER_VISIBILITY_EXPIRED"
    FINISH_LOCKED = "FINISH_LOCKED"
    JOB_END = "JOB_END"
    MEMORY_PHASE_START = "MEMORY_PHASE_START"
    MEMORY_EVICTION_PHASE = "MEMORY_EVICTION_PHASE"
    MEMORY_RETENTION_PHASE = "MEMORY_RETENTION_PHASE"
    RETAIN_ATTEMPTED = "RETAIN_ATTEMPTED"
    RETAINED = "RETAINED"
    EVICT_ATTEMPTED = "EVICT_ATTEMPTED"
    EVICTED = "EVICTED"
    RACK_VIEWED = "RACK_VIEWED"
    INTERVENTION_ARMED = "INTERVENTION_ARMED"
    INTERVENTION_TRIGGERED = "INTERVENTION_TRIGGERED"
    INTERVENTION_NOT_TRIGGERED = "INTERVENTION_NOT_TRIGGERED"


class AuditEvent(StrictModel):
    schema_version: Literal["constraint-forge/event/v0"] = "constraint-forge/event/v0"
    run_id: StrictStr
    lineage_id: StrictStr
    job_id: StrictStr
    job_seed: Seed
    event_sequence: StrictInt = Field(ge=0)
    round: StrictInt = Field(ge=0)
    phase: Phase
    source: Station | Literal["environment"]
    event_kind: EventKind
    action_id: StrictStr | None = None
    action_payload: dict | None = None
    legal: StrictBool | None = None
    rejection_reason: StrictStr | None = None
    pre_state_hash: StrictStr
    post_state_hash: StrictStr
    parent_event_ids: tuple[StrictInt, ...] = ()

    @field_validator("round")
    @classmethod
    def _event_round_within_window(cls, value: int) -> int:
        cap = event_round_cap()
        if value > cap:
            raise ValueError(f"round exceeds configured event cap {cap}")
        return value
    write_budget_before: StrictInt | None = None
    write_budget_after: StrictInt | None = None
    mutation_budget_before: StrictInt | None = None
    mutation_budget_after: StrictInt | None = None
    intervention_id: StrictStr | None = None
    trigger_status: TriggerStatus | None = None
    effect_status: EffectStatus | None = None
    delivery_status: DeliveryStatus | None = None
    visible_from_round: StrictInt | None = None
    rack_hash_before: StrictStr | None = None
    rack_hash_after: StrictStr | None = None
    fragment_hash: StrictStr | None = None
    local_window_bounds: tuple[StrictInt, StrictInt] | None = None
    detail: dict = Field(default_factory=dict)


class EventLog(StrictModel):
    schema_version: Literal["constraint-forge/event-log/v0"] = "constraint-forge/event-log/v0"
    run_id: StrictStr
    lineage_id: StrictStr
    job_id: StrictStr
    job_seed: Seed
    events: tuple[AuditEvent, ...] = ()

    def append(self, **kwargs) -> "EventLog":
        event = AuditEvent(
            run_id=self.run_id,
            lineage_id=self.lineage_id,
            job_id=self.job_id,
            job_seed=self.job_seed,
            event_sequence=len(self.events),
            **kwargs,
        )
        return self.model_copy(update={"events": (*self.events, event)})

    @property
    def payload(self) -> dict:
        return self.model_dump(mode="json")

    @property
    def serialization_bytes(self) -> bytes:
        return canonical_bytes(self.payload)

    @property
    def content_hash(self) -> str:
        return sha256_bytes(self.serialization_bytes)

    def to_jsonl(self) -> str:
        return "\n".join(
            canonical_bytes(event.model_dump(mode="json")).decode("utf-8")
            for event in self.events
        )

    @classmethod
    def from_jsonl(
        cls,
        text: str,
        *,
        run_id: str,
        lineage_id: str,
        job_id: str,
        job_seed: Seed,
    ) -> "EventLog":
        import json

        events = tuple(
            AuditEvent.model_validate(json.loads(line))
            for line in text.splitlines()
            if line.strip()
        )
        for expected, event in enumerate(events):
            if event.event_sequence != expected:
                raise ValueError("event sequence is not contiguous")
        return cls(
            run_id=run_id,
            lineage_id=lineage_id,
            job_id=job_id,
            job_seed=job_seed,
            events=events,
        )
