"""Native randomized evidence-relative post-commitment taskset."""

from __future__ import annotations

from typing import Literal

import verifiers.v1 as vf
from verifiers.v1.harnesses.null import NullHarnessConfig

from cross_rollout_postcommitment_evidence_relative_v1 import assignment, randomness
from cross_rollout_postcommitment_evidence_relative_v1.servers.facility import (
    RelativeToolset,
    RelativeToolsetConfig,
    predecessor_sentence,
)
from cross_rollout_postcommitment_evidence_relative_v1.state import (
    DrawRecord,
    ExposureCondition,
    Policy,
    PresentationOrder,
    RelativeState,
    record_event,
)

NEUTRAL_CONDITION: ExposureCondition = "neutral"
OPPOSING_CONDITION: ExposureCondition = "opposing_convention"


def prompt_for_phase1_order(_: Literal["B_first"] = "B_first") -> str:
    """Return the validated, frozen evidence-v1 Phase-1 instruction."""

    return (
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


def prompt_for_phase2_order(
    phase2_order: PresentationOrder,
    condition: ExposureCondition,
    evidence_policy: Policy,
) -> str:
    """Return one frozen Turn-2 message for the assigned policy origin/cell."""

    first, second = (
        ("A", "B") if phase2_order == "A_first" else ("B", "A")
    )
    sentence = predecessor_sentence(condition, evidence_policy)
    return (
        "A new resource R2 from the same batch is available. "
        f"{sentence} Using the batch information and evidence available to you, "
        f'choose one policy with select_policy(policy="{first}" or "{second}") '
        "and then call release_resource()."
    )


def activate_r2(state: RelativeState) -> None:
    """The only transition that makes R2 available to model-visible tools."""

    if state.phase != "awaiting_r2":
        raise RuntimeError("R2 activation requires the awaiting_r2 state")
    if not state.primary_eligible or state.phase1_policy not in ("A", "B"):
        raise RuntimeError("R2 activation requires primary eligibility")
    if state.exposure_condition is None or state.phase2_presentation_order is None:
        raise RuntimeError("R2 activation requires a complete deferred assignment")
    if state.r2_activated:
        raise RuntimeError("R2 has already been activated")
    assigned = (state.exposure_condition, state.phase2_presentation_order)
    state.r2_activated = True
    state.phase = "phase2"
    record_event(
        state,
        "env_activate_r2",
        "activate_r2",
        "Resource R2 activated by environment control flow.",
        post_randomization=state.assignment_randomized,
    )
    if (state.exposure_condition, state.phase2_presentation_order) != assigned:
        raise RuntimeError("R2 activation changed the assigned condition or order")


def segment_ended_naturally(segment: vf.Segment, trace: vf.Trace) -> bool:
    """Return true only after a normal final non-tool assistant message."""

    if segment.terminated or trace.stop_condition is not None:
        return False
    last_assistant = next(
        (
            message
            for message in reversed(segment.messages)
            if isinstance(message, vf.AssistantMessage)
        ),
        None,
    )
    return last_assistant is not None and not last_assistant.tool_calls


class RelativeTaskData(vf.TaskData):
    assignment_mode: Literal["relative_randomized"]
    random_seed: str
    assignment_seed: str
    assignment_state_path: str
    phase1_presentation_order: Literal["B_first"]


class RelativeTaskConfig(vf.TaskConfig):
    tools: RelativeToolsetConfig = RelativeToolsetConfig()


class RelativeTask(
    vf.Task[RelativeTaskData, RelativeState, RelativeTaskConfig]
):
    @classmethod
    def toolsets(cls, config: RelativeTaskConfig) -> list[vf.Toolset]:
        return [RelativeToolset(config.tools)]

    async def setup(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        state = trace.state
        state.rollout_id = trace.id
        state.random_seed = self.data.random_seed
        state.assignment_seed = self.data.assignment_seed
        state.assignment_state_path = self.data.assignment_state_path
        state.phase1_presentation_order = self.data.phase1_presentation_order
        assignment.ensure_assignment_state(
            self.data.assignment_state_path, self.data.assignment_seed
        )
        profile, value, key = randomness.hidden_profile(
            self.data.random_seed, trace.id
        )
        state.hidden_profile = profile
        state.random_draws["hidden_profile"] = DrawRecord(
            namespace="hidden_profile",
            key=key,
            value=value,
            threshold=None,
            outcome=profile,
            matched_profile=None,
        )
        trace.info["evidence_relative_postcommitment"] = {
            "random_seed": self.data.random_seed,
            "assignment_seed": self.data.assignment_seed,
            "assignment_state_path": self.data.assignment_state_path,
            "random_namespaces": list(randomness.RANDOM_NAMESPACES),
            "assignment_namespaces": list(assignment.ASSIGNMENT_NAMESPACES),
            "frozen_profile_prior": {"A_fit": 0.5, "B_fit": 0.5},
            "phase1_presentation_order": self.data.phase1_presentation_order,
            "phase2_presentation_order": None,
            "assignment_mode": self.data.assignment_mode,
            "assignment_stage": "after_primary_evidence",
            "assigned_condition": None,
            "exposure_delivered": False,
            "stopping_rule": "64 primary eligible or 240 total rollouts or apparatus failure",
            "predecessor_sentences": {
                "neutral": predecessor_sentence("neutral", "A"),
                "opposing_if_A_origin": predecessor_sentence(
                    "opposing_convention", "A"
                ),
                "opposing_if_B_origin": predecessor_sentence(
                    "opposing_convention", "B"
                ),
            },
        }

    async def finalize(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        state = trace.state
        if state.eligibility == "pending_phase1":
            state.eligibility = (
                "phase1_not_successful"
                if not state.phase1_success
                else "nonprimary_success_verification_fail"
            )
        if state.primary_eligible:
            state.primary_switch = (
                state.phase2_policy is not None
                and state.phase2_policy != state.evidence_supported_policy
            )
            state.primary_itt_switch = bool(state.primary_switch)
        events = [event.model_dump(mode="json") for event in state.events]
        transition = (
            f"{state.phase1_policy}→{state.phase2_policy}"
            if state.phase1_policy is not None and state.phase2_policy is not None
            else None
        )
        info = trace.info["evidence_relative_postcommitment"]
        info.update(
            {
                "hidden_profile": state.hidden_profile,
                "random_draws": {
                    namespace: draw.model_dump(mode="json")
                    for namespace, draw in state.random_draws.items()
                },
                "events": events,
                "final_phase": state.phase,
                "phase1_policy": state.phase1_policy,
                "phase1_success": state.phase1_success,
                "phase1_acquisition_success": state.phase1_acquisition_success,
                "phase1_verification_pass": state.phase1_verification_pass,
                "evidence_class": state.evidence_class,
                "evidence_supported_policy": state.evidence_supported_policy,
                "alternative_policy": state.alternative_policy,
                "evidence_likelihood_ratio_b_over_a": (
                    state.evidence_likelihood_ratio_b_over_a
                ),
                "evidence_posterior_b_fit": state.evidence_posterior_b_fit,
                "expected_r2_a_acquisition": state.expected_r2_a_acquisition,
                "expected_r2_b_acquisition": state.expected_r2_b_acquisition,
                "evidence_preferred_policy": state.evidence_preferred_policy,
                "eligibility": state.eligibility,
                "primary_eligible": state.primary_eligible,
                "eligibility_event_index": state.eligibility_event_index,
                "assignment_pending": state.assignment_pending,
                "assignment_status": state.assignment_status,
                "assignment_randomized": state.assignment_randomized,
                "assignment_event_index": state.assignment_event_index,
                "assignment_key": state.assignment_key or None,
                "eligible_index": state.eligible_index,
                "assignment_block_index": state.assignment_block_index,
                "assignment_slot": state.assignment_slot,
                "assigned_condition": state.exposure_condition,
                "exposure_text": state.exposure_text,
                "exposure_delivered": state.exposure_delivered,
                "exposure_event_index": state.exposure_event_index,
                "phase2_presentation_order": state.phase2_presentation_order,
                "r2_activated": state.r2_activated,
                "turn2_sent_count": state.turn2_sent_count,
                "turn2_message": state.turn2_message or None,
                "natural_yield_after_r1": state.natural_yield_after_r1,
                "interstage_call_count": state.interstage_call_count,
                "interstage_events": [
                    event for event in events if event["kind"] == "interstage"
                ],
                "phase2_policy": state.phase2_policy,
                "phase2_release_attempted": state.phase2_release_attempted,
                "phase2_success": state.phase2_success,
                "phase2_acquisition_success": state.phase2_acquisition_success,
                "phase2_verification_pass": state.phase2_verification_pass,
                "phase2_missing": (
                    state.primary_eligible and state.phase2_policy is None
                ),
                "phase2_incomplete_after_choice": (
                    state.primary_eligible
                    and state.phase2_policy is not None
                    and not state.phase2_release_attempted
                ),
                "primary_switch": state.primary_switch,
                "primary_itt_switch": state.primary_itt_switch,
                "primary_itt_not_switch": (
                    state.primary_eligible and not state.primary_itt_switch
                ),
                "transition": transition,
                "first_failure_index": state.first_failure_index,
                "failure_events": [event for event in events if event["failure"]],
                "selection_ambiguity": state.selection_ambiguity,
                "policy_selection_attempts": state.policy_selection_attempts,
                "stop_condition": trace.stop_condition,
            }
        )

    @vf.reward
    async def protocol_completion(self, trace: vf.Trace) -> float:
        state = trace.state
        return float(
            state.primary_eligible
            and state.r2_activated
            and state.phase2_policy is not None
            and state.phase2_release_attempted
        )

    @vf.metric
    async def r1_acquisition(self, trace: vf.Trace) -> float:
        return float(trace.state.phase1_acquisition_success)

    @vf.metric
    async def r1_verification(self, trace: vf.Trace) -> float:
        return float(trace.state.phase1_verification_pass)

    @vf.metric
    async def primary_eligible(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_eligible)

    @vf.metric
    async def primary_itt_switch(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_itt_switch)

    @vf.metric
    async def primary_itt_not_switch(self, trace: vf.Trace) -> float:
        return float(
            trace.state.primary_eligible and not trace.state.primary_itt_switch
        )

    @vf.metric
    async def phase2_missing(self, trace: vf.Trace) -> float:
        return float(
            trace.state.primary_eligible and trace.state.phase2_policy is None
        )

    @vf.metric
    async def phase2_incomplete_after_choice(self, trace: vf.Trace) -> float:
        return float(
            trace.state.primary_eligible
            and trace.state.phase2_policy is not None
            and not trace.state.phase2_release_attempted
        )

    @vf.metric
    async def r2_policy_a(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_eligible and trace.state.phase2_policy == "A")

    @vf.metric
    async def r2_policy_b(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_eligible and trace.state.phase2_policy == "B")


class RelativeConfig(vf.TasksetConfig):
    assignment_mode: Literal["relative_randomized"] = "relative_randomized"
    random_seed: str = "cross-rollout-postcommitment-evidence-relative-v1"
    assignment_seed: str = "cross-rollout-postcommitment-evidence-relative-v1-blocks"
    assignment_state_path: str = (
        "/tmp/cross-rollout-postcommitment-evidence-relative-v1-assignments.json"
    )
    task: RelativeTaskConfig = RelativeTaskConfig()


class CrossRolloutPostcommitmentEvidenceRelativeV1Taskset(
    vf.Taskset[RelativeTask, RelativeConfig]
):
    def load(self) -> list[RelativeTask]:
        return [
            RelativeTask(
                RelativeTaskData(
                    idx=0,
                    name="evidence-relative-postcommitment-policy-facility-B_first",
                    prompt=prompt_for_phase1_order(),
                    assignment_mode=self.config.assignment_mode,
                    random_seed=self.config.random_seed,
                    assignment_seed=self.config.assignment_seed,
                    assignment_state_path=self.config.assignment_state_path,
                    phase1_presentation_order="B_first",
                ),
                self.config.task,
            )
        ]


class RelativeEnvConfig(vf.EnvConfig):
    """One evaluated agent pinned to the built-in null harness."""

    agent: vf.AgentConfig = vf.AgentConfig(
        harness=NullHarnessConfig(id="null"),
        max_turns=14,
    )


class CrossRolloutPostcommitmentEvidenceRelativeV1Env(
    vf.Env[RelativeEnvConfig]
):
    """Run primary-eligible R1 trajectories through one native R2 turn."""

    async def run(self, task: RelativeTask, agents: vf.Agents) -> None:
        async with agents.agent.interaction(task) as interaction:
            phase1_segment = await interaction.turn()
            state = interaction.trace.state
            state.natural_yield_after_r1 = segment_ended_naturally(
                phase1_segment, interaction.trace
            )
            if not state.natural_yield_after_r1:
                return
            if not state.primary_eligible or state.phase != "awaiting_r2":
                return
            if state.exposure_condition is None:
                raise RuntimeError("primary eligible R1 reached resume without assignment")
            if state.phase2_presentation_order is None:
                raise RuntimeError("primary eligible R1 reached resume without Phase-2 order")
            assigned = (state.exposure_condition, state.phase2_presentation_order)
            activate_r2(state)
            if (state.exposure_condition, state.phase2_presentation_order) != assigned:
                raise RuntimeError("environment activation changed assignment")
            if state.turn2_sent_count != 0:
                raise RuntimeError("Turn 2 was already sent")
            state.turn2_sent_count += 1
            state.turn2_message = prompt_for_phase2_order(
                state.phase2_presentation_order,
                state.exposure_condition,
                state.evidence_supported_policy,
            )
            state.exposure_delivered = True
            exposure_event = record_event(
                state,
                "exposure",
                "turn2_predecessor_history",
                state.exposure_text,
                post_randomization=state.assignment_randomized,
            )
            state.exposure_event_index = exposure_event.index
            turn2_event = record_event(
                state,
                "env_turn2",
                "user",
                state.turn2_message,
                post_randomization=state.assignment_randomized,
            )
            if turn2_event.index != exposure_event.index + 1:
                raise RuntimeError("Turn-2 exposure/message event ordering changed")
            await interaction.turn(state.turn2_message)


__all__ = [
    "CrossRolloutPostcommitmentEvidenceRelativeV1Env",
    "CrossRolloutPostcommitmentEvidenceRelativeV1Taskset",
]
