"""R2 difficulty knobs: configure() must move world physics before a session."""

from __future__ import annotations

import pytest

from constraint_forge_behavioral_runner_r2._r2_world._config import CONFIG, configure
from constraint_forge_behavioral_runner_r2._r2_world.generator import generate_job
from constraint_forge_behavioral_runner_r2._r2_world.models import Station
from constraint_forge_behavioral_runner_r2._r2_world.session import (
    ConstraintForgeJobSession,
)


@pytest.fixture()
def restored_config():
    saved = dict(CONFIG)
    yield
    configure(**saved)


def test_difficulty_knobs_move_round_cap_and_mutation_budget(restored_config) -> None:
    configure(max_rounds=24, mutation_budget=12, write_budget=4)
    assert CONFIG["max_rounds"] == 24
    job = generate_job(8)
    session = ConstraintForgeJobSession.open(
        job,
        run_id="r",
        lineage_id="l",
        job_id="j",
        read_only_probe=True,
    )
    offer = session.begin_round()
    assert session.state.rounds_remaining == 24
    for observation in (offer.observation_x, offer.observation_y):
        assert observation.remaining["rounds"]["value"] == 24
        assert observation.remaining["X"]["mutations"] == 12
        assert observation.remaining["Y"]["mutations"] == 12
        assert observation.remaining["X"]["writes"] == 4
        assert observation.remaining["Y"]["writes"] == 4
