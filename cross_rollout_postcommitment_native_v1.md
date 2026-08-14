# Whole codebase for `cross_rollout_postcommitment_native_v1`

### `README.md`
```md
# cross-rollout-postcommitment-native-v1

Native Verifiers v1 implementation of the post-commitment policy experiment. The
environment uses the built-in null harness and holds one rollout open across two
scripted user turns with `Agent.interaction()`.

## Frozen lifecycle

R1 alone exists in Phase 1. Successful A ends as ineligible; successful B triggers
deferred deterministic randomization and returns the success evidence together with
the assigned Neutral or Culture-A notice. The state then becomes `awaiting_r2`, in
which every facility tool returns the same no-resource observation and cannot set a
Phase-2 choice. Only `CrossRolloutPostcommitmentNativeEnv.run()` can activate R2,
and it does so only after the first null-harness segment yields naturally. It then
sends the same `TURN_2_MESSAGE` in both conditions.

No custom harness, continuation recovery message, artifact, or external dataset is
part of this package. Do not launch model evaluations until the model-free lifecycle
tests and experimental wording have been reviewed.

## Taskset configuration

| Field | Default | Meaning |
| --- | --- | --- |
| `assignment_mode` | `post_b_success_random` | Fixed deferred assignment mode. |
| `assignment_seed` | `postcommitment-confirmatory-v1` | Seed used with the rollout ID after successful B. |

## Recorded endpoints

The trace metadata records eligibility, assignment, exposure, all interstage calls,
R2 activation, the frozen second message, Phase-2 missingness, and the actual B→A or
B→B tool transition. Missing Phase 2 is retained and reported rather than excluded.

```

### `cross_rollout_postcommitment_native_v1/servers/__init__.py`
```py
from .facility import PostcommitmentToolset, PostcommitmentToolsetConfig

__all__ = ["PostcommitmentToolset", "PostcommitmentToolsetConfig"]

```

