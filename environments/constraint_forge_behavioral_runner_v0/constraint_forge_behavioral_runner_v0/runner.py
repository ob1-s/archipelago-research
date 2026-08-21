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
from .failures import (
    BehavioralCallFailure,
    FailureClass,
    FailureEvidence,
    ambiguous_failure,
    safe_to_retry,
)
from .harness import context_epoch_scope
from .handoff import FormationHandoffV0, FormationJobReceipt
from .requests import BehavioralRequest, memory_request, round_request

if TYPE_CHECKING:
    from constraint_forge_behavioral_runner_v0.taskset import ConstraintForgeBehavioralTaskData


class DyadAbort(RuntimeError):
    """The dyad cannot continue without guessing about behavioral delivery."""


# Per-call timeout is deliberately finite.  A timeout is an ambiguous behavioral
# boundary and therefore abort-only; it is never silently retried.
CALL_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True)
class SequenceResult:
    """The handoff plus in-process evidence needed by fake/no-network tests."""

    handoff: FormationHandoffV0
    audit_event_count: int
    live_model_calls: int
    traces: tuple[_InteractionTrace, ...]
    ledger: AuditLedger


def stamp_sequence_traces(result: SequenceResult) -> None:
    """Stamp native v1 traces after the persistent interactions have scored.

    v1 closes/scoring happen while the interaction context exits, which is
    before the runner can construct its handoff.  Recording the final reward
    here makes direct runner use and Env.run use share the same post-sequence
    timing-safe result.  Fake interaction traces intentionally have no v1 state
    and are left untouched.
    """

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
        trace.record_reward("formation_accepted", result.handoff.job_success_mean)
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
                "handoff_hash": result.handoff.content_hash,
            }
        )
        trace.info["formation_handoff_v0"] = result.handoff.model_dump(mode="json")


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
            # A native v1 Trace id is the concrete rollout/session identity.
            # Fake actors intentionally have no id and receive a deterministic
            # run-scoped fallback for replay tests.
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
                if message.tool_calls or message.reasoning_content or message.provider_state:
                    raise BehavioralCallFailure(
                        FailureEvidence(
                            failure_class=FailureClass.PARTIAL_RESPONSE,
                            request_dispatched=True,
                            behavioral_sample_produced=None,
                            detail=(
                                "provider assistant message carried tool calls, "
                                "reasoning, or continuation state"
                            ),
                        )
                    )
                return message.content or "", getattr(message, "provider_request_id", None)
            if getattr(message, "role", None) == "assistant":
                if any(
                    getattr(message, field, None)
                    for field in ("tool_calls", "reasoning_content", "provider_state")
                ):
                    raise BehavioralCallFailure(
                        FailureEvidence(
                            failure_class=FailureClass.PARTIAL_RESPONSE,
                            request_dispatched=True,
                            behavioral_sample_produced=None,
                            detail="provider assistant message carried non-text state",
                        )
                    )
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


def _append_prepared_audit(ledger: AuditLedger, record: _CallRecord) -> None:
    """Record a sealed call before its provider boundary is entered."""

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
            # The preparation event is appended immediately before entering
            # v1's interaction boundary.  The pair lock keeps the hash chain
            # mutation serialized while preserving the two-call barrier.
            async with prepared_lock:
                _append_prepared_audit(ledger, record)
            async with asyncio.timeout(CALL_TIMEOUT_SECONDS):
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


async def run_behavioral_sequence(
    data: "ConstraintForgeBehavioralTaskData",
    *,
    actor_x,
    actor_y,
    task,
    runtime_x=None,
    runtime_y=None,
) -> SequenceResult:
    """Run one full sequence using persistent role agents and fresh job contexts."""

    run_id = data.sequence_id
    dyad_id = stable_hash({"run_id": run_id, "protocol": data.protocol_version})[:32]
    identity_x = _agent_identity(
        actor_x, "X", run_id=run_id, dyad_id=dyad_id
    )
    identity_y = _agent_identity(
        actor_y, "Y", run_id=run_id, dyad_id=dyad_id
    )
    ledger = AuditLedger(run_id=run_id, dyad_id=dyad_id)
    receipts: list[FormationJobReceipt] = []
    rack_x = empty_rack()
    rack_y = empty_rack()
    traces: list[_InteractionTrace] = []
    last_state_hash = stable_hash({"sequence": run_id, "state": "not_started"})
    abort_class: str | None = None

    try:
        # The episode-owned agents, interactions, traces, and harness sessions
        # span the whole dyad.  The package-local HarnessSession resets only
        # its provider-visible prompt history at the runner's out-of-band job
        # boundary; the v1 Trace remains the append-only audit record.
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
                # Bind lifecycle identity to the concrete native v1 traces that
                # own these persistent interactions.  Fake actors without a v1
                # trace id retain the deterministic run-scoped fallback.
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
                            failure_reason=job_result.failure_reason,
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
    live_model_calls = sum(
        len(getattr(interaction.trace, "calls", ())) for interaction in traces
    )
    successful_jobs = sum(receipt.success for receipt in receipts)
    job_success_mean = successful_jobs / len(receipts) if receipts else 0.0
    # A complete, infrastructure-valid sequence is distinct from the binary
    # success of each attempted job.  Failed jobs remain in job_receipts and are
    # part of the exploratory data rather than invalidating the dyad.
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
