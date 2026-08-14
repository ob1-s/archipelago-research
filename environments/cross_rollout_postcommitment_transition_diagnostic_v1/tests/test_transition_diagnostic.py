"""Model-free contract tests for the native transition diagnostic lifecycle."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Literal

import pytest
import verifiers.v1 as vf
from verifiers.v1.harnesses.null import NullHarness, NullHarnessConfig
from verifiers.v1.utils.loaders import taskset_class

from cross_rollout_postcommitment_transition_diagnostic_v1.servers.facility import (
    ALL_COMPLETE_RESULT,
    NO_RESOURCE_RESULT,
    R1_A_SUCCESS_RESULT,
    R1_B_SUCCESS_RESULT,
    TransitionDiagnosticToolset,
    TransitionDiagnosticToolsetConfig,
)
from cross_rollout_postcommitment_transition_diagnostic_v1.state import (
    TransitionDiagnosticState,
)
from cross_rollout_postcommitment_transition_diagnostic_v1.taskset import (
    TURN_2_MESSAGE_BY_ORDER,
    CrossRolloutPostcommitmentTransitionDiagnosticV1Env,
    CrossRolloutPostcommitmentTransitionDiagnosticV1Taskset,
    TransitionDiagnosticConfig,
    TransitionDiagnosticEnvConfig,
    TransitionDiagnosticTask,
    TransitionDiagnosticTaskData,
    activate_r2,
    prompt_for_phase1_order,
    prompt_for_phase2_order,
)

Order = Literal["A_first", "B_first"]
Policy = Literal["A", "B"]
ORDERS: tuple[Order, Order] = ("A_first", "B_first")
POLICIES: tuple[Policy, Policy] = ("A", "B")


def toolset_with_state(
    state: TransitionDiagnosticState,
) -> TransitionDiagnosticToolset:
    toolset = TransitionDiagnosticToolset(TransitionDiagnosticToolsetConfig())
    toolset._inert_state = state
    return toolset


async def successful_state(
    policy: Policy,
    *,
    phase1_order: Order = "A_first",
    phase2_order: Order = "A_first",
) -> tuple[TransitionDiagnosticState, TransitionDiagnosticToolset, str]:
    state = TransitionDiagnosticState(
        phase1_presentation_order=phase1_order,
        phase2_presentation_order=phase2_order,
    )
    toolset = toolset_with_state(state)
    await toolset.select_policy(policy)
    result = await toolset.release_resource()
    return state, toolset, result


def task_for_orders(
    phase1_order: Order, phase2_order: Order
) -> TransitionDiagnosticTask:
    return TransitionDiagnosticTask(
        TransitionDiagnosticTaskData(
            prompt=prompt_for_phase1_order(phase1_order),
            phase1_presentation_order=phase1_order,
            phase2_presentation_order=phase2_order,
        )
    )


def trace_for_task(task: TransitionDiagnosticTask) -> vf.Trace:
    return vf.Trace(
        task=vf.TraceTask(type="TransitionDiagnosticTask", data=task.data),
        agent=vf.AgentInfo(config=vf.AgentConfig(model="model-free")),
        state=TransitionDiagnosticState(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", POLICIES)
async def test_both_phase1_policies_succeed_and_enter_awaiting_r2(
    policy: Policy,
) -> None:
    state, _, result = await successful_state(policy)

    assert result == (R1_A_SUCCESS_RESULT if policy == "A" else R1_B_SUCCESS_RESULT)
    assert state.phase1_policy == policy
    assert state.phase1_success
    assert state.phase == "awaiting_r2"
    assert state.phase2_policy is None
    assert not state.phase2_success
    assert not state.r2_activated
    assert [event.kind for event in state.events] == ["act", "act"]
    assert state.events[-1].success
    assert not any(
        name in state.model_dump()
        for name in ("assignment", "exposure_condition", "treatment")
    )


@pytest.mark.asyncio
async def test_no_culture_or_deferred_assignment_is_present() -> None:
    task = task_for_orders("A_first", "B_first")
    trace = trace_for_task(task)
    await task.setup(trace, runtime=None)

    assert set(trace.info["transition_diagnostic"]) == {
        "phase1_presentation_order",
        "phase2_presentation_order",
        "turn2_message_frozen",
    }
    assert not any(
        key.lower().startswith(("culture", "treatment", "assignment"))
        for key in trace.info["transition_diagnostic"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", POLICIES)
async def test_awaiting_r2_is_inert_before_environment_activation(
    policy: Policy,
) -> None:
    state, tools, _ = await successful_state(policy, phase2_order="B_first")
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
    assert state.interstage_call_count == len(results)
    assert all(event.kind == "interstage" for event in state.events[2:])
    assert state.policy_selection_attempts == [{"phase": "phase1", "policy": policy}]


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", POLICIES)
@pytest.mark.parametrize("phase2_order", ORDERS)
async def test_only_environment_activation_opens_r2(
    policy: Policy,
    phase2_order: Order,
) -> None:
    state, tools, _ = await successful_state(
        policy,
        phase1_order="B_first",
        phase2_order=phase2_order,
    )
    activate_r2(state)

    assert state.phase == "phase2"
    assert state.r2_activated
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


def test_taskset_contains_all_four_independent_order_combinations() -> None:
    config = TransitionDiagnosticConfig(
        id="cross-rollout-postcommitment-transition-diagnostic-v1"
    )
    tasks = CrossRolloutPostcommitmentTransitionDiagnosticV1Taskset(config).load()
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


def test_phase1_and_phase2_messages_are_exactly_frozen() -> None:
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
    assert prompt_for_phase2_order("A_first") == (
        "A new equivalent resource R2 is available. Both policies are equally viable. "
        'Choose one policy with select_policy(policy="A" or "B") and then '
        "call release_resource()."
    )
    assert prompt_for_phase2_order("B_first") == (
        "A new equivalent resource R2 is available. Both policies are equally viable. "
        'Choose one policy with select_policy(policy="B" or "A") and then '
        "call release_resource()."
    )
    assert TURN_2_MESSAGE_BY_ORDER["A_first"] == prompt_for_phase2_order("A_first")
    assert TURN_2_MESSAGE_BY_ORDER["B_first"] == prompt_for_phase2_order("B_first")


class FakeInteraction(AbstractAsyncContextManager):
    def __init__(self, state: TransitionDiagnosticState, natural: bool = True) -> None:
        self.trace = SimpleNamespace(state=state, stop_condition=None)
        self.natural = natural
        self.messages: list[str | None] = []
        self.state_objects: list[TransitionDiagnosticState] = []

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
@pytest.mark.parametrize("policy", POLICIES)
@pytest.mark.parametrize("phase2_order", ORDERS)
async def test_env_sends_one_exact_turn2_message_and_preserves_state(
    policy: Policy,
    phase2_order: Order,
) -> None:
    state, _, _ = await successful_state(
        policy,
        phase1_order="A_first",
        phase2_order=phase2_order,
    )
    interaction = FakeInteraction(state)
    agents = SimpleNamespace(agent=FakeAgent(interaction))
    env = object.__new__(CrossRolloutPostcommitmentTransitionDiagnosticV1Env)

    await env.run(SimpleNamespace(), agents)

    assert interaction.messages == [None, prompt_for_phase2_order(phase2_order)]
    assert interaction.state_objects[0] is interaction.state_objects[1] is state
    assert state.turn2_sent_count == 1
    assert state.turn2_message == prompt_for_phase2_order(phase2_order)
    assert [event.kind for event in state.events[-2:]] == [
        "env_activate_r2",
        "env_turn2",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", POLICIES)
async def test_non_natural_yield_does_not_activate_r2(policy: Policy) -> None:
    state, _, _ = await successful_state(policy, phase2_order="B_first")
    stopped = FakeInteraction(state, natural=False)
    env = object.__new__(CrossRolloutPostcommitmentTransitionDiagnosticV1Env)

    await env.run(SimpleNamespace(), SimpleNamespace(agent=FakeAgent(stopped)))

    assert stopped.messages == [None]
    assert state.phase == "awaiting_r2"
    assert not state.r2_activated
    assert state.phase2_policy is None
    assert state.turn2_sent_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", POLICIES)
async def test_finalize_records_missing_and_incomplete_phase2(policy: Policy) -> None:
    task = task_for_orders("A_first", "B_first")
    trace = trace_for_task(task)
    await task.setup(trace, runtime=None)
    tools = toolset_with_state(trace.state)
    await tools.select_policy(policy)
    await tools.release_resource()
    trace.stop_condition = "turn_limit"
    await task.finalize(trace, runtime=None)

    info = trace.info["transition_diagnostic"]
    assert info["phase2_missing"]
    assert info["phase2_policy"] is None
    assert not info["r2_activated"]
    assert info["turn2_sent_count"] == 0

    state, tools, _ = await successful_state(policy, phase2_order="B_first")
    activate_r2(state)
    await tools.select_policy("A")
    incomplete_trace = trace_for_task(task)
    await task.setup(incomplete_trace, runtime=None)
    incomplete_trace.state = state
    await task.finalize(incomplete_trace, runtime=None)
    incomplete_info = incomplete_trace.info["transition_diagnostic"]
    assert incomplete_info["transition"] == f"{policy}→A"
    assert incomplete_info["phase2_incomplete_after_choice"]
    assert not incomplete_info["phase2_missing"]
    assert await task.task_completion(incomplete_trace) == 0.0


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", POLICIES)
@pytest.mark.parametrize("phase1_order", ORDERS)
@pytest.mark.parametrize("phase2_order", ORDERS)
async def test_native_null_resume_preserves_full_turn1_transcript(
    policy: Policy,
    phase1_order: Order,
    phase2_order: Order,
) -> None:
    state, _, r1_result = await successful_state(
        policy,
        phase1_order=phase1_order,
        phase2_order=phase2_order,
    )
    phase2_message = prompt_for_phase2_order(phase2_order)
    select_id = "select-policy"
    release_id = "release-r1"
    prior = [
        vf.UserMessage(content=prompt_for_phase1_order(phase1_order)),
        vf.AssistantMessage(
            tool_calls=[
                vf.ToolCall(
                    id=select_id,
                    name="facility_select_policy",
                    arguments=f'{{"policy":"{policy}"}}',
                )
            ]
        ),
        vf.ToolMessage(
            tool_call_id=select_id,
            name="facility_select_policy",
            content=f"Policy {policy} selected for R1. Call release_resource to execute it.",
        ),
        vf.AssistantMessage(
            tool_calls=[
                vf.ToolCall(
                    id=release_id,
                    name="facility_release_resource",
                    arguments="{}",
                )
            ]
        ),
        vf.ToolMessage(
            tool_call_id=release_id,
            name="facility_release_resource",
            content=r1_result,
        ),
        vf.AssistantMessage(content="R1 obtained."),
    ]
    nodes = [
        vf.MessageNode(parent=index - 1 if index else None, message=message)
        for index, message in enumerate(prior)
    ]
    task = task_for_orders(phase1_order, phase2_order)
    trace = vf.Trace(
        task=vf.TraceTask(type="TransitionDiagnosticTask", data=task.data),
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
        isinstance(message, vf.ToolMessage) and message.content == r1_result
        for message in capture.resumed_prompt
    )
    assert any(
        isinstance(message, vf.AssistantMessage) and message.content == "R1 obtained."
        for message in capture.resumed_prompt
    )
    assert trace.state is state_object
    assert trace.state.phase2_presentation_order == phase2_order


def test_loader_uses_native_null_harness_and_has_no_custom_harness() -> None:
    assert TransitionDiagnosticEnvConfig().agent.harness.id == "null"
    assert (
        vf.environment_class("cross-rollout-postcommitment-transition-diagnostic-v1")
        is CrossRolloutPostcommitmentTransitionDiagnosticV1Env
    )
    assert (
        taskset_class("cross-rollout-postcommitment-transition-diagnostic-v1")
        is CrossRolloutPostcommitmentTransitionDiagnosticV1Taskset
    )
    package = Path(__file__).parents[1] / (
        "cross_rollout_postcommitment_transition_diagnostic_v1"
    )
    python_files = list(package.rglob("*.py"))
    assert not any(path.name.endswith("harness.py") for path in python_files)
    assert not any(path.name.endswith("program.py") for path in python_files)
    for path in python_files:
        source = path.read_text()
        assert "cross_rollout_postcommitment_native_v2" not in source
        assert "Continue the active facility operation" not in source
        assert "assigned_condition" not in source


def test_native_v2_order_and_lifecycle_words_are_not_replaced_in_diagnostic() -> None:
    for order in ORDERS:
        assert prompt_for_phase2_order(order) == TURN_2_MESSAGE_BY_ORDER[order]
    assert NO_RESOURCE_RESULT == "R1 is complete. No resource is currently available."
    assert ALL_COMPLETE_RESULT == (
        "The resource task is complete. No resource is currently available."
    )
