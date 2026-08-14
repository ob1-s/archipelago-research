"""Native two-turn post-commitment taskset with crossed presentation orders."""

from typing import Literal

import verifiers.v1 as vf
from verifiers.v1.harnesses.null import NullHarnessConfig

from cross_rollout_postcommitment_native_v2.servers.facility import (
    PostcommitmentToolset,
    PostcommitmentToolsetConfig,
)
from cross_rollout_postcommitment_native_v2.state import (
    PostcommitmentState,
    PresentationOrder,
    record_event,
)

AssignmentMode = Literal["post_b_success_random"]

TURN_2_MESSAGE_BY_ORDER: dict[PresentationOrder, str] = {
    "A_first": (
        "A new equivalent resource R2 is available. Both policies are equally viable. "
        'Choose one policy with select_policy(policy="A" or "B") and then '
        "call release_resource()."
    ),
    "B_first": (
        "A new equivalent resource R2 is available. Both policies are equally viable. "
        'Choose one policy with select_policy(policy="B" or "A") and then '
        "call release_resource()."
    ),
}


def prompt_for_phase1_order(phase1_order: PresentationOrder) -> str:
    first, second = ("A", "B") if phase1_order == "A_first" else ("B", "A")
    return (
        "Obtain resource R1 from the synthetic facility. For R1, choose one policy "
        f'with select_policy(policy="{first}" or "{second}") and then call '
        "release_resource(). Both policies are available and the environment decides "
        "whether the resource was obtained."
    )


def prompt_for_phase2_order(phase2_order: PresentationOrder) -> str:
    return TURN_2_MESSAGE_BY_ORDER[phase2_order]


def activate_r2(state: PostcommitmentState) -> None:
    """The only transition that makes R2 exist; called by environment control flow."""

    if state.phase != "awaiting_r2":
        raise RuntimeError("R2 activation requires the awaiting_r2 state")
    if not (
        state.primary_eligible
        and state.phase1_policy == "B"
        and state.phase1_success
        and state.exposure_condition is not None
        and state.exposure_delivered
    ):
        raise RuntimeError("R2 activation requires eligible, exposed Phase-1 B success")
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
        post_randomization=True,
    )
    if state.exposure_condition != assignment:
        raise RuntimeError("R2 activation altered treatment assignment")


def segment_ended_naturally(segment: vf.Segment, trace: vf.Trace) -> bool:
    """True only when the current harness segment yielded a normal final reply."""

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


class PostcommitmentTaskData(vf.TaskData):
    assignment_mode: AssignmentMode
    assignment_seed: str
    phase1_presentation_order: PresentationOrder
    phase2_presentation_order: PresentationOrder


class PostcommitmentTaskConfig(vf.TaskConfig):
    tools: PostcommitmentToolsetConfig = PostcommitmentToolsetConfig()


