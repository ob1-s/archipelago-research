from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import verifiers.v1 as vf
from verifiers.v1 import AssistantMessage

from constraint_forge_formation_v0.actions import FinishAction, SetAction
from constraint_forge_behavioral_runner_v1.failures import (
    BehavioralCallFailure,
    FailureClass,
    FailureEvidence,
)
from constraint_forge_behavioral_runner_v1.harness import (
    CALL_TIMEOUT_SECONDS,
    TEXT_PROGRAM_SOURCE,
    ConstraintForgeTextHarness,
    text_program_source,
)
from constraint_forge_behavioral_runner_v1.requests import memory_request
from constraint_forge_behavioral_runner_v1.runner import (
    SequenceResult,
    run_behavioral_sequence,
    stamp_sequence_traces,
)
from constraint_forge_behavioral_runner_v1.taskset import (
    ConstraintForgeBehavioralEnv,
    ConstraintForgeBehavioralEnvConfig,
    ConstraintForgeBehavioralTaskset,
    ConstraintForgeBehavioralTasksetConfig,
)
from constraint_forge_formation_v0.generator import generate_job
from constraint_forge_formation_v0.models import Station
from constraint_forge_formation_v0.rack import full_rack_view
from constraint_forge_formation_v0.world import run_job


class _FakeSegment:
    def __init__(self, raw: str):
        self.messages = [AssistantMessage(content=raw)]


class _FakeInteraction:
    def __init__(self, actor):
        self.actor = actor
        self.history: list[str] = []
        self.trace = type("FakeTrace", (), {})()

    def _prepare_prompt(self, payload: dict) -> None:
        if payload["phase"] != "round":
            return
        job_key = tuple(tuple(pair) for pair in payload["observation"]["private_pairs"])
        if payload["round"] == 1 or self.actor.active_job_key != job_key:
            self.actor.active_job_key = job_key
            self.history = []
            self.actor.contexts.append(self.history)

    async def turn(self, prompt: str):
        if self.actor.delay:
            await asyncio.sleep(self.actor.delay)
        payload = json.loads(prompt)
        self._prepare_prompt(payload)
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
        self.history.append(prompt)
        if payload["phase"] == "round":
            role = payload["role"]
            layer = payload["observation"]["layers"][role]
            mask = tuple(tuple(pair) for pair in payload["observation"]["private_pairs"])
            target = self.actor.target_by_mask[mask]
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
    def __init__(self, target_by_mask, *, delay: float = 0.0, rotate_memory: bool = False, fail_class=None):
        self.target_by_mask = target_by_mask
        self.delay = delay
        self.rotate_memory = rotate_memory
        self.fail_class = fail_class
        self.total_calls = 0
        self.contexts: list[list[str]] = []
        self.active_job_key = None
        self.interaction_count = 0

    @asynccontextmanager
    async def interaction(self, task):
        del task
        self.interaction_count += 1
        yield _FakeInteraction(self)


class _MalformedInteraction(_FakeInteraction):
    async def turn(self, prompt: str):
        payload = json.loads(prompt)
        self._prepare_prompt(payload)
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
        self.interaction_count += 1
        yield _MalformedInteraction(self)


def _task():
    return next(
        iter(
            ConstraintForgeBehavioralTaskset(
                ConstraintForgeBehavioralTasksetConfig(id="test")
            )
        )
    )


def _targets(task):
    targets = {}
    for seed in task.data.job_seeds:
        job = generate_job(seed)
        target = dict(job.target_matching)
        targets[tuple(job.x_mask)] = target
        targets[tuple(job.y_mask)] = target
    return targets


def _scripted_policy(job, station):
    target = dict(job.target_matching)

    def policy(observation):
        for item, current in enumerate(observation.layers[station.value]):
            if current is None:
                return SetAction(action="set", item=item, target=target[item])
        return FinishAction(action="finish")

    return policy


def _distinct_seeded_racks():
    job = generate_job(30)
    result = run_job(
        job,
        run_id="rack-seed",
        lineage_id="rack-seed",
        job_id="rack-seed-job",
        policy_x=_scripted_policy(job, Station.X),
        policy_y=_scripted_policy(job, Station.Y),
        memory_policy_x=lambda *_: (None, 1),
        memory_policy_y=lambda *_: (None, 1),
    )
    return result.final_rack_x, result.final_rack_y


