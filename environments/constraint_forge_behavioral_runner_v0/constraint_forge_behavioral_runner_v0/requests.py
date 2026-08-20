"""Role-local text requests produced by the behavioral referee."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, StrictInt, StrictStr

from constraint_forge_formation_v0.canonical import canonical_bytes, sha256_bytes
from constraint_forge_formation_v0.models import StrictModel
from constraint_forge_formation_v0.rack import FilmFrame, RackView
from constraint_forge_formation_v0.world import Observation


FROZEN_REQUEST_INSTRUCTIONS = (
    "Return exactly one compact JSON object and no surrounding prose. "
    "For a round choose one world action from the available schema. "
    "For eviction choose evict or keep_unchanged. For retention choose retain "
    "with a six-round start_round or keep_unchanged."
)


class BehavioralRequest(StrictModel):
    schema_version: Literal["constraint-forge/behavioral-request/v0"] = (
        "constraint-forge/behavioral-request/v0"
    )
    role: Literal["X", "Y"]
    phase: Literal["round", "eviction", "retention"]
    round: StrictInt | None = Field(default=None, ge=1, le=16)
    job_index: StrictInt = Field(ge=0)
    job_id: StrictStr
    context_epoch: StrictInt = Field(ge=0)
    pre_state_hash: StrictStr
    observation: Observation | None = None
    rack: RackView | None = None
    frames: tuple[FilmFrame, ...] = ()
    instructions: StrictStr = FROZEN_REQUEST_INSTRUCTIONS

    @property
    def visible_payload(self) -> dict:
        """The exact role-local payload sent as the user message."""

        return {
            "schema_version": self.schema_version,
            "role": self.role,
            "phase": self.phase,
            "round": self.round,
            "job_index": self.job_index,
            "job_id": self.job_id,
            "context_epoch": self.context_epoch,
            "pre_state_hash": self.pre_state_hash,
            "observation": self.observation.model_dump(mode="json")
            if self.observation is not None
            else None,
            "rack": self.rack.model_dump(mode="json") if self.rack is not None else None,
            "frames": [frame.model_dump(mode="json") for frame in self.frames],
            "instructions": self.instructions,
        }

    @property
    def request_hash(self) -> str:
        return sha256_bytes(canonical_bytes(self.visible_payload))

    @property
    def prompt_text(self) -> str:
        return canonical_bytes(self.visible_payload).decode("utf-8")


def round_request(
    *,
    role: Literal["X", "Y"],
    job_index: int,
    job_id: str,
    context_epoch: int,
    pre_state_hash: str,
    observation: Observation,
) -> BehavioralRequest:
    return BehavioralRequest(
        role=role,
        phase="round",
        round=observation.round,
        job_index=job_index,
        job_id=job_id,
        context_epoch=context_epoch,
        pre_state_hash=pre_state_hash,
        observation=observation,
    )


def memory_request(
    *,
    role: Literal["X", "Y"],
    phase: Literal["eviction", "retention"],
    job_index: int,
    job_id: str,
    context_epoch: int,
    pre_state_hash: str,
    rack: RackView,
    frames: tuple[FilmFrame, ...],
) -> BehavioralRequest:
    return BehavioralRequest(
        role=role,
        phase=phase,
        job_index=job_index,
        job_id=job_id,
        context_epoch=context_epoch,
        pre_state_hash=pre_state_hash,
        rack=rack,
        frames=frames,
    )


__all__ = [
    "BehavioralRequest",
    "FROZEN_REQUEST_INSTRUCTIONS",
    "memory_request",
    "round_request",
]
