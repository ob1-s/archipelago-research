"""Native v1 taskset wrapper for model-free Constraint Forge job records."""

from __future__ import annotations

from typing import Literal

import verifiers.v1 as vf
from pydantic import Field, StrictInt, StrictStr

from .canonical import stable_hash
from .generator import generate_job, validate_job
from .models import JobRecord, MutableStrictModel, Seed

COMMON_INSTRUCTION_TEMPLATE = """You operate station {X|Y}. Each job has six items and six targets. Your private panel lists the item-target pairs accepted by this station. The other station has a different private panel that you cannot see.

The pair succeeds only if both stations finish with the same complete one-to-one assignment and every selected pair is accepted by both private panels. The two private panels jointly admit exactly one successful assignment. Your panel alone admits more than one.

At job start you receive your station's retained film rack. At each round you receive your private panel, both public assignment layers, the public registers, and remaining budgets. Choose exactly one available action. Your ordinary response text is not shown to the other station and is not retained between jobs.

A retained film is a six-round window from your own observations and actions. It remains available to this station on later jobs. The rack holds at most six films."""


class ConstraintForgeTaskData(vf.TaskData):
    job_seed: Seed
    expected_job_hash: StrictStr
    protocol_version: Literal["constraint-forge/exploration-v0"] = (
        "constraint-forge/exploration-v0"
    )


class ConstraintForgeState(vf.State):
    job: JobRecord | None = None
    generator_valid: bool = False
    success: bool = False


class ConstraintForgeTaskConfig(vf.TaskConfig):
    """No provider, tool, harness, or stochastic behavioral configuration."""


class ConstraintForgeTask(
    vf.Task[ConstraintForgeTaskData, ConstraintForgeState, ConstraintForgeTaskConfig]
):
    async def setup(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        del runtime
        job = generate_job(self.data.job_seed)
        trace.state.job = job
        trace.state.generator_valid = job.payload_hash == self.data.expected_job_hash
        trace.info["constraint_forge"] = {
            "protocol_version": self.data.protocol_version,
            "generator_hash": job.payload_hash,
            "instruction_hash": stable_hash(COMMON_INSTRUCTION_TEMPLATE),
            "live_model_calls": 0,
        }

    async def validate(self, runtime: vf.Runtime) -> bool:
        del runtime
        job = generate_job(self.data.job_seed)
        validate_job(job)
        return job.payload_hash == self.data.expected_job_hash

    async def finalize(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        del runtime
        job = trace.state.job or generate_job(self.data.job_seed)
        trace.info["constraint_forge"].update(
            {
                "generator_valid": trace.state.generator_valid,
                "job_payload": job.payload,
                "job_hash": job.payload_hash,
                "success": trace.state.success,
            }
        )

    @vf.reward
    async def job_success(self, trace: vf.Trace) -> float:
        return float(trace.state.success)


class ConstraintForgeTasksetConfig(vf.TasksetConfig):
    seed_prefix: StrictStr = "constraint-forge/world-v0"
    num_jobs: StrictInt = Field(default=1, ge=1, le=100_000)
    task: ConstraintForgeTaskConfig = ConstraintForgeTaskConfig()


class ConstraintForgeFormationV0Taskset(
    vf.Taskset[ConstraintForgeTask, ConstraintForgeTasksetConfig]
):
    def load(self) -> list[ConstraintForgeTask]:
        tasks: list[ConstraintForgeTask] = []
        for index in range(self.config.num_jobs):
            seed = f"{self.config.seed_prefix}:{index}"
            job = generate_job(seed)
            tasks.append(
                ConstraintForgeTask(
                    ConstraintForgeTaskData(
                        idx=index,
                        name=f"constraint-forge-job-{index}",
                        description="Model-free generator/state validation only.",
                        prompt=COMMON_INSTRUCTION_TEMPLATE,
                        network_allow=[],
                        job_seed=seed,
                        expected_job_hash=job.payload_hash,
                    ),
                    self.config.task,
                )
            )
        return tasks


__all__ = ["ConstraintForgeFormationV0Taskset"]
