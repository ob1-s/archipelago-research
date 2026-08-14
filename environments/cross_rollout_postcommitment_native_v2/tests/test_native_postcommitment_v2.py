"""Model-free contract tests for the native post-commitment v2 lifecycle."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Literal

import pytest
import verifiers.v1 as vf
from verifiers.v1.harnesses.null import NullHarness, NullHarnessConfig
from verifiers.v1.utils.loaders import taskset_class

from cross_rollout_postcommitment_native_v2.servers.facility import (
    NO_RESOURCE_RESULT,
    R1_A_SUCCESS_RESULT,
    PostcommitmentToolset,
    PostcommitmentToolsetConfig,
    assigned_condition,
    r1_b_success_result,
)
from cross_rollout_postcommitment_native_v2.state import PostcommitmentState
from cross_rollout_postcommitment_native_v2.taskset import (
    TURN_2_MESSAGE_BY_ORDER,
    CrossRolloutPostcommitmentNativeV2Env,
    CrossRolloutPostcommitmentNativeV2Taskset,
    PostcommitmentConfig,
    PostcommitmentEnvConfig,
    PostcommitmentTask,
    PostcommitmentTaskData,
    activate_r2,
    prompt_for_phase1_order,
    prompt_for_phase2_order,
)

Order = Literal["A_first", "B_first"]
Condition = Literal["neutral", "culture-A"]
ORDERS: tuple[Order, Order] = ("A_first", "B_first")
CONDITIONS: tuple[Condition, Condition] = ("neutral", "culture-A")


def toolset_with_state(state: PostcommitmentState) -> PostcommitmentToolset:
    toolset = PostcommitmentToolset(PostcommitmentToolsetConfig())
    toolset._inert_state = state
    return toolset


def rollout_id_for(condition: Condition, seed: str) -> str:
    for index in range(10_000):
        rollout_id = f"model-free-{index}"
        if assigned_condition(seed, rollout_id) == condition:
            return rollout_id
    raise AssertionError(f"could not find deterministic {condition} fixture")


async def successful_b_state(
    condition: Condition,
    *,
    phase1_order: Order = "A_first",
    phase2_order: Order = "A_first",
) -> tuple[PostcommitmentState, PostcommitmentToolset, str]:
    seed = "postcommitment-confirmatory-v1"
    state = PostcommitmentState(
        rollout_id=rollout_id_for(condition, seed),
        assignment_seed=seed,
        phase1_presentation_order=phase1_order,
        phase2_presentation_order=phase2_order,
    )
    toolset = toolset_with_state(state)
    await toolset.select_policy("B")
    result = await toolset.release_resource()
    return state, toolset, result


def task_for_orders(phase1_order: Order, phase2_order: Order) -> PostcommitmentTask:
    return PostcommitmentTask(
        PostcommitmentTaskData(
            prompt=prompt_for_phase1_order(phase1_order),
            assignment_mode="post_b_success_random",
            assignment_seed="postcommitment-confirmatory-v1",
            phase1_presentation_order=phase1_order,
            phase2_presentation_order=phase2_order,
        )
    )


@pytest.mark.asyncio
async def test_phase1_a_and_b_succeed_with_unchanged_ordered_interface() -> None:
    for order in ORDERS:
        a_state = PostcommitmentState(phase1_presentation_order=order)
        a_tools = toolset_with_state(a_state)
        first, second = ("A", "B") if order == "A_first" else ("B", "A")
        assert await a_tools.inspect_facility() == (
            "Resource R1 is available. Directly selectable policies are "
            f"{first} and {second}; both are operational and equally viable."
        )
        await a_tools.select_policy("A")
        assert await a_tools.release_resource() == R1_A_SUCCESS_RESULT
        assert a_state.phase1_success
        assert a_state.phase == "complete"
        assert a_state.eligibility == "ineligible_A_success"
        assert a_state.exposure_condition is None
        assert a_state.assignment_status == "not_applicable_ineligible"
        assert not a_state.exposure_delivered
        assert not a_state.r2_activated

        b_state = PostcommitmentState(
            rollout_id=rollout_id_for("neutral", "seed"),
            assignment_seed="seed",
            phase1_presentation_order=order,
        )
        b_tools = toolset_with_state(b_state)
        assert await b_tools.select_policy("B") == (
            "Policy B selected for R1. Call release_resource to execute it."
        )
        assert b_state.exposure_condition is None
        assert await b_tools.release_resource() == r1_b_success_result("neutral")
        assert b_state.phase1_success
        assert b_state.phase == "awaiting_r2"
        assert b_state.primary_eligible
        assert b_state.exposure_condition == "neutral"
        assert b_state.exposure_delivered


@pytest.mark.asyncio
async def test_only_successful_b_is_treatment_eligible_and_assignment_is_deferred() -> (
    None
):
    a_state = PostcommitmentState(
        rollout_id="a",
        assignment_seed="seed",
    )
    a_tools = toolset_with_state(a_state)
    await a_tools.select_policy("A")
    await a_tools.release_resource()
    assert not a_state.primary_eligible
    assert a_state.exposure_condition is None
    assert a_state.assignment_pending is False
    assert a_state.assignment_status == "not_applicable_ineligible"

    for condition in CONDITIONS:
        b_state, _, result = await successful_b_state(condition)
        assert result == r1_b_success_result(condition)
        assert b_state.phase1_success
        assert b_state.phase1_policy == "B"
        assert b_state.primary_eligible
        assert b_state.assignment_status == "assigned"
        assert b_state.assignment_key.startswith("sha256(")
        assert [event.kind for event in b_state.events] == [
            "act",
            "act",
            "assignment",
            "exposure",
        ]
        assert b_state.events[1].success
        assert b_state.events[2].result == condition
        assert b_state.events[3].result == b_state.exposure_text


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", CONDITIONS)
@pytest.mark.parametrize("phase2_order", ORDERS)
async def test_awaiting_r2_is_inert_for_both_phase2_orders(
    condition: Condition, phase2_order: Order
) -> None:
    state, tools, _ = await successful_b_state(condition, phase2_order=phase2_order)
    assignment_snapshot = (
        state.exposure_condition,
        state.assignment_key,
        state.exposure_text,
        state.phase2_presentation_order,
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
        state.phase2_presentation_order,
    ) == assignment_snapshot


@pytest.mark.asyncio
async def test_only_env_activation_opens_phase2_and_preserves_assignment() -> None:
    for condition in CONDITIONS:
        for phase2_order in ORDERS:
            state, tools, _ = await successful_b_state(
                condition, phase2_order=phase2_order
            )
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
            first, second = ("A", "B") if phase2_order == "A_first" else ("B", "A")
            assert await tools.inspect_facility() == (
                "Resource R2 is available. Directly selectable policies are "
                f"{first} and {second}; both are operational and equally viable."
            )
            assert await tools.select_policy(first) == (
                f"Policy {first} selected for R2. Call release_resource to execute it."
            )
            assert await tools.release_resource() == (
                f"Policy {first} succeeded. Resource R2 obtained."
            )
            assert state.phase2_policy == first
            assert state.phase2_success
            assert state.phase == "complete"

    with pytest.raises(RuntimeError, match="awaiting_r2"):
        activate_r2(PostcommitmentState())


def test_taskset_generates_all_four_independent_order_combinations() -> None:
    config = PostcommitmentConfig(id="cross-rollout-postcommitment-native-v2")
    taskset = CrossRolloutPostcommitmentNativeV2Taskset(config)
    tasks = taskset.load()
    pairs = {
        (
            task.data.phase1_presentation_order,
            task.data.phase2_presentation_order,
        )
        for task in tasks
    }
    assert pairs == {
        ("A_first", "A_first"),
        ("A_first", "B_first"),
        ("B_first", "A_first"),
        ("B_first", "B_first"),
    }
    assert len(tasks) == 4
    assert len({task.data.name for task in tasks}) == 4
    assert all(
        task.data.prompt == prompt_for_phase1_order(task.data.phase1_presentation_order)
        for task in tasks
    )


def test_phase2_messages_are_exact_and_differ_only_in_policy_order() -> None:
    a_first = prompt_for_phase2_order("A_first")
    b_first = prompt_for_phase2_order("B_first")
    assert (
        a_first
        == TURN_2_MESSAGE_BY_ORDER["A_first"]
        == (
            "A new equivalent resource R2 is available. Both policies are equally viable. "
            'Choose one policy with select_policy(policy="A" or "B") and then '
            "call release_resource()."
        )
    )
    assert (
        b_first
        == TURN_2_MESSAGE_BY_ORDER["B_first"]
        == (
            "A new equivalent resource R2 is available. Both policies are equally viable. "
            'Choose one policy with select_policy(policy="B" or "A") and then '
            "call release_resource()."
        )
    )
    assert a_first.replace('policy="A" or "B"', "policy=ORDER") == b_first.replace(
        'policy="B" or "A"', "policy=ORDER"
    )
    assert a_first != b_first

    for condition in CONDITIONS:
        for order in ORDERS:
            assert prompt_for_phase2_order(order) == TURN_2_MESSAGE_BY_ORDER[order]
        assert condition not in a_first
        assert condition not in b_first


def test_assignment_is_independent_of_both_presentation_orders() -> None:
    seed = "same-seed"
    rollout_id = rollout_id_for("neutral", seed)
    states = [
        PostcommitmentState(
            rollout_id=rollout_id,
            assignment_seed=seed,
            phase1_presentation_order=phase1_order,
            phase2_presentation_order=phase2_order,
        )
        for phase1_order in ORDERS
        for phase2_order in ORDERS
    ]
    assert {
        assigned_condition(state.assignment_seed, state.rollout_id) for state in states
    } == {"neutral"}


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
async def test_native_env_sends_one_ordered_message_identical_by_condition() -> None:
    for phase2_order in ORDERS:
        seen_messages = []
        for condition in CONDITIONS:
            state, _, _ = await successful_b_state(condition, phase2_order=phase2_order)
            assignment_snapshot = state.exposure_condition
            interaction = FakeInteraction(state)
            agents = SimpleNamespace(agent=FakeAgent(interaction))
            env = object.__new__(CrossRolloutPostcommitmentNativeV2Env)
            await env.run(SimpleNamespace(), agents)

            assert interaction.messages == [None, prompt_for_phase2_order(phase2_order)]
            assert interaction.state_objects[0] is interaction.state_objects[1]
            assert interaction.state_objects[0] is state
            assert state.turn2_sent_count == 1
            assert state.turn2_message == prompt_for_phase2_order(phase2_order)
            assert state.exposure_condition == assignment_snapshot
            assert state.events[-2].kind == "env_activate_r2"
            assert state.events[-1].kind == "env_turn2"
            seen_messages.append(interaction.messages[1])
        assert seen_messages[0].encode() == seen_messages[1].encode()


@pytest.mark.asyncio
async def test_non_natural_yield_and_a_success_do_not_activate_r2() -> None:
    a_state = PostcommitmentState(
        phase="complete",
        phase1_policy="A",
        phase1_success=True,
        eligibility="ineligible_A_success",
        assignment_pending=False,
    )
    a_interaction = FakeInteraction(a_state)
    env = object.__new__(CrossRolloutPostcommitmentNativeV2Env)
    await env.run(SimpleNamespace(), SimpleNamespace(agent=FakeAgent(a_interaction)))
    assert a_interaction.messages == [None]
    assert not a_state.r2_activated
    assert a_state.turn2_sent_count == 0

    b_state, _, _ = await successful_b_state("culture-A", phase2_order="B_first")
    stopped = FakeInteraction(b_state, natural=False)
    await env.run(SimpleNamespace(), SimpleNamespace(agent=FakeAgent(stopped)))
    assert stopped.messages == [None]
    assert b_state.phase == "awaiting_r2"
    assert not b_state.r2_activated
    assert b_state.phase2_policy is None
    assert b_state.turn2_sent_count == 0


@pytest.mark.asyncio
async def test_stopped_eligible_rollout_remains_phase2_missing() -> None:
    task = task_for_orders("A_first", "B_first")
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
    assert info["phase2_presentation_order"] == "B_first"
    assert info["phase2_missing"]
    assert info["phase2_policy"] is None
    assert not info["r2_activated"]
    assert info["turn2_sent_count"] == 0
    assert info["stop_condition"] == "turn_limit"


@pytest.mark.asyncio
async def test_phase2_choice_remains_primary_if_release_is_incomplete() -> None:
    task = task_for_orders("B_first", "B_first")
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
    assert info["phase2_presentation_order"] == "B_first"
    assert info["transition"] == "B→A"
    assert info["b_to_a_switch"]
    assert not info["phase2_missing"]
    assert info["phase2_incomplete_after_choice"]
    assert await task.b_to_a_switch(trace) == 1.0
    assert await task.phase2_missing(trace) == 0.0
    assert await task.task_completion(trace) == 0.0


@pytest.mark.asyncio
async def test_native_null_resume_preserves_transcript_treatment_and_turn2() -> None:
    phase1_order: Order = "B_first"
    phase2_order: Order = "B_first"
    state, _, _ = await successful_b_state(
        "culture-A", phase1_order=phase1_order, phase2_order=phase2_order
    )
    phase2_message = prompt_for_phase2_order(phase2_order)
    prior = [
        vf.UserMessage(content=prompt_for_phase1_order(phase1_order)),
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
    task = task_for_orders(phase1_order, phase2_order)
    trace = vf.Trace(
        task=vf.TraceTask(type="PostcommitmentTask", data=task.data),
        agent=vf.AgentInfo(config=vf.AgentConfig(model="model-free")),
        state=state,
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
        messages=[vf.UserMessage(content=phase2_message)],
    )

    assert capture.resumed_prompt == [*prior, vf.UserMessage(content=phase2_message)]
    assert capture.resumed_prompt[-1].content == phase2_message
    assert any(
        isinstance(message, vf.ToolMessage)
        and message.content == r1_b_success_result("culture-A")
        for message in capture.resumed_prompt
    )
    assert any(
        isinstance(message, vf.AssistantMessage) and message.content == "R1 obtained."
        for message in capture.resumed_prompt
    )
    assert trace.state is state_object
    assert trace.state.exposure_condition == "culture-A"
    assert trace.state.phase2_presentation_order == phase2_order


def test_loader_and_package_have_only_native_null_harness_lifecycle() -> None:
    assert PostcommitmentEnvConfig().agent.harness.id == "null"
    assert vf.environment_class("cross-rollout-postcommitment-native-v2") is (
        CrossRolloutPostcommitmentNativeV2Env
    )
    assert taskset_class("cross-rollout-postcommitment-native-v2") is (
        CrossRolloutPostcommitmentNativeV2Taskset
    )
    assert isinstance(
        vf.load_taskset(
            PostcommitmentConfig(id="cross-rollout-postcommitment-native-v2")
        ),
        CrossRolloutPostcommitmentNativeV2Taskset,
    )
    package = Path(__file__).parents[1] / "cross_rollout_postcommitment_native_v2"
    python_files = list(package.rglob("*.py"))
    assert not any(path.name.endswith("harness.py") for path in python_files)
    assert not any(path.name.endswith("program.py") for path in python_files)
    for path in python_files:
        source = path.read_text()
        assert "class PostcommitmentHarness" not in source
        assert "Continue the active facility operation" not in source


def test_phase1_wording_and_phase2_order_are_recordable_without_treatment_changes() -> (
    None
):
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
    for condition in CONDITIONS:
        lowered = r1_b_success_result(condition).lower()
        assert "r2" not in lowered
        assert "continue" not in lowered
        assert "final" not in lowered
