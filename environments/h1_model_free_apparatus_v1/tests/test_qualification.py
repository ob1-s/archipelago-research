import pytest
from pydantic import ValidationError

from h1_model_free_apparatus_v1.engine import run_fixture
from h1_model_free_apparatus_v1.fixtures import FIXTURE_MANIFEST
from h1_model_free_apparatus_v1.models import FixtureOutcome, QualificationResult
from h1_model_free_apparatus_v1.qualification import run_qualification


def test_qualification_passes_every_named_gate():
    report = run_qualification()
    assert report.readiness == "PASS"
    assert all(report.gate_results.values())
    assert len(report.gate_results) == 15


def test_qualification_is_model_free_and_nonscientific():
    report = run_qualification()
    assert not report.scientific_result
    assert "no model/provider" in report.generated_by


def test_qualification_report_is_deterministic():
    assert run_qualification() == run_qualification()


def test_l5_schema_rejects_missing_durable_evidence():
    data = run_fixture(FIXTURE_MANIFEST[0]).model_dump(mode="python")
    data["provenance_events"] = ()
    data["artifact_inventory"] = ()
    with pytest.raises(ValidationError):
        FixtureOutcome.model_validate(data)


def test_qualification_cannot_mark_failed_gates_as_pass():
    data = run_qualification().model_dump(mode="python")
    data["gate_results"]["fixture_oracles_match"] = False
    with pytest.raises(ValidationError):
        QualificationResult.model_validate(data)


def test_qualification_is_structurally_nonscientific():
    data = run_qualification().model_dump(mode="python")
    data["scientific_result"] = True
    with pytest.raises(ValidationError):
        QualificationResult.model_validate(data)


def test_empty_outcomes_and_arbitrary_truthy_gate_cannot_certify_pass():
    data = run_qualification().model_dump(mode="python")
    data["fixture_outcomes"] = ()
    data["factorial_outcomes"] = ()
    data["parentage_outcomes"] = ()
    data["recovery_outcomes"] = ()
    data["analysis_unit_ids"] = ()
    data["analysis_unit_count"] = 0
    data["gate_results"] = {"foo": True}
    with pytest.raises(ValidationError):
        QualificationResult.model_validate(data)
