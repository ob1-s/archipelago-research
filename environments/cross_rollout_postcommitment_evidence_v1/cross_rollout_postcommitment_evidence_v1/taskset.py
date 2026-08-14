"""Native two-turn evidence-based post-commitment taskset."""

from __future__ import annotations

from typing import Literal

import verifiers.v1 as vf
from verifiers.v1.harnesses.null import NullHarnessConfig

from cross_rollout_postcommitment_evidence_v1 import randomness
from cross_rollout_postcommitment_evidence_v1.servers.facility import (
    CULTURE_A_NOTICE,
    NEUTRAL_NOTICE,
    EvidenceToolset,
    EvidenceToolsetConfig,
)
from cross_rollout_postcommitment_evidence_v1.state import (
    AssignmentMode,
    DrawRecord,
    EvidenceState,
    ExposureCondition,
    PresentationOrder,
    record_event,
)

TURN_2_MESSAGE_BY_ORDER_AND_CONDITION: dict[
    tuple[PresentationOrder, ExposureCondition], str
] = {
    (
        "A_first",
        "neutral",
    ): (
        "A new resource R2 from the same batch is available. "
        f"{NEUTRAL_NOTICE} Using the batch information and evidence available to you, "
        'choose one policy with select_policy(policy="A" or "B") and then '
        "call release_resource()."
    ),
    (
        "B_first",
        "neutral",
    ): (
        "A new resource R2 from the same batch is available. "
        f"{NEUTRAL_NOTICE} Using the batch information and evidence available to you, "
        'choose one policy with select_policy(policy="B" or "A") and then '
        "call release_resource()."
    ),
    (
        "A_first",
        "culture-A",
    ): (
        "A new resource R2 from the same batch is available. "
        f"{CULTURE_A_NOTICE} Using the batch information and evidence available to you, "
        'choose one policy with select_policy(policy="A" or "B") and then '
        "call release_resource()."
    ),
    (
        "B_first",
        "culture-A",
    ): (
        "A new resource R2 from the same batch is available. "
        f"{CULTURE_A_NOTICE} Using the batch information and evidence available to you, "
        'choose one policy with select_policy(policy="B" or "A") and then '
        "call release_resource()."
    ),
}


def prompt_for_phase1_order(_: Literal["B_first"] = "B_first") -> str:
    """Return the frozen B-first R1 instruction."""

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
    phase2_order: PresentationOrder, condition: ExposureCondition = "neutral"
) -> str:
    return TURN_2_MESSAGE_BY_ORDER_AND_CONDITION[(phase2_order, condition)]


def activate_r2(state: EvidenceState) -> None:
    """The only transition that makes R2 available to model-visible tools."""

    if state.phase != "awaiting_r2":
        raise RuntimeError("R2 activation requires the awaiting_r2 state")
    if not state.phase1_success or state.phase1_policy not in ("A", "B"):
        raise RuntimeError("R2 activation requires successful Phase-1 acquisition")
    if state.r2_activated:
        raise RuntimeError("R2 has already been activated")
    assignment = state.exposure_condition
    state.r2_activated = True
    state.phase = "phase2"
    record_event(
        state,
        "env_activate_r2",
        "activate_r2",
        "Resource R2 activated by environment control flow.",
        post_randomization=state.assignment_randomized,
    )
    if state.exposure_condition != assignment:
        raise RuntimeError("R2 activation changed assigned condition")


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


class EvidenceTaskData(vf.TaskData):
    assignment_mode: AssignmentMode
    random_seed: str
    phase1_presentation_order: Literal["B_first"]
    phase2_presentation_order: PresentationOrder


class EvidenceTaskConfig(vf.TaskConfig):
    tools: EvidenceToolsetConfig = EvidenceToolsetConfig()


