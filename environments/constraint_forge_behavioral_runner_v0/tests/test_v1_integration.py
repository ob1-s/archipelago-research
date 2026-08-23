"""No-network native-v1 boundary integration for the behavioral runner."""

from __future__ import annotations

import asyncio
import copy
import json
from urllib.parse import urlparse

import httpx
import verifiers.v1 as vf
from verifiers.v1.clients import Client
from verifiers.v1.configs.agent import AgentConfig
from verifiers.v1.configs.client import EvalClientConfig
from verifiers.v1.interception import InterceptionServer
from verifiers.v1.runtimes import ProgramResult, Runtime
from verifiers.v1.runtimes.subprocess import SubprocessConfig, SubprocessRuntimeInfo
from verifiers.v1.types import AssistantMessage, Response

from constraint_forge_formation_v0.generator import generate_job
from constraint_forge_behavioral_runner_v0.harness import ConstraintForgeTextHarnessConfig
from constraint_forge_behavioral_runner_v0.runner import run_behavioral_sequence
from constraint_forge_behavioral_runner_v0.taskset import (
    ConstraintForgeBehavioralTask,
    ConstraintForgeBehavioralTaskset,
    ConstraintForgeBehavioralTasksetConfig,
)


class _DeterministicClient(Client):
    """A local interception client with an out-of-band target codebook."""

    def __init__(self, data) -> None:
        self.requests: list[dict] = []
        self.session_ids: list[str | None] = []
        self.hidden_state_responses = 0
        self._targets: dict[tuple[tuple[int, int], ...], dict[int, int]] = {}
        for seed in data.job_seeds:
            job = generate_job(seed)
            target = dict(job.target_matching)
            self._targets[tuple(job.x_mask)] = target
            self._targets[tuple(job.y_mask)] = target

    async def get_response(
        self,
        dialect,
        body,
        model,
        sampling_args,
        session_id=None,
        turn=None,
        headers=None,
    ) -> Response:
        del dialect, sampling_args, turn, headers
        self.requests.append(copy.deepcopy(body))
        self.session_ids.append(session_id)
        request = json.loads(body["messages"][-1]["content"])
        if request["phase"] == "round":
            observation = request["observation"]
            target = self._targets[
                tuple(tuple(pair) for pair in observation["private_pairs"])
            ]
            layer = observation["layers"][request["role"]]
            answer = next(
                (
                    {"action": "set", "item": item, "target": target[item]}
                    for item, current in enumerate(layer)
                    if current is None
                ),
                {"action": "finish"},
            )
        else:
            answer = {"action": "keep_unchanged"}
        hidden = self.hidden_state_responses == 0
        if hidden:
            self.hidden_state_responses += 1
        return Response(
            id=f"local-fake-{len(self.requests)}",
            created=0,
            model=model,
            message=AssistantMessage(
                content=json.dumps(answer, separators=(",", ":")),
                reasoning_content="audit-only hidden reasoning" if hidden else None,
                provider_state=[{"opaque": "provider continuation"}] if hidden else None,
            ),
            finish_reason="stop",
        )


class _LengthOnceClient(_DeterministicClient):
    async def get_response(self, *args, **kwargs) -> Response:
        response = await super().get_response(*args, **kwargs)
        if len(self.requests) == 1:
            return response.model_copy(update={"finish_reason": "length"})
        return response


class _DeterministicInterception(InterceptionServer):
    def __init__(self, client: _DeterministicClient) -> None:
        super().__init__()
        self.client = client

    def _client(self, config):
        del config
        return self.client


