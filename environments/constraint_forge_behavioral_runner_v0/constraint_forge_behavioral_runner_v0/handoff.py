"""Deterministic, pre-H1 formation handoff artifact."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from constraint_forge_formation_v0.canonical import canonical_bytes, sha256_bytes
from constraint_forge_formation_v0.models import StrictModel, Seed


class FormationJobReceipt(StrictModel):
    schema_version: Literal["constraint-forge/formation-job-receipt/v0"] = (
        "constraint-forge/formation-job-receipt/v0"
    )
    job_index: StrictInt = Field(ge=0)
    job_id: StrictStr
    job_seed: Seed
    success: StrictBool
    failure_reason: StrictStr | None = None
    final_state_hash: StrictStr
    event_log_hash: StrictStr
    final_rack_x_hash: StrictStr
    final_rack_y_hash: StrictStr


class FormationHandoffV0(StrictModel):
    """What formation produces for a later audit; not an H1 carrier/proof."""

    schema_version: Literal["constraint-forge/formation-handoff/v0"] = (
        "constraint-forge/formation-handoff/v0"
    )
    run_id: StrictStr
    dyad_id: StrictStr
    lineage_x: StrictStr
    lineage_y: StrictStr
    run_valid: StrictBool
    planned_jobs: StrictInt = Field(ge=0)
    accepted: StrictBool
    aborted: StrictBool
    abort_class: StrictStr | None = None
    completed_jobs: StrictInt = Field(ge=0)
    successful_jobs: StrictInt = Field(ge=0)
    job_success_mean: StrictFloat = Field(ge=0.0, le=1.0)
    job_receipts: tuple[FormationJobReceipt, ...] = ()
    audit_chain_hash: StrictStr
    audit_seal_hash: StrictStr
    final_state_hash_x: StrictStr
    final_state_hash_y: StrictStr
    final_rack_x_bytes: bytes
    final_rack_y_bytes: bytes

    @model_validator(mode="after")
    def validate_job_summary(self) -> "FormationHandoffV0":
        if self.completed_jobs != len(self.job_receipts):
            raise ValueError("completed_jobs must equal the retained receipt count")
        if self.completed_jobs > self.planned_jobs:
            raise ValueError("completed_jobs cannot exceed planned_jobs")
        if self.successful_jobs > self.completed_jobs:
            raise ValueError("successful_jobs cannot exceed completed_jobs")
        if self.completed_jobs == 0 and self.job_success_mean != 0.0:
            raise ValueError("empty runs must have zero job-success mean")
        if self.completed_jobs and self.job_success_mean != (
            self.successful_jobs / self.completed_jobs
        ):
            raise ValueError("job_success_mean does not match retained receipts")
        if self.accepted != self.run_valid:
            raise ValueError("accepted is the compatibility alias for run_valid")
        return self

    @property
    def final_rack_x_bytes_hex(self) -> str:
        return self.final_rack_x_bytes.hex()

    @property
    def final_rack_y_bytes_hex(self) -> str:
        return self.final_rack_y_bytes.hex()

    @property
    def serialization_bytes(self) -> bytes:
        return canonical_bytes(self.model_dump(mode="json"))

    @property
    def content_hash(self) -> str:
        return sha256_bytes(self.serialization_bytes)


__all__ = ["FormationHandoffV0", "FormationJobReceipt"]
