"""Model-free audit tests for the frozen relative-condition lifecycle."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Literal, Self

import pytest
import verifiers.v1 as vf
from cross_rollout_postcommitment_evidence_relative_v1 import assignment, randomness
from cross_rollout_postcommitment_evidence_relative_v1.assignment import (
    ASSIGNMENT_NAMESPACES,
    BLOCK_SIZE,
    MAX_PRIMARY_ELIGIBLE,
    assignment_for_index,
    claim_assignment,
)
from cross_rollout_postcommitment_evidence_relative_v1.evidence import (
    MATCH_ACQUISITION_PROBABILITY,
    MATCH_VERIFICATION_PROBABILITY,
    MISMATCH_ACQUISITION_PROBABILITY,
    MISMATCH_VERIFICATION_PROBABILITY,
    summarize_evidence,
)
from cross_rollout_postcommitment_evidence_relative_v1.servers.facility import (
    NEUTRAL_PREDECESSOR_SENTENCE,
    NO_RESOURCE_RESULT,
    OPPOSING_A_PREDECESSOR_SENTENCE,
    OPPOSING_B_PREDECESSOR_SENTENCE,
    RelativeToolset,
    RelativeToolsetConfig,
    r1_result,
)
from cross_rollout_postcommitment_evidence_relative_v1.state import RelativeState
from cross_rollout_postcommitment_evidence_relative_v1.taskset import (
    CrossRolloutPostcommitmentEvidenceRelativeV1Env,
    CrossRolloutPostcommitmentEvidenceRelativeV1Taskset,
    RelativeConfig,
    RelativeTask,
    RelativeTaskConfig,
    RelativeTaskData,
    activate_r2,
    prompt_for_phase1_order,
    prompt_for_phase2_order,
)
from verifiers.v1.harnesses.null import NullHarness, NullHarnessConfig

Policy = Literal["A", "B"]
Order = Literal["A_first", "B_first"]


def state_for(tmp_path: Path, *, profile: Literal["A_fit", "B_fit"] = "B_fit") -> RelativeState:
    return RelativeState(
        rollout_id="model-free-rollout",
        random_seed="model-free-seed",
        assignment_seed="model-free-assignment-seed",
        assignment_state_path=str(tmp_path / "assignments.json"),
        hidden_profile=profile,
        phase1_presentation_order="B_first",
    )


def toolset_with_state(state: RelativeState) -> RelativeToolset:
    toolset = RelativeToolset(RelativeToolsetConfig())
    toolset._inert_state = state
    return toolset


def patch_outcomes(monkeypatch: pytest.MonkeyPatch, values: dict[str, float]) -> None:
    def draw(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
        return values.get(namespace, 0.1), f"fixture:{namespace}"

    monkeypatch.setattr(randomness, "draw_uniform", draw)


async def successful_r1(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    policy: Policy = "B",
    *,
    verification_pass: bool = True,
) -> tuple[RelativeState, RelativeToolset]:
    patch_outcomes(
        monkeypatch,
        {
            "r1_acquisition": 0.1,
            "r1_verification": 0.1 if verification_pass else 0.9,
            "r2_acquisition": 0.1,
            "r2_verification": 0.1,
        },
    )
    state = state_for(tmp_path)
    tools = toolset_with_state(state)
    assert await tools.select_policy(policy) == (
        f"Policy {policy} selected for R1. Call release_resource to execute it."
    )
    await tools.release_resource()
    return state, tools


def task_for(tmp_path: Path) -> RelativeTask:
    return RelativeTask(
        RelativeTaskData(
            idx=0,
            name="model-free-relative",
            prompt=prompt_for_phase1_order(),
            assignment_mode="relative_randomized",
            random_seed="model-free-seed",
            assignment_seed="model-free-assignment-seed",
            assignment_state_path=str(tmp_path / "assignments.json"),
            phase1_presentation_order="B_first",
        ),
        RelativeTaskConfig(),
    )


def trace_for(task: RelativeTask, state: RelativeState | None = None) -> vf.Trace:
    return vf.Trace(
        task=vf.TraceTask(type="RelativeTask", data=task.data),
        agent=vf.AgentInfo(config=vf.AgentConfig(model="model-free")),
        state=state or RelativeState(),
    )


def test_frozen_evidence_model_and_both_primary_origins() -> None:
    assert MATCH_ACQUISITION_PROBABILITY == 0.80
    assert MISMATCH_ACQUISITION_PROBABILITY == 0.55
    assert MATCH_VERIFICATION_PROBABILITY == 0.80
    assert MISMATCH_VERIFICATION_PROBABILITY == 0.30
    for policy in ("A", "B"):
        summary = summarize_evidence(policy, True, True)
        assert summary.evidence_class == f"{policy}_success_pass"
        assert summary.posterior_b_fit == pytest.approx(
            0.7950310559 if policy == "B" else 0.2049689441
        )
        assert summary.expected_r2_b_acquisition == pytest.approx(
            0.7487577640 if policy == "B" else 0.6012422360
        )
        assert summary.expected_r2_a_acquisition == pytest.approx(
            0.6012422360 if policy == "B" else 0.7487577640
        )


def test_randomness_namespaces_are_distinct_and_assignment_is_independent() -> None:
    assert randomness.RANDOM_NAMESPACES == (
        "hidden_profile",
        "r1_acquisition",
        "r1_verification",
        "r2_acquisition",
        "r2_verification",
        "treatment_assignment",
        "phase2_assignment_block",
    )
    assert ASSIGNMENT_NAMESPACES == (
        "treatment_assignment",
        "phase2_assignment_block",
    )
    assert randomness.draw_digest("seed", "rollout", "hidden_profile") != (
        randomness.draw_digest("seed", "rollout", "r1_acquisition")
    )
    first = assignment_for_index("seed", 0)
    second = assignment_for_index("seed", 0)
    assert first == second
    assert first.treatment_key != first.phase2_key
    assert assignment_for_index("seed", 0).condition == assignment_for_index(
        "seed", 0
    ).condition


def test_blocked_assignment_has_exact_four_cells_per_block() -> None:
    assert MAX_PRIMARY_ELIGIBLE == 64
    assert BLOCK_SIZE == 4
    cells = [
        (assignment_for_index("fixed-seed", index).condition,
         assignment_for_index("fixed-seed", index).phase2_order)
        for index in range(MAX_PRIMARY_ELIGIBLE)
    ]
    expected = {
        ("neutral", "A_first"),
        ("neutral", "B_first"),
        ("opposing_convention", "A_first"),
        ("opposing_convention", "B_first"),
    }
    for offset in range(0, MAX_PRIMARY_ELIGIBLE, BLOCK_SIZE):
        assert set(cells[offset : offset + BLOCK_SIZE]) == expected


def test_allocator_claims_sequential_indices_and_never_resets(tmp_path: Path) -> None:
    path = tmp_path / "allocator.json"
    for expected in range(8):
        claimed = claim_assignment(str(path), "seed")
        assert claimed.eligible_index == expected
    assignment.ensure_assignment_state(str(path), "seed")
    assert claim_assignment(str(path), "seed").eligible_index == 8
    with pytest.raises(RuntimeError, match="seed"):
        assignment.ensure_assignment_state(str(path), "other-seed")


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", ["A", "B"])
async def test_a_and_b_success_pass_both_enter_primary_awaiting_r2(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    policy: Policy,
) -> None:
    state, _ = await successful_r1(monkeypatch, tmp_path, policy)
    assert state.primary_eligible
    assert state.phase == "awaiting_r2"
    assert state.evidence_supported_policy == policy
    assert state.alternative_policy == ("B" if policy == "A" else "A")
    assert state.eligibility_event_index == 1
    assert state.assignment_event_index == 2
    assert state.assignment_event_index > state.eligibility_event_index
    assert state.assignment_randomized
    assert state.exposure_condition in ("neutral", "opposing_convention")
    assert state.exposure_text
    assert not state.exposure_delivered


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", ["A", "B"])
async def test_nonprimary_r1_outcomes_end_without_assignment_or_r2(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    policy: Policy,
) -> None:
    state, _ = await successful_r1(
        monkeypatch, tmp_path, policy, verification_pass=False
    )
    assert state.phase == "complete"
    assert state.phase1_success
    assert not state.primary_eligible
    assert state.eligibility == "nonprimary_success_verification_fail"
    assert state.assignment_status == "not_applicable_nonprimary"
    assert state.exposure_condition is None
    assert not state.r2_activated


@pytest.mark.asyncio
async def test_failed_r1_closes_without_r2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    patch_outcomes(monkeypatch, {"r1_acquisition": 0.99, "r1_verification": 0.1})
    state = state_for(tmp_path)
    tools = toolset_with_state(state)
    await tools.select_policy("B")
    result = await tools.release_resource()
    assert result == r1_result("B", False, True)
    assert state.phase == "complete"
    assert not state.primary_eligible
    assert state.eligibility == "phase1_not_successful"
    assert state.assignment_status == "not_applicable_failed"
    assert state.exposure_condition is None
    assert not state.r2_activated


@pytest.mark.asyncio
async def test_awaiting_r2_is_inert_and_hides_predecessor_information(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state, tools = await successful_r1(monkeypatch, tmp_path, "A")
    assigned = (state.exposure_condition, state.phase2_presentation_order)
    assert "predecessor" not in state.events[1].result.lower()
    assert "operators" not in state.events[1].result.lower()
    assert await tools.select_policy("B") == NO_RESOURCE_RESULT
    assert await tools.release_resource() == NO_RESOURCE_RESULT
    assert state.phase == "awaiting_r2"
    assert not state.r2_activated
    assert state.interstage_call_count == 2
    assert assigned == (state.exposure_condition, state.phase2_presentation_order)


@pytest.mark.asyncio
async def test_only_env_activation_opens_r2_and_policy_precedes_outcome(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state, tools = await successful_r1(monkeypatch, tmp_path, "B")
    activate_r2(state)
    assert state.phase == "phase2"
    assert await tools.select_policy("A") == (
        "Policy A selected for R2. Call release_resource to execute it."
    )
    await tools.release_resource()
    assert state.phase == "complete"
    assert state.phase2_policy == "A"
    assert state.events[-2].argument == "select_policy(A)"
    assert state.events[-1].argument == "release_resource"
    assert state.events[-2].index < state.events[-1].index
    assert set(state.random_draws) == {
        "r1_acquisition",
        "r1_verification",
        "r2_acquisition",
        "r2_verification",
        "treatment_assignment",
        "phase2_assignment_block",
    }


@pytest.mark.asyncio
async def test_setup_records_one_hidden_profile_draw(tmp_path: Path) -> None:
    task = task_for(tmp_path)
    trace = trace_for(task)
    await task.setup(trace, runtime=None)
    assert trace.state.hidden_profile in ("A_fit", "B_fit")
    assert set(trace.state.random_draws) == {"hidden_profile"}


def test_messages_are_exact_and_condition_difference_is_only_predecessor_sentence() -> None:
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
    for policy in ("A", "B"):
        for order in ("A_first", "B_first"):
            neutral = prompt_for_phase2_order(order, "neutral", policy)
            opposing = prompt_for_phase2_order(order, "opposing_convention", policy)
            assert "equally viable" not in neutral
            assert "equally viable" not in opposing
            assert neutral.replace(
                NEUTRAL_PREDECESSOR_SENTENCE,
                predecessor_sentence_for_test(policy),
            ) == opposing
            assert "recommend" not in opposing.lower()
    assert OPPOSING_A_PREDECESSOR_SENTENCE != OPPOSING_B_PREDECESSOR_SENTENCE


def predecessor_sentence_for_test(policy: Policy) -> str:
    return (
        OPPOSING_A_PREDECESSOR_SENTENCE
        if policy == "A"
        else OPPOSING_B_PREDECESSOR_SENTENCE
    )


class FakeInteraction(AbstractAsyncContextManager):
    def __init__(self, state: RelativeState, natural: bool = True) -> None:
        self.trace = SimpleNamespace(state=state, stop_condition=None)
        self.natural = natural
        self.messages: list[str | None] = []
        self.state_objects: list[RelativeState] = []

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

    def interaction(self, task: RelativeTask) -> FakeInteraction:
        return self.fake_interaction


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["A_first", "B_first"])
async def test_env_natural_resume_sends_one_exact_turn2_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, order: Order
) -> None:
    state, _ = await successful_r1(monkeypatch, tmp_path, "B")
    state.phase2_presentation_order = order
    state.exposure_condition = "neutral"
    interaction = FakeInteraction(state)
    env = object.__new__(CrossRolloutPostcommitmentEvidenceRelativeV1Env)
    await env.run(SimpleNamespace(), SimpleNamespace(agent=FakeAgent(interaction)))
    assert interaction.messages == [
        None,
        prompt_for_phase2_order(order, "neutral", "B"),
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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state, _ = await successful_r1(monkeypatch, tmp_path, "B")
    interaction = FakeInteraction(state, natural=False)
    env = object.__new__(CrossRolloutPostcommitmentEvidenceRelativeV1Env)
    await env.run(SimpleNamespace(), SimpleNamespace(agent=FakeAgent(interaction)))
    assert interaction.messages == [None]
    assert state.phase == "awaiting_r2"
    assert not state.r2_activated
    assert state.turn2_sent_count == 0


@pytest.mark.asyncio
async def test_native_null_resume_preserves_turn1_transcript(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state, _ = await successful_r1(monkeypatch, tmp_path, "B")
    r1_result_text = state.events[1].result
    task = task_for(tmp_path)
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
        task=vf.TraceTask(type="RelativeTask", data=task.data),
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
    turn2 = prompt_for_phase2_order("B_first", "neutral", "B")
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
    assert trace.state is state_object


@pytest.mark.asyncio
async def test_primary_missing_remains_itt_not_switch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    task = task_for(tmp_path)
    trace = trace_for(task)
    await task.setup(trace, runtime=None)
    state = trace.state
    patch_outcomes(
        monkeypatch,
        {
            "r1_acquisition": 0.1,
            "r1_verification": 0.1,
        },
    )
    tools = toolset_with_state(state)
    await tools.select_policy("B")
    await tools.release_resource()
    trace.stop_condition = "natural_yield_without_resume"
    await task.finalize(trace, runtime=None)
    info = trace.info["evidence_relative_postcommitment"]
    assert info["primary_eligible"]
    assert info["phase2_missing"]
    assert info["primary_itt_not_switch"]
    assert not info["primary_itt_switch"]


@pytest.mark.asyncio
async def test_completed_r2_acquisition_failure_is_not_incomplete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    task = task_for(tmp_path)
    trace = trace_for(task)
    await task.setup(trace, runtime=None)
    state = trace.state
    patch_outcomes(
        monkeypatch,
        {
            "r1_acquisition": 0.1,
            "r1_verification": 0.1,
            "r2_acquisition": 0.99,
            "r2_verification": 0.1,
        },
    )
    tools = toolset_with_state(state)
    await tools.select_policy("B")
    await tools.release_resource()
    activate_r2(state)
    await tools.select_policy("A")
    await tools.release_resource()
    await task.finalize(trace, runtime=None)
    info = trace.info["evidence_relative_postcommitment"]
    assert state.phase2_release_attempted
    assert not state.phase2_success
    assert not info["phase2_incomplete_after_choice"]


@pytest.mark.asyncio
async def test_r2_choice_without_release_is_incomplete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    task = task_for(tmp_path)
    trace = trace_for(task)
    await task.setup(trace, runtime=None)
    state = trace.state
    patch_outcomes(
        monkeypatch,
        {"r1_acquisition": 0.1, "r1_verification": 0.1},
    )
    tools = toolset_with_state(state)
    await tools.select_policy("B")
    await tools.release_resource()
    activate_r2(state)
    await tools.select_policy("A")
    await task.finalize(trace, runtime=None)
    info = trace.info["evidence_relative_postcommitment"]
    assert not state.phase2_release_attempted
    assert info["phase2_incomplete_after_choice"]


def test_taskset_is_one_frozen_b_first_task_and_has_no_custom_continuation() -> None:
    tasks = CrossRolloutPostcommitmentEvidenceRelativeV1Taskset(
        RelativeConfig(id="cross-rollout-postcommitment-evidence-relative-v1")
    ).load()
    assert len(tasks) == 1
    assert tasks[0].data.phase1_presentation_order == "B_first"
    assert tasks[0].data.prompt == prompt_for_phase1_order()
    source = (
        Path(__file__).parents[1] / "cross_rollout_postcommitment_evidence_relative_v1"
    )
    facility_text = (source / "servers" / "facility.py").read_text()
    taskset_text = (source / "taskset.py").read_text()
    assert "custom" not in facility_text.lower()
    assert "continuation" not in taskset_text.lower()
    assert "nudge" not in taskset_text.lower()
    assert "NullHarnessConfig" in taskset_text