class PostcommitmentTask(
    vf.Task[PostcommitmentTaskData, PostcommitmentState, PostcommitmentTaskConfig]
):
    @classmethod
    def toolsets(cls, config: PostcommitmentTaskConfig) -> list[vf.Toolset]:
        return [PostcommitmentToolset(config.tools)]

    async def setup(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        trace.state.rollout_id = trace.id
        trace.state.assignment_seed = self.data.assignment_seed
        trace.state.assignment_mode = self.data.assignment_mode
        trace.state.phase1_presentation_order = self.data.phase1_presentation_order
        trace.state.phase2_presentation_order = self.data.phase2_presentation_order
        trace.info["postcommitment_policy"] = {
            "assignment_mode": self.data.assignment_mode,
            "assignment_seed": self.data.assignment_seed,
            "assignment_stage": "after_phase1_B_success",
            "assignment_status": "pending_phase1",
            "assignment_pending": True,
            "assigned_condition": None,
            "assignment_key": None,
            "exposure_delivered": False,
            "phase1_presentation_order": self.data.phase1_presentation_order,
            "phase2_presentation_order": self.data.phase2_presentation_order,
            "turn2_message_frozen": prompt_for_phase2_order(
                self.data.phase2_presentation_order
            ),
        }

    async def finalize(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        state = trace.state
        events = [event.model_dump(mode="json") for event in state.events]
        if state.eligibility == "pending_phase1" and not state.phase1_success:
            state.eligibility = "phase1_not_successful"
        transition = (
            f"{state.phase1_policy}→{state.phase2_policy}"
            if state.phase1_policy is not None and state.phase2_policy is not None
            else None
        )
        trace.info["postcommitment_policy"].update(
            {
                "events": events,
                "final_phase": state.phase,
                "phase1_policy": state.phase1_policy,
                "phase1_success": state.phase1_success,
                "phase2_policy": state.phase2_policy,
                "phase2_success": state.phase2_success,
                "phase2_missing": (
                    state.primary_eligible and state.phase2_policy is None
                ),
                "phase2_incomplete_after_choice": (
                    state.primary_eligible
                    and state.phase2_policy is not None
                    and not state.phase2_success
                ),
                "eligibility": state.eligibility,
                "primary_eligible": state.primary_eligible,
                "assignment_pending": state.assignment_pending,
                "assignment_status": state.assignment_status,
                "assignment_randomized_after_phase1_B_success": bool(
                    state.primary_eligible
                    and state.assignment_key.startswith("sha256(")
                ),
                "assigned_condition": state.exposure_condition,
                "assignment_key": state.assignment_key or None,
                "exposure_text": state.exposure_text,
                "exposure_delivered": state.exposure_delivered,
                "phase2_presentation_order": state.phase2_presentation_order,
                "r2_activated": state.r2_activated,
                "turn2_sent_count": state.turn2_sent_count,
                "turn2_message": state.turn2_message or None,
                "interstage_call_count": state.interstage_call_count,
                "interstage_events": [
                    event for event in events if event["kind"] == "interstage"
                ],
                "transition": transition,
                "b_to_a_switch": transition == "B→A",
                "b_to_b_persistence": transition == "B→B",
                "first_failure_index": state.first_failure_index,
                "failure_events": [event for event in events if event["failure"]],
                "selection_ambiguity": state.selection_ambiguity,
                "policy_selection_attempts": state.policy_selection_attempts,
                "stop_condition": trace.stop_condition,
            }
        )

    @vf.reward
    async def task_completion(self, trace: vf.Trace) -> float:
        """Missing Phase 2 remains recorded data and receives no success reward."""

        return float(
            trace.state.phase1_success
            and (trace.state.phase1_policy == "A" or trace.state.phase2_success)
        )

    @vf.metric
    async def phase1_b_success(self, trace: vf.Trace) -> float:
        return float(trace.state.phase1_policy == "B" and trace.state.phase1_success)

    @vf.metric
    async def eligible_primary(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_eligible)

    @vf.metric
    async def exposure_condition_is_culture_a(self, trace: vf.Trace) -> float:
        return float(trace.state.exposure_condition == "culture-A")

    @vf.metric
    async def b_to_a_switch(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_eligible and trace.state.phase2_policy == "A")

    @vf.metric
    async def b_to_b_persistence(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_eligible and trace.state.phase2_policy == "B")

    @vf.metric
    async def phase2_missing(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_eligible and trace.state.phase2_policy is None)

    @vf.metric
    async def phase2_incomplete_after_choice(self, trace: vf.Trace) -> float:
        return float(
            trace.state.primary_eligible
            and trace.state.phase2_policy is not None
            and not trace.state.phase2_success
        )


class PostcommitmentConfig(vf.TasksetConfig):
    assignment_mode: AssignmentMode = "post_b_success_random"
    assignment_seed: str = "postcommitment-confirmatory-v1"
    task: PostcommitmentTaskConfig = PostcommitmentTaskConfig()


class CrossRolloutPostcommitmentNativeV2Taskset(
    vf.Taskset[PostcommitmentTask, PostcommitmentConfig]
):
    def load(self) -> list[PostcommitmentTask]:
        order_pairs = [
            (phase1_order, phase2_order)
            for phase1_order in ("A_first", "B_first")
            for phase2_order in ("A_first", "B_first")
        ]
        return [
            PostcommitmentTask(
                PostcommitmentTaskData(
                    idx=index,
                    name=(
                        "native-postcommitment-policy-facility-"
                        f"{phase1_order}-{phase2_order}"
                    ),
                    prompt=prompt_for_phase1_order(phase1_order),
                    assignment_mode=self.config.assignment_mode,
                    assignment_seed=self.config.assignment_seed,
                    phase1_presentation_order=phase1_order,
                    phase2_presentation_order=phase2_order,
                ),
                self.config.task,
            )
            for index, (phase1_order, phase2_order) in enumerate(order_pairs)
        ]


class PostcommitmentEnvConfig(vf.EnvConfig):
    """One evaluated agent, pinned by default to the unmodified null harness."""

    agent: vf.AgentConfig = vf.AgentConfig(
        harness=NullHarnessConfig(id="null"),
        max_turns=14,
    )


class CrossRolloutPostcommitmentNativeV2Env(vf.Env[PostcommitmentEnvConfig]):
    """Runs Phase 1 to natural yield, then conditionally opens the Phase-2 turn."""

    async def run(self, task: PostcommitmentTask, agents: vf.Agents) -> None:
        async with agents.agent.interaction(task) as interaction:
            phase1_segment = await interaction.turn()
            state = interaction.trace.state
            if not segment_ended_naturally(phase1_segment, interaction.trace):
                return
            if not state.primary_eligible or state.phase != "awaiting_r2":
                return

            assignment = state.exposure_condition
            activate_r2(state)
            if state.exposure_condition != assignment:
                raise RuntimeError(
                    "environment activation changed treatment assignment"
                )
            state.turn2_sent_count += 1
            state.turn2_message = prompt_for_phase2_order(
                state.phase2_presentation_order
            )
            record_event(
                state,
                "env_turn2",
                "user",
                state.turn2_message,
                post_randomization=True,
            )
            await interaction.turn(state.turn2_message)


__all__ = [
    "CrossRolloutPostcommitmentNativeV2Env",
    "CrossRolloutPostcommitmentNativeV2Taskset",
]
