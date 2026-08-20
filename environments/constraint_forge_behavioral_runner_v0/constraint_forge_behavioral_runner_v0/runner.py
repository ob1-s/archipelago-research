"""Specialized two-agent behavioral referee for Constraint Forge V0."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from constraint_forge_formation_v0.canonical import sha256_bytes, stable_hash
from constraint_forge_formation_v0.generator import generate_job
from constraint_forge_formation_v0.models import Station
from constraint_forge_formation_v0.rack import empty_rack
from constraint_forge_formation_v0.session import (
    ConstraintForgeJobSession,
    MemoryOffer,
    MemorySubmitResult,
    ParseClassification,
    RoundOffer,
    RoundSubmitResult,
)
from constraint_forge_formation_v0.world import JobResult
from verifiers.v1 import AssistantMessage

from .audit import AuditLedger, AuditSealStatus, AuditStatus
from .failures import (
    BehavioralCallFailure,
    FailureClass,
    FailureEvidence,
    ambiguous_failure,
    safe_to_retry,
)
from .handoff import FormationHandoffV0, FormationJobReceipt
from .requests import BehavioralRequest, memory_request, round_request

if TYPE_CHECKING:
    from constraint_forge_behavioral_runner_v0.taskset import ConstraintForgeBehavioralTaskData


class DyadAbort(RuntimeError):
    """The dyad cannot continue without guessing about behavioral delivery."""


@dataclass(frozen=True)
class SequenceResult:
    """The handoff plus in-process evidence needed by fake/no-network tests."""

    handoff: FormationHandoffV0
    audit_event_count: int
    live_model_calls: int
    traces: tuple[_InteractionTrace, ...]
    ledger: AuditLedger


@dataclass(frozen=True)
class _CallRecord:
    actor: Literal["X", "Y"]
    actor_id: str
    lifecycle_id: str
    context_epoch: int
    job_index: int
    job_id: str
    phase: Literal["round", "eviction", "retention"]
    round: int | None
    call_id: str
    request: BehavioralRequest
    pre_state_hash: str
    world_event_sequence_before: int
    model_hash: str
    provider_hash: str
    config_hash: str
    raw_output: str
    provider_request_id: str | None = None
    retry_of: str | None = None


@dataclass(frozen=True)
class _InteractionTrace:
    trace: object


@dataclass(frozen=True)
class _FailureRecord:
    record: _CallRecord
    evidence: FailureEvidence
    status: AuditStatus


@dataclass(frozen=True)
class _TurnResult:
    record: _CallRecord | None
    failures: tuple[_FailureRecord, ...] = ()
    error: DyadAbort | None = None


def _hash_payload(value) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return stable_hash(value)


def _agent_identity(actor, role: str) -> tuple[str, str, str, str, str]:
    config = getattr(actor, "config", None)
    config_payload = (
        config.model_dump(mode="json", exclude_none=False)
        if hasattr(config, "model_dump")
        else {"type": type(actor).__qualname__}
    )
    config_hash = _hash_payload(config_payload)
    model_hash = _hash_payload({"model": config_payload.get("model")})
    harness = getattr(actor, "harness", None)
    provider_hash = _hash_payload(
        {
            "harness_type": type(harness).__qualname__ if harness is not None else type(actor).__qualname__,
            "harness_config": getattr(getattr(harness, "config", None), "model_dump", lambda **_: {})(
                mode="json"
            )
            if harness is not None
            else {},
        }
    )
    actor_id = stable_hash(
        {"role": role, "model_hash": model_hash, "provider_hash": provider_hash}
    )[:32]
    lifecycle_id = stable_hash(
        {"role": role, "config_hash": config_hash, "actor_type": type(actor).__qualname__}
    )[:32]
    return actor_id, lifecycle_id, model_hash, provider_hash, config_hash


def _raw_assistant_text(segment) -> tuple[str | None, str | None]:
    """Return exact assistant content and a provider request id when exposed."""

    messages = getattr(segment, "messages", None)
    if messages is not None:
        for message in reversed(messages):
            if isinstance(message, AssistantMessage):
                return message.content or "", getattr(message, "provider_request_id", None)
            if getattr(message, "role", None) == "assistant":
                content = getattr(message, "content", None)
                return (content if isinstance(content, str) else ""), getattr(
                    message, "provider_request_id", None
                )
    if isinstance(segment, str):
        return segment, None
    # A fake provider may expose exact text as a simple property; this fallback
    # is test-only convenience and never strips/normalizes it.
    if hasattr(segment, "raw_output"):
        raw = getattr(segment, "raw_output")
        return (raw if isinstance(raw, str) else None), getattr(segment, "provider_request_id", None)
    return None, None


def _append_failure_audit(
    ledger: AuditLedger,
    record: _CallRecord,
    evidence: FailureEvidence,
    *,
    status: AuditStatus,
) -> None:
    ledger.append(
        actor=record.actor,
        actor_id=record.actor_id,
        lifecycle_id=record.lifecycle_id,
        context_epoch=record.context_epoch,
        job_index=record.job_index,
        job_id=record.job_id,
        phase=record.phase,
        round=record.round,
        call_id=record.call_id,
        retry_of=record.retry_of,
        pre_state_hash=record.pre_state_hash,
        world_event_sequence_before=record.world_event_sequence_before,
        request_hash=record.request.request_hash,
        model_hash=record.model_hash,
        provider_hash=record.provider_hash,
        config_hash=record.config_hash,
        provider_status=evidence.provider_status,
        provider_request_id=evidence.provider_request_id,
        raw_output=None,
        raw_output_hash=None,
        parse_classification="not_applicable",
        world_event_sequence_start=None,
        world_event_sequence_end=None,
        post_state_hash=record.pre_state_hash,
        status=status,
        failure_class=evidence.failure_class.value,
    )


def _append_success_audit(
    ledger: AuditLedger,
    record: _CallRecord,
    *,
    parse_classification: ParseClassification | str,
    post_state_hash: str,
    event_start: int | None,
    event_end: int | None,
    status: AuditStatus,
) -> None:
    raw_hash = sha256_bytes(record.raw_output.encode("utf-8"))
    ledger.append(
        actor=record.actor,
        actor_id=record.actor_id,
        lifecycle_id=record.lifecycle_id,
        context_epoch=record.context_epoch,
        job_index=record.job_index,
        job_id=record.job_id,
        phase=record.phase,
        round=record.round,
        call_id=record.call_id,
        retry_of=record.retry_of,
        pre_state_hash=record.pre_state_hash,
        world_event_sequence_before=record.world_event_sequence_before,
        request_hash=record.request.request_hash,
        model_hash=record.model_hash,
        provider_hash=record.provider_hash,
        config_hash=record.config_hash,
        provider_status="completed",
        provider_request_id=record.provider_request_id,
        raw_output=record.raw_output,
        raw_output_hash=raw_hash,
        parse_classification=(
            parse_classification.value
            if isinstance(parse_classification, ParseClassification)
            else parse_classification
        ),
        world_event_sequence_start=event_start,
        world_event_sequence_end=event_end,
        post_state_hash=post_state_hash,
        status=status,
    )


async def _turn_with_safe_retry(
    *,
    interaction,
    request: BehavioralRequest,
    actor: Literal["X", "Y"],
    actor_id: str,
    lifecycle_id: str,
    model_hash: str,
    provider_hash: str,
    config_hash: str,
    job_index: int,
    job_id: str,
    phase: Literal["round", "eviction", "retention"],
    round_number: int | None,
    world_event_sequence_before: int,
) -> _TurnResult:
    retry_of: str | None = None
    failures: list[_FailureRecord] = []
    for attempt in range(2):
        call_id = (
            f"{job_id}:{phase}:{'r'+str(round_number) if round_number is not None else phase}"
            f":{actor}:attempt{attempt}"
        )
        record = _CallRecord(
            actor=actor,
            actor_id=actor_id,
            lifecycle_id=lifecycle_id,
            context_epoch=job_index,
            job_index=job_index,
            job_id=job_id,
            phase=phase,
            round=round_number,
            call_id=call_id,
            request=request,
            pre_state_hash=request.pre_state_hash,
            world_event_sequence_before=world_event_sequence_before,
            model_hash=model_hash,
            provider_hash=provider_hash,
            config_hash=config_hash,
            raw_output="",
            retry_of=retry_of,
        )
        try:
            segment = await interaction.turn(request.prompt_text)
            raw_output, request_id = _raw_assistant_text(segment)
            if raw_output is None:
                raise BehavioralCallFailure(
                    FailureEvidence(
                        failure_class=FailureClass.PARTIAL_RESPONSE,
                        request_dispatched=True,
                        behavioral_sample_produced=None,
                        detail="provider segment contained no assistant message",
                    )
                )
            return _TurnResult(
                record=_CallRecord(
                    **{
                        **record.__dict__,
                        "raw_output": raw_output,
                        "provider_request_id": request_id,
                    }
                ),
                failures=tuple(failures),
            )
        except BehavioralCallFailure as exc:
            evidence = exc.evidence
            status = (
                AuditStatus.SAFE_RETRY
                if safe_to_retry(evidence) and attempt == 0
                else AuditStatus.FAILED
            )
            failures.append(_FailureRecord(record, evidence, status))
            if safe_to_retry(evidence) and attempt == 0:
                retry_of = call_id
                continue
            return _TurnResult(
                record=None,
                failures=tuple(failures),
                error=DyadAbort(
                    f"{actor} {phase} call {call_id} failed: {evidence.failure_class.value}"
                ),
            )
        except TimeoutError as exc:
            failure = ambiguous_failure(str(exc) or "behavioral call timed out", timeout=True)
            failures.append(_FailureRecord(record, failure.evidence, AuditStatus.FAILED))
            return _TurnResult(
                record=None,
                failures=tuple(failures),
                error=DyadAbort(f"{actor} {phase} call timed out"),
            )
        except Exception as exc:  # provider/runtime delivery is ambiguous by default
            failure = ambiguous_failure(f"{type(exc).__name__}: {exc}")
            failures.append(_FailureRecord(record, failure.evidence, AuditStatus.FAILED))
            return _TurnResult(
                record=None,
                failures=tuple(failures),
                error=DyadAbort(f"{actor} {phase} call delivery is ambiguous"),
            )
    return _TurnResult(record=None, failures=tuple(failures), error=DyadAbort("safe retry loop exhausted"))


async def _dispatch_pair(
    *,
    interaction_x,
    interaction_y,
    request_x: BehavioralRequest,
    request_y: BehavioralRequest,
    identity_x: tuple[str, str, str, str, str],
    identity_y: tuple[str, str, str, str, str],
    job_index: int,
    job_id: str,
    phase: Literal["round", "eviction", "retention"],
    round_number: int | None,
    world_event_sequence_before: int,
    ledger: AuditLedger,
) -> tuple[_CallRecord, _CallRecord]:
    # Requests are fully materialized and hashed before either coroutine is
    # scheduled.  gather preserves role association even when completion order
    # differs.
    if request_x.pre_state_hash != request_y.pre_state_hash:
        raise DyadAbort("X/Y requests did not share one pre-state hash")
    if request_x.request_hash == request_y.request_hash:
        # Same bytes are not prohibited, but role labels must still make the two
        # sealed requests explicit; this guard catches accidental aliasing in
        # callers that mutate a request object after construction.
        if request_x.role == request_y.role:
            raise DyadAbort("X/Y request roles were not distinct")
    results = await asyncio.gather(
        _turn_with_safe_retry(
            interaction=interaction_x,
            request=request_x,
            actor="X",
            actor_id=identity_x[0],
            lifecycle_id=identity_x[1],
            model_hash=identity_x[2],
            provider_hash=identity_x[3],
            config_hash=identity_x[4],
            job_index=job_index,
            job_id=job_id,
            phase=phase,
            round_number=round_number,
            world_event_sequence_before=world_event_sequence_before,
        ),
        _turn_with_safe_retry(
            interaction=interaction_y,
            request=request_y,
            actor="Y",
            actor_id=identity_y[0],
            lifecycle_id=identity_y[1],
            model_hash=identity_y[2],
            provider_hash=identity_y[3],
            config_hash=identity_y[4],
            job_index=job_index,
            job_id=job_id,
            phase=phase,
            round_number=round_number,
            world_event_sequence_before=world_event_sequence_before,
        ),
        return_exceptions=True,
    )
    # A task-level cancellation/bug is still converted into an ambiguous pair
    # failure, while ordinary provider evidence arrives as _TurnResult data.
    normalized: list[_TurnResult] = []
    for result in results:
        if isinstance(result, BaseException):
            normalized.append(
                _TurnResult(
                    record=None,
                    error=DyadAbort(f"partner call raised {type(result).__name__}"),
                )
            )
        else:
            normalized.append(result)
    for result in normalized:
        for failure in result.failures:
            _append_failure_audit(
                ledger,
                failure.record,
                failure.evidence,
                status=failure.status,
            )
    errors = [result.error for result in normalized if result.error is not None]
    successes = [result.record for result in normalized if result.record is not None]
    if errors:
        # A sibling response can be real even though the pair cannot advance.
        # Preserve it as audit-only; never feed it into the world or resample it.
        for record in successes:
            _append_success_audit(
                ledger,
                record,
                parse_classification="audit_only",
                post_state_hash=record.pre_state_hash,
                event_start=None,
                event_end=None,
                status=AuditStatus.AUDIT_ONLY,
            )
        error = errors[0]
        for record in successes:
            _append_success_audit(
                ledger,
                record,
                parse_classification="audit_only",
                post_state_hash=record.pre_state_hash,
                event_start=None,
                event_end=None,
                status=AuditStatus.AUDIT_ONLY,
            )
        raise error
    return normalized[0].record, normalized[1].record  # type: ignore[return-value]


def _record_round_successes(
    ledger: AuditLedger,
    calls: tuple[_CallRecord, _CallRecord],
    result: RoundSubmitResult,
) -> None:
    _append_success_audit(
        ledger,
        calls[0],
        parse_classification=result.parse_x,
        post_state_hash=result.post_state_hash,
        event_start=result.event_sequence_start,
        event_end=result.event_sequence_end,
        status=AuditStatus.COMPLETED,
    )
    _append_success_audit(
        ledger,
        calls[1],
        parse_classification=result.parse_y,
        post_state_hash=result.post_state_hash,
        event_start=result.event_sequence_start,
        event_end=result.event_sequence_end,
        status=AuditStatus.COMPLETED,
    )


def _record_memory_successes(
    ledger: AuditLedger,
    calls: tuple[_CallRecord, _CallRecord],
    result: MemorySubmitResult,
) -> None:
    _append_success_audit(
        ledger,
        calls[0],
        parse_classification=result.parse_x,
        post_state_hash=calls[0].pre_state_hash,
        event_start=result.event_sequence_start,
        event_end=result.event_sequence_end,
        status=AuditStatus.COMPLETED,
    )
    _append_success_audit(
        ledger,
        calls[1],
        parse_classification=result.parse_y,
        post_state_hash=calls[1].pre_state_hash,
        event_start=result.event_sequence_start,
        event_end=result.event_sequence_end,
        status=AuditStatus.COMPLETED,
    )


def _job_id(sequence_id: str, index: int) -> str:
    return f"{sequence_id}:job-{index:02d}"


def _intervention_at(data, index: int):
    interventions = getattr(data, "interventions", ())
    return interventions[index] if len(interventions) == len(data.job_seeds) else None


def _read_only_at(data, index: int) -> bool:
    return index in set(getattr(data, "read_only_job_indices", ()))


async def run_behavioral_sequence(
    data: "ConstraintForgeBehavioralTaskData",
    *,
    actor_x,
    actor_y,
    task,
) -> SequenceResult:
    """Run one full sequence using persistent role agents and fresh job contexts."""

    run_id = data.sequence_id
    dyad_id = stable_hash({"run_id": run_id, "protocol": data.protocol_version})[:32]
    identity_x = _agent_identity(actor_x, "X")
    identity_y = _agent_identity(actor_y, "Y")
    ledger = AuditLedger(run_id=run_id, dyad_id=dyad_id)
    receipts: list[FormationJobReceipt] = []
    rack_x = empty_rack()
    rack_y = empty_rack()
    traces: list[_InteractionTrace] = []
    last_state_hash = stable_hash({"sequence": run_id, "state": "not_started"})
    abort_class: str | None = None

    try:
        for job_index, seed in enumerate(data.job_seeds):
            job_id = _job_id(data.sequence_id, job_index)
            job = generate_job(seed)
            session = ConstraintForgeJobSession.open(
                job,
                run_id=run_id,
                lineage_id=dyad_id,
                job_id=job_id,
                rack_x=rack_x,
                rack_y=rack_y,
                intervention=_intervention_at(data, job_index),
                read_only_probe=_read_only_at(data, job_index),
            )
            # A new interaction is the supported v1 context boundary.  The
            # underlying _EpisodeAgent objects (and therefore role lifecycle
            # identity/config) remain the same across this whole loop.
            async with actor_x.interaction(task) as interaction_x:
                async with actor_y.interaction(task) as interaction_y:
                    traces.extend((_InteractionTrace(interaction_x.trace), _InteractionTrace(interaction_y.trace)))
                    while not session.terminal:
                        offer: RoundOffer = session.begin_round()
                        request_x = round_request(
                            role="X",
                            job_index=job_index,
                            job_id=job_id,
                            context_epoch=job_index,
                            pre_state_hash=offer.pre_state_hash,
                            observation=offer.observation_x,
                        )
                        request_y = round_request(
                            role="Y",
                            job_index=job_index,
                            job_id=job_id,
                            context_epoch=job_index,
                            pre_state_hash=offer.pre_state_hash,
                            observation=offer.observation_y,
                        )
                        calls = await _dispatch_pair(
                            interaction_x=interaction_x,
                            interaction_y=interaction_y,
                            request_x=request_x,
                            request_y=request_y,
                            identity_x=identity_x,
                            identity_y=identity_y,
                            job_index=job_index,
                            job_id=job_id,
                            phase="round",
                            round_number=offer.round,
                            world_event_sequence_before=offer.event_sequence_before,
                            ledger=ledger,
                        )
                        round_result = session.submit_round(
                            token=offer.token,
                            raw_x=calls[0].raw_output,
                            raw_y=calls[1].raw_output,
                        )
                        _record_round_successes(ledger, calls, round_result)

                    eviction_offer = session.begin_eviction()
                    if eviction_offer is not None:
                        request_x = memory_request(
                            role="X",
                            phase="eviction",
                            job_index=job_index,
                            job_id=job_id,
                            context_epoch=job_index,
                            pre_state_hash=eviction_offer.state_hash,
                            rack=eviction_offer.rack_view_x,
                            frames=eviction_offer.frames_x,
                        )
                        request_y = memory_request(
                            role="Y",
                            phase="eviction",
                            job_index=job_index,
                            job_id=job_id,
                            context_epoch=job_index,
                            pre_state_hash=eviction_offer.state_hash,
                            rack=eviction_offer.rack_view_y,
                            frames=eviction_offer.frames_y,
                        )
                        calls = await _dispatch_pair(
                            interaction_x=interaction_x,
                            interaction_y=interaction_y,
                            request_x=request_x,
                            request_y=request_y,
                            identity_x=identity_x,
                            identity_y=identity_y,
                            job_index=job_index,
                            job_id=job_id,
                            phase="eviction",
                            round_number=None,
                            world_event_sequence_before=eviction_offer.event_sequence_before,
                            ledger=ledger,
                        )
                        eviction_result = session.submit_eviction(
                            token=eviction_offer.token,
                            raw_x=calls[0].raw_output,
                            raw_y=calls[1].raw_output,
                        )
                        _record_memory_successes(ledger, calls, eviction_result)

                        retention_offer = session.begin_retention()
                        request_x = memory_request(
                            role="X",
                            phase="retention",
                            job_index=job_index,
                            job_id=job_id,
                            context_epoch=job_index,
                            pre_state_hash=retention_offer.state_hash,
                            rack=retention_offer.rack_view_x,
                            frames=retention_offer.frames_x,
                        )
                        request_y = memory_request(
                            role="Y",
                            phase="retention",
                            job_index=job_index,
                            job_id=job_id,
                            context_epoch=job_index,
                            pre_state_hash=retention_offer.state_hash,
                            rack=retention_offer.rack_view_y,
                            frames=retention_offer.frames_y,
                        )
                        calls = await _dispatch_pair(
                            interaction_x=interaction_x,
                            interaction_y=interaction_y,
                            request_x=request_x,
                            request_y=request_y,
                            identity_x=identity_x,
                            identity_y=identity_y,
                            job_index=job_index,
                            job_id=job_id,
                            phase="retention",
                            round_number=None,
                            world_event_sequence_before=retention_offer.event_sequence_before,
                            ledger=ledger,
                        )
                        retention_result = session.submit_retention(
                            token=retention_offer.token,
                            raw_x=calls[0].raw_output,
                            raw_y=calls[1].raw_output,
                        )
                        _record_memory_successes(ledger, calls, retention_result)

                    job_result: JobResult = session.result()
                    rack_x = job_result.final_rack_x
                    rack_y = job_result.final_rack_y
                    last_state_hash = job_result.final_state_hash
                    receipts.append(
                        FormationJobReceipt(
                            job_index=job_index,
                            job_id=job_id,
                            job_seed=job_result.job_seed,
                            success=job_result.success,
                            final_state_hash=job_result.final_state_hash,
                            event_log_hash=job_result.event_log.content_hash,
                            final_rack_x_hash=rack_x.content_hash,
                            final_rack_y_hash=rack_y.content_hash,
                        )
                    )
    except DyadAbort as exc:
        abort_class = type(exc).__name__
    except Exception as exc:
        # A referee/programming failure is still an abort, never a resampling
        # opportunity.  No call is labeled successful after this boundary.
        abort_class = f"runner_error:{type(exc).__name__}"

    seal_status = AuditSealStatus.ABORTED if abort_class is not None else AuditSealStatus.COMPLETED
    seal = ledger.seal(seal_status)
    handoff = FormationHandoffV0(
        run_id=run_id,
        dyad_id=dyad_id,
        lineage_x=identity_x[1],
        lineage_y=identity_y[1],
        accepted=(
            abort_class is None
            and len(receipts) == len(data.job_seeds)
            and all(receipt.success for receipt in receipts)
        ),
        aborted=abort_class is not None,
        abort_class=abort_class,
        completed_jobs=len(receipts),
        job_receipts=tuple(receipts),
        audit_chain_hash=ledger.final_hash,
        audit_seal_hash=stable_hash(seal.model_dump(mode="json")),
        final_state_hash_x=last_state_hash,
        final_state_hash_y=last_state_hash,
        final_rack_x_bytes=rack_x.serialization_bytes,
        final_rack_y_bytes=rack_y.serialization_bytes,
    )
    return SequenceResult(
        handoff=handoff,
        audit_event_count=len(ledger.events),
        live_model_calls=0,
        traces=tuple(traces),
        ledger=ledger,
    )


__all__ = ["DyadAbort", "SequenceResult", "run_behavioral_sequence"]
