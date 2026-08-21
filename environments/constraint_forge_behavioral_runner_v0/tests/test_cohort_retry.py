"""Deterministic checks for the declared cohort-v1 infrastructure retry rule."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from constraint_forge_behavioral_runner_v0.failures import (
    FailureClass,
    infrastructure_failure,
    retryable_infrastructure,
)
from constraint_forge_behavioral_runner_v0.runner import (
    _require_native_ordinary_completion,
    run_behavioral_sequence,
)
from test_runner import (
    _FakeActor,
    _FakeInteraction,
    _FakeSegment,
    _targets,
    _task,
)


def test_infrastructure_failure_evidence_is_bounded_and_provable() -> None:
    evidence = infrastructure_failure(503).evidence
    assert evidence.failure_class is FailureClass.INFRASTRUCTURE_UNDELIVERED
    assert evidence.request_dispatched is True
    assert evidence.behavioral_sample_produced is False
    assert evidence.provider_status == "503"
    assert retryable_infrastructure(evidence)
    assert not retryable_infrastructure(
        evidence.model_copy(update={"failure_class": FailureClass.PARTIAL_RESPONSE})
    )
    assert not retryable_infrastructure(
        evidence.model_copy(update={"behavioral_sample_produced": None})
    )


def _native_call(finish_reason, status_code):
    error = None
    if status_code is not None:
        error = type(
            "E",
            (),
            {
                "model_dump": lambda self, **_: {
                    "type": "ProviderError",
                    "message": "boom",
                    "status_code": status_code,
                }
            },
        )()
    return type("C", (), {"finish_reason": finish_reason, "error": error})()


class _Trace:
    calls: tuple = ()


class _Interaction:
    trace = _Trace()


def _classify(finish_reason, status_code) -> FailureClass:
    _Trace.calls = (_native_call(finish_reason, status_code),)
    try:
        _require_native_ordinary_completion(_Interaction(), 0)
    except Exception as exc:  # noqa: BLE001
        return exc.evidence.failure_class
    raise AssertionError("expected a failure classification")


def test_only_listed_infra_statuses_are_retryable() -> None:
    assert _classify(None, 500) is FailureClass.INFRASTRUCTURE_UNDELIVERED
    assert _classify(None, 429) is FailureClass.INFRASTRUCTURE_UNDELIVERED
    assert _classify(None, 503) is FailureClass.INFRASTRUCTURE_UNDELIVERED
    # Unlisted statuses and delivered nonfinal completions are never retried.
    assert _classify(None, 400) is FailureClass.PARTIAL_RESPONSE
    assert _classify("length", 500) is FailureClass.PARTIAL_RESPONSE
    assert _classify("length", None) is FailureClass.PARTIAL_RESPONSE


class _InfraOnceInteraction(_FakeInteraction):
    async def turn(self, prompt: str):
        if self.actor.fail_on_dispatch == self.actor.total_calls:
            self.actor.fail_on_dispatch = None
            self.actor.total_calls += 1
            raise infrastructure_failure(500)
        return await super().turn(prompt)


class _InfraAlwaysInteraction(_FakeInteraction):
    async def turn(self, prompt: str):
        self.actor.total_calls += 1
        raise infrastructure_failure(429)


class _InfraOnceActor(_FakeActor):
    def __init__(self, target_by_mask, *, fail_on_dispatch=None):
        super().__init__(target_by_mask)
        self.fail_on_dispatch = fail_on_dispatch

    @asynccontextmanager
    async def interaction(self, task):
        del task
        self.interaction_count += 1
        if self.fail_on_dispatch is None:
            yield _InfraAlwaysInteraction(self)
        else:
            yield _InfraOnceInteraction(self)


def test_one_infra_failure_retries_identically_as_one_opportunity(monkeypatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(
        "constraint_forge_behavioral_runner_v0.runner.asyncio.sleep", fake_sleep
    )

    async def run():
        task = _task()
        targets = _targets(task)
        x = _InfraOnceActor(targets, fail_on_dispatch=0)
        y = _FakeActor(targets)
        result = await run_behavioral_sequence(
            task.data,
            actor_x=x,
            actor_y=y,
            task=task,
            max_infra_retries=2,
        )
        return result, x

    result, x = asyncio.run(run())
    infra = [
        event for event in result.ledger.events if event.status.value == "infra_retry"
    ]
    assert len(infra) == 1
    assert infra[0].actor == "X"
    assert infra[0].call_id.endswith("X:attempt0")
    successors = [
        event
        for event in result.ledger.events
        if event.retry_of == infra[0].call_id and event.status.value == "completed"
    ]
    assert len(successors) == 1
    assert successors[0].actor == "X"
    # One behavioral opportunity: the world advanced once despite two dispatches.
    assert not any(event.status.value == "audit_only" for event in result.ledger.events)
    assert result.handoff.aborted is False
    assert sleeps == [4.0]


def test_exhausted_infra_budget_aborts_with_all_attempts_persisted(monkeypatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(
        "constraint_forge_behavioral_runner_v0.runner.asyncio.sleep", fake_sleep
    )

    async def run():
        task = _task()
        targets = _targets(task)
        x = _InfraOnceActor(targets)
        y = _FakeActor(targets)
        return await run_behavioral_sequence(
            task.data,
            actor_x=x,
            actor_y=y,
            task=task,
            max_infra_retries=1,
        )

    result = asyncio.run(run())
    assert result.handoff.aborted
    x_events = [event for event in result.ledger.events if event.actor == "X"]
    assert sum(event.status.value == "infra_retry" for event in x_events) == 1
    failed = [event for event in x_events if event.status.value == "failed"]
    assert len(failed) == 1
    assert failed[0].failure_class == "infrastructure_undelivered"
    assert failed[0].call_id.endswith("X:attempt1")
    # Backoff fired once, before the final (budget-exhausting) re-dispatch.
    assert sleeps == [4.0]
