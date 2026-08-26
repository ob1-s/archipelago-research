"""Frozen 12-dyad exploratory formation cohort on the qualified Ox/Zen boundary.

The scientific specification lives in the frozen taskset, schedule, protocol,
runner, and harness modules. This module only instantiates the declared
12-sequence cohort once per dyad, executes it under one frozen provider
configuration, and persists per-dyad evidence plus a cohort manifest sufficient
to reconstruct exactly what ran. It owns no scientific rule.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr

from constraint_forge_formation_v0.canonical import canonical_bytes, sha256_bytes, stable_hash
from constraint_forge_formation_v0.models import StrictModel

from .audit import AuditSeal, AuditStatus, RunnerAuditEvent
from .evidence import JobEvidenceV0, TraceEvidenceV0
from .handoff import FormationHandoffV0
from .schedule import JOB_COUNT
from .taskset import (
    ConstraintForgeBehavioralTask,
    ConstraintForgeBehavioralTaskset,
    ConstraintForgeBehavioralTasksetConfig,
)

COHORT_SCHEMA_VERSION = "constraint-forge/cohort-manifest/v0"
DYAD_SCHEMA_VERSION = "constraint-forge/cohort-dyad-evidence/v0"
COHORT_SEED_PREFIX = "constraint-forge/behavioral-sequence-v0"
COHORT_NUM_DYADS = 12
# 24 jobs x (16 rounds + eviction + retention) is the exact worst case per role.
COHORT_MAX_TURNS_PER_ROLE = JOB_COUNT * 18
CONSECUTIVE_INFRA_ABORT_STOP = 3
# Under --concurrency N the sequential streak translates to: stop scheduling
# once this many executed dyads have aborted and none has completed.
PARALLEL_ABORT_STOP_TOTAL = CONSECUTIVE_INFRA_ABORT_STOP
# Jobs 10..17 are the final eight writable ordinary slots (gate-1 input).
FINAL_EIGHT_NONOCCLUDED_INDICES = tuple(range(10, 18))


class CohortProviderConfigV0(StrictModel):
    model: StrictStr
    base_url: StrictStr
    x_key_var: StrictStr
    y_key_var: StrictStr
    shared_credential: StrictBool
    max_completion_tokens: StrictInt
    reasoning_effort: StrictStr | None = None
    call_timeout_seconds: StrictInt = 120
    max_retries: StrictInt = 0
    # Declared cohort-v1 retry budget: identical re-dispatch per behavioral
    # opportunity after explicit infrastructure statuses (429/500/502/503/504)
    # that provably delivered no response. Completed responses, malformed
    # actions, length stops, refusals, and timeouts are never retried.
    infra_retries: StrictInt = 0
    infra_backoff_seconds: tuple[StrictInt, ...] = (4, 8)


class CohortSequenceRowV0(StrictModel):
    dyad_index: StrictInt = Field(ge=0)
    sequence_id: StrictStr
    plan_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    plan_serialization: dict


class DyadStatus(StrEnum):
    NOT_STARTED = "not_started"
    COMPLETED = "completed"
    ABORTED = "aborted"


class DyadSummaryRowV0(StrictModel):
    dyad_index: StrictInt = Field(ge=0)
    sequence_id: StrictStr
    plan_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    status: DyadStatus
    abort_class: StrictStr | None = None
    rerun_after_crash: StrictBool = False
    live_model_calls: StrictInt = 0
    infra_retry_events: StrictInt = 0
    completed_jobs: StrictInt = 0
    successful_jobs: StrictInt = 0
    job_success_mean: float = 0.0
    final_eight_nonoccluded_success_mean: float = 0.0
    retained_films_x: StrictInt = 0
    retained_films_y: StrictInt = 0
    evidence_path: StrictStr
    evidence_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class CohortManifestV0(StrictModel):
    schema_version: Literal["constraint-forge/cohort-manifest/v0"] = COHORT_SCHEMA_VERSION
    eligibility: Literal["constraint-forge/exploratory-formation-cohort-v0"] = (
        "constraint-forge/exploratory-formation-cohort-v0"
    )
    cohort_id: StrictStr
    freeze_commit: StrictStr
    protocol_version: Literal["constraint-forge/behavioral-runner-r1"] = (
        "constraint-forge/behavioral-runner-r1"
    )
    seed_prefix: StrictStr
    num_dyads: StrictInt = Field(ge=1)
    qualification_canary_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    provider_config: CohortProviderConfigV0
    sequences: tuple[CohortSequenceRowV0, ...]
    stop_rule: StrictStr = (
        "one execution attempt per dyad; aborts are final and preserved; "
        f"stop cleanly after {CONSECUTIVE_INFRA_ABORT_STOP} consecutive "
        "infrastructure-class dyad aborts"
    )
    manifest_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class DyadEvidenceBundleV0(StrictModel):
    """Self-contained evidence for one executed cohort dyad."""

    schema_version: Literal["constraint-forge/cohort-dyad-evidence/v0"] = (
        DYAD_SCHEMA_VERSION
    )
    cohort_id: StrictStr
    dyad_index: StrictInt = Field(ge=0)
    sequence_id: StrictStr
    plan_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    freeze_commit: StrictStr
    started_utc: StrictStr
    finished_utc: StrictStr
    rerun_after_crash: StrictBool = False
    handoff: FormationHandoffV0
    audit_events: tuple[RunnerAuditEvent, ...]
    audit_seal: AuditSeal
    jobs: tuple[JobEvidenceV0, ...] = ()
    traces: tuple[TraceEvidenceV0, ...] = ()

    @property
    def serialization_bytes(self) -> bytes:
        return canonical_bytes(self.model_dump(mode="json"))

    @property
    def content_hash(self) -> str:
        return sha256_bytes(self.serialization_bytes)


def build_cohort_tasks() -> list[ConstraintForgeBehavioralTask]:
    """The declared 12-dyad manifest from the frozen taskset configuration."""

    taskset = ConstraintForgeBehavioralTaskset(
        ConstraintForgeBehavioralTasksetConfig(
            id="constraint-forge-formation-cohort-ox-v0",
            seed_prefix=COHORT_SEED_PREFIX,
            num_sequences=COHORT_NUM_DYADS,
        )
    )
    return list(taskset)


def build_manifest(
    *,
    cohort_id: str,
    freeze_commit: str,
    provider_config: CohortProviderConfigV0,
    qualification_canary_sha256: str,
    tasks: list[ConstraintForgeBehavioralTask],
) -> CohortManifestV0:
    sequences = tuple(
        CohortSequenceRowV0(
            dyad_index=task.data.idx,
            sequence_id=task.data.sequence_id,
            plan_hash=task.data.plan_hash,
            plan_serialization=task.data.run_plan.serialization_payload,
        )
        for task in tasks
    )
    payload = {
        "cohort_id": cohort_id,
        "freeze_commit": freeze_commit,
        "seed_prefix": COHORT_SEED_PREFIX,
        "num_dyads": len(tasks),
        "provider_config": provider_config.model_dump(mode="json"),
        "sequences": [row.model_dump(mode="json") for row in sequences],
    }
    return CohortManifestV0(
        cohort_id=cohort_id,
        freeze_commit=freeze_commit,
        seed_prefix=COHORT_SEED_PREFIX,
        num_dyads=len(tasks),
        qualification_canary_sha256=qualification_canary_sha256,
        provider_config=provider_config,
        sequences=sequences,
        manifest_hash=stable_hash(payload),
    )


def final_eight_nonoccluded_mean(handoff: FormationHandoffV0) -> float:
    """Success mean over the final eight writable ordinary jobs (gate-1 input)."""

    receipts = {receipt.job_index: receipt.success for receipt in handoff.job_receipts}
    observed = [receipts[index] for index in FINAL_EIGHT_NONOCCLUDED_INDICES if index in receipts]
    if not observed:
        return 0.0
    return sum(bool(success) for success in observed) / len(observed)


def _count_calls(bundle: DyadEvidenceBundleV0) -> int:
    return sum(len(trace.native_calls) for trace in bundle.traces)


def _count_infra_retries(bundle: DyadEvidenceBundleV0) -> int:
    return sum(
        1
        for event in bundle.audit_events
        if getattr(event.status, "value", event.status) == AuditStatus.INFRA_RETRY.value
    )


def dyad_summary_row(
    *,
    bundle: DyadEvidenceBundleV0,
    evidence_path: Path,
) -> DyadSummaryRowV0:
    handoff = bundle.handoff
    last_job = bundle.jobs[-1] if bundle.jobs else None
    return DyadSummaryRowV0(
        dyad_index=bundle.dyad_index,
        sequence_id=bundle.sequence_id,
        plan_hash=bundle.plan_hash,
        status=DyadStatus.ABORTED if handoff.aborted else DyadStatus.COMPLETED,
        abort_class=handoff.abort_class,
        rerun_after_crash=bundle.rerun_after_crash,
        live_model_calls=_count_calls(bundle),
        infra_retry_events=_count_infra_retries(bundle),
        completed_jobs=handoff.completed_jobs,
        successful_jobs=handoff.successful_jobs,
        job_success_mean=handoff.job_success_mean,
        final_eight_nonoccluded_success_mean=final_eight_nonoccluded_mean(handoff),
        retained_films_x=len(last_job.rack_x.films) if last_job else 0,
        retained_films_y=len(last_job.rack_y.films) if last_job else 0,
        evidence_path=str(evidence_path),
        evidence_sha256=bundle.content_hash,
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_atomic(path: Path, payload: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(payload)
    tmp.replace(path)


__all__ = [
    "COHORT_MAX_TURNS_PER_ROLE",
    "COHORT_NUM_DYADS",
    "COHORT_SCHEMA_VERSION",
    "COHORT_SEED_PREFIX",
    "CONSECUTIVE_INFRA_ABORT_STOP",
    "PARALLEL_ABORT_STOP_TOTAL",
    "DyadEvidenceBundleV0",
    "DyadStatus",
    "DyadSummaryRowV0",
    "CohortManifestV0",
    "CohortProviderConfigV0",
    "CohortSequenceRowV0",
    "build_cohort_tasks",
    "build_manifest",
    "dyad_summary_row",
    "final_eight_nonoccluded_mean",
    "utc_now",
    "write_atomic",
]
