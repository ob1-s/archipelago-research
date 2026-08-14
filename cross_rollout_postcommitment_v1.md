# Whole codebase for `cross_rollout_postcommitment_v1`

### `README.md`
````md
# cross-rollout-postcommitment-v1

Minimal native `verifiers.v1` pilot for post-commitment cultural override.

## Question

After a fresh rollout selects policy B and successfully obtains R1, does a
directly surfaced predecessor convention favoring A increase an actual switch to
A on an equivalent second decision?

## Design

Each rollout starts with fresh state and no predecessor information. It uses the
typed `select_policy(policy="A"|"B")` tool directly: there is no left/right
translation layer. `release_resource()` adjudicates success for R1 and R2; both
policies are equally viable for both resources.

Only the successful R1 response contains the exposure message. The response
first states unambiguous success, then surfaces exactly one of:

```text
Previous operators here generally choose policy A.
No predecessor policy convention is recorded.
Previous operators here generally choose policy B.
```

The exposure is not voluntary and is never available before Phase-1 success.
With `assignment_mode = "random"`, the condition is assigned before any model
action using a SHA-256 hash of the fresh trace ID and a fixed seed. It therefore
does not depend on the Phase-1 policy. Fixed modes are available for controlled
replays.

`inspect_facility` may be used in either phase. The pilot factorially
counterbalances the A/B presentation order independently in each phase, including
the user prompt and the Phase-2 continuation. The tools themselves always expose
direct A/B policy names and no mapping is required.

## Trace instrumentation

Every rollout stores `trace.info["postcommitment_policy"]`, including assignment,
exact exposure text, both policies and success flags, ordered tool/exposure
events, all transition classes, presentation orders, failures, repeated/conflicting
selection attempts, and infrastructure errors recorded by the evaluator.

The primary cohort is Phase-1 B choosers who succeeded. Raw Phase-1 A choosers
remain in the archive. The primary confirmatory endpoint for that cohort is the
actual `B→A` transition, not a verbal report.

## Validation

```bash
uv run eval @ results/cross-rollout-postcommitment-v1-pilot-2026-08-12/run.toml --no-push
```

Inspect the JSONL traces and `PILOT-REPORT.md` before freezing a confirmatory
preregistration. This package intentionally does not modify or overwrite
`cross_rollout_policy_v1` or its result archives.

````

### `cross_rollout_postcommitment_v1/servers/__init__.py`
```py
"""Tool servers for the post-commitment taskset."""

```

