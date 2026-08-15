import asyncio

import verifiers.v1 as vf

from h1_model_free_apparatus_v1 import H1ModelFreeTaskset
from h1_model_free_apparatus_v1.fixtures import FIXTURE_MANIFEST
from h1_model_free_apparatus_v1.taskset import H1ModelFreeTasksetConfig


def taskset():
    return H1ModelFreeTaskset(H1ModelFreeTasksetConfig(id="h1-model-free-apparatus-v1"))


def test_native_v1_taskset_loads_frozen_manifest():
    tasks = list(taskset())
    assert len(tasks) == len(FIXTURE_MANIFEST)
    assert [task.data.case for task in tasks] == list(FIXTURE_MANIFEST)
    assert all(task.data.prompt is None for task in tasks)
    assert all(task.data.network_allow == [] for task in tasks)


def test_taskset_exports_exactly_one_taskset_class():
    import h1_model_free_apparatus_v1 as package

    assert package.__all__ == ["H1ModelFreeTaskset"]
    assert issubclass(package.H1ModelFreeTaskset, vf.Taskset)


def test_task_validation_is_model_free_and_accepts_all_oracles():
    for task in taskset():
        assert asyncio.run(task.validate(runtime=None))


def test_task_type_is_concrete():
    assert H1ModelFreeTaskset.task_type().__name__ == "H1ModelFreeTask"
