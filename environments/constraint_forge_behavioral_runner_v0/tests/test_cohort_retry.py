"""Deterministic checks for the declared cohort-v2 infrastructure retry rule."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from constraint_forge_behavioral_runner_v0.failures import (
    FailureClass,
    infrastructure_failure,
    retryable_infrastructure,
)
from constraint_forge_behavioral_runner_v0.harness import (
    ConstraintForgeTextHarnessSession,
    configure_text_harness_boundary,
    text_harness_boundary,
)
from constraint_forge_behavioral_runner_v0.runner import (
    _inspect_segment_native_calls,
    run_behavioral_sequence,
)
from test_runner import (
    _FakeActor,
    _FakeInteraction,
    _targets,
    _task,
)


def _error_call(status_code: int):
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
    return SimpleNamespace(finish_reason=None, error=error)


def _stop_call():
    return SimpleNamespace(finish_reason="stop", error=None)


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


class _Trace:
    def __init__(self, calls: list):
        self.calls = calls


class _Interaction:
    def __init__(self, calls: list, segment=None, error: Exception | None = None):
        self.trace = _Trace(calls)
        self._segment = segment
        self._error = error
        self.dispatches = 0

    async def turn(self, prompt: str):
        self.dispatches += 1
        if self._error is not None:
            raise self._error
        return self._segment


def _classify(calls) -> FailureClass | None:
    interaction = _Interaction(list(calls))
    _, _, evidence = _inspect_segment_native_calls(interaction, 0)
    return evidence.failure_class if evidence is not None else None


def test_only_listed_infra_statuses_are_retryable_and_multi_attempt_segments_pass() -> None:
    segment_ok = object()
    # A consumed 500 followed by a clean stop is a valid v2 success segment.
    interaction = _Interaction([_error_call(500), _stop_call()], segment=segment_ok)
    final, infra_attempts, evidence = _inspect_segment_native_calls(interaction, 0)
    assert evidence is None
    assert len(infra_attempts) == 1
    assert final is not None

    assert _classify([_error_call(400)]) is FailureClass.PARTIAL_RESPONSE
    assert _classify([]) is FailureClass.PARTIAL_RESPONSE
    delivered_length = SimpleNamespace(finish_reason="length", error=None)
    assert _classify([delivered_length]) is FailureClass.PARTIAL_RESPONSE
    assert _classify([_error_call(500), delivered_length]) is FailureClass.PARTIAL_RESPONSE
    # A non-infra intermediate invalidates the whole segment.
    assert _classify([delivered_length, _stop_call()]) is FailureClass.PARTIAL_RESPONSE


class _HarnessRelaunchInteraction(_FakeInteraction):
    """The harness consumes one infra retry inside this single dispatch."""

    async def turn(self, prompt: str):
        self.actor.total_calls += 1
        if self.actor.fail_once:
            self.actor.fail_once = False
            # The harness relaunch leaves the failed attempt on the trace and
            # still returns a delivered response for this opportunity.
            self.trace.calls.append(_error_call(500))
        self.trace.calls.append(_stop_call())
        return await super().turn(prompt)


class _RelaunchActor(_FakeActor):
    def __init__(self, target_by_mask):
        super().__init__(target_by_mask)
        self.fail_once = True

    @asynccontextmanager
    async def interaction(self, task):
        del task
        self.interaction_count += 1
        interaction = _HarnessRelaunchInteraction(self)
        interaction.trace.calls = list(getattr(self, "_seed_calls", []))
        yield interaction


def test_one_consumed_harness_retry_counts_as_one_opportunity(monkeypatch) -> None:
    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    sleeps: list[float] = []
    monkeypatch.setattr(
        "constraint_forge_behavioral_runner_v0.runner.asyncio.sleep", fake_sleep
    )

    async def run():
        task = _task()
        targets = _targets(task)
        x = _RelaunchActor(targets)
        y = _FakeActor(targets)
        result = await run_behavioral_sequence(
            task.data, actor_x=x, actor_y=y, task=task
        )
        return result

    result = asyncio.run(run())
    infra = [
        event for event in result.ledger.events if event.status.value == "infra_retry"
    ]
    assert len(infra) == 1
    assert infra[0].actor == "X"
    assert infra[0].failure_class == "infrastructure_undelivered"
    completed_with_chain = [
        event
        for event in result.ledger.events
        if event.status.value == "completed" and event.retry_of == infra[0].call_id
    ]
    assert len(completed_with_chain) == 1
    assert not any(event.status.value == "audit_only" for event in result.ledger.events)
    assert result.handoff.aborted is False


def test_exhausted_budget_aborts_without_reentering_the_interaction() -> None:
    class _ExhaustedActor(_FakeActor):
        @asynccontextmanager
        async def interaction(self, task):
            del task
            self.interaction_count += 1

            class _T(_FakeInteraction):
                async def turn(self, prompt: str):
                    self.actor.total_calls += 1
                    if not hasattr(self.trace, "calls"):
                        self.trace.calls = []
                    self.trace.calls.append(_error_call(429))
                    raise infrastructure_failure(429)

            yield _T(self)

    async def run():
        task = _task()
        targets = _targets(task)
        x = _ExhaustedActor(targets)
        y = _FakeActor(targets)
        return await run_behavioral_sequence(
            task.data, actor_x=x, actor_y=y, task=task
        ), x

    result, x = asyncio.run(run())
    assert result.handoff.aborted
    assert x.total_calls == 1, "runner must never re-enter a dead exchange"
    x_events = [event for event in result.ledger.events if event.actor == "X"]
    failed = [event for event in x_events if event.status.value == "failed"]
    assert len(failed) == 1
    assert failed[0].failure_class == "infrastructure_undelivered"


def _make_session(trace_calls: list, exit_codes: list[int], receipt: dict):
    session = ConstraintForgeTextHarnessSession.__new__(ConstraintForgeTextHarnessSession)
    session.trace = SimpleNamespace(calls=trace_calls)
    from types import SimpleNamespace as _NS

    async def _write_messages_file(runtime, data):
        del runtime, data
        return "cf-messages-test.json"

    session.harness = _NS(
        config=_NS(resolved_env={}),
        _wire_messages=lambda data: [{"role": "user", "content": "x"}],
        _write_messages_file=_write_messages_file,
    )

    async def prepare_uv_script(source, env):
        del source, env
        return ["prog"]

    async def run_program(argv, env):
        del argv, env
        code = exit_codes.pop(0)
        if code != 0:
            trace_calls.append(_error_call(500))
        else:
            trace_calls.append(_stop_call())
        return SimpleNamespace(exit_code=code, stderr="")

    session.runtime = SimpleNamespace(
        prepare_uv_script=prepare_uv_script, run_program=run_program
    )
    return session


def test_harness_relaunch_loop_consumes_declared_budget(monkeypatch) -> None:
    configure_text_harness_boundary(
        call_timeout_seconds=300.0,
        infra_retries=2,
        infra_backoff_seconds=(4.0, 8.0),
    )
    assert text_harness_boundary() == (300.0, 2, (4.0, 8.0))

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(
        "constraint_forge_behavioral_runner_v0.harness.asyncio.sleep", fake_sleep
    )

    calls: list = []
    receipt: dict = {"attempts": []}
    session = _make_session(calls, exit_codes=[1, 1, 0], receipt=receipt)
    result = asyncio.run(
        session._launch_with_infra_retries(
            ctx=SimpleNamespace(model="m"),
            runtime=session.runtime,
            endpoint="http://x",
            secret="s",
            data=SimpleNamespace(),
            request_receipt=receipt,
            call_count=0,
        )
    )
    assert result.exit_code == 0
    assert len(calls) == 3
    assert [a["attempt"] for a in receipt["attempts"]] == [0, 1, 2]
    assert sleeps == [4.0, 8.0]

    # Budget exhaustion returns the last failure instead of looping forever.
    calls2: list = []
    receipt2: dict = {"attempts": []}
    session2 = _make_session(calls2, exit_codes=[1, 1, 1], receipt=receipt2)
    result2 = asyncio.run(
        session2._launch_with_infra_retries(
            ctx=SimpleNamespace(model="m"),
            runtime=session2.runtime,
            endpoint="http://x",
            secret="s",
            data=SimpleNamespace(),
            request_receipt=receipt2,
            call_count=0,
        )
    )
    assert result2.exit_code == 1
    assert len(receipt2["attempts"]) == 3


def test_runner_guard_honors_the_declared_boundary_timeout(monkeypatch) -> None:
    """A slow-but-live launch must survive when the boundary timeout allows it."""

    from verifiers.v1 import AssistantMessage

    class _SlowFirstDispatch(_FakeInteraction):
        def __init__(self, actor, seconds: float):
            super().__init__(actor)
            self.seconds = seconds
            self.trace.calls = []

        async def turn(self, prompt: str):
            delay, self.seconds = self.seconds, 0.0
            if delay:
                await asyncio.sleep(delay)
            self.trace.calls.append(_stop_call())
            return await super().turn(prompt)

    class _SlowActor(_FakeActor):
        def __init__(self, target_by_mask, seconds: float):
            super().__init__(target_by_mask)
            self.slow_seconds = seconds

        @asynccontextmanager
        async def interaction(self, task):
            del task
            self.interaction_count += 1
            yield _SlowFirstDispatch(self, self.slow_seconds)

    def run_with(boundary_seconds: float, slow: float):
        from constraint_forge_behavioral_runner_v0.harness import (
            configure_text_harness_boundary,
        )

        configure_text_harness_boundary(call_timeout_seconds=boundary_seconds)
        task = _task()
        targets = _targets(task)
        x = _SlowActor(targets, slow)
        y = _FakeActor(targets)
        return asyncio.run(
            run_behavioral_sequence(task.data, actor_x=x, actor_y=y, task=task)
        )

    # A generation slower than any plausible default but within the declared
    # boundary completes and advances the world.
    ok = run_with(30.0, 2.0)
    assert not ok.handoff.aborted
    assert ok.handoff.completed_jobs == len(ok.jobs)
    # The identical generation under a tighter declared guard is aborted as a
    # visible timeout, never silently absorbed as a partial response.
    guarded = run_with(1.0, 2.0)
    assert guarded.handoff.aborted
    timeouts = [
        event
        for event in guarded.ledger.events
        if event.failure_class == "timeout_ambiguous"
    ]
    assert timeouts


