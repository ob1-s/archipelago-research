"""Canonical persisted evidence bundle for non-scientific behavioral canaries."""

from __future__ import annotations

from typing import Literal

from pydantic import StrictBool, StrictStr

from constraint_forge_behavioral_runner_r2._r2_world.canonical import canonical_bytes, sha256_bytes
from constraint_forge_behavioral_runner_r2._r2_world.events import EventLog
from constraint_forge_behavioral_runner_r2._r2_world.models import Seed, StrictModel
from constraint_forge_behavioral_runner_r2._r2_world.rack import RackMutation, RackState

from .audit import AuditSeal, RunnerAuditEvent
from .handoff import FormationHandoffV0


class JobEvidenceV0(StrictModel):
    """Typed world/rack evidence, including an interrupted active job if any."""

    job_id: StrictStr
    job_seed: Seed
    complete: StrictBool
    event_log: EventLog
    rack_x: RackState
    rack_y: RackState
    memory_mutations_x: tuple[RackMutation, ...] = ()
    memory_mutations_y: tuple[RackMutation, ...] = ()


class TraceEvidenceV0(StrictModel):
    role: Literal["X", "Y"]
    lifecycle_id: StrictStr
    trace_id: StrictStr
    agent_config: dict
    provider_requests: tuple[dict, ...] = ()
    # Sanitized native call summaries are persisted so a failed live canary says
    # *why* the provider call failed instead of only recording "partial_response".
    # Tracebacks are intentionally omitted; the launcher's byte-level secret scan
    # still runs over the complete artifact before it is written.
    native_calls: tuple[dict, ...] = ()


class CanaryEvidenceBundleV0(StrictModel):
    """Self-contained evidence for a throwaway plumbing canary.

    This artifact is deliberately ineligible for scientific analysis. Scientific
    formation runs will require a separately frozen cohort manifest and explicit
    eligibility decision after the canary passes.
    """

    schema_version: Literal["constraint-forge/canary-evidence/v0"] = (
        "constraint-forge/canary-evidence/v0"
    )
    scientific_eligible: Literal[False] = False
    run_id: StrictStr
    dyad_id: StrictStr
    handoff: FormationHandoffV0
    audit_events: tuple[RunnerAuditEvent, ...]
    audit_seal: AuditSeal
    jobs: tuple[JobEvidenceV0, ...]
    traces: tuple[TraceEvidenceV0, ...]

    @property
    def serialization_bytes(self) -> bytes:
        return canonical_bytes(self.model_dump(mode="json"))

    @property
    def content_hash(self) -> str:
        return sha256_bytes(self.serialization_bytes)


__all__ = ["CanaryEvidenceBundleV0", "JobEvidenceV0", "TraceEvidenceV0"]