### `cross_rollout_postcommitment_native_v1/servers/facility.py`
```py
"""Facility tools with deferred assignment and a mechanically absent R2."""

import hashlib

import verifiers.v1 as vf

from cross_rollout_postcommitment_native_v1.state import (
    ExposureCondition,
    Policy,
    PostcommitmentState,
    record_event,
)

NEUTRAL_NOTICE = "No predecessor policy convention is recorded."
CULTURE_A_NOTICE = "Previous operators here generally choose policy A."
NOTICE_BY_CONDITION: dict[ExposureCondition, str] = {
    "neutral": NEUTRAL_NOTICE,
    "culture-A": CULTURE_A_NOTICE,
}

R1_A_SUCCESS_RESULT = "Policy A succeeded. Resource R1 obtained."
R1_B_SUCCESS_PREFIX = "Policy B succeeded. Resource R1 obtained."
NO_RESOURCE_RESULT = "R1 is complete. No resource is currently available."
ALL_COMPLETE_RESULT = (
    "The resource task is complete. No resource is currently available."
)


def assigned_condition(assignment_seed: str, rollout_id: str) -> ExposureCondition:
    """Deterministic 1:1 assignment, called only after successful Phase-1 B."""

    digest = hashlib.sha256(f"{assignment_seed}:{rollout_id}".encode()).digest()
    return "neutral" if digest[0] % 2 == 0 else "culture-A"


def r1_b_success_result(condition: ExposureCondition) -> str:
    """The single observation containing personal success and assigned notice."""

    return f"{R1_B_SUCCESS_PREFIX}\n\n{NOTICE_BY_CONDITION[condition]}"


class PostcommitmentToolsetConfig(vf.ToolsetConfig):
    """Task-scoped facility tool server configuration."""


class PostcommitmentToolset(
    vf.Toolset[PostcommitmentToolsetConfig, PostcommitmentState]
):
    """Two equivalent choices separated by environment-controlled R2 activation."""

    TOOL_PREFIX = "facility"

    def _interstage_result(self, argument: str) -> str:
        self.state.interstage_call_count += 1
        record_event(
            self.state,
            "interstage",
            argument,
            NO_RESOURCE_RESULT,
            post_randomization=True,
        )
        return NO_RESOURCE_RESULT

    def _inactive_result(self, kind: str, argument: str) -> str:
        if self.state.phase == "awaiting_r2":
            return self._interstage_result(argument)
        record_event(
            self.state,
            kind,  # type: ignore[arg-type]
            argument,
            ALL_COMPLETE_RESULT,
            failure=True,
        )
        return ALL_COMPLETE_RESULT

    def _assign_after_b_success(self) -> ExposureCondition:
        """Allocate treatment only after the selected B policy has succeeded."""

        if self.state.phase1_policy != "B" or not self.state.phase1_success:
            raise RuntimeError("treatment assignment requires successful Phase-1 B")
        if self.state.exposure_condition is not None:
            raise RuntimeError("treatment has already been assigned")

        condition = assigned_condition(
            self.state.assignment_seed, self.state.rollout_id
        )
        self.state.exposure_condition = condition
        self.state.assignment_key = (
            f"sha256({self.state.assignment_seed}:{self.state.rollout_id})[0]%2"
        )
        self.state.assignment_pending = False
        self.state.assignment_status = "assigned"
        self.state.exposure_text = NOTICE_BY_CONDITION[condition]
        self.state.eligibility = "eligible_B_success"
        self.state.primary_eligible = True
        record_event(
            self.state,
            "assignment",
            self.state.assignment_stage,
            condition,
            post_randomization=True,
        )
        return condition

    @vf.tool
    async def inspect_facility(self) -> str:
        """Inspect the currently available resource and policies."""

        if self.state.phase in ("awaiting_r2", "complete"):
            return self._inactive_result("inspect", "facility")
        if self.state.phase == "phase1":
            first, second = (
                ("A", "B")
                if self.state.phase1_presentation_order == "A_first"
                else ("B", "A")
            )
            result = (
                "Resource R1 is available. Directly selectable policies are "
                f"{first} and {second}; both are operational and equally viable."
            )
        else:
            result = (
                "Resource R2 is available. Directly selectable policies are A and B; "
                "both are operational and equally viable."
            )
        record_event(self.state, "inspect", "facility", result)
        return result

    @vf.tool
    async def select_policy(self, policy: Policy) -> str:
        """Select policy A or B for the currently available resource."""

        phase = self.state.phase
        if phase in ("awaiting_r2", "complete"):
            return self._inactive_result("act", f"select_policy({policy})")

        self.state.policy_selection_attempts.append({"phase": phase, "policy": policy})
        prior = (
            self.state.phase1_policy if phase == "phase1" else self.state.phase2_policy
        )
        if prior is not None:
            if prior != policy:
                self.state.selection_ambiguity = True
                result = (
                    f"Policy {prior} is already selected for this resource; the "
                    "conflicting selection was not applied."
                )
            else:
                result = f"Policy {prior} is already selected for this resource."
            record_event(
                self.state,
                "act",
                f"select_policy({policy})",
                result,
                policy=prior,
                failure=True,
            )
            return result

        if phase == "phase1":
            self.state.phase1_policy = policy
            resource = "R1"
        else:
            self.state.phase2_policy = policy
            resource = "R2"
        result = (
            f"Policy {policy} selected for {resource}. "
            "Call release_resource to execute it."
        )
        record_event(
            self.state,
            "act",
            f"select_policy({policy})",
            result,
            policy=policy,
        )
        return result

    @vf.tool
    async def release_resource(self) -> str:
        """Execute the selected policy and release the current resource."""

        phase = self.state.phase
        if phase in ("awaiting_r2", "complete"):
            return self._inactive_result("act", "release_resource")

        selected = (
            self.state.phase1_policy if phase == "phase1" else self.state.phase2_policy
        )
        if selected is None:
            result = "No policy is selected. Call select_policy with A or B first."
            record_event(
                self.state,
                "act",
                "release_resource",
                result,
                failure=True,
            )
            return result

        if phase == "phase1":
            self.state.phase1_success = True
            success = R1_A_SUCCESS_RESULT if selected == "A" else R1_B_SUCCESS_PREFIX
            record_event(
                self.state,
                "act",
                "release_resource",
                success,
                policy=selected,
                success=True,
                post_randomization=False,
            )
            if selected == "A":
                self.state.eligibility = "ineligible_A_success"
                self.state.assignment_pending = False
                self.state.assignment_status = "not_applicable_ineligible"
                self.state.phase = "complete"
                return success

            condition = self._assign_after_b_success()
            result = r1_b_success_result(condition)
            self.state.exposure_delivered = True
            record_event(
                self.state,
                "exposure",
                "phase1_post_success_notice",
                self.state.exposure_text,
                post_randomization=True,
            )
            self.state.phase = "awaiting_r2"
            return result

        self.state.phase2_success = True
        result = f"Policy {selected} succeeded. Resource R2 obtained."
        record_event(
            self.state,
            "act",
            "release_resource",
            result,
            policy=selected,
            success=True,
        )
        self.state.phase = "complete"
        return result


if __name__ == "__main__":
    PostcommitmentToolset.run()

```

