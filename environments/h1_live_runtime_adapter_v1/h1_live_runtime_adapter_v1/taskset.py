"""Native v1 typed manifest adapter. It never launches a model."""

from __future__ import annotations

import verifiers.v1 as vf


class H1LiveRuntimeTaskData(vf.TaskData):
    qualification_only: bool = True
    scientific_result: bool = False


class H1LiveRuntimeTaskConfig(vf.TaskConfig):
    """No behavioral or stochastic task configuration is accepted."""


class H1LiveRuntimeTask(
    vf.Task[H1LiveRuntimeTaskData, vf.State, H1LiveRuntimeTaskConfig]
):
    async def validate(self, runtime: vf.Runtime) -> bool:
        del runtime
        return self.data.qualification_only and not self.data.scientific_result

    async def finalize(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        del runtime
        trace.info["h1_live_runtime_adapter"] = {
            "qualification_only": True,
            "scientific_result": False,
            "live_model_calls": 0,
        }

    @vf.metric
    async def scientific_result(self, trace: vf.Trace) -> float:
        del trace
        return 0.0


class H1LiveRuntimeTasksetConfig(vf.TasksetConfig):
    task: H1LiveRuntimeTaskConfig = H1LiveRuntimeTaskConfig()


class H1LiveRuntimeTaskset(
    vf.Taskset[H1LiveRuntimeTask, H1LiveRuntimeTasksetConfig]
):
    def load(self) -> list[H1LiveRuntimeTask]:
        return [
            H1LiveRuntimeTask(
                H1LiveRuntimeTaskData(
                    idx=0,
                    name="mechanical-runtime-boundary-qualification",
                    description="Nonscientific mechanical manifest; do not run as H1.",
                    prompt=None,
                    network_allow=[],
                ),
                self.config.task,
            )
        ]


__all__ = ["H1LiveRuntimeTaskset"]