class EvidenceTask(
    vf.Task[EvidenceTaskData, EvidenceState, EvidenceTaskConfig]
):
    @classmethod
    def toolsets(cls, config: EvidenceTaskConfig) -> list[vf.Toolset]:
        return [EvidenceToolset(config.tools)]

    async def setup(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        state = trace.state
        state.rollout_id = trace.id
        state.random_seed = self.data.random_seed
        state.assignment_mode = self.data.assignment_mode
        state.phase1_presentation_order = self.data.phase1_presentation_order
        state.phase2_presentation_order = self.data.phase2_presentation_order
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
        trace.info["evidence_postcommitment"] = {
            "random_seed": self.data.random_seed,
            "random_namespaces": list(randomness.RANDOM_NAMESPACES),
            "frozen_profile_prior": {"A_fit": 0.5, "B_fit": 0.5},
            "phase1_presentation_order": self.data.phase1_presentation_order,
            "phase2_presentation_order": self.data.phase2_presentation_order,
            "assignment_mode": self.data.assignment_mode,
            "assignment_stage": "after_phase1_evidence",
            "assigned_condition": None,
            "exposure_delivered": False,
            "turn2_messages_frozen": {
                condition: prompt_for_phase2_order(
                    self.data.phase2_presentation_order, condition
                )
                for condition in ("neutral", "culture-A")
            },
        }

    async def finalize(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        state = trace.state
        if state.eligibility == "pending_phase1" and not state.phase1_success:
            state.eligibility = "phase1_not_successful"
        events = [event.model_dump(mode="json") for event in state.events]
        transition = (
            f"{state.phase1_policy}→{state.phase2_policy}"
            if state.phase1_policy is not None and state.phase2_policy is not None
            else None
        )
        info = trace.info["evidence_postcommitment"]
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
                "phase2_missing": state.phase1_success and state.phase2_policy is None,
                "phase2_incomplete_after_choice": (
                    state.phase1_success
                    and state.phase2_policy is not None
                    and not state.phase2_success
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
        """Reward protocol completion separately from stochastic resource success."""

        state = trace.state
        return float(
            state.phase1_success
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
    async def r1_evidence_b_success_pass(self, trace: vf.Trace) -> float:
        return float(trace.state.evidence_class == "B_success_pass")

    @vf.metric
    async def r1_evidence_b_success_fail(self, trace: vf.Trace) -> float:
        return float(trace.state.evidence_class == "B_success_fail")

    @vf.metric
    async def r2_policy_a(self, trace: vf.Trace) -> float:
        return float(trace.state.phase1_success and trace.state.phase2_policy == "A")

    @vf.metric
    async def r2_policy_b(self, trace: vf.Trace) -> float:
        return float(trace.state.phase1_success and trace.state.phase2_policy == "B")

    @vf.metric
    async def r2_acquisition(self, trace: vf.Trace) -> float:
        return float(trace.state.phase1_success and trace.state.phase2_acquisition_success)

    @vf.metric
    async def r2_verification(self, trace: vf.Trace) -> float:
        return float(trace.state.phase1_success and trace.state.phase2_verification_pass)

    @vf.metric
    async def evidence_aligned_r2_policy(self, trace: vf.Trace) -> float:
        return float(
            trace.state.phase1_success
            and trace.state.phase2_policy is not None
            and trace.state.phase2_policy == trace.state.evidence_preferred_policy
        )

    @vf.metric
    async def primary_b_to_a(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_eligible and trace.state.phase2_policy == "A")

    @vf.metric
    async def primary_b_to_b(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_eligible and trace.state.phase2_policy == "B")

    @vf.metric
    async def phase2_missing(self, trace: vf.Trace) -> float:
        return float(trace.state.phase1_success and trace.state.phase2_policy is None)

    @vf.metric
    async def phase2_incomplete_after_choice(self, trace: vf.Trace) -> float:
        return float(
            trace.state.phase1_success
            and trace.state.phase2_policy is not None
            and not trace.state.phase2_success
        )


class EvidenceConfig(vf.TasksetConfig):
    assignment_mode: AssignmentMode = "post_b_success_random"
    random_seed: str = "cross-rollout-postcommitment-evidence-v1"
    task: EvidenceTaskConfig = EvidenceTaskConfig()


class CrossRolloutPostcommitmentEvidenceV1Taskset(
    vf.Taskset[EvidenceTask, EvidenceConfig]
):
    def load(self) -> list[EvidenceTask]:
        return [
            EvidenceTask(
                EvidenceTaskData(
                    idx=index,
                    name=(
                        "evidence-postcommitment-policy-facility-B_first-"
                        f"{phase2_order}"
                    ),
                    prompt=prompt_for_phase1_order(),
                    assignment_mode=self.config.assignment_mode,
                    random_seed=self.config.random_seed,
                    phase1_presentation_order="B_first",
                    phase2_presentation_order=phase2_order,
                ),
                self.config.task,
            )
            for index, phase2_order in enumerate(("A_first", "B_first"))
        ]


class EvidenceEnvConfig(vf.EnvConfig):
    """One evaluated agent pinned to the built-in null harness."""

    agent: vf.AgentConfig = vf.AgentConfig(
        harness=NullHarnessConfig(id="null"),
        max_turns=14,
    )


class CrossRolloutPostcommitmentEvidenceV1Env(vf.Env[EvidenceEnvConfig]):
    """Run R1 to natural yield, then Env-activate exactly one R2 turn."""

    async def run(self, task: EvidenceTask, agents: vf.Agents) -> None:
        async with agents.agent.interaction(task) as interaction:
            phase1_segment = await interaction.turn()
            state = interaction.trace.state
            state.natural_yield_after_r1 = segment_ended_naturally(
                phase1_segment, interaction.trace
            )
            if not state.natural_yield_after_r1:
                return
            if not state.phase1_success or state.phase != "awaiting_r2":
                return

            condition = state.exposure_condition
            if condition is None:
                raise RuntimeError("successful R1 reached resume without assignment")
            activate_r2(state)
            if state.exposure_condition != condition:
                raise RuntimeError("environment activation changed assigned condition")
            if state.turn2_sent_count != 0:
                raise RuntimeError("Turn 2 was already sent")
            state.turn2_sent_count += 1
            state.turn2_message = prompt_for_phase2_order(
                state.phase2_presentation_order, condition
            )
            state.exposure_delivered = True
            exposure_event = record_event(
                state,
                "exposure",
                "turn2_predecessor_notice",
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
    "CrossRolloutPostcommitmentEvidenceV1Env",
    "CrossRolloutPostcommitmentEvidenceV1Taskset",
]
