from h1_live_runtime_adapter_v1.canonical import stable_hash
from h1_live_runtime_adapter_v1.models import L0_CLAIM
from h1_live_runtime_adapter_v1.qualification import READINESS_SCOPE


def test_qualification_is_pass_with_repairs_for_design_freeze_only(qualification_report) -> None:
    assert qualification_report["status"] == "PASS WITH REPAIRS"
    assert qualification_report["readiness_scope"] == READINESS_SCOPE
    assert qualification_report["authorized_to_run_h1"] is False
    assert len(qualification_report["required_repairs_before_preregistration_or_run"]) == 5


def test_all_mechanical_gates_pass(qualification_report) -> None:
    assert len(qualification_report["gate_results"]) == 18
    assert all(qualification_report["gate_results"].values())


def test_record_is_nonscientific_and_contains_no_live_calls_or_secret_fields(qualification_report) -> None:
    assert qualification_report["scientific_result"] is False
    assert qualification_report["live_model_calls"] == 0
    assert qualification_report["contains_secret_field"] is False
    assert qualification_report["runtime_boundary"]["live_model_calls"] == 0
    assert qualification_report["runtime_boundary"]["scientific_result"] is False


def test_exact_claim_mapping_blocks_L1_through_L5(qualification_report) -> None:
    claims = {item["level"]: item for item in qualification_report["claim_mapping"]}
    assert claims["L0"]["supported"] is True
    assert claims["L0"]["basis"] == L0_CLAIM
    assert all(not claims[f"L{level}"]["supported"] for level in range(1, 6))
    assert all(item["scientific_evidence"] is False for item in claims.values())


def test_runtime_fixtures_A_through_F_fail_and_G_pass(qualification_report) -> None:
    fixtures = qualification_report["runtime_fixture_assessments"]
    names = list(fixtures)
    assert names == [
        "A-session-continuation",
        "B-reused-worker",
        "C-filesystem-leak",
        "D-env-cache-leak",
        "E-signing-key-reuse",
        "F-undeclared-carrier",
        "G-clean-declared-carrier",
    ]
    assert all(not fixtures[name]["clean"] for name in names[:6])
    assert fixtures[names[-1]]["clean"]


def test_readiness_has_exactly_nineteen_adjudicated_questions(qualification_report) -> None:
    questions = qualification_report["readiness_questions"]
    assert [item["question_id"] for item in questions] == [
        f"Q{index:02d}" for index in range(1, 20)
    ]
    assert {item["status"] for item in questions} == {"PASS", "PASS WITH REPAIRS"}
    repairs = {item["question_id"] for item in questions if item["status"] != "PASS"}
    assert repairs == {"Q07", "Q13", "Q14", "Q15"}


def test_original_model_free_report_still_has_15_of_15_gates(qualification_report) -> None:
    original = qualification_report["model_free_regression"]
    assert original["apparatus_version"] == "h1-model-free-apparatus/v1"
    assert original["readiness"] == "PASS"
    assert original["gate_count"] == 15
    assert all(original["gate_results"].values())
    assert (original["fixture_count"], original["factorial_count"], original["parentage_count"], original["recovery_count"]) == (10, 4, 6, 7)


def test_durable_record_contains_required_mechanical_evidence(qualification_report) -> None:
    evidence = qualification_report["runtime_boundary"]
    assert evidence["runtime_versions"].keys() >= {
        "adapter_package", "python", "bubblewrap", "verifiers", "openai", "cryptography"
    }
    assert evidence["backend_version"] == "scripted-mechanical/v1"
    assert evidence["predecessors"] and evidence["successors"]
    assert evidence["teardowns"]
    assert evidence["carrier_records"][0]["writer"]["signature_b64"]
    assert evidence["carrier_records"][0]["write_capability_hash"]
    assert evidence["carrier_records"][0]["read_capability_hashes"]
    assert len(evidence["carrier_capabilities"]) == 2
    assert evidence["schedule_contract"]["schedule_hash"]
    assert evidence["predecessors"][0]["identity"]["registration_signature_b64"]
    assert evidence["retry_attempts"][0]["wire_attempt_id"]
    assert evidence["provider_output_hash"]
    assert evidence["provider_gateway_receipt"]["signature_b64"]
    assert evidence["provider_response_acceptance"]["signature_b64"]
    assert evidence["provider_request_action"]["action"] == "provider_request"
    assert evidence["predecessor_canary"]["action"]["action"] == "write_canaries"
    assert evidence["successor_path_probe_action"]["action"] == "probe_paths"
    assert evidence["network_probe_action"]["action"] == "network_probe"
    assert evidence["residual_opaque_state"]
    assert evidence["provider_storage_observed"] is False
    unsigned = {
        key: value
        for key, value in qualification_report.items()
        if key != "record_hash"
    }
    assert qualification_report["record_hash"] == stable_hash(unsigned)
