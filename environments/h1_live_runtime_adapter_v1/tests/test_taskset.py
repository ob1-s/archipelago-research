import asyncio

import verifiers.v1 as vf

from h1_live_runtime_adapter_v1 import H1LiveRuntimeTaskset
from h1_live_runtime_adapter_v1.taskset import H1LiveRuntimeTasksetConfig


def _taskset():
    return H1LiveRuntimeTaskset(H1LiveRuntimeTasksetConfig(id="h1-live-runtime-adapter-v1"))


def test_package_exports_exactly_one_native_v1_taskset() -> None:
    import h1_live_runtime_adapter_v1 as package

    assert package.__all__ == ["H1LiveRuntimeTaskset"]
    assert issubclass(package.H1LiveRuntimeTaskset, vf.Taskset)


def test_taskset_is_one_nonscientific_manifest_with_no_prompt_or_network() -> None:
    tasks = list(_taskset())
    assert len(tasks) == 1
    task = tasks[0]
    assert task.data.prompt is None
    assert task.data.network_allow == []
    assert task.data.qualification_only is True
    assert task.data.scientific_result is False
    assert asyncio.run(task.validate(runtime=None)) is True


def test_task_type_is_concrete() -> None:
    assert H1LiveRuntimeTaskset.task_type().__name__ == "H1LiveRuntimeTask"

