"""Native v1 taskset and multi-agent environment declaration."""

from __future__ import annotations

from typing import Literal

import verifiers.v1 as vf
from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr
from constraint_forge_formation_v0.canonical import stable_hash
from constraint_forge_formation_v0.generator import generate_job, validate_job
from constraint_forge_formation_v0.interventions import InterventionSchedule
from constraint_forge_formation_v0.models import Seed

from .harness import ConstraintForgeTextHarnessConfig
from .protocol import (
    ACTION_SCHEMA_HASH,
    COMMON_INSTRUCTION_HASH,
    NEUTRAL_SYSTEM_PROMPT,
    NEUTRAL_SYSTEM_PROMPT_HASH,
    ROLE_INSTRUCTION_HASHES,
)
from .runner import run_behavioral_sequence, stamp_sequence_traces
from .schedule import JOB_COUNT, FormationRunPlan, build_run_plan


class ConstraintForgeBehavioralTaskData(vf.TaskData):
    protocol_version: Literal["constraint-forge/behavioral-runner-v0"] = (
        "constraint-forge/behavioral-runner-v0"
    )
    sequence_id: StrictStr
    job_seeds: tuple[Seed, ...] = Field(min_length=JOB_COUNT, max_length=JOB_COUNT)
    expected_job_hashes: tuple[StrictStr, ...] = Field(
        min_length=JOB_COUNT, max_length=JOB_COUNT
    )
    run_plan: FormationRunPlan
    plan_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    common_instruction_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    action_schema_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    system_prompt_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    role_instruction_hash_x: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    role_instruction_hash_y: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    # These projections are retained for simple audit consumers; the immutable
    # run_plan is authoritative and is hash-pinned into the sequence manifest.
    interventions: tuple[InterventionSchedule | None, ...] = ()
    read_only_job_indices: tuple[StrictInt, ...] = ()


class ConstraintForgeBehavioralState(vf.State):
    sequence_valid: StrictBool = False
    completed: StrictBool = False
    run_valid: StrictBool = False
    accepted: StrictBool = False
    aborted: StrictBool = False
    completed_jobs: StrictInt = 0
    successful_jobs: StrictInt = 0
    job_success_mean: StrictFloat = 0.0
    handoff_hash: StrictStr | None = None
    live_model_calls: StrictInt = 0


class ConstraintForgeBehavioralTaskConfig(vf.TaskConfig):
    """No task-level model, tool, or provider behavior is configured here."""


