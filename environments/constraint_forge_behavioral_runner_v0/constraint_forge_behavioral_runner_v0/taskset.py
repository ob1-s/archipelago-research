"""Native v1 taskset and multi-agent environment declaration."""

from __future__ import annotations

from typing import Literal

import verifiers.v1 as vf
from pydantic import Field, StrictBool, StrictInt, StrictStr
from constraint_forge_formation_v0.canonical import stable_hash
from constraint_forge_formation_v0.generator import generate_job, validate_job
from constraint_forge_formation_v0.interventions import InterventionSchedule
from constraint_forge_formation_v0.models import Seed, StrictModel

from .handoff import FormationHandoffV0
from .harness import ConstraintForgeTextHarnessConfig
from .runner import run_behavioral_sequence


NEUTRAL_SYSTEM_PROMPT = """You are one station in a deterministic Constraint Forge behavioral job sequence.
The referee sends one role-local JSON request per turn. Keep ordinary conversational
context within the current job only. Return exactly the JSON action requested by the
current request, with no prose, tools, files, streaming, or continuation state.
The other station's private observations and rack are never available to you."""


class ConstraintForgeBehavioralTaskData(vf.TaskData):
    protocol_version: Literal["constraint-forge/behavioral-runner-v0"] = (
        "constraint-forge/behavioral-runner-v0"
    )
    sequence_id: StrictStr
    job_seeds: tuple[Seed, ...] = Field(min_length=24, max_length=24)
    expected_job_hashes: tuple[StrictStr, ...] = Field(min_length=24, max_length=24)
    interventions: tuple[InterventionSchedule | None, ...] = ()
    read_only_job_indices: tuple[StrictInt, ...] = ()


class ConstraintForgeBehavioralState(vf.State):
    sequence_valid: StrictBool = False
    completed: StrictBool = False
    accepted: StrictBool = False
    aborted: StrictBool = False
    completed_jobs: StrictInt = 0
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
        if len(self.data.interventions) not in {0, len(self.data.job_seeds)}:
            raise ValueError("interventions must be empty or contain one entry per job")
        jobs = [generate_job(seed) for seed in self.data.job_seeds]
        trace.state.sequence_valid = all(
            validate_job(job).payload_hash == expected
            for job, expected in zip(jobs, self.data.expected_job_hashes)
        )
        trace.info["constraint_forge_behavioral_runner"] = {
            "protocol_version": self.data.protocol_version,
            "sequence_id": self.data.sequence_id,
            "job_count": len(self.data.job_seeds),
            "sequence_hash": stable_hash(
                {
                    "sequence_id": self.data.sequence_id,
                    "job_seeds": list(self.data.job_seeds),
                    "expected_job_hashes": list(self.data.expected_job_hashes),
                }
            ),
            "live_model_calls": 0,
        }
        if not trace.state.sequence_valid:
            raise ValueError("behavioral task data does not match deterministic generator")

    async def validate(self, runtime: vf.Runtime) -> bool:
        del runtime
        return all(
            generate_job(seed).payload_hash == expected
            for seed, expected in zip(self.data.job_seeds, self.data.expected_job_hashes)
        )

    async def finalize(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        del runtime
        info = trace.info.setdefault("constraint_forge_behavioral_runner", {})
        info["live_model_calls"] = len(trace.calls)
        trace.state.live_model_calls = len(trace.calls)
        info["completed"] = trace.state.completed
        info["accepted"] = trace.state.accepted
        info["aborted"] = trace.state.aborted
        info["completed_jobs"] = trace.state.completed_jobs
        info["handoff_hash"] = trace.state.handoff_hash

    @vf.reward
    async def formation_accepted(self, trace: vf.Trace) -> float:
        return float(trace.state.accepted and trace.state.completed)


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
            seeds = tuple(
                f"{self.config.seed_prefix}:{sequence_index}:job:{job_index}"
                for job_index in range(24)
            )
            expected = tuple(generate_job(seed).payload_hash for seed in seeds)
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
        max_turns=1024,
        retries=vf.RetryConfig(max_retries=0),
    )
    y: vf.AgentConfig = vf.AgentConfig(
        harness=ConstraintForgeTextHarnessConfig(),
        max_turns=1024,
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
        # Each interaction's trace is the v1 record for the role that produced
        # it.  The handoff is duplicated into both role traces for episode-local
        # auditability; it is not used as an H1 carrier or proof.
        for interaction in result.traces:
            interaction.trace.state.completed = result.handoff.aborted is False
            interaction.trace.state.accepted = result.handoff.accepted
            interaction.trace.state.aborted = result.handoff.aborted
            interaction.trace.state.completed_jobs = result.handoff.completed_jobs
            interaction.trace.state.handoff_hash = result.handoff.content_hash
            interaction.trace.state.live_model_calls = result.live_model_calls
            runner_info = interaction.trace.info.setdefault(
                "constraint_forge_behavioral_runner", {}
            )
            runner_info.update(
                {
                    "live_model_calls": result.live_model_calls,
                    "completed": interaction.trace.state.completed,
                    "accepted": interaction.trace.state.accepted,
                    "aborted": interaction.trace.state.aborted,
                    "completed_jobs": interaction.trace.state.completed_jobs,
                    "handoff_hash": result.handoff.content_hash,
                }
            )
            interaction.trace.info["formation_handoff_v0"] = result.handoff.model_dump(
                mode="json"
            )


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
