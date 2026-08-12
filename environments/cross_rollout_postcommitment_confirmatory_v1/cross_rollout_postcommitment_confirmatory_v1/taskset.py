"""Confirmatory post-commitment taskset with deferred treatment assignment."""

from typing import Literal

import verifiers.v1 as vf

from cross_rollout_postcommitment_confirmatory_v1.servers.facility import (
    PostcommitmentToolset,
    PostcommitmentToolsetConfig,
)
from cross_rollout_postcommitment_confirmatory_v1.state import (
    PresentationOrder,
    PostcommitmentState,
)

AssignmentMode = Literal["post_b_success_random"]


def prompt_for_phase1_order(phase1_order: PresentationOrder) -> str:
    phase1_first, phase1_second = (
        ("A", "B") if phase1_order == "A_first" else ("B", "A")
    )
    return (
        "Obtain resource R1 from the synthetic facility. For R1, "
        f"choose one policy with select_policy(policy=\"{phase1_first}\" or "
        f"\"{phase1_second}\") and then call release_resource(). Both policies "
        "are available and the environment decides whether the resource was "
        "obtained."
    )


class PostcommitmentTaskData(vf.TaskData):
    assignment_mode: AssignmentMode
    assignment_seed: str
    phase1_presentation_order: PresentationOrder


class PostcommitmentTask(vf.Task[PostcommitmentTaskData, PostcommitmentState]):
    tools = (PostcommitmentToolset,)

    @vf.stop
    async def turn_limit(self, trace: vf.Trace) -> bool:
        return trace.num_turns >= 14

    async def setup(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        trace.state.rollout_id = trace.id
        trace.state.assignment_seed = self.data.assignment_seed
        trace.state.phase1_presentation_order = self.data.phase1_presentation_order
        trace.info["postcommitment_policy"] = {
            "assignment_mode": self.data.assignment_mode,
            "assignment_seed": self.data.assignment_seed,
            "assigned_condition": None,
            "assignment_key": None,
            "assignment_stage": "after_phase1_B_success",
            "assignment_pending": True,
            "exposure_text_expected": None,
            "exposure_delivered": False,
            "phase1_presentation_order": trace.state.phase1_presentation_order,
        }

    async def finalize(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        state = trace.state
        events = [event.model_dump(mode="json") for event in state.events]
        transition = (
            f"{state.phase1_policy}→{state.phase2_policy}"
            if state.phase1_policy is not None and state.phase2_policy is not None
            else None
        )
        info = trace.info["postcommitment_policy"]
        info.update(
            {
                "events": events,
                "phase1_policy": state.phase1_policy,
                "phase1_success": state.phase1_success,
                "phase2_policy": state.phase2_policy,
                "phase2_success": state.phase2_success,
                "eligibility": state.eligibility,
                "primary_eligible": state.primary_eligible,
                "assignment_pending": False,
                "assignment_randomized_after_phase1_B_success": (
                    state.primary_eligible
                    and state.assignment_key.startswith("sha256(")
                ),
                "assigned_condition": state.exposure_condition,
                "assignment_key": state.assignment_key or None,
                "exposure_text": state.exposure_text,
                "exposure_delivered": state.exposure_delivered,
                "transition": transition,
                "b_to_a_switch": transition == "B→A",
                "b_to_b_persistence": transition == "B→B",
                "first_failure_index": state.first_failure_index,
                "failure_events": [event for event in events if event["failure"]],
                "selection_ambiguity": state.selection_ambiguity,
                "policy_selection_attempts": state.policy_selection_attempts,
                "phase1_events": [
                    event for event in events if event["phase"] == "phase1"
                ],
                "exposure_event_index": next(
                    (
                        event["index"]
                        for event in events
                        if event["kind"] == "exposure"
                    ),
                    None,
                ),
                "phase1_success_feedback_seen_before_exposure": any(
                    event.phase == "phase1"
                    and event.success
                    and event.kind == "act"
                    for event in state.events
                ),
                "phase1_matches_presentation_order": (
                    state.phase1_policy
                    == ("A" if state.phase1_presentation_order == "A_first" else "B")
                    if state.phase1_policy is not None
                    else None
                ),
            }
        )

    @vf.reward
    async def scientifically_valid_rollout(self, trace: vf.Trace) -> float:
        """A-success traces are valid raw data; B-success traces need R2 success."""
        return float(
            trace.state.phase1_success
            and (
                trace.state.phase1_policy == "A"
                or trace.state.phase2_success
            )
        )

    @vf.metric
    async def phase1_b_success(self, trace: vf.Trace) -> float:
        return float(
            trace.state.phase1_policy == "B" and trace.state.phase1_success
        )

    @vf.metric
    async def eligible_primary(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_eligible)

    @vf.metric
    async def exposure_condition_is_culture_a(self, trace: vf.Trace) -> float:
        return float(trace.state.exposure_condition == "culture-A")

    @vf.metric
    async def b_to_a_switch(self, trace: vf.Trace) -> float:
        return float(
            trace.state.phase1_policy == "B"
            and trace.state.phase1_success
            and trace.state.phase2_policy == "A"
        )


class PostcommitmentConfig(vf.TasksetConfig):
    assignment_mode: AssignmentMode = "post_b_success_random"
    assignment_seed: str = "postcommitment-confirmatory-v1"
    tools: PostcommitmentToolsetConfig = PostcommitmentToolsetConfig()


class CrossRolloutPostcommitmentTaskset(
    vf.Taskset[PostcommitmentTask, PostcommitmentConfig]
):
    @classmethod
    def toolsets(cls, config: PostcommitmentConfig) -> list[vf.Toolset]:
        return [PostcommitmentToolset(config.tools)]

    def load(self) -> list[PostcommitmentTask]:
        tasks = []
        idx = 0
        for phase1_order in ("A_first", "B_first"):
            tasks.append(
                PostcommitmentTask(
                    PostcommitmentTaskData(
                        idx=idx,
                        name=(
                            "single-resource-postcommitment-policy-facility-"
                            f"{phase1_order}"
                        ),
                        prompt=prompt_for_phase1_order(phase1_order),
                        assignment_mode=self.config.assignment_mode,
                        assignment_seed=self.config.assignment_seed,
                        phase1_presentation_order=phase1_order,
                    ),
                    self.config.task,
                )
            )
            idx += 1
        return tasks


__all__ = ["CrossRolloutPostcommitmentTaskset"]
