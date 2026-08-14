"""Model-free tests for the frozen balanced evidence contract."""

from __future__ import annotations

import inspect
from contextlib import AbstractAsyncContextManager
from types import MethodType, SimpleNamespace
from typing import get_type_hints

import pytest
import verifiers.v1 as vf
from verifiers.v1.harnesses.null import NullHarness, NullHarnessConfig

from cross_rollout_postcommitment_evidence_interface_balanced_v1.assignment import (
    MAX_PRIMARY_ELIGIBLE,
    assignment_for_index,
    claim_assignment,
    ensure_assignment_state,
)
from cross_rollout_postcommitment_evidence_interface_balanced_v1.constants import (
    MATCH_ACQUISITION_PROBABILITY,
    MATCH_VERIFICATION_PROBABILITY,
    MISMATCH_ACQUISITION_PROBABILITY,
    MISMATCH_VERIFICATION_PROBABILITY,
    NEUTRAL_PREDECESSOR_SENTENCE,
    OPPOSING_PREDECESSOR_SENTENCE,
    RELEASE_DESCRIPTION,
    SELECT_DESCRIPTION,
    phase1_prompt,
    phase2_prompt,
)
from cross_rollout_postcommitment_evidence_interface_balanced_v1.evidence import (
    policy_matches_profile,
    summarize_evidence,
)
from cross_rollout_postcommitment_evidence_interface_balanced_v1.randomness import (
    ROLLOUT_NAMESPACES,
    hidden_profile,
)
from cross_rollout_postcommitment_evidence_interface_balanced_v1.schedule import (
    MAX_ATTEMPTS,
    SCHEDULE_SEED,
    SECONDARY_SCHEDULE_SEED,
    TARGET_PRIMARY_ELIGIBLE,
    build_schedule,
)
from cross_rollout_postcommitment_evidence_interface_balanced_v1.servers.facility import (
    NO_RESOURCE_RESULT,
    BalancedToolset,
    BalancedToolsetConfig,
)
from cross_rollout_postcommitment_evidence_interface_balanced_v1.state import (
    BalancedState,
)
from cross_rollout_postcommitment_evidence_interface_balanced_v1.taskset import (
    BalancedConfig,
    BalancedEnvConfig,
    CrossRolloutPostcommitmentEvidenceInterfaceBalancedV1Env,
    CrossRolloutPostcommitmentEvidenceInterfaceBalancedV1Taskset,
    activate_r2,
    segment_ended_naturally,
)


def toolset_with_state(
    *,
    profile: str = "policy_1_fit",
    phase: str = "phase1",
    assignment_path: str = "/tmp/balanced-test-assignments.json",
) -> BalancedToolset:
    toolset = BalancedToolset(BalancedToolsetConfig())
    toolset._inert_state = BalancedState(
        rollout_id="fixture-rollout",
        random_seed="fixture-random-seed",
        assignment_seed="fixture-assignment-seed",
        assignment_state_path=assignment_path,
        hidden_profile=profile,
        phase=phase,
        exposure_condition="neutral" if phase != "phase1" else None,
        phase2_presentation_order="K_first" if phase != "phase1" else None,
        assignment_status="fixed_neutral_nonprimary"
        if phase != "phase1"
        else "pending_phase1",
    )
    return toolset


def test_frozen_schedule_is_240_alternating_and_secondary_balanced() -> None:
    schedule = build_schedule(SCHEDULE_SEED, SECONDARY_SCHEDULE_SEED)
    assert len(schedule) == MAX_ATTEMPTS == 240
    assert [row.attempt_index for row in schedule] == list(range(MAX_ATTEMPTS))
    assert [row.phase1_order for row in schedule[:8]] == [
        "K_first",
        "M_first",
        "K_first",
        "M_first",
        "K_first",
        "M_first",
        "K_first",
        "M_first",
    ]
    assert sum(row.phase1_order == "K_first" for row in schedule) == 120
    assert sum(row.phase1_order == "M_first" for row in schedule) == 120
    assert sum(row.secondary_phase2_order == "K_first" for row in schedule) == 120
    assert sum(row.secondary_phase2_order == "M_first" for row in schedule) == 120
    assert {
        (row.phase1_order, row.secondary_phase2_order) for row in schedule
    } == {
        ("K_first", "K_first"),
        ("K_first", "M_first"),
        ("M_first", "K_first"),
        ("M_first", "M_first"),
    }
    assert schedule == build_schedule(SCHEDULE_SEED, SECONDARY_SCHEDULE_SEED)