def test_fake_24_job_dyad_is_complete_and_has_no_live_calls() -> None:
    async def run():
        task = _task()
        targets = _targets(task)
        x = _FakeActor(targets, delay=0.001, rotate_memory=True)
        y = _FakeActor(targets, delay=0.0, rotate_memory=True)
        return await run_behavioral_sequence(task.data, actor_x=x, actor_y=y, task=task), x, y

    result, x, y = asyncio.run(run())
    assert result.handoff.run_valid
    assert result.handoff.accepted
    assert not result.handoff.aborted
    assert result.handoff.completed_jobs == 24
    assert len(result.jobs) == 24
    assert all(job.complete for job in result.jobs)
    assert result.live_model_calls == 0
    assert len(x.contexts) == len(y.contexts) == 24
    assert x.interaction_count == y.interaction_count == 1
    assert result.ledger.verify().valid
    assert result.handoff.final_rack_x_bytes != result.handoff.final_rack_y_bytes
    for role in ("X", "Y"):
        role_events = [event for event in result.ledger.events if event.actor == role]
        assert len({event.actor_id for event in role_events}) == 1
        assert len({event.lifecycle_id for event in role_events}) == 1
        assert {event.context_epoch for event in role_events} == set(range(24))


def test_requests_are_sealed_from_one_prestate_and_completion_order_is_irrelevant() -> None:
    async def run(delay_x: float, delay_y: float):
        task = _task()
        targets = _targets(task)
        x = _FakeActor(targets, delay=delay_x)
        y = _FakeActor(targets, delay=delay_y)
        result = await run_behavioral_sequence(task.data, actor_x=x, actor_y=y, task=task)
        return result, x, y

    result, x, y = asyncio.run(run(0.003, 0.0))
    reversed_result, _, _ = asyncio.run(run(0.0, 0.003))
    x_requests = [json.loads(prompt) for context in x.contexts for prompt in context]
    y_requests = [json.loads(prompt) for context in y.contexts for prompt in context]
    assert all(
        key not in x_requests[0] and key not in y_requests[0]
        for key in ("job_index", "job_id", "context_epoch", "pre_state_hash", "schema_version")
    )
    x_events = {
        (event.job_index, event.phase, event.round): event.pre_state_hash
        for event in result.ledger.events
        if event.actor == "X" and event.status.value == "completed"
    }
    y_events = {
        (event.job_index, event.phase, event.round): event.pre_state_hash
        for event in result.ledger.events
        if event.actor == "Y" and event.status.value == "completed"
    }
    assert x_events == y_events
    assert result.handoff.run_valid
    assert result.handoff.serialization_bytes == reversed_result.handoff.serialization_bytes
    assert result.ledger.final_hash == reversed_result.ledger.final_hash


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
    assert "job-00" not in x.contexts[1][0]
    assert "job-00" not in y.contexts[1][0]
    assert "assistant" not in x.contexts[1][0]
    assert len(x.contexts[1][0]) > 0
    assert len(json.loads(x.contexts[1][0])["observation"]["rack"]["full_films"]) == 1
    assert len(json.loads(x.contexts[1][0])["observation"]["private_pairs"]) == 18
    assert len(result.handoff.job_receipts) == 24


def test_x_and_y_receive_only_their_role_local_rack() -> None:
    rack_x, rack_y = _distinct_seeded_racks()
    x_view = full_rack_view(rack_x)
    y_view = full_rack_view(rack_y)
    x_request = memory_request(
        role="X",
        phase="eviction",
        job_index=0,
        job_id="j",
        context_epoch=0,
        pre_state_hash="0" * 64,
        rack=x_view,
        frames=(),
        success=True,
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
        success=True,
    )
    assert set(x_request.visible_payload) == set(y_request.visible_payload)
    assert "rack_x" not in x_request.prompt_text
    assert "rack_y" not in x_request.prompt_text
    assert x_request.visible_payload["role"] == "X"
    assert y_request.visible_payload["role"] == "Y"
    assert x_request.visible_payload["success"] is True
    assert y_request.visible_payload["success"] is True
    assert "failure_reason" not in x_request.visible_payload
    assert "target_matching" not in x_request.visible_payload
    for film in rack_y.films:
        assert film.handle not in x_request.prompt_text
        assert film.content_hash not in x_request.prompt_text
    for film in rack_x.films:
        assert film.handle not in y_request.prompt_text
        assert film.content_hash not in y_request.prompt_text
    assert "source_job_id" not in x_request.prompt_text
    assert "source_job_id" not in y_request.prompt_text


def test_safe_preinference_retry_has_one_behavioral_sample() -> None:
    async def run():
        task = _task()
        targets = _targets(task)
        x = _FakeActor(targets, fail_class=FailureClass.LOCAL_PRE_DISPATCH)
        y = _FakeActor(targets)
        return await run_behavioral_sequence(task.data, actor_x=x, actor_y=y, task=task), x

    result, x = asyncio.run(run())
    assert result.handoff.accepted
    assert x.total_calls == sum(
        event.actor == "X" and event.status.value == "prepared"
        for event in result.ledger.events
    )
    safe = [event for event in result.ledger.events if event.status.value == "safe_retry"]
    assert len(safe) == 1
    assert safe[0].raw_output is None
    assert sum(event.status.value == "completed" for event in result.ledger.events) > 0


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
    assert len(result.jobs) == 1
    assert result.jobs[0].complete is False
    assert result.jobs[0].event_log.events
    assert any(event.status.value == "audit_only" for event in result.ledger.events)
    assert sum(event.status.value == "audit_only" for event in result.ledger.events) == 1
    assert all(
        event.world_event_sequence_start is None
        for event in result.ledger.events
        if event.status.value in {"failed", "audit_only"}
    )
    assert result.ledger.verify().valid


