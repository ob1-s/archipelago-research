import pytest

from h1_model_free_apparatus_v1.engine import run_fixture
from h1_model_free_apparatus_v1.fixtures import FIXTURE_MANIFEST, oracle_errors
from h1_model_free_apparatus_v1.models import FixtureKind


@pytest.mark.parametrize("case", FIXTURE_MANIFEST, ids=lambda case: case.case_id)
def test_fixture_matches_frozen_oracle(case):
    assert oracle_errors(run_fixture(case)) == ()


def test_complete_positive_reaches_only_bounded_l5_claim():
    outcome = run_fixture(FIXTURE_MANIFEST[0])
    assert outcome.claims.l5_routine_reconstruction
    assert "organizational continuity" in outcome.disallowed_claims
    assert outcome.routine_fidelity == 1.0


def test_all_fixture_records_are_model_free():
    for case in FIXTURE_MANIFEST:
        outcome = run_fixture(case)
        assert not any(
            "model" in event.action.lower()
            for event in outcome.provenance_events
            if event.action
        )


def test_negative_fixture_kinds_never_reach_l5():
    for case in FIXTURE_MANIFEST:
        if case.fixture is not FixtureKind.COMPLETE_TURNOVER:
            assert not run_fixture(case).claims.l5_routine_reconstruction