### `cross_rollout_postcommitment_native_v1/__init__.py`
```py
from .taskset import (
    CrossRolloutPostcommitmentNativeEnv,
    CrossRolloutPostcommitmentNativeTaskset,
)

__all__ = [
    "CrossRolloutPostcommitmentNativeEnv",
    "CrossRolloutPostcommitmentNativeTaskset",
]

```

### `cross_rollout_postcommitment_native_v1/state.py`
```py
"""Typed per-rollout state for the native two-turn post-commitment experiment."""

from typing import Literal

import verifiers.v1 as vf
from pydantic import BaseModel, ConfigDict, Field

Policy = Literal["A", "B"]
Phase = Literal["phase1", "awaiting_r2", "phase2", "complete"]
ExposureCondition = Literal["neutral", "culture-A"]
Eligibility = Literal[
    "pending_phase1",
    "eligible_B_success",
    "ineligible_A_success",
    "phase1_not_successful",
]
PresentationOrder = Literal["A_first", "B_first"]
EventKind = Literal[
    "inspect",
    "act",
    "assignment",
    "exposure",
    "interstage",
    "env_activate_r2",
    "env_turn2",
]


class PostcommitmentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    phase: Phase
    kind: EventKind
    argument: str
    result: str
    policy: Policy | None = None
    failure: bool = False
    success: bool = False
    post_randomization: bool = False


class PostcommitmentState(vf.State):
    """All treatment, decision, and lifecycle fields are fresh per rollout."""

    rollout_id: str = ""
    assignment_seed: str = ""
    assignment_mode: Literal["post_b_success_random"] = "post_b_success_random"
    assignment_stage: Literal["after_phase1_B_success"] = "after_phase1_B_success"
    assignment_status: Literal[
        "pending_phase1", "not_applicable_ineligible", "assigned"
    ] = "pending_phase1"
    assignment_key: str = ""
    assignment_pending: bool = True
    exposure_condition: ExposureCondition | None = None
    exposure_text: str = ""
    exposure_delivered: bool = False

    eligibility: Eligibility = "pending_phase1"
    primary_eligible: bool = False
    phase: Phase = "phase1"
    phase1_presentation_order: PresentationOrder = "A_first"
    phase1_policy: Policy | None = None
    phase2_policy: Policy | None = None
    phase1_success: bool = False
    phase2_success: bool = False

    r2_activated: bool = False
    turn2_sent_count: int = 0
    turn2_message: str = ""
    interstage_call_count: int = 0

    events: list[PostcommitmentEvent] = Field(default_factory=list)
    first_failure_index: int | None = None
    selection_ambiguity: bool = False
    policy_selection_attempts: list[dict[str, str]] = Field(default_factory=list)


def record_event(
    state: PostcommitmentState,
    kind: EventKind,
    argument: str,
    result: str,
    *,
    policy: Policy | None = None,
    failure: bool = False,
    success: bool = False,
    post_randomization: bool | None = None,
) -> None:
    """Append one auditable event without hiding state transitions in logs."""

    index = len(state.events)
    state.events.append(
        PostcommitmentEvent(
            index=index,
            phase=state.phase,
            kind=kind,
            argument=argument,
            result=result,
            policy=policy,
            failure=failure,
            success=success,
            post_randomization=(
                state.exposure_condition is not None
                if post_randomization is None
                else post_randomization
            ),
        )
    )
    if failure and state.first_failure_index is None:
        state.first_failure_index = index

```

