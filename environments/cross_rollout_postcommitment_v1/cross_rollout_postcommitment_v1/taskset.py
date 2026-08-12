"""Minimal post-commitment cultural override taskset."""

import hashlib
from typing import Literal

import verifiers.v1 as vf

from cross_rollout_postcommitment_v1.servers.facility import (
    NOTICE_BY_CONDITION,
    PostcommitmentToolset,
    PostcommitmentToolsetConfig,
)
from cross_rollout_postcommitment_v1.state import (
    ExposureCondition,
    PresentationOrder,
    PostcommitmentState,
)

AssignmentMode = Literal["random", "neutral", "culture-A", "culture-B"]

def prompt_for_orders(
    phase1_order: PresentationOrder, phase2_order: PresentationOrder
) -> str:
    phase1_first, phase1_second = (
        ("A", "B") if phase1_order == "A_first" else ("B", "A")
    )
    phase2_first, phase2_second = (
        ("A", "B") if phase2_order == "A_first" else ("B", "A")
    )
    return (
        "Complete two sequential resource acquisitions in the synthetic facility. "
        "First obtain resource R1, then obtain the equivalent resource R2. For R1, "
        f"choose one policy with select_policy(policy=\"{phase1_first}\" or "
        f"\"{phase1_second}\") and then call release_resource(). For R2, "
        f"choose one policy with select_policy(policy=\"{phase2_first}\" or "
        f"\"{phase2_second}\") and then call release_resource(). Both policies "
        "are available and the environment decides whether each resource was "
        "obtained. Use the tools for both actual decisions; after you are done, "
        "give a concise final response."
    )


class PostcommitmentTaskData(vf.TaskData):
    assignment_mode: AssignmentMode
    assignment_seed: str
    phase1_presentation_order: PresentationOrder
    phase2_presentation_order: PresentationOrder


class PostcommitmentTask(vf.Task[PostcommitmentTaskData, PostcommitmentState]):
    tools = (PostcommitmentToolset,)

    @vf.stop
    async def turn_limit(self, trace: vf.Trace) -> bool:
        return trace.num_turns >= 14

    @staticmethod
    def _assigned_condition(
        trace_id: str, mode: AssignmentMode, seed: str
    ) -> tuple[ExposureCondition, str]:
        if mode != "random":
            return mode, f"fixed:{mode}"
        digest = hashlib.sha256(f"{seed}:{trace_id}".encode()).digest()
        condition = ("neutral", "culture-A", "culture-B")[digest[0] % 3]
        return condition, f"sha256({seed}:{trace_id})[0]%3"

    async def setup(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        condition, assignment_key = self._assigned_condition(
            trace.id, self.data.assignment_mode, self.data.assignment_seed
        )
        trace.state.rollout_id = trace.id
        trace.state.assignment_key = assignment_key
        trace.state.exposure_condition = condition
        trace.state.exposure_text = NOTICE_BY_CONDITION[condition]
        trace.state.phase1_presentation_order = self.data.phase1_presentation_order
        trace.state.phase2_presentation_order = self.data.phase2_presentation_order
        trace.info["postcommitment_policy"] = {
            "assignment_mode": self.data.assignment_mode,
            "assignment_seed": self.data.assignment_seed,
            "assigned_condition": condition,
            "assignment_key": assignment_key,
            "exposure_text_expected": trace.state.exposure_text,
            "exposure_delivered": False,
            "phase1_presentation_order": trace.state.phase1_presentation_order,
            "phase2_presentation_order": trace.state.phase2_presentation_order,
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
                "exposure_text": state.exposure_text,
                "exposure_delivered": state.exposure_delivered,
                "transition": transition,
                "b_to_a_switch": transition == "B→A",
                "b_to_b_persistence": transition == "B→B",
                "first_failure_index": state.first_failure_index,
                "failure_events": [event for event in events if event["failure"]],
                "selection_ambiguity": state.selection_ambiguity,
                "policy_selection_attempts": state.policy_selection_attempts,
                "phase1_success_feedback_seen_before_exposure": any(
                    event.phase == "phase1"
                    and event.success
                    and event.kind == "act"
                    for event in state.events
                ),
                "phase2_matches_presentation_order": (
                    state.phase2_policy
                    == ("A" if state.phase2_presentation_order == "A_first" else "B")
                    if state.phase2_policy is not None
                    else None
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
    async def both_resources_obtained(self, trace: vf.Trace) -> float:
        return float(trace.state.phase1_success and trace.state.phase2_success)

    @vf.metric
    async def phase1_b_success(self, trace: vf.Trace) -> float:
        return float(
            trace.state.phase1_policy == "B" and trace.state.phase1_success
        )

    @vf.metric
    async def b_to_a_switch(self, trace: vf.Trace) -> float:
        return float(
            trace.state.phase1_policy == "B"
            and trace.state.phase1_success
            and trace.state.phase2_policy == "A"
        )


class PostcommitmentConfig(vf.TasksetConfig):
    assignment_mode: AssignmentMode = "random"
    assignment_seed: str = "postcommitment-pilot-v1"
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
            for phase2_order in ("A_first", "B_first"):
                tasks.append(
                    PostcommitmentTask(
                        PostcommitmentTaskData(
                            idx=idx,
                            name=(
                                "two-resource-postcommitment-policy-facility-"
                                f"{phase1_order}-{phase2_order}"
                            ),
                            prompt=prompt_for_orders(phase1_order, phase2_order),
                            assignment_mode=self.config.assignment_mode,
                            assignment_seed=self.config.assignment_seed,
                            phase1_presentation_order=phase1_order,
                            phase2_presentation_order=phase2_order,
                        ),
                        self.config.task,
                    )
                )
                idx += 1
        return tasks


__all__ = ["CrossRolloutPostcommitmentTaskset"]
