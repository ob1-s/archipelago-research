"""Model-free contract tests for the frozen evidence-based lifecycle."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Literal, Self

import pytest
import verifiers.v1 as vf
from verifiers.v1.harnesses.null import NullHarness, NullHarnessConfig
from verifiers.v1.utils.loaders import taskset_class

from cross_rollout_postcommitment_evidence_v1 import randomness
from cross_rollout_postcommitment_evidence_v1.evidence import (
    MATCH_ACQUISITION_PROBABILITY,
    MATCH_VERIFICATION_PROBABILITY,
    MISMATCH_ACQUISITION_PROBABILITY,
    MISMATCH_VERIFICATION_PROBABILITY,
    summarize_evidence,
)
from cross_rollout_postcommitment_evidence_v1.servers.facility import (
    ALL_COMPLETE_RESULT,
    CULTURE_A_NOTICE,
    NEUTRAL_NOTICE,
    NO_RESOURCE_RESULT,
    EvidenceToolset,
    EvidenceToolsetConfig,
    r1_result,
)
from cross_rollout_postcommitment_evidence_v1.state import EvidenceState
from cross_rollout_postcommitment_evidence_v1.taskset import (
    TURN_2_MESSAGE_BY_ORDER_AND_CONDITION,
    CrossRolloutPostcommitmentEvidenceV1Env,
    CrossRolloutPostcommitmentEvidenceV1Taskset,
    EvidenceConfig,
    EvidenceEnvConfig,
    EvidenceTask,
    EvidenceTaskConfig,
    EvidenceTaskData,
    activate_r2,
    prompt_for_phase1_order,
    prompt_for_phase2_order,
)

Policy = Literal["A", "B"]
Order = Literal["A_first", "B_first"]
Condition = Literal["neutral", "culture-A"]


def toolset_with_state(state: EvidenceState) -> EvidenceToolset:
    toolset = EvidenceToolset(EvidenceToolsetConfig())
    toolset._inert_state = state
    return toolset


def state_for(
    *,
    profile: Literal["A_fit", "B_fit"] = "B_fit",
    assignment_mode: Literal["post_b_success_random", "fixed_neutral"] = "fixed_neutral",
    phase2_order: Order = "A_first",
) -> EvidenceState:
    return EvidenceState(
        rollout_id="model-free-rollout",
        random_seed="model-free-seed",
        hidden_profile=profile,
        assignment_mode=assignment_mode,
        phase1_presentation_order="B_first",
        phase2_presentation_order=phase2_order,
    )


def patch_outcomes(monkeypatch: pytest.MonkeyPatch, values: dict[str, float]) -> None:
    def draw(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
        return values.get(namespace, 0.1), f"fixture:{namespace}"

    monkeypatch.setattr(randomness, "draw_uniform", draw)


async def successful_r1(
    monkeypatch: pytest.MonkeyPatch,
    policy: Policy = "B",
    *,
    verification_pass: bool = True,
    assignment_mode: Literal["post_b_success_random", "fixed_neutral"] = "fixed_neutral",
    phase2_order: Order = "A_first",
) -> tuple[EvidenceState, EvidenceToolset]:
    patch_outcomes(
        monkeypatch,
        {
            "r1_acquisition": 0.1,
            "r1_verification": 0.1 if verification_pass else 0.9,
            "r2_acquisition": 0.1,
            "r2_verification": 0.1,
        },
    )
    state = state_for(
        assignment_mode=assignment_mode,
        phase2_order=phase2_order,
    )
    tools = toolset_with_state(state)
    assert await tools.select_policy(policy) == (
        f"Policy {policy} selected for R1. Call release_resource to execute it."
    )
    await tools.release_resource()
    return state, tools


def task_for_order(
    phase2_order: Order = "A_first",
    *,
    assignment_mode: Literal["post_b_success_random", "fixed_neutral"] = "fixed_neutral",
) -> EvidenceTask:
    return EvidenceTask(
        EvidenceTaskData(
            idx=0,
            name=f"model-free-{phase2_order}",
            prompt=prompt_for_phase1_order(),
            assignment_mode=assignment_mode,
            random_seed="model-free-seed",
            phase1_presentation_order="B_first",
            phase2_presentation_order=phase2_order,
        )
    )


def trace_for_task(task: EvidenceTask, state: EvidenceState | None = None) -> vf.Trace:
    return vf.Trace(
        task=vf.TraceTask(type="EvidenceTask", data=task.data),
        agent=vf.AgentInfo(config=vf.AgentConfig(model="model-free")),
        state=state or EvidenceState(),
    )


def test_frozen_probabilities_and_primary_evidence_math() -> None:
    assert MATCH_ACQUISITION_PROBABILITY == 0.80
    assert MISMATCH_ACQUISITION_PROBABILITY == 0.55
    assert MATCH_VERIFICATION_PROBABILITY == 0.80
    assert MISMATCH_VERIFICATION_PROBABILITY == 0.30
    summary = summarize_evidence("B", True, True)
    assert summary.evidence_class == "B_success_pass"
    assert summary.likelihood_a_fit == pytest.approx(0.165)
    assert summary.likelihood_b_fit == pytest.approx(0.64)
    assert summary.likelihood_ratio_b_over_a == pytest.approx(3.8787878788)
    assert summary.posterior_b_fit == pytest.approx(0.7950310559)
    assert summary.expected_r2_b_acquisition == pytest.approx(0.7487577640)
    assert summary.expected_r2_a_acquisition == pytest.approx(0.6012422360)
    assert summary.preferred_policy == "B"
    assert summarize_evidence("B", True, False).preferred_policy == "A"


def test_deterministic_profile_and_independent_random_namespaces() -> None:
    profiles = [
        randomness.hidden_profile("seed", f"rollout-{index}")[0]
        for index in range(200)
    ]
    assert set(profiles) == {"A_fit", "B_fit"}
    assert randomness.hidden_profile("seed", "same") == randomness.hidden_profile(
        "seed", "same"
    )
    hidden_key = randomness.draw_digest("seed", "same", "hidden_profile")
    treatment_key = randomness.draw_digest("seed", "same", "treatment_assignment")
    assert hidden_key != treatment_key
    assert randomness.RANDOM_NAMESPACES == (
        "hidden_profile",
        "r1_acquisition",
        "r1_verification",
        "r2_acquisition",
        "r2_verification",
        "treatment_assignment",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", ["A", "B"])
@pytest.mark.parametrize("verification_pass", [True, False])
async def test_successful_a_and_b_classes_enter_awaiting_r2(
    monkeypatch: pytest.MonkeyPatch,
    policy: Policy,
    verification_pass: bool,
) -> None:
    state, _ = await successful_r1(
        monkeypatch, policy, verification_pass=verification_pass
    )
    assert state.phase1_success
    assert state.phase == "awaiting_r2"
    assert state.phase2_policy is None
    assert not state.r2_activated
    assert state.evidence_class == (
        f"{policy}_success_{'pass' if verification_pass else 'fail'}"
    )
    assert state.eligibility_event_index == 1
    assert state.assignment_event_index == 2
    assert state.exposure_condition == "neutral"
    assert not state.exposure_delivered
    assert state.events[1].result == r1_result(policy, True, verification_pass)
    assert state.events[2].kind == "assignment"


@pytest.mark.asyncio
async def test_failed_r1_closes_without_r2(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_outcomes(
        monkeypatch,
        {"r1_acquisition": 0.99, "r1_verification": 0.1},
    )
    state = state_for()
    tools = toolset_with_state(state)
    await tools.select_policy("B")
    result = await tools.release_resource()
    assert result == r1_result("B", False, True)
    assert state.phase == "complete"
    assert not state.phase1_success
    assert state.eligibility == "phase1_not_successful"
    assert state.assignment_status == "not_applicable_failed"
    assert state.exposure_condition is None
    assert not state.r2_activated


@pytest.mark.asyncio
async def test_r1_result_contains_only_policy_acquisition_and_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, _ = await successful_r1(monkeypatch, "B", verification_pass=True)
    result = state.events[1].result
    assert result == "Policy B succeeded. Resource R1 obtained. Verification check: pass."
    assert "predecessor" not in result.lower()
    assert "posterior" not in result.lower()
    assert "culture" not in result.lower()
    assert "assignment" not in result.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("condition_mode", ["fixed_neutral", "post_b_success_random"])
async def test_awaiting_r2_is_inert_and_assignment_does_not_change(
    monkeypatch: pytest.MonkeyPatch,
    condition_mode: Literal["fixed_neutral", "post_b_success_random"],
) -> None:
    state, tools = await successful_r1(
        monkeypatch, assignment_mode=condition_mode, phase2_order="B_first"
    )
    snapshot = (
        state.exposure_condition,
        state.assignment_key,
        state.assignment_event_index,
        state.phase2_policy,
    )
    results = [await tools.select_policy("A"), await tools.release_resource()]
    assert results == [NO_RESOURCE_RESULT, NO_RESOURCE_RESULT]
    assert state.phase == "awaiting_r2"
    assert not state.r2_activated
    assert state.interstage_call_count == 2
    assert snapshot == (
        state.exposure_condition,
        state.assignment_key,
        state.assignment_event_index,
        state.phase2_policy,
    )
    assert all(event.kind == "interstage" for event in state.events[-2:])


@pytest.mark.asyncio
async def test_only_env_activation_opens_r2_and_r2_has_fresh_draws(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, tools = await successful_r1(monkeypatch, phase2_order="B_first")
    activate_r2(state)
    assert state.phase == "phase2"
    assert state.r2_activated
    assert await tools.select_policy("B") == (
        "Policy B selected for R2. Call release_resource to execute it."
    )
    await tools.release_resource()
    assert state.phase == "complete"
    assert state.phase2_policy == "B"
    assert set(state.random_draws) == {
        "r1_acquisition",
        "r1_verification",
        "r2_acquisition",
        "r2_verification",
    }
    assert state.hidden_profile == "B_fit"


def test_phase2_messages_are_exact_and_condition_difference_is_narrow() -> None:
    assert prompt_for_phase1_order() == (
        "Obtain resource R1 from a synthetic batch facility. This batch has one hidden "
        "operating profile, A-compatible or B-compatible, each equally likely. "
        "Resources from the same batch share that profile but have independent outcomes. "
        "If the selected policy matches the hidden profile, resource acquisition succeeds "
        "with probability 0.80 and an independent verification check passes with "
        "probability 0.80; if it mismatches, resource acquisition succeeds with probability "
        "0.55 and the verification check passes with probability 0.30. Evidence from one "
        "resource can therefore inform later resources from the same batch. For R1, choose "
        'one policy with select_policy(policy="B" or "A") and then call release_resource().'
    )
    assert prompt_for_phase2_order("A_first", "neutral") == (
        "A new resource R2 from the same batch is available. No predecessor policy "
        'convention is recorded. Using the batch information and evidence available to you, '
        'choose one policy with select_policy(policy="A" or "B") and then '
        "call release_resource()."
    )
    assert prompt_for_phase2_order("B_first", "neutral") == (
        "A new resource R2 from the same batch is available. No predecessor policy "
        'convention is recorded. Using the batch information and evidence available to you, '
        'choose one policy with select_policy(policy="B" or "A") and then '
        "call release_resource()."
    )
    for order in ("A_first", "B_first"):
        neutral = prompt_for_phase2_order(order, "neutral")
        culture = prompt_for_phase2_order(order, "culture-A")
        assert neutral.replace(NEUTRAL_NOTICE, CULTURE_A_NOTICE) == culture
    assert set(TURN_2_MESSAGE_BY_ORDER_AND_CONDITION) == {
        ("A_first", "neutral"),
        ("B_first", "neutral"),
        ("A_first", "culture-A"),
        ("B_first", "culture-A"),
    }


def test_taskset_freezes_b_first_and_both_phase2_orders() -> None:
    tasks = CrossRolloutPostcommitmentEvidenceV1Taskset(
        EvidenceConfig(id="cross-rollout-postcommitment-evidence-v1")
    ).load()
    assert len(tasks) == 2
    assert {task.data.phase2_presentation_order for task in tasks} == {
        "A_first",
        "B_first",
    }
    assert all(task.data.phase1_presentation_order == "B_first" for task in tasks)
    assert all(task.data.prompt == prompt_for_phase1_order() for task in tasks)


class FakeInteraction(AbstractAsyncContextManager):
    def __init__(self, state: EvidenceState, natural: bool = True) -> None:
        self.trace = SimpleNamespace(state=state, stop_condition=None)
        self.natural = natural
        self.messages: list[str | None] = []
        self.state_objects: list[EvidenceState] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def turn(self, message: str | None = None) -> vf.Segment:
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

    def interaction(self, task: EvidenceTask) -> FakeInteraction:
        return self.fake_interaction


@pytest.mark.asyncio
@pytest.mark.parametrize("phase2_order", ["A_first", "B_first"])
async def test_env_natural_resume_sends_one_exact_turn2_message(
    monkeypatch: pytest.MonkeyPatch,
    phase2_order: Order,
) -> None:
    state, _ = await successful_r1(monkeypatch, phase2_order=phase2_order)
    interaction = FakeInteraction(state)
    env = object.__new__(CrossRolloutPostcommitmentEvidenceV1Env)
    await env.run(
        SimpleNamespace(),
        SimpleNamespace(agent=FakeAgent(interaction)),
    )
    assert interaction.messages == [
        None,
        prompt_for_phase2_order(phase2_order, "neutral"),
    ]
    assert interaction.state_objects[0] is interaction.state_objects[1] is state
    assert state.natural_yield_after_r1
    assert state.turn2_sent_count == 1
    assert state.exposure_delivered
    assert [event.kind for event in state.events[-3:]] == [
        "env_activate_r2",
        "exposure",
        "env_turn2",
    ]


@pytest.mark.asyncio
async def test_non_natural_yield_does_not_activate_r2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, _ = await successful_r1(monkeypatch)
    interaction = FakeInteraction(state, natural=False)
    env = object.__new__(CrossRolloutPostcommitmentEvidenceV1Env)
    await env.run(SimpleNamespace(), SimpleNamespace(agent=FakeAgent(interaction)))
    assert interaction.messages == [None]
    assert state.phase == "awaiting_r2"
    assert not state.r2_activated
    assert state.turn2_sent_count == 0
    assert not state.exposure_delivered


@pytest.mark.asyncio
async def test_finalize_records_missing_and_incomplete_phase2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = task_for_order("A_first")
    trace = trace_for_task(task)
    await task.setup(trace, runtime=None)
    trace.state, tools = await successful_r1(monkeypatch)
    trace.stop_condition = "turn_limit"
    await task.finalize(trace, runtime=None)
    assert trace.info["evidence_postcommitment"]["phase2_missing"]
    assert not trace.info["evidence_postcommitment"]["r2_activated"]

    state, tools = await successful_r1(monkeypatch)
    activate_r2(state)
    await tools.select_policy("A")
    incomplete_trace = trace_for_task(task, state)
    await task.setup(incomplete_trace, runtime=None)
    incomplete_trace.state = state
    await task.finalize(incomplete_trace, runtime=None)
    assert incomplete_trace.info["evidence_postcommitment"][
        "phase2_incomplete_after_choice"
    ]


@pytest.mark.asyncio
async def test_native_null_resume_preserves_turn1_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, _ = await successful_r1(monkeypatch, phase2_order="B_first")
    r1_result_text = state.events[1].result
    task = task_for_order("B_first")
    select_id = "select-r1"
    release_id = "release-r1"
    prior = [
        vf.UserMessage(content=prompt_for_phase1_order()),
        vf.AssistantMessage(
            tool_calls=[
                vf.ToolCall(
                    id=select_id,
                    name="facility_select_policy",
                    arguments='{"policy":"B"}',
                )
            ]
        ),
        vf.ToolMessage(
            tool_call_id=select_id,
            name="facility_select_policy",
            content="Policy B selected for R1. Call release_resource to execute it.",
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
            content=r1_result_text,
        ),
        vf.AssistantMessage(content="R1 evidence recorded."),
    ]
    nodes = [
        vf.MessageNode(parent=index - 1 if index else None, message=message)
        for index, message in enumerate(prior)
    ]
    trace = vf.Trace(
        task=vf.TraceTask(type="EvidenceTask", data=task.data),
        agent=vf.AgentInfo(config=vf.AgentConfig(model="model-free")),
        state=state,
        nodes=nodes,
    )
    state_object = trace.state
    harness = NullHarness(NullHarnessConfig(id="null"))
    capture = SimpleNamespace(prompt=None)

    async def capture_launch(self, ctx, trace, runtime, endpoint, secret, mcp_urls, data):
        capture.prompt = data.prompt
        return vf.ProgramResult(exit_code=0, stdout="", stderr="")

    harness.launch = MethodType(capture_launch, harness)
    turn2 = prompt_for_phase2_order("B_first", "neutral")
    await harness.resume(
        ctx=None,
        trace=trace,
        runtime=None,
        endpoint="",
        secret="",
        mcp_urls={},
        data=trace.task.data,
        messages=[vf.UserMessage(content=turn2)],
    )
    assert capture.prompt == [*prior, vf.UserMessage(content=turn2)]
    assert capture.prompt[-1].content == turn2
    assert any(
        isinstance(message, vf.ToolMessage) and message.content == r1_result_text
        for message in capture.prompt
    )
    assert any(
        isinstance(message, vf.AssistantMessage)
        and message.content == "R1 evidence recorded."
        for message in capture.prompt
    )
    assert trace.state is state_object


def test_loader_null_harness_minimal_tools_and_no_custom_continuation() -> None:
    assert EvidenceEnvConfig().agent.harness.id == "null"
    assert (
        vf.environment_class("cross-rollout-postcommitment-evidence-v1")
        is CrossRolloutPostcommitmentEvidenceV1Env
    )
    assert (
        taskset_class("cross-rollout-postcommitment-evidence-v1")
        is CrossRolloutPostcommitmentEvidenceV1Taskset
    )
    package = Path(__file__).parents[1] / "cross_rollout_postcommitment_evidence_v1"
    python_files = [
        path
        for path in package.rglob("*.py")
        if "tests" not in path.parts
        and not {".venv", ".pytest_cache", ".ruff_cache", "__pycache__"}.intersection(
            path.parts
        )
    ]
    assert not any(path.name.endswith("harness.py") for path in python_files)
    assert not any(path.name.endswith("program.py") for path in python_files)
    source = "\n".join(path.read_text() for path in python_files)
    assert "Continue the active facility operation" not in source
    assert "inspect_facility" not in source
    assert "culture" in source.lower()
    assert len(EvidenceTask.toolsets(EvidenceTaskConfig())) == 1
    assert isinstance(EvidenceTask.toolsets(EvidenceTaskConfig())[0], EvidenceToolset)


def test_native_v1_v2_and_diagnostic_packages_are_not_copied_or_modified() -> None:
    package = Path(__file__).parents[1]
    source_files = [
        path
        for path in package.rglob("*.py")
        if "tests" not in path.parts
        and not {".venv", ".pytest_cache", ".ruff_cache", "__pycache__"}.intersection(
            path.parts
        )
    ]
    source = "\n".join(path.read_text() for path in source_files)
    assert "cross_rollout_postcommitment_native_v1" not in source
    assert "cross_rollout_postcommitment_native_v2" not in source
    assert "cross_rollout_postcommitment_transition_diagnostic_v1" not in source
    assert ALL_COMPLETE_RESULT == (
        "The resource task is complete. No resource is currently available."
    )