def test_taskset_materializes_the_frozen_schedule_and_prompt_variants() -> None:
    tasks = CrossRolloutPostcommitmentEvidenceInterfaceBalancedV1Taskset(
        BalancedConfig()
    ).load()
    assert len(tasks) == 240
    assert [task.data.attempt_index for task in tasks] == list(range(240))
    assert tasks[0].data.prompt == phase1_prompt("K_first")
    assert tasks[1].data.prompt == phase1_prompt("M_first")
    assert sum(task.data.phase1_presentation_order == "K_first" for task in tasks) == 120
    assert sum(task.data.phase1_presentation_order == "M_first" for task in tasks) == 120


def test_phase1_has_only_one_ordered_label_pair() -> None:
    for order, first, second in (
        ("K_first", "K", "M"),
        ("M_first", "M", "K"),
    ):
        prompt = phase1_prompt(order)
        assert prompt.count(f'"{first}" or "{second}"') == 1
        before_instruction = prompt.split("For R1, choose one policy with", 1)[0]
        assert "K" not in before_instruction
        assert "M" not in before_instruction
        assert "R2" not in prompt
        assert "predecessor" not in prompt.lower()


def test_phase2_has_only_the_explicit_ordered_pair_and_relative_history() -> None:
    for order, first, second in (
        ("K_first", "K", "M"),
        ("M_first", "M", "K"),
    ):
        for condition, sentence in (
            ("neutral", NEUTRAL_PREDECESSOR_SENTENCE),
            ("opposing_convention", OPPOSING_PREDECESSOR_SENTENCE),
        ):
            prompt = phase2_prompt(order, condition)
            assert prompt.count(f'"{first}" or "{second}"') == 1
            assert sentence in prompt
            prefix = prompt.split("Using the batch information", 1)[0]
            assert "K" not in prefix
            assert "M" not in prefix
        neutral = phase2_prompt(order, "neutral")
        opposing = phase2_prompt(order, "opposing_convention")
        assert neutral.replace(NEUTRAL_PREDECESSOR_SENTENCE, "HISTORY") == opposing.replace(
            OPPOSING_PREDECESSOR_SENTENCE, "HISTORY"
        )


def test_frozen_evidence_math_is_symmetric_and_exact() -> None:
    for policy in ("K", "M"):
        summary = summarize_evidence(policy, True, True)
        assert summary.likelihood_ratio_selected_over_alternative == pytest.approx(
            3.8787878788, abs=1e-9
        )
        assert summary.posterior_selected_fit == pytest.approx(0.7950310559, abs=1e-9)
        assert summary.expected_selected_r2_acquisition == pytest.approx(
            0.7487577640, abs=1e-9
        )
        assert summary.expected_alternative_r2_acquisition == pytest.approx(
            0.6012422360, abs=1e-9
        )
        assert summary.selected_policy == policy
        assert summary.alternative_policy != policy
    assert MATCH_ACQUISITION_PROBABILITY == 0.80
    assert MISMATCH_ACQUISITION_PROBABILITY == 0.55
    assert MATCH_VERIFICATION_PROBABILITY == 0.80
    assert MISMATCH_VERIFICATION_PROBABILITY == 0.30


def test_profile_prior_and_policy_mechanics_are_symmetric() -> None:
    outcomes = [hidden_profile("fixture-seed", str(i))[0] for i in range(400)]
    assert set(outcomes) == {"policy_1_fit", "policy_2_fit"}
    assert hidden_profile("fixture-seed", "same") == hidden_profile(
        "fixture-seed", "same"
    )
    assert policy_matches_profile("K", "policy_1_fit")
    assert policy_matches_profile("M", "policy_2_fit")
    assert not policy_matches_profile("K", "policy_2_fit")
    assert not policy_matches_profile("M", "policy_1_fit")
    assert set(ROLLOUT_NAMESPACES) == {
        "hidden_profile",
        "r1_acquisition",
        "r1_verification",
        "r2_acquisition",
        "r2_verification",
    }