class _InProcessRuntime(Runtime):
    """A test runtime that executes the real harness launch against local v1."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.config = SubprocessConfig()
        self.info = SubprocessRuntimeInfo()
        self.files: dict[str, bytes] = {}

    async def start(self) -> None:
        self.info.id = self.name

    async def write(self, path: str, data: bytes) -> None:
        self.files[path] = data

    async def prepare_uv_script(self, *args, **kwargs) -> list[str]:
        return ["constraint-forge-test-program"]

    async def run(self, argv: list[str], env: dict[str, str]) -> ProgramResult:
        del argv, env
        return ProgramResult(exit_code=0, stdout="", stderr="")

    async def run_program(self, argv: list[str], env: dict[str, str]) -> ProgramResult:
        del env
        endpoint = next(
            value.split("=", 1)[1]
            for value in argv
            if value.startswith("--base-url=")
        )
        if urlparse(endpoint).hostname != "127.0.0.1":
            return ProgramResult(1, "", "test runtime would leave localhost")
        api_key = next(
            value.split("=", 1)[1]
            for value in argv
            if value.startswith("--api-key=")
        )
        model = next(
            value.split("=", 1)[1]
            for value in argv
            if value.startswith("--model=")
        )
        messages_file = next(
            value.split("=", 1)[1]
            for value in argv
            if value.startswith("--messages-file=")
        )
        messages = json.loads(self.files[messages_file].decode("utf-8"))
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{endpoint}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "messages": messages, "stream": False},
            )
        if response.status_code != 200:
            return ProgramResult(response.status_code, "", response.text)
        del model, messages
        return ProgramResult(0, "", "")

    async def _read(self, path: str) -> bytes:
        del path
        return b""


async def _run_native(client_type=_DeterministicClient):
    base_task = next(
        iter(
            ConstraintForgeBehavioralTaskset(
                ConstraintForgeBehavioralTasksetConfig(id="v1-integration")
            )
        )
    )
    data = base_task.data.model_copy(
        update={"network_allow": ["*"], "network_block": []}
    )
    task = ConstraintForgeBehavioralTask(data, base_task.config)
    client = client_type(data)
    interception = _DeterministicInterception(client)
    config = AgentConfig(
        model="constraint-forge-local-fake",
        client=EvalClientConfig(
            base_url="http://127.0.0.1:1/v1",
            api_key_var="CONSTRAINT_FORGE_TEST_KEY",
        ),
        harness=ConstraintForgeTextHarnessConfig(),
        runtime=SubprocessConfig(),
        max_turns=420,
    )
    agent_x = vf.Agent(config, interception=interception)
    agent_y = vf.Agent(config, interception=interception)
    async with interception:
        result = await run_behavioral_sequence(
            data,
            actor_x=agent_x,
            actor_y=agent_y,
            task=task,
            runtime_x=_InProcessRuntime("constraint-forge-x"),
            runtime_y=_InProcessRuntime("constraint-forge-y"),
        )
    return result, client


def test_real_v1_agent_harness_session_and_interception_are_no_network_and_sanitized() -> None:
    result, client = asyncio.run(_run_native())
    assert result.handoff.run_valid
    assert result.handoff.job_success_mean > 0.0
    assert result.handoff.completed_jobs == 24
    assert len(result.jobs) == 24
    assert 0 < result.live_model_calls <= 2 * 420
    assert len(result.traces) == 2
    assert all(trace.trace.reward > 0.0 for trace in result.traces)
    assert all(trace.trace.state.run_valid for trace in result.traces)
    assert all(len(trace.trace.calls) > 0 for trace in result.traces)
    assert all(call.finish_reason == "stop" for trace in result.traces for call in trace.trace.calls)
    assert client.hidden_state_responses == 1
    assert any(
        message.reasoning_content == "audit-only hidden reasoning"
        for trace in result.traces
        for message in trace.trace.assistant_messages
    )
    assert any(
        message.provider_state == [{"opaque": "provider continuation"}]
        for trace in result.traces
        for message in trace.trace.assistant_messages
    )
    assert all(trace.trace.id for trace in result.traces)
    assert result.handoff.lineage_x != result.handoff.lineage_y
    assert {
        event.lifecycle_id
        for event in result.ledger.events
        if event.actor == "X"
    } == {result.handoff.lineage_x}
    assert {
        event.lifecycle_id
        for event in result.ledger.events
        if event.actor == "Y"
    } == {result.handoff.lineage_y}
    assert len({session_id for session_id in client.session_ids if session_id}) == 2

    # The normal persisted Trace now carries one self-contained, explicitly
    # non-scientific evidence bundle rather than only summary hashes.
    for wrapped in result.traces:
        info = wrapped.trace.info
        bundle = info["constraint_forge_canary_evidence_v0"]
        assert bundle["scientific_eligible"] is False
        assert len(bundle["audit_events"]) == len(result.ledger.events)
        assert len(bundle["jobs"]) == 24
        assert len(bundle["traces"]) == 2
        assert info["constraint_forge_canary_evidence_hash"]
        receipts = info["constraint_forge_provider_requests"]
        assert receipts
        assert all(receipt["completed"] is True for receipt in receipts)
        assert all(receipt["finish_reason"] == "stop" for receipt in receipts)
        assert all(receipt["request"]["stream"] is False for receipt in receipts)
        assert all(receipt["request"]["endpoint_path"] == "/chat/completions" for receipt in receipts)
        assert all(receipt["request"]["messages"][0]["role"] == "system" for receipt in receipts)

    forbidden_keys = {
        "schema_version",
        "job_index",
        "job_id",
        "context_epoch",
        "pre_state_hash",
        "run_id",
        "lineage_id",
        "source_job_id",
    }
    current_job_by_session: dict[str, list[str]] = {}
    for body, session_id in zip(client.requests, client.session_ids):
        assert session_id is not None
        encoded = json.dumps(body, sort_keys=True)
        assert "source_job_id" not in encoded
        assert all(f'"{key}"' not in encoded for key in forbidden_keys)
        for message in body["messages"]:
            if message["role"] == "assistant":
                assert set(message) <= {"role", "content"}
        current = json.loads(body["messages"][-1]["content"])
        if current["phase"] != "round":
            continue
        current_job = current_job_by_session.setdefault(session_id, [])
        wire_contents = [message.get("content", "") for message in body["messages"]]
        if current["round"] == 1:
            assert all(previous not in wire_contents for previous in current_job)
            current_job.clear()
        else:
            assert current_job
            assert current_job[-1] in wire_contents
            assert any(message["role"] == "assistant" for message in body["messages"])
        current_job.append(body["messages"][-1]["content"])


def test_native_length_completion_aborts_before_world_advance_and_keeps_evidence() -> None:
    result, _ = asyncio.run(_run_native(_LengthOnceClient))
    assert result.handoff.aborted
    assert result.handoff.run_valid is False
    assert result.handoff.completed_jobs == 0
    assert len(result.jobs) == 1
    assert result.jobs[0].complete is False
    assert not any(
        event.event_kind.value in {"ACTION_SUBMITTED", "ACTION_REJECTED"}
        for event in result.jobs[0].event_log.events
    )
    assert any(
        call.finish_reason == "length"
        for wrapped in result.traces
        for call in wrapped.trace.calls
    )
    for wrapped in result.traces:
        bundle = wrapped.trace.info["constraint_forge_canary_evidence_v0"]
        assert bundle["scientific_eligible"] is False
        assert bundle["audit_seal"]["status"] == "aborted"