class ConstraintForgeBehavioralTask(
    vf.Task[
        ConstraintForgeBehavioralTaskData,
        ConstraintForgeBehavioralState,
        ConstraintForgeBehavioralTaskConfig,
    ]
):
    async def setup(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        del runtime
        jobs = [generate_job(condition.job_seed) for condition in self.data.run_plan.jobs]
        plan_matches = (
            self.data.run_plan.sequence_id == self.data.sequence_id
            and self.data.run_plan.plan_hash == self.data.plan_hash
            and tuple(condition.job_seed for condition in self.data.run_plan.jobs)
            == self.data.job_seeds
            and tuple(condition.expected_job_hash for condition in self.data.run_plan.jobs)
            == self.data.expected_job_hashes
        )
        protocol_matches = (
            self.data.common_instruction_hash == COMMON_INSTRUCTION_HASH
            and self.data.action_schema_hash == ACTION_SCHEMA_HASH
            and self.data.system_prompt_hash == NEUTRAL_SYSTEM_PROMPT_HASH
            and self.data.role_instruction_hash_x == ROLE_INSTRUCTION_HASHES["X"]
            and self.data.role_instruction_hash_y == ROLE_INSTRUCTION_HASHES["Y"]
        )
        trace.state.sequence_valid = all(
            validate_job(job).payload_hash == expected
            for job, expected in zip(jobs, self.data.expected_job_hashes)
        ) and plan_matches and protocol_matches
        trace.info["constraint_forge_behavioral_runner"] = {
            "protocol_version": self.data.protocol_version,
            "sequence_id": self.data.sequence_id,
            "job_count": len(self.data.run_plan.jobs),
            "run_plan_hash": self.data.plan_hash,
            "common_instruction_hash": self.data.common_instruction_hash,
            "action_schema_hash": self.data.action_schema_hash,
            "system_prompt_hash": self.data.system_prompt_hash,
            "role_instruction_hashes": {
                "X": self.data.role_instruction_hash_x,
                "Y": self.data.role_instruction_hash_y,
            },
            "sequence_hash": stable_hash(
                {
                    "sequence_id": self.data.sequence_id,
                    "run_plan": self.data.run_plan.model_dump(mode="json"),
                }
            ),
            "live_model_calls": 0,
        }
        if not trace.state.sequence_valid:
            raise ValueError("behavioral task data does not match deterministic generator")

    async def validate(self, runtime: vf.Runtime) -> bool:
        del runtime
        protocol_matches = (
            self.data.common_instruction_hash == COMMON_INSTRUCTION_HASH
            and self.data.action_schema_hash == ACTION_SCHEMA_HASH
            and self.data.system_prompt_hash == NEUTRAL_SYSTEM_PROMPT_HASH
            and self.data.role_instruction_hash_x == ROLE_INSTRUCTION_HASHES["X"]
            and self.data.role_instruction_hash_y == ROLE_INSTRUCTION_HASHES["Y"]
        )
        return protocol_matches and self.data.run_plan.sequence_id == self.data.sequence_id and all(
            generate_job(condition.job_seed).payload_hash == condition.expected_job_hash
            for condition in self.data.run_plan.jobs
        ) and self.data.run_plan.plan_hash == self.data.plan_hash

    async def finalize(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        del runtime
        info = trace.info.setdefault("constraint_forge_behavioral_runner", {})
        info["live_model_calls"] = len(trace.calls)
        trace.state.live_model_calls = len(trace.calls)
        info["completed"] = trace.state.completed
        info["run_valid"] = trace.state.run_valid
        info["accepted"] = trace.state.accepted
        info["aborted"] = trace.state.aborted
        info["completed_jobs"] = trace.state.completed_jobs
        info["successful_jobs"] = trace.state.successful_jobs
        info["job_success_mean"] = trace.state.job_success_mean
        info["handoff_hash"] = trace.state.handoff_hash

    @vf.reward
    async def formation_accepted(self, trace: vf.Trace) -> float:
        # This is the frozen behavioral reward: mean job success.  Infrastructure
        # validity is separate.  An infrastructure-invalid partial dyad remains
        # audit-only and cannot receive a positive behavioral reward.
        return float(trace.state.job_success_mean if trace.state.run_valid else 0.0)


class ConstraintForgeBehavioralTasksetConfig(vf.TasksetConfig):
    seed_prefix: StrictStr = "constraint-forge/behavioral-sequence-v0"
    num_sequences: StrictInt = Field(default=1, ge=1, le=100_000)
    task: ConstraintForgeBehavioralTaskConfig = ConstraintForgeBehavioralTaskConfig()


class ConstraintForgeBehavioralTaskset(
    vf.Taskset[ConstraintForgeBehavioralTask, ConstraintForgeBehavioralTasksetConfig]
):
    def load(self) -> list[ConstraintForgeBehavioralTask]:
        tasks: list[ConstraintForgeBehavioralTask] = []
        for sequence_index in range(self.config.num_sequences):
            sequence_id = f"sequence-{sequence_index:06d}"
            plan = build_run_plan(
                sequence_id=sequence_id,
                sequence_index=sequence_index,
                seed_prefix=self.config.seed_prefix,
            )
            seeds = tuple(condition.job_seed for condition in plan.jobs)
            expected = tuple(condition.expected_job_hash for condition in plan.jobs)
            tasks.append(
                ConstraintForgeBehavioralTask(
                    ConstraintForgeBehavioralTaskData(
                        idx=sequence_index,
                        name=f"constraint-forge-behavioral-sequence-{sequence_index}",
                        description="One deterministic 24-job multi-agent formation sequence.",
                        prompt=None,
                        system_prompt=NEUTRAL_SYSTEM_PROMPT,
                        network_allow=[],
                        network_block=["*"],
                        sequence_id=sequence_id,
                        job_seeds=seeds,
                        expected_job_hashes=expected,
                        run_plan=plan,
                        plan_hash=plan.plan_hash,
                        common_instruction_hash=COMMON_INSTRUCTION_HASH,
                        action_schema_hash=ACTION_SCHEMA_HASH,
                        system_prompt_hash=NEUTRAL_SYSTEM_PROMPT_HASH,
                        role_instruction_hash_x=ROLE_INSTRUCTION_HASHES["X"],
                        role_instruction_hash_y=ROLE_INSTRUCTION_HASHES["Y"],
                        interventions=tuple(condition.intervention for condition in plan.jobs),
                        read_only_job_indices=tuple(
                            condition.job_index
                            for condition in plan.jobs
                            if condition.read_only_probe
                        ),
                    ),
                    self.config.task,
                )
            )
        return tasks


class ConstraintForgeBehavioralEnvConfig(vf.EnvConfig):
    """Two role-local agents, both pinned to the minimal built-in text harness."""

    id: StrictStr = "constraint-forge-behavioral-runner-v0"
    taskset: ConstraintForgeBehavioralTasksetConfig = ConstraintForgeBehavioralTasksetConfig(
        id="constraint-forge-behavioral-runner-v0"
    )
    x: vf.AgentConfig = vf.AgentConfig(
        harness=ConstraintForgeTextHarnessConfig(),
        max_turns=420,
        retries=vf.RetryConfig(max_retries=0),
    )
    y: vf.AgentConfig = vf.AgentConfig(
        harness=ConstraintForgeTextHarnessConfig(),
        max_turns=420,
        retries=vf.RetryConfig(max_retries=0),
    )
    retries: vf.RetryConfig = vf.RetryConfig(max_retries=0)
    max_concurrent_agents: StrictInt = Field(default=2, ge=1)


class ConstraintForgeBehavioralEnv(vf.Env[ConstraintForgeBehavioralEnvConfig]):
    """The ordinary v1 multi-agent referee for one 24-job sequence."""

    async def run(
        self,
        task: ConstraintForgeBehavioralTask,
        agents: vf.Agents,
    ) -> None:
        result = await run_behavioral_sequence(
            task.data,
            actor_x=agents.x,
            actor_y=agents.y,
            task=task,
        )
        # run_behavioral_sequence stamps the already-closed native v1 traces;
        # this idempotent call keeps Env.run's contract explicit for callers
        # that provide a custom SequenceResult implementation.
        stamp_sequence_traces(result)


__all__ = [
    "ConstraintForgeBehavioralEnv",
    "ConstraintForgeBehavioralEnvConfig",
    "ConstraintForgeBehavioralState",
    "ConstraintForgeBehavioralTask",
    "ConstraintForgeBehavioralTaskConfig",
    "ConstraintForgeBehavioralTaskData",
    "ConstraintForgeBehavioralTaskset",
    "ConstraintForgeBehavioralTasksetConfig",
    "NEUTRAL_SYSTEM_PROMPT",
]
