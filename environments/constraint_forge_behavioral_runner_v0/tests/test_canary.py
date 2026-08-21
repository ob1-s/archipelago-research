from __future__ import annotations

import asyncio
import json

from constraint_forge_behavioral_runner_v0.canary import run_throwaway_canary
from constraint_forge_formation_v0.generator import generate_job
from test_runner import _FakeActor, _task


def _canary_targets(task):
    run_id = f"{task.data.sequence_id}:throwaway-canary"
    targets = {}
    for index in (0, 1):
        job = generate_job(f"{run_id}:ordinary:{index}")
        target = dict(job.target_matching)
        targets[tuple(job.x_mask)] = target
        targets[tuple(job.y_mask)] = target
    return targets


def test_throwaway_canary_completes_one_job_then_exactly_one_fresh_job_round() -> None:
    async def run():
        task = _task()
        targets = _canary_targets(task)
        x = _FakeActor(targets, rotate_memory=True)
        y = _FakeActor(targets, rotate_memory=True)
        result = await run_throwaway_canary(
            task.data,
            actor_x=x,
            actor_y=y,
            task=task,
        )
        return result, x, y, task

    result, x, y, task = asyncio.run(run())
    assert result.handoff.run_valid is False
    assert result.handoff.accepted is False
    assert result.handoff.aborted is False
    assert result.handoff.planned_jobs == 2
    assert result.handoff.completed_jobs == 1
    assert len(result.jobs) == 2
    assert result.jobs[0].complete is True
    assert result.jobs[1].complete is False
    assert x.interaction_count == y.interaction_count == 1
    assert len(x.contexts) == len(y.contexts) == 2
    assert result.live_model_calls == 0
    assert result.ledger.verify().valid
    scientific_seeds = set(task.data.job_seeds)
    assert all(job.job_seed not in scientific_seeds for job in result.jobs)

    # The second visible context is fresh, but it receives the role-local rack
    # naturally retained during the completed first job.
    x_second = json.loads(x.contexts[1][0])
    y_second = json.loads(y.contexts[1][0])
    assert x_second["round"] == y_second["round"] == 1
    assert x_second["observation"]["rack"]["full_films"]
    assert y_second["observation"]["rack"]["full_films"]
    assert "job-00" not in x.contexts[1][0]
    assert "job-00" not in y.contexts[1][0]
