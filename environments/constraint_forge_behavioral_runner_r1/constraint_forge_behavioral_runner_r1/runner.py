"""Specialized two-agent behavioral referee for Constraint Forge V0."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from constraint_forge_formation_v0.canonical import sha256_bytes, stable_hash
from constraint_forge_formation_v0.generator import generate_job
from constraint_forge_formation_v0.rack import empty_rack
from constraint_forge_formation_v0.session import (
    ConstraintForgeJobSession,
    MemorySubmitResult,
    ParseClassification,
    RoundOffer,
    RoundSubmitResult,
)
from constraint_forge_formation_v0.world import JobResult
from verifiers.v1 import AssistantMessage

from .audit import AuditLedger, AuditSealStatus, AuditStatus
from .handoff import RackWipeRecord
from .r1_physics import r1_adjudicate, r1_void, station_note
from .evidence import CanaryEvidenceBundleV0, JobEvidenceV0, TraceEvidenceV0
from .failures import (
    BehavioralCallFailure,
    FailureClass,
    FailureEvidence,
    RETRYABLE_INFRA_STATUSES,
    ambiguous_failure,
    infrastructure_failure,
    native_error_status,
    retryable_infrastructure,
    safe_to_retry,
)
from .harness import CALL_TIMEOUT_SECONDS, context_epoch_scope, text_harness_boundary
from .handoff import FormationHandoffV0, FormationJobReceipt
from .requests import BehavioralRequest, memory_request, round_request

if TYPE_CHECKING:
    from constraint_forge_behavioral_runner_r1.taskset import ConstraintForgeBehavioralTaskData


class DyadAbort(RuntimeError):
    """The dyad cannot continue without guessing about behavioral delivery."""


@dataclass(frozen=True)
class SequenceResult:
    """The handoff plus canonical evidence retained after a behavioral sequence."""

    handoff: FormationHandoffV0
    audit_event_count: int
    live_model_calls: int
    traces: tuple[_InteractionTrace, ...]
    ledger: AuditLedger
    jobs: tuple[JobEvidenceV0, ...]


def _native_trace_evidence(result: SequenceResult) -> tuple[TraceEvidenceV0, ...]:
    records: list[TraceEvidenceV0] = []
    lifecycles = {"X": result.handoff.lineage_x, "Y": result.handoff.lineage_y}
    for role, interaction in zip(("X", "Y"), result.traces, strict=False):
        trace = interaction.trace
        trace_id = getattr(trace, "id", None)
        info = getattr(trace, "info", None)
        agent = getattr(trace, "agent", None)
        config = getattr(agent, "config", None)
        if not trace_id or not isinstance(info, dict):
            continue
        config_payload = (
            config.model_dump(mode="json", exclude_none=False)
            if hasattr(config, "model_dump")
            else {"type": type(config).__qualname__ if config is not None else "unknown"}
        )
        records.append(
            TraceEvidenceV0(
                role=role,
                lifecycle_id=lifecycles[role],
                trace_id=trace_id,
                agent_config=config_payload,
                provider_requests=tuple(info.get("constraint_forge_provider_requests", ())),
            )
        )
    return tuple(records)


def stamp_sequence_traces(result: SequenceResult) -> None:
    """Stamp native v1 traces after the persistent interactions have scored.

    v1 closes/scoring happen while the interaction context exits, which is
    before the runner can construct its handoff. Recording the final reward and
    canonical evidence here makes direct runner use and Env.run use share the
    same post-sequence result. Fake interaction traces intentionally have no v1
    state and are left untouched.
    """

    seal = result.ledger.seal_record
    trace_evidence = _native_trace_evidence(result)
    evidence_bundle = None
    if seal is not None and len(trace_evidence) == 2:
        evidence_bundle = CanaryEvidenceBundleV0(
            run_id=result.handoff.run_id,
            dyad_id=result.handoff.dyad_id,
            handoff=result.handoff,
            audit_events=result.ledger.events,
            audit_seal=seal,
            jobs=result.jobs,
            traces=trace_evidence,
        )

    for interaction in result.traces:
        trace = interaction.trace
        state = getattr(trace, "state", None)
        if state is None or not hasattr(trace, "record_reward"):
            continue
        state.completed = result.handoff.aborted is False
        state.run_valid = result.handoff.run_valid
        state.accepted = result.handoff.accepted
        state.aborted = result.handoff.aborted
        state.completed_jobs = result.handoff.completed_jobs
        state.successful_jobs = result.handoff.successful_jobs
        state.job_success_mean = result.handoff.job_success_mean
        state.handoff_hash = result.handoff.content_hash
        state.live_model_calls = result.live_model_calls
        behavioral_reward = (
            result.handoff.job_success_mean if result.handoff.run_valid else 0.0
        )
        trace.record_reward("formation_accepted", behavioral_reward)
        runner_info = trace.info.setdefault("constraint_forge_behavioral_runner", {})
        runner_info.update(
            {
                "live_model_calls": result.live_model_calls,
                "completed": state.completed,
                "run_valid": state.run_valid,
                "accepted": state.accepted,
                "aborted": state.aborted,
                "completed_jobs": state.completed_jobs,
                "successful_jobs": state.successful_jobs,
                "job_success_mean": state.job_success_mean,
                "behavioral_reward": behavioral_reward,
                "handoff_hash": result.handoff.content_hash,
            }
        )
        trace.info["formation_handoff_v0"] = result.handoff.model_dump(mode="json")
        if evidence_bundle is not None:
            trace.info["constraint_forge_canary_evidence_v0"] = (
                evidence_bundle.model_dump(mode="json")
            )
            trace.info["constraint_forge_canary_evidence_hash"] = evidence_bundle.content_hash


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


def _agent_identity(
    actor,
    role: str,
    *,
    run_id: str,
    dyad_id: str,
    trace=None,
) -> tuple[str, str, str, str, str]:
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
        {
            "run_id": run_id,
            "dyad_id": dyad_id,
            "role": role,
            "model_hash": model_hash,
            "provider_hash": provider_hash,
            "config_hash": config_hash,
        }
    )[:32]
    lifecycle_id = stable_hash(
        {
            "run_id": run_id,
            "dyad_id": dyad_id,
            "role": role,
            "actor_id": actor_id,
            "config_hash": config_hash,
            "actor_type": type(actor).__qualname__,
            "trace_id": getattr(trace, "id", None),
        }
    )[:32]
    return actor_id, lifecycle_id, model_hash, provider_hash, config_hash


def _raw_assistant_text(segment) -> tuple[str | None, str | None]:
    """Return exact assistant content and a provider request id when exposed."""

    messages = getattr(segment, "messages", None)
    if messages is not None:
        for message in reversed(messages):
            if isinstance(message, AssistantMessage):
                if message.tool_calls:
                    raise BehavioralCallFailure(
                        FailureEvidence(
                            failure_class=FailureClass.PARTIAL_RESPONSE,
                            request_dispatched=True,
                            behavioral_sample_produced=None,
                            detail="provider assistant message carried tool calls",
                        )
                    )
                return message.content or "", getattr(message, "provider_request_id", None)
            if getattr(message, "role", None) == "assistant":
                if getattr(message, "tool_calls", None):
                    raise BehavioralCallFailure(
                        FailureEvidence(
                            failure_class=FailureClass.PARTIAL_RESPONSE,
                            request_dispatched=True,
                            behavioral_sample_produced=None,
                            detail="provider assistant message carried tool calls",
                        )
                    )
                content = getattr(message, "content", None)
                return (content if isinstance(content, str) else ""), getattr(
                    message, "provider_request_id", None
                )
    if isinstance(segment, str):
        return segment, None
    if hasattr(segment, "raw_output"):
        raw = getattr(segment, "raw_output")
        return (raw if isinstance(raw, str) else None), getattr(segment, "provider_request_id", None)
    return None, None


def _native_error_status(call) -> int | None:
    return native_error_status(call)


def _is_infra_failed_native_call(call) -> bool:
    """True for an explicit listed-status error that delivered no completion."""

    finish_reason = getattr(call.finish_reason, "value", call.finish_reason)
    if finish_reason is not None:
        return False
    return native_error_status(call) in RETRYABLE_INFRA_STATUSES


def _inspect_segment_native_calls(
    interaction,
    call_count_before: int | None,
) -> tuple[object | None, list, FailureEvidence | None]:
    """Validate a segment's native calls without raising.

    A v2 harness segment may contain ``k >= 1`` native calls: every call
    except the last must be an explicit listed-status infrastructure failure
    that delivered no response (a consumed declared same-session retry). The
    last call decides the segment outcome. Returns ``(final_call,
    infra_attempts, failure_evidence_or_None)``.
    """

    if call_count_before is None:
        return None, [], None
    trace = getattr(interaction, "trace", None)
    calls = getattr(trace, "calls", None)
    if calls is None:
        return None, [], None
    new_calls = list(calls[call_count_before:])
    if not new_calls:
        return (
            None,
            [],
            FailureEvidence(
                failure_class=FailureClass.PARTIAL_RESPONSE,
                request_dispatched=True,
                behavioral_sample_produced=None,
                detail="native behavioral segment did not bind to any provider call",
            ),
        )
    for index, earlier in enumerate(new_calls[:-1]):
        if not _is_infra_failed_native_call(earlier):
            return (
                None,
                [],
                FailureEvidence(
                    failure_class=FailureClass.PARTIAL_RESPONSE,
                    request_dispatched=True,
                    behavioral_sample_produced=None,
                    detail=(
                        "intermediate behavioral attempt was not an "
                        f"infrastructure failure: index {index}"
                    ),
                ),
            )
    infra_attempts = new_calls[:-1]
    call = new_calls[-1]
    finish_reason = getattr(call.finish_reason, "value", call.finish_reason)
    if call.error is not None and finish_reason is None:
        status = native_error_status(call)
        if status in RETRYABLE_INFRA_STATUSES:
            # Declared retry budget exhausted at the harness boundary with no
            # delivered response for this behavioral opportunity.
            return call, infra_attempts, infrastructure_failure(status).evidence
    if call.error is not None or finish_reason != "stop":
        return (
            call,
            infra_attempts,
            FailureEvidence(
                failure_class=FailureClass.PARTIAL_RESPONSE,
                request_dispatched=True,
                behavioral_sample_produced=(True if call.error is None else None),
                detail=(
                    "native provider completion was not an ordinary final stop: "
                    f"finish_reason={finish_reason!r}, error={call.error is not None}"
                ),
            ),
        )
    return call, infra_attempts, None


def _append_prepared_audit(ledger: AuditLedger, record: _CallRecord) -> None:
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
        provider_status="prepared",
        provider_request_id=None,
        raw_output=None,
        raw_output_hash=None,
        parse_classification="not_applicable",
        world_event_sequence_start=None,
        world_event_sequence_end=None,
        post_state_hash=record.pre_state_hash,
        status=AuditStatus.PREPARED,
    )


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
    ledger: AuditLedger,
    prepared_lock: asyncio.Lock,
) -> _TurnResult:
    """One behavioral opportunity under the declared v2 retry policy.

    Same-session infrastructure re-launches happen inside the harness, below
    the agent boundary; this function never re-dispatches after anything was
    sent. Its only remaining re-dispatch is the frozen v0 bounded exact retry
    for mechanically proven pre-dispatch failures, where nothing reached the
    provider and the opportunity is provably unconsumed. Every consumed
    same-session attempt is persisted as an ``infra_retry`` ledger event with
    the identical request hash and a ``retry_of`` chain.
    """

    base_call_id = (
        f"{job_id}:{phase}:{'r'+str(round_number) if round_number is not None else phase}"
        f":{actor}"
    )

    def _record(ordinal: int, retry_of: str | None, raw_output: str = "") -> _CallRecord:
        return _CallRecord(
            actor=actor,
            actor_id=actor_id,
            lifecycle_id=lifecycle_id,
            context_epoch=job_index,
            job_index=job_index,
            job_id=job_id,
            phase=phase,
            round=round_number,
            call_id=f"{base_call_id}:attempt{ordinal}",
            request=request,
            pre_state_hash=request.pre_state_hash,
            world_event_sequence_before=world_event_sequence_before,
            model_hash=model_hash,
            provider_hash=provider_hash,
            config_hash=config_hash,
            raw_output=raw_output,
            retry_of=retry_of,
        )

    def _emit_infra_attempt(attempt_ordinal: int, previous: str | None, call) -> str:
        attempt_record = _record(attempt_ordinal, previous)
        status_code = native_error_status(call)
        ledger.append(
            actor=actor,
            actor_id=actor_id,
            lifecycle_id=lifecycle_id,
            context_epoch=job_index,
            job_index=job_index,
            job_id=job_id,
            phase=phase,
            round=round_number,
            call_id=attempt_record.call_id,
            retry_of=previous,
            pre_state_hash=request.pre_state_hash,
            world_event_sequence_before=world_event_sequence_before,
            request_hash=request.request_hash,
            model_hash=model_hash,
            provider_hash=provider_hash,
            config_hash=config_hash,
            provider_status=str(status_code),
            raw_output=None,
            raw_output_hash=None,
            parse_classification="not_applicable",
            world_event_sequence_start=None,
            world_event_sequence_end=None,
            post_state_hash=request.pre_state_hash,
            status=AuditStatus.INFRA_RETRY,
            failure_class=FailureClass.INFRASTRUCTURE_UNDELIVERED.value,
        )
        return attempt_record.call_id

    failures: list[_FailureRecord] = []
    safe_retry_used = False
    retry_of: str | None = None
    ordinal = 0
    while True:
        record = _record(ordinal, retry_of)
        try:
            async with prepared_lock:
                _append_prepared_audit(ledger, record)
            trace = getattr(interaction, "trace", None)
            native_calls = getattr(trace, "calls", None)
            native_call_count = len(native_calls) if native_calls is not None else None
            # The runner-side guard must match the declared subprocess
            # timeout exactly: a shorter guard here cancels slow-but-live
            # launches mid-flight and misclassifies them as partial responses.
            async with asyncio.timeout(text_harness_boundary()[0]):
                segment = await interaction.turn(request.prompt_text)
            _, infra_attempts, evidence = _inspect_segment_native_calls(
                interaction, native_call_count
            )
            if evidence is not None:
                raise BehavioralCallFailure(evidence)
            previous = retry_of
            for index, attempt_call in enumerate(infra_attempts):
                previous = _emit_infra_attempt(ordinal + index, previous, attempt_call)
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
            final = _record(ordinal + len(infra_attempts), previous)
            return _TurnResult(
                record=_CallRecord(
                    **{
                        **final.__dict__,
                        "raw_output": raw_output,
                        "provider_request_id": request_id,
                    }
                ),
                failures=tuple(failures),
            )
        except BehavioralCallFailure as exc:
            evidence = exc.evidence
            consumed = 0
            previous = retry_of
            if native_call_count is not None:
                new_calls = list(
                    (getattr(getattr(interaction, "trace", None), "calls", None) or [])[
                        native_call_count:
                    ]
                )
                for index, attempt_call in enumerate(new_calls[:-1]):
                    if not _is_infra_failed_native_call(attempt_call):
                        break
                    previous = _emit_infra_attempt(
                        ordinal + index, previous, attempt_call
                    )
                    consumed += 1
            terminal = _record(ordinal + consumed, previous if consumed else retry_of)
            if safe_to_retry(evidence) and not safe_retry_used:
                safe_retry_used = True
                failures.append(_FailureRecord(terminal, evidence, AuditStatus.SAFE_RETRY))
                retry_of = terminal.call_id
                ordinal += consumed + 1
                continue
            failures.append(_FailureRecord(terminal, evidence, AuditStatus.FAILED))
            return _TurnResult(
                record=None,
                failures=tuple(failures),
                error=DyadAbort(
                    f"{actor} {phase} call {terminal.call_id} failed: "
                    f"{evidence.failure_class.value}"
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
        except Exception as exc:
            failure = ambiguous_failure(f"{type(exc).__name__}: {exc}")
            failures.append(_FailureRecord(record, failure.evidence, AuditStatus.FAILED))
            return _TurnResult(
                record=None,
                failures=tuple(failures),
                error=DyadAbort(f"{actor} {phase} call delivery is ambiguous"),
            )


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
    if request_x.pre_state_hash != request_y.pre_state_hash:
        raise DyadAbort("X/Y requests did not share one pre-state hash")
    if request_x.request_hash == request_y.request_hash and request_x.role == request_y.role:
        raise DyadAbort("X/Y request roles were not distinct")
    prepared_lock = asyncio.Lock()
    with context_epoch_scope(job_index):
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
                ledger=ledger,
                prepared_lock=prepared_lock,
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
                ledger=ledger,
                prepared_lock=prepared_lock,
            ),
            return_exceptions=True,
        )
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
        raise errors[0]
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
    plan = getattr(data, "run_plan", None)
    if plan is not None:
        return plan.jobs[index].intervention
    interventions = getattr(data, "interventions", ())
    return interventions[index] if len(interventions) == len(data.job_seeds) else None


def _read_only_at(data, index: int) -> bool:
    plan = getattr(data, "run_plan", None)
    if plan is not None and plan.jobs[index].read_only_probe:
        return True
    return index in set(getattr(data, "read_only_job_indices", ()))


def _wipe_at(data, index: int) -> bool:
    """V1 memory manipulation: probe starts with emptied rack films.

    Snapshot-and-restore semantics: the accumulated rack is restored after the
    job, so the wiped/intact contrast inside a difficulty-matched pair differs
    only in film availability during that single job.
    """

    plan = getattr(data, "run_plan", None)
    if plan is not None:
        return bool(getattr(plan.jobs[index], "wipe_rack", False))
    return index in set(getattr(data, "wipe_rack_job_indices", ()))


def _session_evidence(session: ConstraintForgeJobSession, *, complete: bool) -> JobEvidenceV0:
    return JobEvidenceV0(
        job_id=session.job_id,
        job_seed=session.job.job_seed,
        complete=complete,
        event_log=session.event_log,
        rack_x=session.rack_x,
        rack_y=session.rack_y,
        memory_mutations_x=tuple(session.mutations_x),
        memory_mutations_y=tuple(session.mutations_y),
    )


async def run_behavioral_sequence(
    data: "ConstraintForgeBehavioralTaskData",
    *,
    actor_x,
    actor_y,
    task,
    runtime_x=None,
    runtime_y=None,
) -> SequenceResult:
    """Run one full sequence using persistent role agents and fresh job contexts.

    Infrastructure re-launch budgets are owned by the configured harness
    (see ``ConstraintForgeTextHarnessConfig``); the runner records what they
    consumed.
    """

    run_id = data.sequence_id
    dyad_id = stable_hash({"run_id": run_id, "protocol": data.protocol_version})[:32]
    identity_x = _agent_identity(actor_x, "X", run_id=run_id, dyad_id=dyad_id)
    identity_y = _agent_identity(actor_y, "Y", run_id=run_id, dyad_id=dyad_id)
    ledger = AuditLedger(run_id=run_id, dyad_id=dyad_id)
    receipts: list[FormationJobReceipt] = []
    job_evidence: list[JobEvidenceV0] = []
    active_session: ConstraintForgeJobSession | None = None
    rack_x = empty_rack()
    rack_y = empty_rack()
    traces: list[_InteractionTrace] = []
    last_state_hash = stable_hash({"sequence": run_id, "state": "not_started"})
    abort_class: str | None = None

    try:
        x_interaction = (
            actor_x.interaction(task, runtime=runtime_x)
            if runtime_x is not None
            else actor_x.interaction(task)
        )
        y_interaction = (
            actor_y.interaction(task, runtime=runtime_y)
            if runtime_y is not None
            else actor_y.interaction(task)
        )
        async with x_interaction as interaction_x:
            async with y_interaction as interaction_y:
                traces.extend(
                    (_InteractionTrace(interaction_x.trace), _InteractionTrace(interaction_y.trace))
                )
                identity_x = _agent_identity(
                    actor_x,
                    "X",
                    run_id=run_id,
                    dyad_id=dyad_id,
                    trace=interaction_x.trace,
                )
                identity_y = _agent_identity(
                    actor_y,
                    "Y",
                    run_id=run_id,
                    dyad_id=dyad_id,
                    trace=interaction_y.trace,
                )
                job_wipe_records: dict[int, dict[str, object]] = {}
                for job_index, seed in enumerate(data.job_seeds):
                    job_id = _job_id(data.sequence_id, job_index)
                    job = generate_job(seed)
                    wipe_info: dict[str, object] | None = None
                    snapshot_rack_x = snapshot_rack_y = None
                    if _wipe_at(data, job_index):
                        snapshot_rack_x, snapshot_rack_y = rack_x, rack_y
                        wipe_info = {
                            "prior_films_x": len(rack_x.films),
                            "prior_films_y": len(rack_y.films),
                            "prior_content_hash_x": rack_x.content_hash,
                            "prior_content_hash_y": rack_y.content_hash,
                        }
                        rack_x = empty_rack()
                        rack_y = empty_rack()
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
                    active_session = session
                    while not session.terminal:
                        offer: RoundOffer = session.begin_round()
                        request_x = round_request(
                            role="X",
                            job_index=job_index,
                            job_id=job_id,
                            context_epoch=job_index,
                            pre_state_hash=offer.pre_state_hash,
                            observation=offer.observation_x,
                            station_note=station_note(r1_void(job.job_seed)),
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
                        job_adj = r1_adjudicate(
                            world_success=eviction_offer.success,
                            job_seed=job.job_seed,
                            events=session.event_log.events,
                        )
                        request_x = memory_request(
                            role="X",
                            phase="eviction",
                            job_index=job_index,
                            job_id=job_id,
                            context_epoch=job_index,
                            pre_state_hash=eviction_offer.state_hash,
                            rack=eviction_offer.rack_view_x,
                            frames=eviction_offer.frames_x,
                            success=job_adj["success"],
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
                            success=job_adj["success"],
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
                            success=job_adj["success"],
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
                            success=job_adj["success"],
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
                    job_evidence.append(_session_evidence(session, complete=True))
                    active_session = None
                    if wipe_info is not None:
                        # Restore the snapshot: read-only probes cannot regen-
                        # erate films, so post-wipe emptiness must never leak
                        # into later intact probes. Record what was hidden.
                        job_wipe_records[job_index] = {
                            **wipe_info,
                            "wiped_content_hash_x": job_result.final_rack_x.content_hash,
                            "wiped_content_hash_y": job_result.final_rack_y.content_hash,
                        }
                        rack_x = snapshot_rack_x
                        rack_y = snapshot_rack_y
                    else:
                        rack_x = job_result.final_rack_x
                        rack_y = job_result.final_rack_y
                    last_state_hash = job_result.final_state_hash
                    receipts.append(
                        FormationJobReceipt(
                            job_index=job_index,
                            job_id=job_id,
                            job_seed=job_result.job_seed,
                            **r1_adjudicate(
                                world_success=job_result.success,
                                job_seed=job_result.job_seed,
                                events=job_result.event_log.events,
                            ),
                            failure_reason=job_result.failure_reason,
                            final_state_hash=job_result.final_state_hash,
                            event_log_hash=job_result.event_log.content_hash,
                            final_rack_x_hash=rack_x.content_hash,
                            final_rack_y_hash=rack_y.content_hash,
                            rack_wipe=RackWipeRecord(
                                job_index=job_index,
                                **job_wipe_records[job_index]
                            ) if job_index in job_wipe_records else None,
                        )
                    )
    except DyadAbort as exc:
        abort_class = type(exc).__name__
        if active_session is not None:
            job_evidence.append(_session_evidence(active_session, complete=False))
            active_session = None
    except Exception as exc:
        import os as _os, traceback as _tb
        if _os.environ.get("CF_DEBUG_TRACEBACK"):
            _tb.print_exc()
        abort_class = f"runner_error:{type(exc).__name__}"
        if active_session is not None:
            job_evidence.append(_session_evidence(active_session, complete=False))
            active_session = None

    seal_status = AuditSealStatus.ABORTED if abort_class is not None else AuditSealStatus.COMPLETED
    seal = ledger.seal(seal_status)
    live_model_calls = sum(
        len(getattr(interaction.trace, "calls", ())) for interaction in traces
    )
    successful_jobs = sum(receipt.success for receipt in receipts)
    job_success_mean = successful_jobs / len(receipts) if receipts else 0.0
    run_valid = abort_class is None and len(receipts) == len(data.job_seeds)
    handoff = FormationHandoffV0(
        run_id=run_id,
        dyad_id=dyad_id,
        lineage_x=identity_x[1],
        lineage_y=identity_y[1],
        run_valid=run_valid,
        planned_jobs=len(data.job_seeds),
        accepted=run_valid,
        aborted=abort_class is not None,
        abort_class=abort_class,
        completed_jobs=len(receipts),
        successful_jobs=successful_jobs,
        job_success_mean=job_success_mean,
        job_receipts=tuple(receipts),
        audit_chain_hash=ledger.final_hash,
        audit_seal_hash=stable_hash(seal.model_dump(mode="json")),
        final_state_hash_x=last_state_hash,
        final_state_hash_y=last_state_hash,
        final_rack_x_bytes=rack_x.serialization_bytes,
        final_rack_y_bytes=rack_y.serialization_bytes,
    )
    result = SequenceResult(
        handoff=handoff,
        audit_event_count=len(ledger.events),
        live_model_calls=live_model_calls,
        traces=tuple(traces),
        ledger=ledger,
        jobs=tuple(job_evidence),
    )
    stamp_sequence_traces(result)
    return result


__all__ = [
    "CALL_TIMEOUT_SECONDS",
    "DyadAbort",
    "SequenceResult",
    "run_behavioral_sequence",
    "stamp_sequence_traces",
]
