"""Native two-turn taskset for the no-culture transition diagnostic."""

import verifiers.v1 as vf
from verifiers.v1.harnesses.null import NullHarnessConfig

from cross_rollout_postcommitment_transition_diagnostic_v1.servers.facility import (
    TransitionDiagnosticToolset,
    TransitionDiagnosticToolsetConfig,
)
from cross_rollout_postcommitment_transition_diagnostic_v1.state import (
    PresentationOrder,
    TransitionDiagnosticState,
    record_event,
)

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


def activate_r2(state: TransitionDiagnosticState) -> None:
    """The only transition that makes R2 exist; called by environment control flow."""

    if state.phase != "awaiting_r2":
        raise RuntimeError("R2 activation requires the awaiting_r2 state")
    if not (state.phase1_policy in ("A", "B") and state.phase1_success):
        raise RuntimeError("R2 activation requires successful Phase-1 policy")
    if state.r2_activated:
        raise RuntimeError("R2 has already been activated")

    state.r2_activated = True
    state.phase = "phase2"
    record_event(
        state,
        "env_activate_r2",
        "activate_r2",
        "Resource R2 activated by environment control flow.",
    )


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


class TransitionDiagnosticTaskData(vf.TaskData):
    phase1_presentation_order: PresentationOrder
    phase2_presentation_order: PresentationOrder


class TransitionDiagnosticTaskConfig(vf.TaskConfig):
    tools: TransitionDiagnosticToolsetConfig = TransitionDiagnosticToolsetConfig()


