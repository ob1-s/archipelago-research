"""Explicitly non-scientific two-job live-canary execution path."""

from __future__ import annotations

from constraint_forge_formation_v0.canonical import stable_hash
from constraint_forge_formation_v0.generator import generate_job
from constraint_forge_formation_v0.rack import empty_rack
from constraint_forge_formation_v0.session import ConstraintForgeJobSession, RoundOffer
from constraint_forge_formation_v0.world import JobResult

from .audit import AuditLedger, AuditSealStatus
from .handoff import FormationHandoffV0, FormationJobReceipt
from .requests import memory_request, round_request
from .runner import (
    DyadAbort,
    SequenceResult,
    _InteractionTrace,
    _agent_identity,
    _dispatch_pair,
    _job_id,
    _record_memory_successes,
    _record_round_successes,
    _session_evidence,
    stamp_sequence_traces,
)


async def run_throwaway_canary(
    data,
    *,
    actor_x,
    actor_y,
    task,
    runtime_x=None,
    runtime_y=None,
) -> SequenceResult:
    """Exercise one complete ordinary job plus one round of a fresh second job.

    The canary borrows the intact frozen task/configuration surface but uses
    separate throwaway seeds. It is therefore incapable of becoming scientific
    cohort data or pre-exposing a frozen cohort job.
    """

    if len(data.run_plan.jobs) != 24:
        raise ValueError("canary must borrow the intact frozen 24-job task data")

    run_id = f"{data.sequence_id}:throwaway-canary"
    dyad_id = stable_hash({"run_id": run_id, "protocol": data.protocol_version})[:32]
    canary_seeds = (
        f"{run_id}:ordinary:0",
        f"{run_id}:ordinary:1",
    )
    identity_x = _agent_identity(actor_x, "X", run_id=run_id, dyad_id=dyad_id)
    identity_y = _agent_identity(actor_y, "Y", run_id=run_id, dyad_id=dyad_id)
    ledger = AuditLedger(run_id=run_id, dyad_id=dyad_id)
    traces: list[_InteractionTrace] = []
    jobs = []
    receipt: FormationJobReceipt | None = None
    rack_x = empty_rack()
    rack_y = empty_rack()
    active_session: ConstraintForgeJobSession | None = None
    abort_class: str | None = None
    last_state_hash = stable_hash({"run": run_id, "state": "not_started"})
    second_round_resolved = False

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

                # Job 1: full ordinary throwaway job plus both memory subphases.
                job_index = 0
                job_id = _job_id(run_id, job_index)
                job = generate_job(canary_seeds[0])
                session = ConstraintForgeJobSession.open(
                    job,
                    run_id=run_id,
                    lineage_id=dyad_id,
                    job_id=job_id,
                    rack_x=rack_x,
                    rack_y=rack_y,
                )
                active_session = session
                while not session.terminal:
                    offer: RoundOffer = session.begin_round()
                    calls = await _dispatch_pair(
                        interaction_x=interaction_x,
                        interaction_y=interaction_y,
                        request_x=round_request(
                            role="X",
                            job_index=job_index,
                            job_id=job_id,
                            context_epoch=job_index,
                            pre_state_hash=offer.pre_state_hash,
                            observation=offer.observation_x,
                        ),
                        request_y=round_request(
                            role="Y",
                            job_index=job_index,
                            job_id=job_id,
                            context_epoch=job_index,
                            pre_state_hash=offer.pre_state_hash,
                            observation=offer.observation_y,
                        ),
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

                eviction = session.begin_eviction()
                if eviction is None:
                    raise RuntimeError("canary ordinary job unexpectedly skipped memory")
                calls = await _dispatch_pair(
                    interaction_x=interaction_x,
                    interaction_y=interaction_y,
                    request_x=memory_request(
                        role="X",
                        phase="eviction",
                        job_index=job_index,
                        job_id=job_id,
                        context_epoch=job_index,
                        pre_state_hash=eviction.state_hash,
                        rack=eviction.rack_view_x,
                        frames=eviction.frames_x,
                        success=eviction.success,
                    ),
                    request_y=memory_request(
                        role="Y",
                        phase="eviction",
                        job_index=job_index,
                        job_id=job_id,
                        context_epoch=job_index,
                        pre_state_hash=eviction.state_hash,
                        rack=eviction.rack_view_y,
                        frames=eviction.frames_y,
                        success=eviction.success,
                    ),
                    identity_x=identity_x,
                    identity_y=identity_y,
                    job_index=job_index,
                    job_id=job_id,
                    phase="eviction",
                    round_number=None,
                    world_event_sequence_before=eviction.event_sequence_before,
                    ledger=ledger,
                )
                eviction_result = session.submit_eviction(
                    token=eviction.token,
                    raw_x=calls[0].raw_output,
                    raw_y=calls[1].raw_output,
                )
                _record_memory_successes(ledger, calls, eviction_result)

                retention = session.begin_retention()
                calls = await _dispatch_pair(
                    interaction_x=interaction_x,
                    interaction_y=interaction_y,
                    request_x=memory_request(
                        role="X",
                        phase="retention",
                        job_index=job_index,
                        job_id=job_id,
                        context_epoch=job_index,
                        pre_state_hash=retention.state_hash,
                        rack=retention.rack_view_x,
                        frames=retention.frames_x,
                        success=retention.success,
                    ),
                    request_y=memory_request(
                        role="Y",
                        phase="retention",
                        job_index=job_index,
                        job_id=job_id,
                        context_epoch=job_index,
                        pre_state_hash=retention.state_hash,
                        rack=retention.rack_view_y,
                        frames=retention.frames_y,
                        success=retention.success,
                    ),
                    identity_x=identity_x,
                    identity_y=identity_y,
                    job_index=job_index,
                    job_id=job_id,
                    phase="retention",
                    round_number=None,
                    world_event_sequence_before=retention.event_sequence_before,
                    ledger=ledger,
                )
                retention_result = session.submit_retention(
                    token=retention.token,
                    raw_x=calls[0].raw_output,
                    raw_y=calls[1].raw_output,
                )
                _record_memory_successes(ledger, calls, retention_result)

                first_result: JobResult = session.result()
                jobs.append(_session_evidence(session, complete=True))
                active_session = None
                rack_x = first_result.final_rack_x
                rack_y = first_result.final_rack_y
                last_state_hash = first_result.final_state_hash
                receipt = FormationJobReceipt(
                    job_index=0,
                    job_id=job_id,
                    job_seed=first_result.job_seed,
                    success=first_result.success,
                    failure_reason=first_result.failure_reason,
                    final_state_hash=first_result.final_state_hash,
                    event_log_hash=first_result.event_log.content_hash,
                    final_rack_x_hash=rack_x.content_hash,
                    final_rack_y_hash=rack_y.content_hash,
                )

                # Job 2: fresh visible context, inherited role-local racks, one paired round.
                job_index = 1
                job_id = _job_id(run_id, job_index)
                second = generate_job(canary_seeds[1])
                session = ConstraintForgeJobSession.open(
                    second,
                    run_id=run_id,
                    lineage_id=dyad_id,
                    job_id=job_id,
                    rack_x=rack_x,
                    rack_y=rack_y,
                )
                active_session = session
                offer = session.begin_round()
                calls = await _dispatch_pair(
                    interaction_x=interaction_x,
                    interaction_y=interaction_y,
                    request_x=round_request(
                        role="X",
                        job_index=job_index,
                        job_id=job_id,
                        context_epoch=job_index,
                        pre_state_hash=offer.pre_state_hash,
                        observation=offer.observation_x,
                    ),
                    request_y=round_request(
                        role="Y",
                        job_index=job_index,
                        job_id=job_id,
                        context_epoch=job_index,
                        pre_state_hash=offer.pre_state_hash,
                        observation=offer.observation_y,
                    ),
                    identity_x=identity_x,
                    identity_y=identity_y,
                    job_index=job_index,
                    job_id=job_id,
                    phase="round",
                    round_number=offer.round,
                    world_event_sequence_before=offer.event_sequence_before,
                    ledger=ledger,
                )
                second_round = session.submit_round(
                    token=offer.token,
                    raw_x=calls[0].raw_output,
                    raw_y=calls[1].raw_output,
                )
                _record_round_successes(ledger, calls, second_round)
                second_round_resolved = True
                last_state_hash = second_round.post_state_hash
                jobs.append(_session_evidence(session, complete=False))
                active_session = None
                # Normal interaction-context exit is the clean canary completion path.
                # No cancellation, actor replacement, or forced retention is used.
    except DyadAbort as exc:
        abort_class = type(exc).__name__
        if active_session is not None:
            jobs.append(_session_evidence(active_session, complete=False))
            active_session = None
    except Exception as exc:
        abort_class = f"runner_error:{type(exc).__name__}"
        if active_session is not None:
            jobs.append(_session_evidence(active_session, complete=False))
            active_session = None

    seal = ledger.seal(
        AuditSealStatus.ABORTED if abort_class is not None else AuditSealStatus.COMPLETED
    )
    live_model_calls = sum(
        len(getattr(interaction.trace, "calls", ())) for interaction in traces
    )
    successful_jobs = int(bool(receipt and receipt.success))
    handoff = FormationHandoffV0(
        run_id=run_id,
        dyad_id=dyad_id,
        lineage_x=identity_x[1],
        lineage_y=identity_y[1],
        # A canary is intentionally never a valid formation run, even on clean completion.
        run_valid=False,
        planned_jobs=2,
        accepted=False,
        aborted=abort_class is not None,
        abort_class=abort_class,
        completed_jobs=1 if receipt is not None else 0,
        successful_jobs=successful_jobs,
        job_success_mean=float(successful_jobs) if receipt is not None else 0.0,
        job_receipts=(receipt,) if receipt is not None else (),
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
        jobs=tuple(jobs),
    )
    stamp_sequence_traces(result)
    for wrapped in result.traces:
        info = getattr(wrapped.trace, "info", None)
        if isinstance(info, dict):
            info["constraint_forge_throwaway_canary"] = {
                "scientific_eligible": False,
                "clean_completion": abort_class is None,
                "first_job_completed": receipt is not None,
                "second_job_rounds_resolved": int(second_round_resolved),
                "maximum_model_calls": 38,
                "uses_scientific_job_seeds": False,
            }
    return result


__all__ = ["run_throwaway_canary"]
