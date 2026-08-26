from __future__ import annotations

import asyncio
from constraint_forge_behavioral_runner_r2.audit import AuditLedger
from constraint_forge_behavioral_runner_r2.failures import (
    FailureClass,
    FailureEvidence,
    safe_to_retry,
)
from constraint_forge_behavioral_runner_r2.runner import run_behavioral_sequence
from test_runner import _FakeActor, _targets, _task


def test_closed_failure_taxonomy_only_retries_proven_no_sample() -> None:
    assert safe_to_retry(
        FailureEvidence(
            failure_class=FailureClass.LOCAL_PRE_DISPATCH,
            request_dispatched=False,
            behavioral_sample_produced=False,
        )
    )
    assert safe_to_retry(
        FailureEvidence(
            failure_class=FailureClass.PROVIDER_REJECTED_PRE_INFERENCE,
            request_dispatched=False,
            behavioral_sample_produced=False,
        )
    )
    for failure_class in (
        FailureClass.DELIVERY_AMBIGUOUS,
        FailureClass.TIMEOUT_AMBIGUOUS,
        FailureClass.PARTIAL_RESPONSE,
    ):
        assert not safe_to_retry(
            FailureEvidence(
                failure_class=failure_class,
                request_dispatched=True,
                behavioral_sample_produced=None,
            )
        )


def test_audit_chain_detects_payload_tampering_and_reordering() -> None:
    async def run():
        task = _task()
        targets = _targets(task)
        x = _FakeActor(targets)
        y = _FakeActor(targets)
        return await run_behavioral_sequence(task.data, actor_x=x, actor_y=y, task=task)

    result = asyncio.run(run())
    assert result.ledger.verify().valid
    events = list(result.ledger.events)
    tampered = events[0].model_copy(update={"raw_output": "tampered"})
    assert not AuditLedger.verify_events((tampered, *events[1:]), result.ledger.seal_record).valid
    assert not AuditLedger.verify_events(tuple(reversed(events)), result.ledger.seal_record).valid


def test_completed_call_events_bind_raw_text_hash_and_world_interval() -> None:
    async def run():
        task = _task()
        targets = _targets(task)
        x = _FakeActor(targets)
        y = _FakeActor(targets)
        return await run_behavioral_sequence(task.data, actor_x=x, actor_y=y, task=task)

    result = asyncio.run(run())
    completed = [event for event in result.ledger.events if event.status.value == "completed"]
    assert completed
    assert all(event.raw_output is not None for event in completed)
    assert all(event.raw_output_hash is not None for event in completed)
    assert all(event.world_event_sequence_start is not None for event in completed)
    assert all(event.world_event_sequence_end is not None for event in completed)
    assert all(event.world_event_sequence_start < event.world_event_sequence_end for event in completed)


def test_every_completed_call_has_a_pre_dispatch_prepared_record() -> None:
    async def run():
        task = _task()
        targets = _targets(task)
        return await run_behavioral_sequence(
            task.data,
            actor_x=_FakeActor(targets),
            actor_y=_FakeActor(targets),
            task=task,
        )

    result = asyncio.run(run())
    prepared = {
        (event.actor, event.call_id)
        for event in result.ledger.events
        if event.status.value == "prepared"
    }
    completed = {
        (event.actor, event.call_id)
        for event in result.ledger.events
        if event.status.value == "completed"
    }
    assert completed <= prepared
