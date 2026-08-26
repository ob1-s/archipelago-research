"""R1 register-coded adjudication and prompt-privacy regressions."""

from __future__ import annotations

import asyncio
import types

from constraint_forge_formation_v0.canonical import stable_hash

from constraint_forge_behavioral_runner_r1.requests import round_request
from constraint_forge_behavioral_runner_r1.r1_physics import (
    final_register0_symbols,
    r1_adjudicate,
    r1_void,
    station_note,
)
from test_runner import _FakeActor, _targets, _task


def _event(kind, source="environment", action_id=None, payload=None, legal=None):
    return types.SimpleNamespace(
        event_kind=kind,
        source=source,
        action_id=action_id,
        action_payload=payload,
        legal=legal,
        detail={},
    )


def test_void_is_deterministic_and_in_domain() -> None:
    seed = "constraint-forge/r1-qualification-v0:0:job:3"
    assert r1_void(seed) == r1_void(seed)
    assert r1_void(seed) == int(stable_hash({"void": seed})[:8], 16) % 4
    assert all(0 <= r1_void(f"s:{i}") <= 3 for i in range(200))


def test_register0_extraction_joins_delivered_writes_and_ignores_suppressed() -> None:
    events = [
        _event(
            "ACTION_SUBMITTED",
            "X",
            "X:r1",
            {"action": "write", "register": 0, "symbol": 2},
            True,
        ),
        _event(
            "ACTION_SUBMITTED",
            "Y",
            "Y:r1",
            {"action": "write", "register": 0, "symbol": 3},
            True,
        ),
        _event("WRITE_DELIVERED", "X", "X:r1"),
        _event("WRITE_DELIVERED", "Y", "Y:r1"),
        _event(
            "ACTION_SUBMITTED",
            "Y",
            "Y:r2",
            {"action": "write", "register": 0, "symbol": 1},
            True,
        ),
    ]
    assert final_register0_symbols(events) == (2, 3)


def test_adjudicate_truth_table() -> None:
    base = dict(job_seed="s", events=())
    assert r1_adjudicate(world_success=False, **base)["success"] is False
    ev_x = [_event("ACTION_SUBMITTED", "X", "a", {"action": "write", "register": 0, "symbol": 1}, True), _event("WRITE_DELIVERED", "X", "a")]
    ev_y = [_event("ACTION_SUBMITTED", "Y", "b", {"action": "write", "register": 0, "symbol": 1}, True), _event("WRITE_DELIVERED", "Y", "b")]
    void_one = next(seed for seed in (f"t{i}" for i in range(500)) if r1_void(seed) == 1)
    void_other = next(seed for seed in (f"u{i}" for i in range(500)) if r1_void(seed) != 1)
    assert r1_adjudicate(world_success=True, job_seed=void_one, events=ev_x + ev_y)["success"] is False
    assert r1_adjudicate(world_success=True, job_seed=void_other, events=ev_x + ev_y)["success"] is True
    assert r1_adjudicate(world_success=True, job_seed=void_other, events=ev_x)["success"] is False


def test_station_note_privacy() -> None:
    from constraint_forge_formation_v0.models import RegisterState, Station
    from constraint_forge_formation_v0.rack import empty_rack, full_rack_view
    from constraint_forge_formation_v0.world import Observation

    observation = Observation(
        station=Station.X,
        round=1,
        private_pairs=(),
        layers={"X": tuple([None] * 6), "Y": tuple([None] * 6)},
        registers={
            "X": (RegisterState(), RegisterState()),
            "Y": (RegisterState(), RegisterState()),
        },
        remaining={},
        finished={"X": False, "Y": False},
        rack=full_rack_view(empty_rack()),
    )
    y_x_base_instructions = None
    request = round_request(
        role="X",
        job_index=0,
        job_id="j",
        context_epoch=0,
        pre_state_hash="h",
        observation=observation,
        station_note=station_note(2),
    )
    assert "void symbol for register 0 is 2" in request.instructions
    from constraint_forge_behavioral_runner_r1.protocol import model_instructions as mi

    assert request.instructions == mi("X") + "\n\n" + station_note(2)
    y_x_base_instructions = mi("Y")
    y_request = round_request(
        role="Y",
        job_index=0,
        job_id="j",
        context_epoch=0,
        pre_state_hash="h",
        observation=observation,
    )
    assert "void symbol for register 0 is" not in y_request.instructions
    assert y_request.instructions == y_x_base_instructions
    try:
        round_request(
            role="Y",
            job_index=0,
            job_id="j",
            context_epoch=0,
            pre_state_hash="h",
            observation=observation,
            station_note=station_note(2),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("station note must be rejected for station Y")


def test_conjunct_bites_on_void_collision_dyad_wide() -> None:
    from constraint_forge_behavioral_runner_r1.runner import run_behavioral_sequence

    async def run():
        task = _task()
        targets = _targets(task)
        return await run_behavioral_sequence(
            task.data,
            actor_x=_ZeroWriter(targets),
            actor_y=_FakeActor(targets),
            task=task,
        )

    result = asyncio.run(run())
    receipts = result.handoff.job_receipts
    collided = [r for r in receipts if r.world_success and not r.success]
    agreed = [r for r in receipts if r.success]
    assert collided, "a void-0 job must fail the always-zero convention"
    assert all(r.x_register0_final == 0 and r.y_register0_final == 0 for r in collided)
    assert agreed, "non-zero-void jobs must still succeed under the convention"
    assert all(r.void_symbol == r1_void(r.job_seed) for r in receipts)


class _ZeroWriter(_FakeActor):
    def __init__(self, target_by_mask):
        super().__init__(target_by_mask, force_void_collision=True)
