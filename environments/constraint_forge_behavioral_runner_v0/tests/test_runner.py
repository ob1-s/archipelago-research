from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from verifiers.v1 import AssistantMessage

from constraint_forge_behavioral_runner_v0.failures import (
    BehavioralCallFailure,
    FailureClass,
    FailureEvidence,
)
from constraint_forge_behavioral_runner_v0.harness import ConstraintForgeTextHarness
from constraint_forge_behavioral_runner_v0.requests import memory_request
from constraint_forge_behavioral_runner_v0.runner import run_behavioral_sequence
from constraint_forge_behavioral_runner_v0.taskset import (
    ConstraintForgeBehavioralTaskset,
    ConstraintForgeBehavioralTasksetConfig,
)
from constraint_forge_formation_v0.rack import RackState, full_rack_view


class _FakeSegment:
    def __init__(self, raw: str):
        self.messages = [AssistantMessage(content=raw)]


class _FakeInteraction:
    def __init__(self, actor, history: list[str]):
        self.actor = actor
        self.history = history
        self.trace = type("FakeTrace", (), {})()

    async def turn(self, prompt: str):
        self.history.append(prompt)
        self.actor.total_calls += 1
        if self.actor.fail_class is not None and self.actor.total_calls == 1:
            evidence = FailureEvidence(
                failure_class=self.actor.fail_class,
                request_dispatched=self.actor.fail_class
                not in {FailureClass.LOCAL_PRE_DISPATCH, FailureClass.PROVIDER_REJECTED_PRE_INFERENCE},
                behavioral_sample_produced=(
                    False
                    if self.actor.fail_class
                    in {FailureClass.LOCAL_PRE_DISPATCH, FailureClass.PROVIDER_REJECTED_PRE_INFERENCE}
                    else None
                ),
                detail="fake provider failure",
            )
            raise BehavioralCallFailure(evidence)
        payload = json.loads(prompt)
        if payload["phase"] == "round":
            role = payload["role"]
            layer = payload["observation"]["layers"][role]
            target = self.actor.target_by_job[payload["job_index"]]
            for item, current in enumerate(layer):
                if current is None:
                    raw = {"action": "set", "item": item, "target": target[item]}
                    break
            else:
                raw = {"action": "finish"}
        elif payload["phase"] == "eviction":
            films = (payload["rack"] or {}).get("full_films", [])
            raw = (
                {"action": "evict", "fragment_handle": films[0]["handle"]}
                if self.actor.rotate_memory and films
                else {"action": "keep_unchanged"}
            )
        else:
            raw = (
                {"action": "retain", "start_round": 1}
                if self.actor.rotate_memory
                else {"action": "keep_unchanged"}
            )
        return _FakeSegment(json.dumps(raw, separators=(",", ":")))


class _FakeActor:
    def __init__(self, target_by_job, *, delay: float = 0.0, rotate_memory: bool = False, fail_class=None):
        self.target_by_job = target_by_job
        self.delay = delay
        self.rotate_memory = rotate_memory
        self.fail_class = fail_class
        self.total_calls = 0
        self.contexts: list[list[str]] = []

    @asynccontextmanager
    async def interaction(self, task):
        del task
        history: list[str] = []
        self.contexts.append(history)
        if self.delay:
            await asyncio.sleep(self.delay)
        yield _FakeInteraction(self, history)


class _MalformedInteraction(_FakeInteraction):
    async def turn(self, prompt: str):
        if self.actor.malformed:
            self.actor.malformed = False
            self.history.append(prompt)
            self.actor.total_calls += 1
            return _FakeSegment("{not-json")
        return await super().turn(prompt)


class _MalformedOnceActor(_FakeActor):
    def __init__(self, target_by_job):
        super().__init__(target_by_job)
        self.malformed = True

    @asynccontextmanager
    async def interaction(self, task):
        del task
        history: list[str] = []
        self.contexts.append(history)
        yield _MalformedInteraction(self, history)


def _task():
    return next(
        iter(
            ConstraintForgeBehavioralTaskset(
                ConstraintForgeBehavioralTasksetConfig(id="test")
            )
        )
    )


def _targets(task):
    from constraint_forge_formation_v0.generator import generate_job

    return [dict(generate_job(seed).target_matching) for seed in task.data.job_seeds]


def test_fake_24_job_dyad_is_complete_and_has_no_live_calls() -> None:
    async def run():
        task = _task()
        targets = _targets(task)
        x = _FakeActor(targets, delay=0.001, rotate_memory=True)
        y = _FakeActor(targets, delay=0.0, rotate_memory=True)
        return await run_behavioral_sequence(task.data, actor_x=x, actor_y=y, task=task), x, y

    result, x, y = asyncio.run(run())
    assert result.handoff.accepted
    assert not result.handoff.aborted
    assert result.handoff.completed_jobs == 24
    assert result.live_model_calls == 0
    assert len(x.contexts) == len(y.contexts) == 24
    assert result.ledger.verify().valid
    assert result.handoff.final_rack_x_bytes != result.handoff.final_rack_y_bytes
    for role in ("X", "Y"):
        role_events = [event for event in result.ledger.events if event.actor == role]
        assert len({event.actor_id for event in role_events}) == 1
        assert len({event.lifecycle_id for event in role_events}) == 1
        assert {event.context_epoch for event in role_events} == set(range(24))


