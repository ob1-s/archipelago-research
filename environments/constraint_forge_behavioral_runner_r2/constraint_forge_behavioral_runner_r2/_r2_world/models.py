"""Strict, serializable data models for the model-free V0 core."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from .canonical import canonical_bytes, sha256_bytes
from ._config import CONFIG, event_round_cap, max_rounds, release_round_cap


class StrictModel(BaseModel):
    """Immutable wire/audit model with no undeclared fields."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )


class MutableStrictModel(BaseModel):
    """Mutable state model with strict assignment and no undeclared fields."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        allow_inf_nan=False,
    )


class Station(StrEnum):
    X = "X"
    Y = "Y"


class Phase(StrEnum):
    JOB = "job"
    EVICTION = "eviction"
    RETENTION = "retention"


class DeliveryStatus(StrEnum):
    DELIVERED = "DELIVERED"
    DROPPED = "DROPPED"
    DELAYED = "DELAYED"
    CANCELLED_AT_JOB_END = "CANCELLED_AT_JOB_END"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class TriggerStatus(StrEnum):
    ARMED = "ARMED"
    TRIGGERED = "TRIGGERED"
    NOT_TRIGGERED = "INTERVENTION_NOT_TRIGGERED"


class EffectStatus(StrEnum):
    PENDING = "PENDING"
    APPLIED = "APPLIED"
    CANCELLED_AT_JOB_END = "CANCELLED_AT_JOB_END"
    VISIBILITY_EXPIRED_AT_JOB_END = "VISIBILITY_EXPIRED_AT_JOB_END"
    NOT_APPLICABLE = "NOT_APPLICABLE"


Pair = tuple[StrictInt, StrictInt]
Target = StrictInt | None
Layer = tuple[Target, Target, Target, Target, Target, Target]
Seed = StrictInt | StrictStr


class RegisterState(StrictModel):
    symbol: StrictInt | None = None
    counter: StrictInt = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_symbol(self) -> "RegisterState":
        if self.symbol is not None and not 0 <= self.symbol <= 3:
            raise ValueError("register symbols must be in {0,1,2,3}")
        return self


class JobRecord(StrictModel):
    """Complete immutable generator record, including hidden construction data."""

    schema_version: Literal["constraint-forge/job/v0"] = "constraint-forge/job/v0"
    job_seed: Seed
    rho: tuple[StrictInt, ...]
    sigma: tuple[StrictInt, ...]
    target_factor: StrictInt
    x_decoy_factors: tuple[StrictInt, StrictInt]
    y_decoy_factors: tuple[StrictInt, StrictInt]
    unused_factor: StrictInt
    target_matching: tuple[Pair, ...]
    x_mask: tuple[Pair, ...]
    y_mask: tuple[Pair, ...]
    x_presentation: tuple[Pair, ...]
    y_presentation: tuple[Pair, ...]

    @property
    def payload(self) -> dict:
        return self.model_dump(mode="json")

    @property
    def payload_hash(self) -> str:
        return sha256_bytes(canonical_bytes(self.payload))

    @property
    def intersection(self) -> frozenset[tuple[int, int]]:
        return frozenset(self.x_mask).intersection(self.y_mask)


class StationState(MutableStrictModel):
    station: Station
    private_pairs: tuple[Pair, ...]
    layer: Layer = (None, None, None, None, None, None)
    writes_remaining: StrictInt = Field(
        default_factory=lambda: CONFIG["write_budget"], ge=0
    )
    mutations_remaining: StrictInt = Field(
        default_factory=lambda: CONFIG["mutation_budget"], ge=0
    )
    finished: StrictBool = False
    finish_round: StrictInt | None = Field(default=None, ge=1)
    legal_action_count: StrictInt = Field(default=0, ge=0)
    illegal_action_count: StrictInt = Field(default=0, ge=0)

    @field_validator("writes_remaining")
    @classmethod
    def _writes_within_budget(cls, value: int) -> int:
        if value > CONFIG["write_budget"]:
            raise ValueError(
                f"writes_remaining exceeds configured write budget {CONFIG['write_budget']}"
            )
        return value

    @field_validator("mutations_remaining")
    @classmethod
    def _mutations_within_budget(cls, value: int) -> int:
        if value > CONFIG["mutation_budget"]:
            raise ValueError(
                f"mutations_remaining exceeds configured mutation budget {CONFIG['mutation_budget']}"
            )
        return value

    @field_validator("finish_round")
    @classmethod
    def _finish_round_within_job(cls, value: int | None) -> int | None:
        if value is not None and value > max_rounds():
            raise ValueError(f"finish_round exceeds configured max_rounds {max_rounds()}")
        return value


class InterventionState(StrictModel):
    intervention_id: StrictStr
    kind: StrictStr
    target_stations: tuple[Station, ...] = ()
    trigger_status: TriggerStatus = TriggerStatus.ARMED
    effect_status: EffectStatus = EffectStatus.PENDING
    trigger_round: StrictInt | None = Field(default=None, ge=1)
    effect_round: StrictInt | None = Field(default=None, ge=1)
    detail: StrictStr = ""

    @field_validator("trigger_round")
    @classmethod
    def _trigger_round_within_job(cls, value: int | None) -> int | None:
        if value is not None and value > max_rounds():
            raise ValueError(f"trigger_round exceeds configured max_rounds {max_rounds()}")
        return value

    @field_validator("effect_round")
    @classmethod
    def _effect_round_within_window(cls, value: int | None) -> int | None:
        if value is not None and value > event_round_cap():
            raise ValueError(
                f"effect_round exceeds configured event cap {event_round_cap()}"
            )
        return value


class PendingWrite(StrictModel):
    station: Station
    register: Annotated[StrictInt, Field(ge=0, le=1)]
    symbol: Annotated[StrictInt, Field(ge=0, le=3)]
    selected_round: Annotated[StrictInt, Field(ge=1)]
    delivery_round: Annotated[StrictInt, Field(ge=1)]
    action_id: StrictStr

    @field_validator("selected_round")
    @classmethod
    def _selected_round_within_job(cls, value: int) -> int:
        if value > max_rounds():
            raise ValueError(f"selected_round exceeds configured max_rounds {max_rounds()}")
        return value

    @field_validator("delivery_round")
    @classmethod
    def _delivery_round_within_window(cls, value: int) -> int:
        if value > event_round_cap():
            raise ValueError(
                f"delivery_round exceeds configured event cap {event_round_cap()}"
            )
        return value


class VisibilitySuppression(StrictModel):
    owner: Station
    item: Annotated[StrictInt, Field(ge=0, le=5)]
    selected_round: Annotated[StrictInt, Field(ge=1)]
    release_round: Annotated[StrictInt, Field(ge=1)]
    hidden_target: StrictInt

    @field_validator("selected_round")
    @classmethod
    def _suppressed_round_within_job(cls, value: int) -> int:
        if value > max_rounds():
            raise ValueError(f"selected_round exceeds configured max_rounds {max_rounds()}")
        return value

    @field_validator("release_round")
    @classmethod
    def _release_round_within_window(cls, value: int) -> int:
        if value > release_round_cap():
            raise ValueError(
                f"release_round exceeds configured release cap {release_round_cap()}"
            )
        return value


class WorldState(MutableStrictModel):
    """Authoritative job state; event history is deliberately external."""

    schema_version: Literal["constraint-forge/state/v0"] = "constraint-forge/state/v0"
    run_id: StrictStr
    lineage_id: StrictStr
    job_id: StrictStr
    job_seed: Seed
    # Hidden generator truth used only for deterministic scoring/replay.
    target_matching: tuple[Pair, ...]
    x: StationState
    y: StationState
    # These are the two directional sender-register banks: one bank per sender.
    registers_x: tuple[RegisterState, RegisterState] = (
        RegisterState(),
        RegisterState(),
    )
    registers_y: tuple[RegisterState, RegisterState] = (
        RegisterState(),
        RegisterState(),
    )
    # Authoritative layers and each station's currently visible partner view.
    visible_layer_to_x: Layer = (None, None, None, None, None, None)
    visible_layer_to_y: Layer = (None, None, None, None, None, None)
    round: StrictInt = Field(default=1, ge=1)
    rounds_remaining: StrictInt = Field(
        default_factory=lambda: CONFIG["max_rounds"], ge=0
    )
    terminal: StrictBool = False
    success: StrictBool = False
    pending_writes: tuple[PendingWrite, ...] = ()
    visibility_suppression: VisibilitySuppression | None = None
    intervention: InterventionState | None = None
    visible_effects_x: tuple[StrictStr, ...] = ()
    visible_effects_y: tuple[StrictStr, ...] = ()

    @field_validator("round")
    @classmethod
    def _round_within_job(cls, value: int) -> int:
        if value > max_rounds():
            raise ValueError(f"round exceeds configured max_rounds {max_rounds()}")
        return value

    @field_validator("rounds_remaining")
    @classmethod
    def _remaining_within_job(cls, value: int) -> int:
        if value > max_rounds():
            raise ValueError(
                f"rounds_remaining exceeds configured max_rounds {max_rounds()}"
            )
        return value

    @property
    def station(self) -> dict[Station, StationState]:
        return {Station.X: self.x, Station.Y: self.y}

    @property
    def authoritative_layers(self) -> dict[Station, Layer]:
        return {Station.X: self.x.layer, Station.Y: self.y.layer}


class MemoryOperationResult(StrictModel):
    station: Station
    operation: StrictStr
    legal: StrictBool
    rejection_reason: StrictStr | None = None
    rack_hash_before: StrictStr
    rack_hash_after: StrictStr
    fragment_hash: StrictStr | None = None


class StateTransition(StrictModel):
    """Model-free transition evidence used by tests and deterministic replay."""

    round: Annotated[StrictInt, Field(ge=1)]
    station: Station
    action_id: StrictStr
    action_payload: dict
    legal: StrictBool
    rejection_reason: StrictStr | None = None
    pre_state_hash: StrictStr
    post_state_hash: StrictStr

    @field_validator("round")
    @classmethod
    def _transition_round_within_job(cls, value: int) -> int:
        if value > max_rounds():
            raise ValueError(f"round exceeds configured max_rounds {max_rounds()}")
        return value
