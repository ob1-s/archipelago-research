"""Native one-turn Phase-1 label/interface diagnostic."""

from __future__ import annotations

import json
from typing import Literal

import verifiers.v1 as vf
from verifiers.v1.harnesses.null import NullHarnessConfig
from verifiers.v1.types import AssistantMessage

from . import randomness
from .constants import (
    LabelSet,
    expected_schema_enum,
    labels_for,
    render_prompt,
)
from .schedule import SCHEDULE_SEED, TOTAL_ROLLOUTS, build_schedule
from .servers.facility import (
    ABASchemaFacility,
    ABBSchemaFacility,
    DiagnosticToolsetConfig,
    KMKSchemaFacility,
    KMMESchemaFacility,
)
from .state import DrawRecord, LabelDiagnosticState

SCHEMA_TOOLSETS = {
    "AB_A": ABASchemaFacility,
    "AB_B": ABBSchemaFacility,
    "KM_K": KMKSchemaFacility,
    "KM_M": KMMESchemaFacility,
}


class LabelDiagnosticTaskData(vf.TaskData):
    label_set: LabelSet
    random_seed: str
    descriptive_order: str
    instruction_order: str
    schema_order: str
    schema_variant: Literal["AB_A", "AB_B", "KM_K", "KM_M"]
    schedule_seed: str
    schedule_index: int
    cell_key: str
    prompt: str


class LabelDiagnosticTaskConfig(vf.TaskConfig):
    tools: DiagnosticToolsetConfig = DiagnosticToolsetConfig()


class LabelDiagnosticTask(
    vf.Task[LabelDiagnosticTaskData, LabelDiagnosticState, LabelDiagnosticTaskConfig]
):
    @classmethod
    def toolsets(cls, config: LabelDiagnosticTaskConfig) -> list[vf.Toolset]:
        return [SCHEMA_TOOLSETS[config.tools.variant](config.tools)]

    async def setup(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        state = trace.state
        state.rollout_id = trace.id
        state.random_seed = self.data.random_seed
        state.label_set = self.data.label_set
        state.descriptive_order = self.data.descriptive_order
        state.instruction_order = self.data.instruction_order
        state.schema_order = self.data.schema_order
        state.schema_variant = self.data.schema_variant
        if self.config.tools.variant != self.data.schema_variant:
            raise RuntimeError("task/schema variant mismatch")
        profile, value, key = randomness.hidden_profile(
            self.data.random_seed, trace.id
        )
        state.hidden_profile = profile
        state.random_draws["hidden_profile"] = DrawRecord(
            namespace="hidden_profile",
            key=key,
            value=value,
            threshold=0.5,
            outcome=profile,
            matched_profile=None,
        )
        trace.info["phase1_label_attractor_diagnostic"] = {
            "random_seed": self.data.random_seed,
            "random_namespaces": list(randomness.RANDOM_NAMESPACES),
            "frozen_profile_prior": {
                "policy_1_fit": 0.5,
                "policy_2_fit": 0.5,
            },
            "label_set": self.data.label_set,
            "descriptive_order": self.data.descriptive_order,
            "instruction_order": self.data.instruction_order,
            "schema_order": self.data.schema_order,
            "schema_variant": self.data.schema_variant,
            "schedule_seed": self.data.schedule_seed,
            "schedule_index": self.data.schedule_index,
            "cell_key": self.data.cell_key,
            "prompt": self.data.prompt,
            "expected_schema_enum": expected_schema_enum(self.data.schema_variant),
            "tool_descriptions": {
                "select_policy": "Select one operating policy for the current resource.",
                "release_resource": "Execute the selected policy and close the current resource.",
            },
            "r2_present": False,
            "predecessor_information_present": False,
            "culture_information_present": False,
            "custom_harness_present": False,
            "continuation_nudge_present": False,
        }

    async def finalize(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        state = trace.state
        info = trace.info["phase1_label_attractor_diagnostic"]
        first_call_name: str | None = None
        first_argument: str | None = None
        first_policy: str | None = None
        invalid = False
        allowed = set(labels_for(self.data.label_set))
        for message in trace.assistant_messages:
            for call in message.tool_calls or []:
                if call.name.endswith("select_policy"):
                    first_call_name = call.name
                    first_argument = call.arguments
                    try:
                        arguments = json.loads(call.arguments)
                    except json.JSONDecodeError:
                        invalid = True
                        break
                    candidate = arguments.get("policy") if isinstance(arguments, dict) else None
                    if candidate in allowed:
                        first_policy = candidate
                    else:
                        invalid = True
                    break
            if first_call_name is not None:
                break
        choice = (
            "invalid"
            if invalid
            else first_policy
            if first_policy is not None
            else "missing"
        )
        events = [event.model_dump(mode="json") for event in state.events]
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
                "phase1_release_attempted": state.phase1_release_attempted,
                "natural_yield_after_r1": state.natural_yield_after_r1,
                "first_select_call_name": first_call_name,
                "first_select_call_arguments": first_argument,
                "first_select_policy": first_policy,
                "choice": choice,
                "selection_ambiguity": state.selection_ambiguity,
                "policy_selection_attempts": state.policy_selection_attempts,
                "first_failure_index": state.first_failure_index,
                "stop_condition": trace.stop_condition,
            }
        )

    @vf.metric
    async def selected_a(self, trace: vf.Trace) -> float:
        return float(trace.info["phase1_label_attractor_diagnostic"]["choice"] == "A")

    @vf.metric
    async def selected_b(self, trace: vf.Trace) -> float:
        return float(trace.info["phase1_label_attractor_diagnostic"]["choice"] == "B")

    @vf.metric
    async def selected_k(self, trace: vf.Trace) -> float:
        return float(trace.info["phase1_label_attractor_diagnostic"]["choice"] == "K")

    @vf.metric
    async def selected_m(self, trace: vf.Trace) -> float:
        return float(trace.info["phase1_label_attractor_diagnostic"]["choice"] == "M")

    @vf.metric
    async def choice_missing(self, trace: vf.Trace) -> float:
        return float(trace.info["phase1_label_attractor_diagnostic"]["choice"] == "missing")

    @vf.metric
    async def choice_invalid(self, trace: vf.Trace) -> float:
        return float(trace.info["phase1_label_attractor_diagnostic"]["choice"] == "invalid")