def test_requests_are_sealed_from_one_prestate_and_completion_order_is_irrelevant() -> None:
    async def run():
        task = _task()
        targets = _targets(task)
        x = _FakeActor(targets, delay=0.003)
        y = _FakeActor(targets, delay=0.0)
        result = await run_behavioral_sequence(task.data, actor_x=x, actor_y=y, task=task)
        return result, x, y

    result, x, y = asyncio.run(run())
    x_requests = [json.loads(prompt) for context in x.contexts for prompt in context]
    y_requests = [json.loads(prompt) for context in y.contexts for prompt in context]
    x_hashes = {(p["job_index"], p["round"], p["phase"]): p["pre_state_hash"] for p in x_requests if p["phase"] == "round"}
    y_hashes = {(p["job_index"], p["round"], p["phase"]): p["pre_state_hash"] for p in y_requests if p["phase"] == "round"}
    assert x_hashes == y_hashes
    assert result.handoff.accepted


def test_job_context_resets_but_role_lifecycle_and_rack_sequence_continue() -> None:
    async def run():
        task = _task()
        targets = _targets(task)
        x = _FakeActor(targets, rotate_memory=True)
        y = _FakeActor(targets, rotate_memory=True)
        result = await run_behavioral_sequence(task.data, actor_x=x, actor_y=y, task=task)
        return result, x, y

    result, x, y = asyncio.run(run())
    assert result.handoff.accepted
    # Every context starts with the current job's fresh request.  The next job
    # cannot see the previous job id or assistant text.
    assert "job-00" not in x.contexts[1][0]
    assert "job-00" not in y.contexts[1][0]
    assert "assistant" not in x.contexts[1][0]
    assert len(x.contexts[1][0]) > 0
    assert len(json.loads(x.contexts[1][0])["observation"]["rack"]["full_films"]) == 1
    assert len(json.loads(x.contexts[1][0])["observation"]["private_pairs"]) == 18
    assert len(result.handoff.job_receipts) == 24


def test_x_and_y_receive_only_their_role_local_rack() -> None:
    x_view = full_rack_view(RackState())
    y_view = full_rack_view(RackState())
    x_request = memory_request(
        role="X",
        phase="eviction",
        job_index=0,
        job_id="j",
        context_epoch=0,
        pre_state_hash="0" * 64,
        rack=x_view,
        frames=(),
    )
    y_request = memory_request(
        role="Y",
        phase="eviction",
        job_index=0,
        job_id="j",
        context_epoch=0,
        pre_state_hash="0" * 64,
        rack=y_view,
        frames=(),
    )
    assert set(x_request.visible_payload) == set(y_request.visible_payload)
    assert "rack_x" not in x_request.prompt_text
    assert "rack_y" not in x_request.prompt_text
    assert x_request.visible_payload["role"] == "X"
    assert y_request.visible_payload["role"] == "Y"


def test_safe_preinference_retry_has_one_behavioral_sample() -> None:
    async def run():
        task = _task()
        targets = _targets(task)
        x = _FakeActor(
            targets,
            fail_class=FailureClass.LOCAL_PRE_DISPATCH,
        )
        y = _FakeActor(targets)
        return await run_behavioral_sequence(task.data, actor_x=x, actor_y=y, task=task), x

    result, x = asyncio.run(run())
    assert result.handoff.accepted
    assert x.total_calls == result.audit_event_count // 2 + 1
    safe = [event for event in result.ledger.events if event.status.value == "safe_retry"]
    assert len(safe) == 1
    assert safe[0].raw_output is None
    assert sum(event.status.value == "completed" for event in result.ledger.events) == result.audit_event_count - 1


def test_ambiguous_delivery_aborts_and_sibling_output_is_audit_only() -> None:
    async def run():
        task = _task()
        targets = _targets(task)
        x = _FakeActor(targets, fail_class=FailureClass.DELIVERY_AMBIGUOUS)
        y = _FakeActor(targets)
        return await run_behavioral_sequence(task.data, actor_x=x, actor_y=y, task=task)

    result = asyncio.run(run())
    assert result.handoff.aborted
    assert not result.handoff.accepted
    assert result.handoff.completed_jobs == 0
    assert any(event.status.value == "audit_only" for event in result.ledger.events)
    assert all(
        event.world_event_sequence_start is None
        for event in result.ledger.events
        if event.status.value in {"failed", "audit_only"}
    )
    assert result.ledger.verify().valid


def test_read_only_sequence_job_has_no_memory_calls() -> None:
    async def run():
        task = _task()
        data = task.data.model_copy(update={"read_only_job_indices": (0,)})
        targets = _targets(task)
        x = _FakeActor(targets)
        y = _FakeActor(targets)
        return await run_behavioral_sequence(data, actor_x=x, actor_y=y, task=task), x, y

    result, x, y = asyncio.run(run())
    assert result.handoff.accepted
    assert len(x.contexts[0]) == len(y.contexts[0]) == 7
    assert len(x.contexts[1]) > len(x.contexts[0])


def test_malformed_response_is_behavioral_data_and_is_not_retried() -> None:
    async def run():
        task = _task()
        targets = _targets(task)
        x = _MalformedOnceActor(targets)
        y = _FakeActor(targets)
        return await run_behavioral_sequence(task.data, actor_x=x, actor_y=y, task=task)

    result = asyncio.run(run())
    assert result.handoff.accepted
    malformed = [
        event
        for event in result.ledger.events
        if event.parse_classification == "malformed_noop"
    ]
    assert len(malformed) == 1
    assert malformed[0].status.value == "completed"
    assert result.live_model_calls == 0


def test_minimal_harness_forbids_tools_and_uses_native_session_surface() -> None:
    assert ConstraintForgeTextHarness.SUPPORTS_MCP is False
    assert ConstraintForgeTextHarness.SUPPORTS_RESUME is True
    assert ConstraintForgeTextHarness.EXECUTES_CODE is False
    assert ConstraintForgeTextHarness.NEEDS_CONTAINER is False