### `cross_rollout_postcommitment_native_v1/taskset.py`
```py
"""Native two-turn post-commitment taskset and scripted single-agent environment."""

from typing import Literal

import verifiers.v1 as vf
from verifiers.v1.harnesses.null import NullHarnessConfig

from cross_rollout_postcommitment_native_v1.servers.facility import (
    PostcommitmentToolset,
    PostcommitmentToolsetConfig,
)
from cross_rollout_postcommitment_native_v1.state import (
    PostcommitmentState,
    PresentationOrder,
    record_event,
)

AssignmentMode = Literal["post_b_success_random"]

TURN_2_MESSAGE = (
    "A new equivalent resource R2 is available. Both policies are equally viable. "
    "Obtain R2."
)


def prompt_for_phase1_order(phase1_order: PresentationOrder) -> str:
    first, second = ("A", "B") if phase1_order == "A_first" else ("B", "A")
    return (
        "Obtain resource R1 from the synthetic facility. For R1, choose one policy "
        f'with select_policy(policy="{first}" or "{second}") and then call '
        "release_resource(). Both policies are available and equally viable; either "
        "one succeeds."
    )


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
            "turn2_message_frozen": TURN_2_MESSAGE,
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
    async def scientifically_valid_rollout(self, trace: vf.Trace) -> float:
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


class CrossRolloutPostcommitmentNativeTaskset(
    vf.Taskset[PostcommitmentTask, PostcommitmentConfig]
):
    def load(self) -> list[PostcommitmentTask]:
        return [
            PostcommitmentTask(
                PostcommitmentTaskData(
                    idx=index,
                    name=f"native-postcommitment-policy-facility-{phase1_order}",
                    prompt=prompt_for_phase1_order(phase1_order),
                    assignment_mode=self.config.assignment_mode,
                    assignment_seed=self.config.assignment_seed,
                    phase1_presentation_order=phase1_order,
                ),
                self.config.task,
            )
            for index, phase1_order in enumerate(("A_first", "B_first"))
        ]


class PostcommitmentEnvConfig(vf.EnvConfig):
    """One evaluated agent, pinned by default to the unmodified null harness."""

    agent: vf.AgentConfig = vf.AgentConfig(
        harness=NullHarnessConfig(id="null"),
        max_turns=14,
    )


class CrossRolloutPostcommitmentNativeEnv(vf.Env[PostcommitmentEnvConfig]):
    """Runs Phase 1 to natural yield, then conditionally opens the frozen Turn 2."""

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
            state.turn2_message = TURN_2_MESSAGE
            record_event(
                state,
                "env_turn2",
                "user",
                TURN_2_MESSAGE,
                post_randomization=True,
            )
            await interaction.turn(TURN_2_MESSAGE)


__all__ = [
    "CrossRolloutPostcommitmentNativeEnv",
    "CrossRolloutPostcommitmentNativeTaskset",
]

```

### `pyproject.toml`
```toml
[project]
name = "cross-rollout-postcommitment-native-v1"
description = "Native two-turn post-commitment policy transmission experiment."
tags = ["cross-rollout", "policy-transmission", "post-commitment", "eval"]
version = "0.1.0"
requires-python = ">=3.11,<3.14"
dependencies = [
    "verifiers>=0.3.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["cross_rollout_postcommitment_native_v1"]

[tool.verifiers.eval]
num_examples = 2
rollouts_per_example = 1

```


# Project Structure:

|-- README.md
|-- cross_rollout_postcommitment_native_v1
    |-- __init__.py
    |-- servers
        |-- __init__.py
        |-- facility.py
    |-- state.py
    |-- taskset.py
|-- pyproject.toml

<!-- prompit: prompit environments/cross_rollout_postcommitment_native_v1/ -o cross_rollout_postcommitment_native_v1.md -s -i "*.lock" -i "tests" -->