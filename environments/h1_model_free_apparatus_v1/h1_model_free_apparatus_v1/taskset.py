"""Native verifiers.v1 taskset adapter for the model-free fixture manifest."""

from __future__ import annotations

import verifiers.v1 as vf

from .engine import run_fixture
from .fixtures import FIXTURE_MANIFEST, oracle_errors
from .models import FixtureCase


class H1ModelFreeTaskData(vf.TaskData):
    case: FixtureCase
    qualification_only: bool = True


class H1ModelFreeTaskConfig(vf.TaskConfig):
    """No model, judge, tool, or stochastic configuration is accepted."""


class H1ModelFreeTask(vf.Task[H1ModelFreeTaskData, vf.State, H1ModelFreeTaskConfig]):
    async def validate(self, runtime: vf.Runtime) -> bool:
        del runtime
        return not oracle_errors(run_fixture(self.data.case))

    async def finalize(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        del runtime
        outcome = run_fixture(self.data.case)
        trace.info["h1_model_free_apparatus"] = outcome.model_dump(mode="json")

    @vf.metric
    async def l0_turnover_validity(self, trace: vf.Trace) -> float:
        return float(run_fixture(self.data.case).claims.l0_turnover_validity)

    @vf.metric
    async def l1_carrier_continuity(self, trace: vf.Trace) -> float:
        return float(run_fixture(self.data.case).claims.l1_carrier_continuity)

    @vf.metric
    async def l2_functional_reuse(self, trace: vf.Trace) -> float:
        return float(run_fixture(self.data.case).claims.l2_functional_reuse)

    @vf.metric
    async def l3_endogenous_state_production(self, trace: vf.Trace) -> float:
        return float(run_fixture(self.data.case).claims.l3_endogenous_state_production)

    @vf.metric
    async def l4_causal_transmission_or_recovery(self, trace: vf.Trace) -> float:
        return float(
            run_fixture(self.data.case).claims.l4_causal_transmission_or_recovery
        )

    @vf.metric
    async def l5_routine_reconstruction(self, trace: vf.Trace) -> float:
        return float(run_fixture(self.data.case).claims.l5_routine_reconstruction)


class H1ModelFreeTasksetConfig(vf.TasksetConfig):
    task: H1ModelFreeTaskConfig = H1ModelFreeTaskConfig()


class H1ModelFreeTaskset(vf.Taskset[H1ModelFreeTask, H1ModelFreeTasksetConfig]):
    def load(self) -> list[H1ModelFreeTask]:
        return [
            H1ModelFreeTask(
                H1ModelFreeTaskData(
                    idx=index,
                    name=case.case_id,
                    description="Deterministic test oracle; not a behavioral task.",
                    prompt=None,
                    network_allow=[],
                    case=case,
                ),
                self.config.task,
            )
            for index, case in enumerate(FIXTURE_MANIFEST)
        ]


__all__ = ["H1ModelFreeTaskset"]
