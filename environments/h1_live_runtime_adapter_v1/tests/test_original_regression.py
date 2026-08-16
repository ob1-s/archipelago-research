from h1_model_free_apparatus_v1.qualification import run_qualification


def test_original_model_free_qualification_remains_exactly_pass() -> None:
    report = run_qualification()
    assert report.readiness == "PASS"
    assert len(report.gate_results) == 15
    assert all(report.gate_results.values())
    assert len(report.fixture_outcomes) == 10
    assert len(report.factorial_outcomes) == 4
    assert len(report.parentage_outcomes) == 6
    assert len(report.recovery_outcomes) == 7
    assert report.scientific_result is False