class TransitionDiagnosticTask(
    vf.Task[
        TransitionDiagnosticTaskData,
        TransitionDiagnosticState,
        TransitionDiagnosticTaskConfig,
    ]
):
    @classmethod
    def toolsets(cls, config: TransitionDiagnosticTaskConfig) -> list[vf.Toolset]:
        return [TransitionDiagnosticToolset(config.tools)]

    async def setup(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        trace.state.rollout_id = trace.id
        trace.state.phase1_presentation_order = self.data.phase1_presentation_order
        trace.state.phase2_presentation_order = self.data.phase2_presentation_order
        trace.info["transition_diagnostic"] = {
            "phase1_presentation_order": self.data.phase1_presentation_order,
            "phase2_presentation_order": self.data.phase2_presentation_order,
            "turn2_message_frozen": prompt_for_phase2_order(
                self.data.phase2_presentation_order
            ),
        }

    async def finalize(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        state = trace.state
        events = [event.model_dump(mode="json") for event in state.events]
        transition = (
            f"{state.phase1_policy}→{state.phase2_policy}"
            if state.phase1_policy is not None and state.phase2_policy is not None
            else None
        )
        trace.info["transition_diagnostic"].update(
            {
                "events": events,
                "final_phase": state.phase,
                "phase1_policy": state.phase1_policy,
                "phase1_success": state.phase1_success,
                "phase2_policy": state.phase2_policy,
                "phase2_success": state.phase2_success,
                "phase2_missing": state.phase1_success and state.phase2_policy is None,
                "phase2_incomplete_after_choice": (
                    state.phase1_success
                    and state.phase2_policy is not None
                    and not state.phase2_success
                ),
                "r2_activated": state.r2_activated,
                "turn2_sent_count": state.turn2_sent_count,
                "turn2_message": state.turn2_message or None,
                "interstage_call_count": state.interstage_call_count,
                "interstage_events": [
                    event for event in events if event["kind"] == "interstage"
                ],
                "transition": transition,
                "first_failure_index": state.first_failure_index,
                "failure_events": [event for event in events if event["failure"]],
                "selection_ambiguity": state.selection_ambiguity,
                "policy_selection_attempts": state.policy_selection_attempts,
                "stop_condition": trace.stop_condition,
            }
        )

    @vf.reward
    async def task_completion(self, trace: vf.Trace) -> float:
        """A complete two-resource lifecycle is the model-free task reward."""

        return float(trace.state.phase1_success and trace.state.phase2_success)

    @vf.metric
    async def phase1_a_success(self, trace: vf.Trace) -> float:
        return float(trace.state.phase1_policy == "A" and trace.state.phase1_success)

    @vf.metric
    async def phase1_b_success(self, trace: vf.Trace) -> float:
        return float(trace.state.phase1_policy == "B" and trace.state.phase1_success)

    @vf.metric
    async def phase2_a_choice(self, trace: vf.Trace) -> float:
        return float(trace.state.phase1_success and trace.state.phase2_policy == "A")

    @vf.metric
    async def phase2_b_choice(self, trace: vf.Trace) -> float:
        return float(trace.state.phase1_success and trace.state.phase2_policy == "B")

    @vf.metric
    async def transition_a_to_a(self, trace: vf.Trace) -> float:
        return float(
            trace.state.phase1_policy == "A" and trace.state.phase2_policy == "A"
        )

    @vf.metric
    async def transition_a_to_b(self, trace: vf.Trace) -> float:
        return float(
            trace.state.phase1_policy == "A" and trace.state.phase2_policy == "B"
        )

    @vf.metric
    async def transition_b_to_a(self, trace: vf.Trace) -> float:
        return float(
            trace.state.phase1_policy == "B" and trace.state.phase2_policy == "A"
        )

    @vf.metric
    async def transition_b_to_b(self, trace: vf.Trace) -> float:
        return float(
            trace.state.phase1_policy == "B" and trace.state.phase2_policy == "B"
        )

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


class TransitionDiagnosticConfig(vf.TasksetConfig):
    task: TransitionDiagnosticTaskConfig = TransitionDiagnosticTaskConfig()


class CrossRolloutPostcommitmentTransitionDiagnosticV1Taskset(
    vf.Taskset[TransitionDiagnosticTask, TransitionDiagnosticConfig]
):
    def load(self) -> list[TransitionDiagnosticTask]:
        order_pairs = [
            (phase1_order, phase2_order)
            for phase1_order in ("A_first", "B_first")
            for phase2_order in ("A_first", "B_first")
        ]
        return [
            TransitionDiagnosticTask(
                TransitionDiagnosticTaskData(
                    idx=index,
                    name=(
                        "native-postcommitment-transition-diagnostic-"
                        f"{phase1_order}-{phase2_order}"
                    ),
                    prompt=prompt_for_phase1_order(phase1_order),
                    phase1_presentation_order=phase1_order,
                    phase2_presentation_order=phase2_order,
                ),
                self.config.task,
            )
            for index, (phase1_order, phase2_order) in enumerate(order_pairs)
        ]


class TransitionDiagnosticEnvConfig(vf.EnvConfig):
    """One evaluated agent, pinned to the unmodified null harness."""

    agent: vf.AgentConfig = vf.AgentConfig(
        harness=NullHarnessConfig(id="null"),
        max_turns=14,
    )


class CrossRolloutPostcommitmentTransitionDiagnosticV1Env(
    vf.Env[TransitionDiagnosticEnvConfig]
):
    """Run Phase 1 to natural yield, then conditionally open the Phase-2 turn."""

    async def run(self, task: TransitionDiagnosticTask, agents: vf.Agents) -> None:
        async with agents.agent.interaction(task) as interaction:
            phase1_segment = await interaction.turn()
            state = interaction.trace.state
            if not segment_ended_naturally(phase1_segment, interaction.trace):
                return
            if not state.phase1_success or state.phase != "awaiting_r2":
                return

            activate_r2(state)
            state.turn2_sent_count += 1
            state.turn2_message = prompt_for_phase2_order(
                state.phase2_presentation_order
            )
            record_event(
                state,
                "env_turn2",
                "user",
                state.turn2_message,
            )
            await interaction.turn(state.turn2_message)


__all__ = [
    "CrossRolloutPostcommitmentTransitionDiagnosticV1Env",
    "CrossRolloutPostcommitmentTransitionDiagnosticV1Taskset",
]