class DiagnosticConfig(vf.TasksetConfig):
    random_seed: str = "cross-rollout-phase1-label-attractor-diagnostic-v1-random-2026-08-13"
    schedule_seed: str = SCHEDULE_SEED
    task: LabelDiagnosticTaskConfig = LabelDiagnosticTaskConfig()


class CrossRolloutPhase1LabelAttractorDiagnosticV1Taskset(
    vf.Taskset[LabelDiagnosticTask, DiagnosticConfig]
):
    def load(self) -> list[LabelDiagnosticTask]:
        schedule = build_schedule(self.config.schedule_seed)
        if len(schedule) != TOTAL_ROLLOUTS:
            raise RuntimeError("diagnostic schedule is not exactly 160 rows")
        tasks: list[LabelDiagnosticTask] = []
        for index, cell in enumerate(schedule):
            prompt = render_prompt(
                cell.label_set,
                cell.descriptive_order,
                cell.instruction_order,
            )
            task_config = self.config.task.model_copy(
                update={
                    "tools": self.config.task.tools.model_copy(
                        update={"variant": cell.schema_variant}
                    )
                }
            )
            tasks.append(
                LabelDiagnosticTask(
                    LabelDiagnosticTaskData(
                        idx=index,
                        name=f"phase1-label-attractor-{index:03d}-{cell.key}",
                        prompt=prompt,
                        label_set=cell.label_set,
                        random_seed=self.config.random_seed,
                        descriptive_order=cell.descriptive_order,
                        instruction_order=cell.instruction_order,
                        schema_order=cell.schema_order,
                        schema_variant=cell.schema_variant,
                        schedule_seed=self.config.schedule_seed,
                        schedule_index=index,
                        cell_key=cell.key,
                    ),
                    task_config,
                )
            )
        return tasks


class DiagnosticEnvConfig(vf.EnvConfig):
    agent: vf.AgentConfig = vf.AgentConfig(
        harness=NullHarnessConfig(id="null"),
        max_turns=8,
    )


def segment_ended_naturally(segment: vf.Segment) -> bool:
    if segment.terminated:
        return False
    last_assistant = next(
        (
            message
            for message in reversed(segment.messages)
            if isinstance(message, AssistantMessage)
        ),
        None,
    )
    return last_assistant is not None and not last_assistant.tool_calls


class CrossRolloutPhase1LabelAttractorDiagnosticV1Env(
    vf.Env[DiagnosticEnvConfig]
):
    async def run(
        self,
        task: LabelDiagnosticTask,
        agents: vf.Agents,
    ) -> None:
        async with agents.agent.interaction(task) as interaction:
            segment = await interaction.turn()
            interaction.trace.state.natural_yield_after_r1 = segment_ended_naturally(segment)


__all__ = [
    "CrossRolloutPhase1LabelAttractorDiagnosticV1Env",
    "CrossRolloutPhase1LabelAttractorDiagnosticV1Taskset",
]