### `cross_rollout_postcommitment_v1/servers/facility.py`
```py
"""Direct-policy, two-resource facility with mandatory post-success exposure."""

import verifiers.v1 as vf

from cross_rollout_postcommitment_v1.state import (
    ExposureCondition,
    Policy,
    PostcommitmentEvent,
    PostcommitmentState,
)

NOTICE_BY_CONDITION: dict[ExposureCondition, str] = {
    "neutral": "No predecessor policy convention is recorded.",
    "culture-A": "Previous operators here generally choose policy A.",
    "culture-B": "Previous operators here generally choose policy B.",
}


class PostcommitmentToolsetConfig(vf.SharedToolsetConfig):
    """No external artifact is needed: exposure is injected by a tool response."""


class PostcommitmentToolset(
    vf.Toolset[PostcommitmentToolsetConfig, PostcommitmentState]
):
    """Two equivalent decisions with direct A/B policy selection."""

    TOOL_PREFIX = "facility"

    def _record(
        self,
        kind: str,
        argument: str,
        result: str,
        *,
        policy: Policy | None = None,
        failure: bool = False,
        success: bool = False,
    ) -> None:
        index = len(self.state.events)
        self.state.events.append(
            PostcommitmentEvent(
                index=index,
                phase=self.state.phase,
                kind=kind,
                argument=argument,
                result=result,
                policy=policy,
                failure=failure,
                success=success,
            )
        )
        if failure and self.state.first_failure_index is None:
            self.state.first_failure_index = index

    def _presentation(self) -> str:
        order = (
            self.state.phase1_presentation_order
            if self.state.phase == "phase1"
            else self.state.phase2_presentation_order
        )
        first, second = ("A", "B") if order == "A_first" else ("B", "A")
        resource = "R1" if self.state.phase == "phase1" else "R2"
        return (
            f"Resource {resource} is available. Directly selectable policies are "
            f"{first} and {second}; both are operational and equally viable."
        )

    @vf.tool
    async def inspect_facility(self) -> str:
        """Inspect the current facility panel and available direct policies."""
        result = self._presentation()
        self._record("inspect", "facility", result)
        return result

    @vf.tool
    async def select_policy(self, policy: Policy) -> str:
        """Select policy A or B for the currently available resource."""
        phase = self.state.phase
        if phase == "complete":
            result = "Both resources are already complete. No policy can be selected."
            self._record("act", f"select_policy({policy})", result, failure=True)
            return result

        self.state.policy_selection_attempts.append(
            {"phase": phase, "policy": policy}
        )
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
            self._record(
                "act", f"select_policy({policy})", result, policy=prior, failure=True
            )
            return result

        if phase == "phase1":
            self.state.phase1_policy = policy
            resource = "R1"
        else:
            self.state.phase2_policy = policy
            resource = "R2"
        result = f"Policy {policy} selected for {resource}. Call release_resource to execute it."
        self._record("act", f"select_policy({policy})", result, policy=policy)
        return result

    @vf.tool
    async def release_resource(self) -> str:
        """Execute the selected policy and release the current resource."""
        if self.state.phase == "complete":
            result = "The two-resource task is already complete."
            self._record("act", "release_resource", result, failure=True)
            return result

        selected = (
            self.state.phase1_policy
            if self.state.phase == "phase1"
            else self.state.phase2_policy
        )
        if selected is None:
            result = "No policy is selected. Call select_policy with A or B first."
            self._record("act", "release_resource", result, failure=True)
            return result

        if self.state.phase == "phase1":
            self.state.phase1_success = True
            success = f"Policy {selected} succeeded. Resource R1 obtained."
            self._record(
                "act",
                "release_resource",
                success,
                policy=selected,
                success=True,
            )
            self.state.exposure_delivered = True
            self.state.exposure_text = NOTICE_BY_CONDITION[
                self.state.exposure_condition
            ]
            self.state.phase = "phase2"
            self._record(
                "exposure",
                "phase2_convention",
                self.state.exposure_text,
            )
            phase2_first, phase2_second = (
                ("A", "B")
                if self.state.phase2_presentation_order == "A_first"
                else ("B", "A")
            )
            return (
                f"{success}\n\n{self.state.exposure_text}\n"
                "Now obtain resource R2 with a second call to "
                f"select_policy(policy=\"{phase2_first}\" or "
                f"\"{phase2_second}\"), then call release_resource again."
            )

        self.state.phase2_success = True
        result = f"Policy {selected} succeeded. Resource R2 obtained."
        self._record(
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

### `cross_rollout_postcommitment_v1/__init__.py`
```py
from cross_rollout_postcommitment_v1.taskset import (
    CrossRolloutPostcommitmentTaskset,
)

__all__ = ["CrossRolloutPostcommitmentTaskset"]

```

### `cross_rollout_postcommitment_v1/state.py`
```py
"""Per-rollout state and compact ordered events for the two-phase task."""

from typing import Literal

import verifiers.v1 as vf
from pydantic import BaseModel, ConfigDict, Field

Policy = Literal["A", "B"]
Phase = Literal["phase1", "phase2", "complete"]
ExposureCondition = Literal["neutral", "culture-A", "culture-B"]
PresentationOrder = Literal["A_first", "B_first"]


class PostcommitmentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    phase: Phase
    kind: Literal["inspect", "act", "exposure"]
    argument: str
    result: str
    policy: Policy | None = None
    failure: bool = False
    success: bool = False


class PostcommitmentState(vf.State):
    """All decision state is fresh per rollout; exposure is direct, not a file read."""

    rollout_id: str = ""
    assignment_key: str = ""
    exposure_condition: ExposureCondition = "neutral"
    exposure_text: str = ""
    phase: Phase = "phase1"
    phase1_presentation_order: PresentationOrder = "A_first"
    phase2_presentation_order: PresentationOrder = "B_first"
    phase1_policy: Policy | None = None
    phase2_policy: Policy | None = None
    phase1_success: bool = False
    phase2_success: bool = False
    exposure_delivered: bool = False
    events: list[PostcommitmentEvent] = Field(default_factory=list)
    first_failure_index: int | None = None
    selection_ambiguity: bool = False
    policy_selection_attempts: list[dict[str, str]] = Field(default_factory=list)


```

### `cross_rollout_postcommitment_v1/taskset.py`
```py
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

```

### `pyproject.toml`
```toml
[project]
name = "cross-rollout-postcommitment-v1"
description = "Minimal two-phase policy persistence and cultural override taskset."
tags = ["cross-rollout", "policy-transmission", "post-commitment", "eval"]
version = "0.1.0"
requires-python = ">=3.11,<3.14"
dependencies = ["verifiers>=0.3.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["cross_rollout_postcommitment_v1"]

```


# Project Structure:

|-- README.md
|-- cross_rollout_postcommitment_v1
    |-- __init__.py
    |-- servers
        |-- __init__.py
        |-- facility.py
    |-- state.py
    |-- taskset.py
|-- pyproject.toml

<!-- prompit: prompit environments/cross_rollout_postcommitment_v1/ -o cross_rollout_postcommitment_v1.md -s -->