def test_tool_schema_boundary_is_plain_string_and_label_neutral() -> None:
    parameter = inspect.signature(BalancedToolset.select_policy).parameters["policy"]
    assert parameter.annotation is str
    assert inspect.getdoc(BalancedToolset.select_policy) == SELECT_DESCRIPTION
    assert inspect.getdoc(BalancedToolset.release_resource) == RELEASE_DESCRIPTION
    assert not any(label in SELECT_DESCRIPTION for label in ("K", "M"))
    assert not any(label in RELEASE_DESCRIPTION for label in ("K", "M"))
    assert get_type_hints(BalancedToolset.select_policy)["policy"] is str


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("policy", "profile"),
    [("K", "policy_1_fit"), ("M", "policy_2_fit")],
)
async def test_success_pass_enters_awaiting_and_claims_primary_assignment(
    tmp_path, monkeypatch: pytest.MonkeyPatch, policy: str, profile: str
) -> None:
    values = {"r1_acquisition": 0.1, "r1_verification": 0.1}

    def draw(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
        return values[namespace], f"fixture:{namespace}"

    monkeypatch.setattr(
        "cross_rollout_postcommitment_evidence_interface_balanced_v1.servers.facility.randomness.draw_uniform",
        draw,
    )
    path = str(tmp_path / "assignments.json")
    toolset = toolset_with_state(profile=profile, assignment_path=path)
    ensure_assignment_state(path, "fixture-assignment-seed")
    assert await toolset.select_policy(policy) == (
        f"Policy {policy} selected for R1. Call release_resource to execute it."
    )
    result = await toolset.release_resource()
    assert result == f"Policy {policy} succeeded. Resource R1 obtained. Verification check: pass."
    assert NEUTRAL_PREDECESSOR_SENTENCE not in result
    assert OPPOSING_PREDECESSOR_SENTENCE not in result
    assert toolset.state.primary_eligible
    assert toolset.state.phase == "awaiting_r2"
    assert not toolset.state.r2_activated
    assert toolset.state.turn2_message == ""
    assert toolset.state.assignment_randomized
    assert toolset.state.exposure_condition in {"neutral", "opposing_convention"}
    assert toolset.state.exposure_text
    assert "K" not in toolset.state.exposure_text
    assert "M" not in toolset.state.exposure_text
    assert toolset.state.evidence_supported_policy == policy
    assert toolset.state.eligible_index == 0


@pytest.mark.asyncio
async def test_success_verification_fail_enters_neutral_secondary_control(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def draw(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
        values = {"r1_acquisition": 0.1, "r1_verification": 0.9}
        return values[namespace], f"fixture:{namespace}"

    monkeypatch.setattr(
        "cross_rollout_postcommitment_evidence_interface_balanced_v1.servers.facility.randomness.draw_uniform",
        draw,
    )
    toolset = toolset_with_state(
        profile="policy_1_fit",
        assignment_path=str(tmp_path / "assignments.json"),
    )
    await toolset.select_policy("K")
    result = await toolset.release_resource()
    assert result == "Policy K succeeded. Resource R1 obtained. Verification check: fail."
    assert toolset.state.evidence_class == "K_success_fail"
    assert toolset.state.phase == "awaiting_r2"
    assert toolset.state.exposure_condition == "neutral"
    assert toolset.state.assignment_randomized is False
    assert toolset.state.assignment_status == "fixed_neutral_nonprimary"
    assert toolset.state.phase2_presentation_order == toolset.state.secondary_phase2_order
    assert toolset.state.eligible_index is None
    assert toolset.state.exposure_text == NEUTRAL_PREDECESSOR_SENTENCE


@pytest.mark.asyncio
async def test_r2_stays_inert_until_env_activation_then_uses_fresh_draws(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def draw(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
        return 0.1, f"fixture:{namespace}"

    monkeypatch.setattr(
        "cross_rollout_postcommitment_evidence_interface_balanced_v1.servers.facility.randomness.draw_uniform",
        draw,
    )
    toolset = toolset_with_state(
        profile="policy_1_fit",
        assignment_path=str(tmp_path / "assignments.json"),
    )
    ensure_assignment_state(toolset.state.assignment_state_path, "fixture-assignment-seed")
    await toolset.select_policy("K")
    await toolset.release_resource()
    assert toolset.state.phase == "awaiting_r2"
    before = (
        toolset.state.phase,
        toolset.state.phase2_policy,
        toolset.state.r2_activated,
        toolset.state.turn2_sent_count,
        toolset.state.exposure_delivered,
    )
    assert await toolset.select_policy("M") == NO_RESOURCE_RESULT
    assert await toolset.release_resource() == NO_RESOURCE_RESULT
    assert (
        toolset.state.phase,
        toolset.state.phase2_policy,
        toolset.state.r2_activated,
        toolset.state.turn2_sent_count,
        toolset.state.exposure_delivered,
    ) == before
    assert toolset.state.interstage_call_count == 2

    activate_r2(toolset.state)
    toolset.state.turn2_message = phase2_prompt(
        toolset.state.phase2_presentation_order, toolset.state.exposure_condition
    )
    toolset.state.turn2_sent_count = 1
    toolset.state.exposure_delivered = True
    assert await toolset.select_policy("K") == (
        "Policy K selected for R2. Call release_resource to execute it."
    )
    assert toolset.state.phase2_policy == "K"
    assert "r2_acquisition" not in toolset.state.random_draws
    result = await toolset.release_resource()
    assert result.startswith("Policy K ")
    assert toolset.state.phase == "complete"
    assert {"r2_acquisition", "r2_verification"} <= toolset.state.random_draws.keys()


class FakeInteraction(AbstractAsyncContextManager):
    def __init__(self, state: BalancedState, natural: bool = True) -> None:
        self.trace = SimpleNamespace(state=state, stop_condition=None)
        self.natural = natural
        self.messages: list[str | None] = []
        self.state_objects: list[BalancedState] = []

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
async def test_env_sends_one_turn2_after_natural_yield_and_preserves_state(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def draw(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
        return 0.1, f"fixture:{namespace}"

    monkeypatch.setattr(
        "cross_rollout_postcommitment_evidence_interface_balanced_v1.servers.facility.randomness.draw_uniform",
        draw,
    )
    toolset = toolset_with_state(
        profile="policy_1_fit",
        assignment_path=str(tmp_path / "assignments.json"),
    )
    ensure_assignment_state(toolset.state.assignment_state_path, "fixture-assignment-seed")
    await toolset.select_policy("K")
    await toolset.release_resource()
    state = toolset.state
    interaction = FakeInteraction(state)
    env = object.__new__(CrossRolloutPostcommitmentEvidenceInterfaceBalancedV1Env)
    await env.run(SimpleNamespace(), SimpleNamespace(agent=FakeAgent(interaction)))

    expected = phase2_prompt(state.phase2_presentation_order, state.exposure_condition)
    assert interaction.messages == [None, expected]
    assert interaction.state_objects == [state, state]
    assert state.natural_yield_after_r1
    assert state.r2_activated
    assert state.turn2_sent_count == 1
    assert state.turn2_message == expected
    assert state.events[-2].kind == "exposure"
    assert state.events[-1].kind == "env_turn2"

    stopped = toolset_with_state(
        phase="awaiting_r2", assignment_path=str(tmp_path / "stopped.json")
    )
    stopped.state.exposure_condition = "neutral"
    stopped.state.phase2_presentation_order = "K_first"
    stopped.state.assignment_status = "fixed_neutral_nonprimary"
    stopped_interaction = FakeInteraction(stopped.state, natural=False)
    await env.run(SimpleNamespace(), SimpleNamespace(agent=FakeAgent(stopped_interaction)))
    assert stopped_interaction.messages == [None]
    assert not stopped.state.r2_activated
    assert stopped.state.turn2_sent_count == 0


@pytest.mark.asyncio
async def test_null_resume_preserves_entire_r1_transcript_and_state(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def draw(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
        return 0.1, f"fixture:{namespace}"

    monkeypatch.setattr(
        "cross_rollout_postcommitment_evidence_interface_balanced_v1.servers.facility.randomness.draw_uniform",
        draw,
    )
    config = BalancedConfig(assignment_state_path=str(tmp_path / "assignments.json"))
    task = CrossRolloutPostcommitmentEvidenceInterfaceBalancedV1Taskset(config).load()[0]
    trace = vf.Trace(
        task=vf.TraceTask(type="BalancedTask", data=task.data),
        agent=vf.AgentInfo(config=vf.AgentConfig(model="model-free")),
        state=BalancedState(),
    )
    await task.setup(trace, runtime=None)
    toolset = BalancedToolset(BalancedToolsetConfig())
    toolset._inert_state = trace.state
    await toolset.select_policy("K")
    r1_result_text = await toolset.release_resource()
    phase2_message = phase2_prompt(
        trace.state.phase2_presentation_order, trace.state.exposure_condition
    )
    prior = [
        vf.UserMessage(content=task.data.prompt),
        vf.AssistantMessage(
            tool_calls=[
                vf.ToolCall(
                    id="select-k",
                    name="facility_select_policy",
                    arguments='{"policy":"K"}',
                )
            ]
        ),
        vf.ToolMessage(
            tool_call_id="select-k",
            name="facility_select_policy",
            content="Policy K selected for R1. Call release_resource to execute it.",
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
            content=r1_result_text,
        ),
        vf.AssistantMessage(content="R1 evidence received."),
    ]
    trace.nodes = [
        vf.MessageNode(parent=index - 1 if index else None, message=message)
        for index, message in enumerate(prior)
    ]
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
        isinstance(message, vf.ToolMessage) and message.content == r1_result_text
        for message in capture.resumed_prompt
    )
    assert any(
        isinstance(message, vf.AssistantMessage)
        and message.content == "R1 evidence received."
        for message in capture.resumed_prompt
    )
    assert trace.state is state_object


@pytest.mark.asyncio
async def test_primary_missing_r2_is_not_scored_as_non_switch(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def draw(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
        return 0.1, f"fixture:{namespace}"

    monkeypatch.setattr(
        "cross_rollout_postcommitment_evidence_interface_balanced_v1.servers.facility.randomness.draw_uniform",
        draw,
    )
    config = BalancedConfig(assignment_state_path=str(tmp_path / "assignments.json"))
    task = CrossRolloutPostcommitmentEvidenceInterfaceBalancedV1Taskset(config).load()[0]
    trace = vf.Trace(
        task=vf.TraceTask(type="BalancedTask", data=task.data),
        agent=vf.AgentInfo(config=vf.AgentConfig(model="model-free")),
        state=BalancedState(),
    )
    await task.setup(trace, runtime=None)
    toolset = BalancedToolset(BalancedToolsetConfig())
    toolset._inert_state = trace.state
    await toolset.select_policy("K")
    await toolset.release_resource()
    trace.stop_condition = "turn_limit"
    await task.finalize(trace, runtime=None)

    info = trace.info["evidence_interface_balanced"]
    assert info["primary_eligible"]
    assert info["phase2_missing"]
    assert info["primary_choice_observed"] is False
    assert info["primary_itt_switch"] is False
    assert info["primary_itt_not_switch"] is True
    assert await task.primary_itt_switch(trace) == 0.0
    assert await task.primary_itt_not_switch(trace) == 1.0
    assert await task.primary_choice_observed(trace) == 0.0


@pytest.mark.asyncio
async def test_primary_choice_without_release_is_recorded_but_itt_is_not_switch(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def draw(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
        return 0.1, f"fixture:{namespace}"

    monkeypatch.setattr(
        "cross_rollout_postcommitment_evidence_interface_balanced_v1.servers.facility.randomness.draw_uniform",
        draw,
    )
    config = BalancedConfig(assignment_state_path=str(tmp_path / "assignments.json"))
    task = CrossRolloutPostcommitmentEvidenceInterfaceBalancedV1Taskset(config).load()[0]
    trace = vf.Trace(
        task=vf.TraceTask(type="BalancedTask", data=task.data),
        agent=vf.AgentInfo(config=vf.AgentConfig(model="model-free")),
        state=BalancedState(),
    )
    await task.setup(trace, runtime=None)
    toolset = BalancedToolset(BalancedToolsetConfig())
    toolset._inert_state = trace.state
    await toolset.select_policy("K")
    await toolset.release_resource()
    activate_r2(trace.state)
    await toolset.select_policy("M")
    await task.finalize(trace, runtime=None)

    info = trace.info["evidence_interface_balanced"]
    assert info["phase2_incomplete_after_choice"]
    assert info["phase2_policy"] == "M"
    assert info["transition"] == "K→M"
    assert info["primary_switch"] is True
    assert info["primary_itt_switch"] is False
    assert info["primary_itt_not_switch"] is True
    assert info["primary_choice_observed"] is True


@pytest.mark.asyncio
async def test_invalid_r2_release_is_recorded_as_missing(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def draw(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
        return 0.1, f"fixture:{namespace}"

    monkeypatch.setattr(
        "cross_rollout_postcommitment_evidence_interface_balanced_v1.servers.facility.randomness.draw_uniform",
        draw,
    )
    config = BalancedConfig(assignment_state_path=str(tmp_path / "assignments.json"))
    task = CrossRolloutPostcommitmentEvidenceInterfaceBalancedV1Taskset(config).load()[0]
    trace = vf.Trace(
        task=vf.TraceTask(type="BalancedTask", data=task.data),
        agent=vf.AgentInfo(config=vf.AgentConfig(model="model-free")),
        state=BalancedState(),
    )
    await task.setup(trace, runtime=None)
    toolset = BalancedToolset(BalancedToolsetConfig())
    toolset._inert_state = trace.state
    await toolset.select_policy("K")
    await toolset.release_resource()
    activate_r2(trace.state)
    await toolset.select_policy("invalid")
    await toolset.release_resource()
    await task.finalize(trace, runtime=None)

    info = trace.info["evidence_interface_balanced"]
    assert info["phase2_missing"]
    assert info["phase2_policy"] is None
    assert info["stop_reason"] == "r2_missing"
    assert info["primary_itt_switch"] is False
    assert info["primary_itt_not_switch"] is True


def test_segment_natural_yield_requires_non_tool_assistant_reply() -> None:
    natural = vf.Segment(messages=[vf.AssistantMessage(content="done")])
    tool_reply = vf.Segment(
        messages=[vf.AssistantMessage(tool_calls=[vf.ToolCall(id="x", name="tool", arguments="{}")])]
    )
    trace = SimpleNamespace(stop_condition=None)
    assert segment_ended_naturally(natural, trace)
    assert not segment_ended_naturally(tool_reply, trace)


@pytest.mark.asyncio
async def test_invalid_first_policy_cannot_be_reinterpreted_as_primary() -> None:
    toolset = toolset_with_state()
    result = await toolset.select_policy("not-a-policy")
    assert "invalid" in result.lower()
    retry = await toolset.select_policy("K")
    assert "first R1" in retry
    closed = await toolset.release_resource()
    assert "invalid first" in closed
    assert toolset.state.phase == "complete"
    assert not toolset.state.primary_eligible


@pytest.mark.asyncio
async def test_awaiting_r2_is_inert_until_environment_activation() -> None:
    toolset = toolset_with_state(phase="awaiting_r2")
    assert await toolset.select_policy("K") == (
        "R1 is complete. No resource is currently available."
    )
    assert await toolset.release_resource() == (
        "R1 is complete. No resource is currently available."
    )
    assert toolset.state.phase2_policy is None
    assert toolset.state.interstage_call_count == 2
    activate_r2(toolset.state)
    assert toolset.state.phase == "phase2"


def test_blocked_assignment_has_exact_four_cell_balance_per_block(tmp_path) -> None:
    path = str(tmp_path / "assignments.json")
    ensure_assignment_state(path, "assignment-seed")
    assignments = [
        claim_assignment(path, "assignment-seed")
        for _ in range(MAX_PRIMARY_ELIGIBLE)
    ]
    assert len(assignments) == TARGET_PRIMARY_ELIGIBLE
    for block in range(16):
        cells = {
            (item.condition, item.phase2_order)
            for item in assignments[block * 4 : block * 4 + 4]
        }
        assert cells == {
            ("neutral", "K_first"),
            ("neutral", "M_first"),
            ("opposing_convention", "K_first"),
            ("opposing_convention", "M_first"),
        }
    assert assignment_for_index("assignment-seed", 0) == assignment_for_index(
        "assignment-seed", 0
    )


def test_no_custom_harness_or_r2_in_environment_config() -> None:
    env_config = BalancedEnvConfig()
    assert env_config.agent.harness.id == "null"
    assert not hasattr(env_config, "user")
    assert MAX_ATTEMPTS == 240
    assert TARGET_PRIMARY_ELIGIBLE == 64
