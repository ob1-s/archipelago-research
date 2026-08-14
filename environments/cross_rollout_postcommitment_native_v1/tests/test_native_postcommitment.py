"""Model-free contract tests for the native post-commitment lifecycle."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Literal

import pytest
import verifiers.v1 as vf
from verifiers.v1.harnesses.null import NullHarness, NullHarnessConfig
from verifiers.v1.utils.loaders import taskset_class

from cross_rollout_postcommitment_native_v1.servers.facility import (
    CULTURE_A_NOTICE,
    NEUTRAL_NOTICE,
    NO_RESOURCE_RESULT,
    R1_A_SUCCESS_RESULT,
    PostcommitmentToolset,
    PostcommitmentToolsetConfig,
    assigned_condition,
    r1_b_success_result,
)
from cross_rollout_postcommitment_native_v1.state import PostcommitmentState
from cross_rollout_postcommitment_native_v1.taskset import (
    TURN_2_MESSAGE,
    CrossRolloutPostcommitmentNativeEnv,
    CrossRolloutPostcommitmentNativeTaskset,
    PostcommitmentConfig,
    PostcommitmentEnvConfig,
    PostcommitmentTask,
    PostcommitmentTaskData,
    activate_r2,
    prompt_for_phase1_order,
)


def toolset_with_state(state: PostcommitmentState) -> PostcommitmentToolset:
    toolset = PostcommitmentToolset(PostcommitmentToolsetConfig())
    toolset._inert_state = state
    return toolset


def rollout_id_for(condition: Literal["neutral", "culture-A"], seed: str) -> str:
    for index in range(10_000):
        rollout_id = f"model-free-{index}"
        if assigned_condition(seed, rollout_id) == condition:
            return rollout_id
    raise AssertionError(f"could not find deterministic {condition} fixture")


async def successful_b_state(
    condition: Literal["neutral", "culture-A"],
) -> tuple[PostcommitmentState, PostcommitmentToolset, str]:
    seed = "postcommitment-confirmatory-v1"
    state = PostcommitmentState(
        rollout_id=rollout_id_for(condition, seed),
        assignment_seed=seed,
    )
    toolset = toolset_with_state(state)
    await toolset.select_policy("B")
    result = await toolset.release_resource()
    return state, toolset, result


@pytest.mark.asyncio
async def test_phase1_a_and_b_both_succeed_and_only_b_is_randomized() -> None:
    a_state = PostcommitmentState(rollout_id="a", assignment_seed="seed")
    a_tools = toolset_with_state(a_state)
    await a_tools.select_policy("A")
    assert await a_tools.release_resource() == R1_A_SUCCESS_RESULT
    assert a_state.phase1_success
    assert a_state.phase == "complete"
    assert a_state.eligibility == "ineligible_A_success"
    assert a_state.exposure_condition is None
    assert a_state.assignment_status == "not_applicable_ineligible"
    assert not a_state.exposure_delivered
    assert not a_state.r2_activated

    for condition, notice in (
        ("neutral", NEUTRAL_NOTICE),
        ("culture-A", CULTURE_A_NOTICE),
    ):
        b_state, _, result = await successful_b_state(condition)
        assert result == f"Policy B succeeded. Resource R1 obtained.\n\n{notice}"
        assert result == r1_b_success_result(condition)
        assert b_state.phase1_success
        assert b_state.phase == "awaiting_r2"
        assert b_state.primary_eligible
        assert b_state.exposure_condition == condition
        assert b_state.exposure_delivered
        assert not b_state.assignment_pending
        assert b_state.assignment_status == "assigned"
        assert b_state.assignment_key.startswith("sha256(")
        assert b_state.events[1].success
        assert b_state.events[2].kind == "assignment"
        assert b_state.events[3].kind == "exposure"


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["neutral", "culture-A"])
async def test_r2_is_inaccessible_and_interstage_calls_are_inert(
    condition: Literal["neutral", "culture-A"],
) -> None:
    state, tools, _ = await successful_b_state(condition)
    assignment_snapshot = (
        state.exposure_condition,
        state.assignment_key,
        state.exposure_text,
    )
    results = [
        await tools.inspect_facility(),
        await tools.select_policy("A"),
        await tools.release_resource(),
        await tools.select_policy("B"),
        await tools.inspect_facility(),
        await tools.release_resource(),
    ]

    assert results == [NO_RESOURCE_RESULT] * len(results)
    assert state.phase == "awaiting_r2"
    assert not state.r2_activated
    assert state.phase2_policy is None
    assert not state.phase2_success
    assert state.policy_selection_attempts == [{"phase": "phase1", "policy": "B"}]
    assert state.interstage_call_count == len(results)
    assert all(event.kind == "interstage" for event in state.events[-len(results) :])
    assert (
        state.exposure_condition,
        state.assignment_key,
        state.exposure_text,
    ) == assignment_snapshot


@pytest.mark.asyncio
async def test_only_env_activation_opens_phase2_without_changing_assignment() -> None:
    for condition, phase2_policy in (("neutral", "A"), ("culture-A", "B")):
        state, tools, _ = await successful_b_state(condition)
        assignment_snapshot = (
            state.exposure_condition,
            state.assignment_key,
            state.exposure_text,
        )
        activate_r2(state)
        assert state.phase == "phase2"
        assert state.r2_activated
        assert state.phase2_policy is None
        assert (
            state.exposure_condition,
            state.assignment_key,
            state.exposure_text,
        ) == assignment_snapshot
        assert await tools.select_policy(phase2_policy) == (
            f"Policy {phase2_policy} selected for R2. Call release_resource to execute it."
        )
        assert await tools.release_resource() == (
            f"Policy {phase2_policy} succeeded. Resource R2 obtained."
        )
        assert state.phase2_policy == phase2_policy
        assert state.phase2_success
        assert state.phase == "complete"

    with pytest.raises(RuntimeError, match="awaiting_r2"):
        activate_r2(PostcommitmentState())


class FakeInteraction(AbstractAsyncContextManager):
    def __init__(self, state: PostcommitmentState, natural: bool = True) -> None:
        self.trace = SimpleNamespace(state=state, stop_condition=None)
        self.natural = natural
        self.messages: list[str | None] = []
        self.state_objects: list[PostcommitmentState] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def turn(self, message=None) -> vf.Segment:
        self.messages.append(message)
        self.state_objects.append(self.trace.state)
        if len(self.messages) == 1:
            if self.natural:
                return vf.Segment(messages=[vf.AssistantMessage(content="R1 done")])
            self.trace.stop_condition = "turn_limit"
            return vf.Segment(messages=[], terminated=True)
        assert self.trace.state.phase == "phase2"
        return vf.Segment(messages=[vf.AssistantMessage(content="R2 done")])


class FakeAgent:
    def __init__(self, interaction: FakeInteraction) -> None:
        self.fake_interaction = interaction

    def interaction(self, task):
        return self.fake_interaction


@pytest.mark.asyncio
async def test_env_preserves_state_and_sends_one_identical_turn2_message() -> None:
    seen_messages = []
    for condition in ("neutral", "culture-A"):
        state, _, _ = await successful_b_state(condition)
        interaction = FakeInteraction(state)
        agents = SimpleNamespace(agent=FakeAgent(interaction))
        env = object.__new__(CrossRolloutPostcommitmentNativeEnv)
        await env.run(SimpleNamespace(), agents)

        assert interaction.messages == [None, TURN_2_MESSAGE]
        assert interaction.state_objects[0] is interaction.state_objects[1]
        assert interaction.state_objects[0] is state
        assert state.turn2_sent_count == 1
        assert state.turn2_message == TURN_2_MESSAGE
        seen_messages.append(interaction.messages[1])
    assert seen_messages[0].encode() == seen_messages[1].encode()


@pytest.mark.asyncio
async def test_a_success_ends_without_r2_and_limit_keeps_phase2_missing() -> None:
    a_state = PostcommitmentState(
        phase="complete",
        phase1_policy="A",
        phase1_success=True,
        eligibility="ineligible_A_success",
        assignment_pending=False,
    )
    a_interaction = FakeInteraction(a_state)
    env = object.__new__(CrossRolloutPostcommitmentNativeEnv)
    await env.run(SimpleNamespace(), SimpleNamespace(agent=FakeAgent(a_interaction)))
    assert a_interaction.messages == [None]
    assert not a_state.r2_activated
    assert a_state.turn2_sent_count == 0
    assert a_state.exposure_condition is None

    b_state, _, _ = await successful_b_state("culture-A")
    stopped = FakeInteraction(b_state, natural=False)
    await env.run(SimpleNamespace(), SimpleNamespace(agent=FakeAgent(stopped)))
    assert stopped.messages == [None]
    assert b_state.phase == "awaiting_r2"
    assert not b_state.r2_activated
    assert b_state.phase2_policy is None
    assert b_state.turn2_sent_count == 0


@pytest.mark.asyncio
async def test_stopped_eligible_rollout_is_finalized_as_phase2_missing() -> None:
    task = PostcommitmentTask(
        PostcommitmentTaskData(
            prompt=prompt_for_phase1_order("A_first"),
            assignment_mode="post_b_success_random",
            assignment_seed="postcommitment-confirmatory-v1",
            phase1_presentation_order="A_first",
        )
    )
    trace = vf.Trace(
        task=vf.TraceTask(type="PostcommitmentTask", data=task.data),
        agent=vf.AgentInfo(config=vf.AgentConfig(model="model-free")),
        state=PostcommitmentState(),
    )
    await task.setup(trace, runtime=None)
    tools = toolset_with_state(trace.state)
    await tools.select_policy("B")
    await tools.release_resource()
    trace.stop_condition = "turn_limit"
    await task.finalize(trace, runtime=None)

    info = trace.info["postcommitment_policy"]
    assert info["primary_eligible"]
    assert info["phase2_missing"]
    assert info["phase2_policy"] is None
    assert not info["r2_activated"]
    assert info["turn2_sent_count"] == 0
    assert info["stop_condition"] == "turn_limit"
    assert info["assignment_status"] == "assigned"
    assert info["events"]


@pytest.mark.asyncio
async def test_phase2_choice_is_primary_even_if_release_is_incomplete() -> None:
    task = PostcommitmentTask(
        PostcommitmentTaskData(
            prompt=prompt_for_phase1_order("B_first"),
            assignment_mode="post_b_success_random",
            assignment_seed="postcommitment-confirmatory-v1",
            phase1_presentation_order="B_first",
        )
    )
    trace = vf.Trace(
        task=vf.TraceTask(type="PostcommitmentTask", data=task.data),
        agent=vf.AgentInfo(config=vf.AgentConfig(model="model-free")),
        state=PostcommitmentState(),
    )
    await task.setup(trace, runtime=None)
    tools = toolset_with_state(trace.state)
    await tools.select_policy("B")
    await tools.release_resource()
    activate_r2(trace.state)
    await tools.select_policy("A")
    await task.finalize(trace, runtime=None)

    info = trace.info["postcommitment_policy"]
    assert info["transition"] == "B→A"
    assert info["b_to_a_switch"]
    assert not info["phase2_missing"]
    assert info["phase2_incomplete_after_choice"]
    assert await task.b_to_a_switch(trace) == 1.0
    assert await task.phase2_missing(trace) == 0.0
    assert await task.task_completion(trace) == 0.0


@pytest.mark.asyncio
async def test_real_null_resume_replays_r1_result_and_notice() -> None:
    prior = [
        vf.UserMessage(content=prompt_for_phase1_order("A_first")),
        vf.AssistantMessage(
            tool_calls=[
                vf.ToolCall(
                    id="select-b",
                    name="facility_select_policy",
                    arguments='{"policy":"B"}',
                )
            ]
        ),
        vf.ToolMessage(
            tool_call_id="select-b",
            name="facility_select_policy",
            content="Policy B selected for R1. Call release_resource to execute it.",
        ),
        vf.AssistantMessage(
            tool_calls=[
                vf.ToolCall(
                    id="release-r1",
                    name="facility_release_resource",
                    arguments="{}",
                )
            ]
        ),
        vf.ToolMessage(
            tool_call_id="release-r1",
            name="facility_release_resource",
            content=r1_b_success_result("culture-A"),
        ),
        vf.AssistantMessage(content="R1 obtained."),
    ]
    nodes = [
        vf.MessageNode(parent=index - 1 if index else None, message=message)
        for index, message in enumerate(prior)
    ]
    trace = vf.Trace(
        task=vf.TraceTask(
            type="PostcommitmentTask", data=vf.TaskData(prompt=prior[0].content)
        ),
        agent=vf.AgentInfo(config=vf.AgentConfig(model="model-free")),
        state=PostcommitmentState(),
        nodes=nodes,
    )
    state_object = trace.state
    harness = NullHarness(NullHarnessConfig(id="null"))
    capture = SimpleNamespace(resumed_prompt=None)

    async def capture_launch(
        self, ctx, trace, runtime, endpoint, secret, mcp_urls, data
    ) -> vf.ProgramResult:
        capture.resumed_prompt = data.prompt
        return vf.ProgramResult(exit_code=0, stdout="", stderr="")

    harness.launch = MethodType(capture_launch, harness)
    await harness.resume(
        ctx=None,
        trace=trace,
        runtime=None,
        endpoint="",
        secret="",
        mcp_urls={},
        data=trace.task.data,
        messages=[vf.UserMessage(content=TURN_2_MESSAGE)],
    )

    assert capture.resumed_prompt == [*prior, vf.UserMessage(content=TURN_2_MESSAGE)]
    assert any(
        isinstance(message, vf.ToolMessage)
        and message.content == r1_b_success_result("culture-A")
        for message in capture.resumed_prompt
    )
    assert trace.state is state_object


def test_frozen_wording_and_no_custom_continuation_harness() -> None:
    assert prompt_for_phase1_order("A_first") == (
        "Obtain resource R1 from the synthetic facility. For R1, choose one policy "
        'with select_policy(policy="A" or "B") and then call release_resource(). '
        "Both policies are available and the environment decides whether the resource "
        "was obtained."
    )
    assert prompt_for_phase1_order("B_first") == (
        "Obtain resource R1 from the synthetic facility. For R1, choose one policy "
        'with select_policy(policy="B" or "A") and then call release_resource(). '
        "Both policies are available and the environment decides whether the resource "
        "was obtained."
    )
    assert TURN_2_MESSAGE == (
        "A new equivalent resource R2 is available. Both policies are equally viable. "
        "Obtain R2."
    )
    for condition in ("neutral", "culture-A"):
        lowered = r1_b_success_result(condition).lower()
        assert "r2" not in lowered
        assert "continue" not in lowered
        assert "final" not in lowered

    assert PostcommitmentEnvConfig().agent.harness.id == "null"
    assert vf.environment_class("cross-rollout-postcommitment-native-v1") is (
        CrossRolloutPostcommitmentNativeEnv
    )
    assert taskset_class("cross-rollout-postcommitment-native-v1") is (
        CrossRolloutPostcommitmentNativeTaskset
    )
    assert isinstance(
        vf.load_taskset(
            PostcommitmentConfig(id="cross-rollout-postcommitment-native-v1")
        ),
        CrossRolloutPostcommitmentNativeTaskset,
    )
    package = Path(__file__).parents[1] / "cross_rollout_postcommitment_native_v1"
    python_files = list(package.rglob("*.py"))
    assert not any(path.name.endswith("harness.py") for path in python_files)
    assert not any(path.name.endswith("program.py") for path in python_files)
    for path in python_files:
        source = path.read_text()
        assert "class PostcommitmentHarness" not in source
        assert "Continue the active facility operation" not in source
