import pytest

from h1_model_free_apparatus_v1.engine import run_fixture
from h1_model_free_apparatus_v1.fixtures import FIXTURE_MANIFEST


@pytest.mark.parametrize(
    ("index", "fraction", "survivors", "complete", "continues"),
    [
        (1, 0.0, 4, False, True),
        (2, 0.5, 2, False, True),
        (3, 1.0, 0, True, False),
    ],
)
def test_redundant_turnover_classification(
    index, fraction, survivors, complete, continues
):
    outcome = run_fixture(FIXTURE_MANIFEST[index])
    assert outcome.turnover_fraction == fraction
    assert outcome.surviving_actor_count == survivors
    assert outcome.complete_turnover is complete
    assert outcome.turnover_valid is complete
    assert outcome.routine_execution_success is continues
    assert not outcome.claims.l5_routine_reconstruction


def test_hidden_leak_fails_closed():
    outcome = run_fixture(FIXTURE_MANIFEST[8])
    assert outcome.hidden_state_violation
    assert not outcome.turnover_valid
    assert not outcome.complete_turnover
    assert outcome.surviving_actor_count == 1
    assert not outcome.provenance.valid
    assert not any(outcome.claims.model_dump().values())