def test_invalid_partial_run_keeps_statistics_but_receives_zero_reward() -> None:
    async def run():
        task = _task()
        targets = _targets(task)
        return await run_behavioral_sequence(
            task.data,
            actor_x=_FakeActor(targets),
            actor_y=_FakeActor(targets),
            task=task,
        )

    valid = asyncio.run(run())

    class V1LikeTrace:
        def __init__(self):
            self.state = type("State", (), {})()
            self.info = {}
            self.rewards = {}

        def record_reward(self, name: str, value: float) -> None:
            self.rewards[name] = value

    trace = V1LikeTrace()
    invalid_handoff = valid.handoff.model_copy(
        update={
            "run_valid": False,
            "accepted": False,
            "aborted": True,
            "abort_class": "DyadAbort",
        }
    )
    invalid = SequenceResult(
        handoff=invalid_handoff,
        audit_event_count=valid.audit_event_count,
        live_model_calls=valid.live_model_calls,
        traces=(SimpleNamespace(trace=trace),),
        ledger=valid.ledger,
        jobs=valid.jobs,
    )
    stamp_sequence_traces(invalid)

    assert invalid_handoff.job_success_mean > 0.0
    assert trace.state.job_success_mean == invalid_handoff.job_success_mean
    assert trace.rewards["formation_accepted"] == 0.0
    assert trace.info["constraint_forge_behavioral_runner"]["behavioral_reward"] == 0.0


def test_read_only_sequence_job_has_no_memory_calls() -> None:
    async def run():
        task = _task()
        data = task.data.model_copy(update={"read_only_job_indices": (0,)})
        targets = _targets(task)
        x = _FakeActor(targets)
        y = _FakeActor(targets)
        return await run_behavioral_sequence(data, actor_x=x, actor_y=y, task=task), x, y

    result, x, y = asyncio.run(run())
    assert result.handoff.run_valid
    assert len(x.contexts[0]) == len(y.contexts[0]) == 7
    assert len(x.contexts[1]) > len(x.contexts[0])


def test_malformed_response_is_rejected_behavioral_data_and_is_not_retried() -> None:
    async def run():
        task = _task()
        targets = _targets(task)
        x = _MalformedOnceActor(targets)
        y = _FakeActor(targets)
        return await run_behavioral_sequence(task.data, actor_x=x, actor_y=y, task=task)

    result = asyncio.run(run())
    assert result.handoff.run_valid
    malformed = [
        event
        for event in result.ledger.events
        if event.parse_classification == "malformed_rejected"
    ]
    assert len(malformed) == 1
    assert malformed[0].status.value == "completed"
    assert result.live_model_calls == 0
    first_job = result.jobs[0]
    malformed_rejections = [
        event
        for event in first_job.event_log.events
        if event.event_kind.value == "ACTION_REJECTED"
        and event.rejection_reason == "malformed_action"
    ]
    assert len(malformed_rejections) == 1
    rejected = malformed_rejections[0]
    assert rejected.legal is False
    assert rejected.action_payload == {"action": "rejected"}
    assert "{not-json" not in json.dumps(first_job.model_dump(mode="json"))


def test_minimal_harness_forbids_tools_and_uses_native_session_surface() -> None:
    assert issubclass(ConstraintForgeBehavioralEnv, vf.Env)
    assert issubclass(ConstraintForgeTextHarness, vf.Harness)
    assert ConstraintForgeTextHarness.SUPPORTS_MCP is False
    assert ConstraintForgeTextHarness.SUPPORTS_RESUME is True
    assert ConstraintForgeTextHarness.EXECUTES_CODE is False
    assert ConstraintForgeTextHarness.NEEDS_CONTAINER is False
    assert CALL_TIMEOUT_SECONDS == 120.0
    # The embedded SDK timeout stays a declared knob with the frozen 120 s
    # default; launchers may override it per process.
    assert "default=120.0" in text_program_source()
    assert "default=300.0" in text_program_source(300.0)
    assert "timeout=args.timeout" in text_program_source()
    assert "max_retries=0" in TEXT_PROGRAM_SOURCE
    assert "stream=True" not in TEXT_PROGRAM_SOURCE
    assert "mcp" not in TEXT_PROGRAM_SOURCE.lower()
    assert "tool" not in TEXT_PROGRAM_SOURCE.lower()
    config = ConstraintForgeBehavioralEnvConfig()
    assert config.retries.max_retries == 0
    assert config.x.retries.max_retries == 0
    assert config.y.retries.max_retries == 0
