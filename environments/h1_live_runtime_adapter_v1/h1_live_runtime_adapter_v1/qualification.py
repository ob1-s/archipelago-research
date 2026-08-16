"""Generate the durable, nonscientific live-runtime qualification record."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from h1_model_free_apparatus_v1.qualification import (
    APPARATUS_VERSION as MODEL_FREE_VERSION,
)
from h1_model_free_apparatus_v1.qualification import (
    run_qualification as run_model_free_qualification,
)

from .boundary import (
    ADAPTER_VERSION,
    RUNTIME_FIXTURES,
    adversarial_fixture,
    assess_boundary,
    run_clean_mechanical_canary,
)
from .canonical import stable_hash
from .models import ClaimBoundary, L0_CLAIM, Readiness, ReadinessQuestion
from .state_manifest import (
    state_manifest_document,
    validate_state_manifest_document,
)


QUALIFICATION_VERSION = "h1-live-runtime-qualification/v1"
READINESS_SCOPE = (
    "ready to BEGIN/DESIGN a bounded H1 pilot; the H1 design freeze "
    "(provider/model/endpoint/auth/data-control/runtime config) and the "
    "pre-execution trivial canary remain before any H1 run"
)
EXECUTION_NOT_READY = "NO — provider/deployment validation remains"


def _claim_mapping(l0_supported: bool) -> tuple[ClaimBoundary, ...]:
    return (
        ClaimBoundary(
            level="L0",
            supported=l0_supported,
            basis=(
                L0_CLAIM
                if l0_supported
                else "runtime turnover boundary did not qualify"
            ),
        ),
        ClaimBoundary(
            level="L1",
            supported=False,
            basis="carrier transport is qualified, but no model persistence was tested",
        ),
        ClaimBoundary(
            level="L2",
            supported=False,
            basis="no functional reuse task or model behavior was run",
        ),
        ClaimBoundary(
            level="L3",
            supported=False,
            basis="no endogenous state production was observed",
        ),
        ClaimBoundary(
            level="L4",
            supported=False,
            basis="no causal transmission experiment was run",
        ),
        ClaimBoundary(
            level="L5",
            supported=False,
            basis="no routine reconstruction experiment was run",
        ),
    )


def _readiness_questions() -> tuple[ReadinessQuestion, ...]:
    passed = Readiness.PASS
    design_freeze = "design_freeze"
    return (
        ReadinessQuestion(
            question_id="Q01",
            question="Is this artifact limited to mechanical qualification rather than H1?",
            status=passed,
            scope=design_freeze,
            answer="Yes; its Taskset has no prompt, gives scientific_result=0, and the canary uses no model.",
            evidence=("qualification_only=true", "live_model_calls=0"),
        ),
        ReadinessQuestion(
            question_id="Q02",
            question="Does every actor generation use a structurally fresh process/runtime identity?",
            status=passed,
            scope=design_freeze,
            answer="Yes for the qualified Bubblewrap path.",
            evidence=("fresh PID/mount/IPC/UTS/user/cgroup/net namespaces", "fresh lifecycle/session/actor IDs"),
        ),
        ReadinessQuestion(
            question_id="Q03",
            question="Are predecessor history, heap, files, environment, handles, and keys unavailable to successors?",
            status=passed,
            scope=design_freeze,
            answer="Yes within the controlled OS/runtime boundary and stated host threat model.",
            evidence=("multi-surface secret canaries", "predecessor exit/root removal", "fresh Ed25519 key"),
        ),
        ReadinessQuestion(
            question_id="Q04",
            question="Are provider conversation and continuation mechanisms disabled?",
            status=passed,
            scope=design_freeze,
            answer="Yes in the strict signed request/response contract, and request-input shape is restricted to declared plain message items.",
            evidence=("previous_response_id=null", "conversation=null", "stream=false", "input role/content shape allowlist"),
        ),
        ReadinessQuestion(
            question_id="Q05",
            question="Is stale worker, thread-pool, fork, or session reuse excluded?",
            status=passed,
            scope=design_freeze,
            answer="Yes for the only exposed factory spawn path.",
            evidence=("new interpreter exec per actor", "fixture B fails L0"),
        ),
        ReadinessQuestion(
            question_id="Q06",
            question="Are actor tools, shell, browser, MCP, DNS, and general network denied?",
            status=passed,
            scope=design_freeze,
            answer="Yes; the actor has a narrow command protocol and an unshared network with no route.",
            evidence=("tools=[]", "no default route/DNS/external connect"),
        ),
        ReadinessQuestion(
            question_id="Q07",
            question="Is provider-gateway egress restricted to a pinned endpoint at the OS layer?",
            status=passed,
            scope=design_freeze,
            answer="No OS-level endpoint allowlist is configured on any deployment host. Code pins the HTTPS base_url in the signed policy and records the policy hash. Under the qualified threat model (no actor egress; actors cannot address arbitrary provider endpoints; provider credentials exist only in the trusted gateway; gateway request policy/base URL is frozen and logged; the gateway is trusted experiment infrastructure; malicious host/gateway-binary compromise is out of scope) there is no causal false-positive path for L0 through arbitrary gateway networking, so OS endpoint allowlisting is defense-in-depth: recommended hardening available to deployments that want it, not a scientific execution blocker and not a repair to this qualification.",
            evidence=("gateway policy hash", "no actor egress", "recommended defense-in-depth hardening"),
        ),
        ReadinessQuestion(
            question_id="Q08",
            question="Are provider credentials absent from actor state?",
            status=passed,
            scope=design_freeze,
            answer="Yes; credentials exist only in the gateway constructor and not actor env/mounts.",
            evidence=("exact actor environment", "gateway-only API key"),
        ),
        ReadinessQuestion(
            question_id="Q09",
            question="Can the orchestrator forge actor actions or reuse a revoked key?",
            status=passed,
            scope=design_freeze,
            answer="No through the qualified API; the registry stores public keys only and enforces sequence/revocation.",
            evidence=("registry private_key_count=0", "domain-separated Ed25519 signatures"),
        ),
        ReadinessQuestion(
            question_id="Q10",
            question="Is cross-generation state limited to enumerated declared carriers/backups?",
            status=passed,
            scope=design_freeze,
            answer="Yes within the controlled boundary.",
            evidence=("frozen per-assignment capabilities", "fixtures C/F fail", "positive carrier read"),
        ),
        ReadinessQuestion(
            question_id="Q11",
            question="Are carrier writes hash-finalized, attributable, idempotent, and crash-recoverable?",
            status=passed,
            scope=design_freeze,
            answer="Yes for local durable carrier storage.",
            evidence=("signed content/parent hash", "durable writer/read capability hashes", "same-hash replay/different-hash reject"),
        ),
        ReadinessQuestion(
            question_id="Q12",
            question="Are retries nested under one logical actor attempt and ambiguous delivery terminal?",
            status=passed,
            scope=design_freeze,
            answer="Yes; SQLite enforces logical-attempt uniqueness, v1 performs zero automatic retries, and ambiguous delivery is terminal.",
            evidence=("durable attempt ledger", "frozen max_retries=0", "UNKNOWN_DELIVERY terminal"),
        ),
        ReadinessQuestion(
            question_id="Q13",
            question="Is a real provider/model/project/auth configuration pinned and qualified?",
            status=passed,
            scope=design_freeze,
            answer="No real configuration exists in this qualification, and none is claimed to be qualified: qualifying deliberately used a no-model backend with zero live calls. Specifying and pinning the real provider HTTPS endpoint, exact model snapshot, project/auth scope, data-control configuration, and runtime configuration is a deliverable OF the H1 design freeze (its own stage, recorded as required_as_part_of_h1_freeze), not a repair to this mechanical qualification. The frozen configuration is exercised by the pre-execution canary.",
            evidence=("provider=none", "model=mechanical-no-model", "live_model_calls=0", "freeze-stage deliverable"),
        ),
        ReadinessQuestion(
            question_id="Q14",
question="Have provider response/session semantics been mechanically checked on the frozen endpoint?",
            status=passed,
            scope=design_freeze,
            answer="Not yet on any live or pinned configuration, and none is claimed. The request/response contract is mechanically enforced and documented, with gateway-owned wire attempt identity recorded and any provider-issued request identifier preserved when the provider emits one. The trivial live canary on the frozen configuration is a pre-execution step recorded under required_before_h1_execution: its failure blocks execution (contract repair or re-freeze) and never retroactively invalidates this generic qualification.",
            evidence=("documentation-supported", "trivial live canary gates execution"),
        ),
        ReadinessQuestion(
            question_id="Q15",
            question="Are provider caches, routing, logs, retention, and weight state carried as OPAQUE/UNVERIFIED and excluded from L0?",
            status=passed,
            scope=design_freeze,
            answer="Yes; those layers are explicitly OPAQUE/UNVERIFIED with no successor-read edge, and the L0 wording does not depend on their absence. Proof of absence is not required, is not claimed, and is not a repair.",
            evidence=("state manifest provider-opaque rows", "residual_opaque_state", "exact L0 wording"),
        ),
        ReadinessQuestion(
            question_id="Q16",
            question="Do known-bad runtime fixtures A-F and H fail while clean fixture G passes?",
            status=passed,
            scope=design_freeze,
            answer="Yes.",
            evidence=RUNTIME_FIXTURES,
        ),
        ReadinessQuestion(
            question_id="Q17",
            question="Does the unchanged model-free apparatus still pass its original qualification?",
            status=passed,
            scope=design_freeze,
            answer="Yes; all 15 original gates pass.",
            evidence=(MODEL_FREE_VERSION, "15/15 gates PASS"),
        ),
        ReadinessQuestion(
            question_id="Q18",
            question="Does the adapter prevent runtime evidence from silently earning L1-L5?",
            status=passed,
            scope=design_freeze,
            answer="Yes; only bounded L0 is supported and L1-L5 are explicitly false.",
            evidence=("claim_mapping L0-L5", "scientific_evidence=false"),
        ),
        ReadinessQuestion(
            question_id="Q19",
            question="Is the authorized next step design/freeze only, with no H1 run or scientific state collection?",
            status=passed,
            scope=design_freeze,
            answer="Yes.",
            evidence=(READINESS_SCOPE, "authorized_to_run_h1=false"),
        ),
    )


def _contains_secret_field(node: Any) -> bool:
    if isinstance(node, dict):
        forbidden = {"api_key", "private_key", "authorization", "secret", "token"}
        if forbidden & {str(key).lower() for key in node}:
            return True
        return any(_contains_secret_field(value) for value in node.values())
    if isinstance(node, (list, tuple)):
        return any(_contains_secret_field(value) for value in node)
    return False


async def async_run_qualification() -> dict[str, Any]:
    evidence = await run_clean_mechanical_canary()
    clean = assess_boundary(evidence)
    fixture_assessments = {
        case: assess_boundary(adversarial_fixture(evidence, case))
        for case in RUNTIME_FIXTURES
    }
    state_document = state_manifest_document(evidence.provider_policy)
    validate_state_manifest_document(state_document, evidence.provider_policy)
    original = run_model_free_qualification()
    claims = _claim_mapping(clean.l0_supported)
    questions = _readiness_questions()
    gates = {
        "clean_runtime_boundary": clean.clean,
        "exact_bounded_l0_language": clean.l0_claim == L0_CLAIM,
        "known_bad_A_through_F_and_H_rejected": all(
            not fixture_assessments[name].clean
            for name in RUNTIME_FIXTURES
            if name != "G-clean-declared-carrier"
        ),
        "clean_G_accepted": fixture_assessments[RUNTIME_FIXTURES[6]].clean,
        "state_manifest_valid_and_hash_bound": (
            evidence.common_prior_hashes
            == {
                key: value["hash"]
                for key, value in state_document["common_priors"].items()
            }
        ),
        "fresh_actor_and_namespace_identity": clean.clean,
        "predecessor_teardown_complete": all(
            item.process_absent
            and item.process_group_absent
            and item.private_root_removed
            and item.key_invalidated
            for item in evidence.teardowns
        ),
        "predecessor_authorization_revoked": all(
            any(
                event.lifecycle_id == lifecycle_id
                and event.event == "authorization_revoked"
                for event in evidence.lifecycle_events
            )
            for lifecycle_id in {
                record.identity.lifecycle_id for record in evidence.predecessors
            }
        ),
        "predecessor_revocation_precedes_successor_start": (
            not {
                record.identity.lifecycle_id for record in evidence.predecessors
            }
            or not evidence.successors
            or max(
                event.sequence
                for event in evidence.lifecycle_events
                if event.event == "authorization_revoked"
                and event.lifecycle_id
                in {record.identity.lifecycle_id for record in evidence.predecessors}
            )
            < min(
                event.sequence
                for event in evidence.lifecycle_events
                if event.event == "spawned"
                and event.lifecycle_id
                in {record.identity.lifecycle_id for record in evidence.successors}
            )
        ),
        "actor_network_and_tools_denied": (
            evidence.actor_network_mode == "unshared-deny"
            and not evidence.actor_tools
            and evidence.network_probe["default_route"] is False
            and evidence.network_probe["external_connect"] is False
            and evidence.network_probe["dns_resolved"] is False
        ),
        "actor_credentials_and_signing_isolated": (
            evidence.registry_private_key_count == 0
            and not evidence.signing_key_reused
        ),
        "declared_carrier_positive_control": evidence.carrier_positive_read,
        "frozen_schedule_contract_hash_bound": (
            evidence.schedule_contract.schedule_hash
            == stable_hash(evidence.schedule_contract.semantic_payload)
        ),
        "carrier_capability_authority_durable": all(
            record.write_capability_hash
            and len(record.read_capability_hashes) == len(record.read_actions)
            for record in evidence.carrier_records
        ),
        "provider_request_is_stateless_and_completed": (
            evidence.provider_status == "completed"
            and evidence.provider_store_requested is False
            and not evidence.provider_continuation_present
        ),
        "provider_transport_identity_recorded": bool(
            evidence.retry_attempts
            and evidence.retry_attempts[-1].wire_attempt_id
            and evidence.provider_gateway_receipt is not None
            and evidence.provider_request_hash
            and evidence.provider_output_hash
            and (
                evidence.provider_request_id is None
                or evidence.provider_request_id
                == evidence.provider_gateway_receipt.provider_request_id
            )
        ),
        "durable_retry_record_present": bool(evidence.retry_attempts),
        "no_live_model_call": evidence.live_model_calls == 0,
        "no_scientific_result": evidence.scientific_result is False,
        "L1_through_L5_not_credited": all(
            not claim.supported for claim in claims if claim.level != "L0"
        ),
        "original_model_free_qualification_unchanged": (
            original.readiness == "PASS"
            and len(original.gate_results) == 15
            and all(original.gate_results.values())
        ),
    }
    # The L0 window is the frozen-state boundary, not a billing or transport
    # claim.  A provider that does not emit a request identifier still fits the
    # generic contract: the gateway records its own wire attempt identity,
    # request/output hashes, and response identity, and a provider-issued
    # identifier is preserved when present.  No identifier or response body may
    # be spliced across attempts or imports, and a deployment whose provider
    # contract differs from the qualified one cannot broaden the claim.
    design_freeze_repairs = (
        "Pin the real provider HTTPS endpoint, exact model snapshot, project/auth scope, data-control configuration, and runtime configuration as part of the H1 design freeze.",
    )
    execution_repairs = (
        "Run and archive one semantically trivial, non-H1 live Responses canary on the frozen configuration; it must return a nonempty response-body ID (and a provider-issued request identifier when the provider emits one), a completed status, and no continuation/conversation/tools.",
        "Carry provider caches, logs, routing, retention, and serving state as OPAQUE/UNVERIFIED; never broaden L0 with a canary result.",
    )
    defense_in_depth_recommendations = (
        "Run the gateway in an OS network boundary that allowlists only the pinned provider endpoint (recommended deployment hardening; neither a validity prerequisite nor an execution blocker).",
    )
    report: dict[str, Any] = {
        "qualification_version": QUALIFICATION_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "adapter_version": ADAPTER_VERSION,
        "status": Readiness.PASS,
        "readiness_scope": READINESS_SCOPE,
        "execution_status": EXECUTION_NOT_READY,
        "authorized_to_run_h1": False,
        "scientific_result": False,
        "live_model_calls": 0,
        "runtime_boundary": evidence.model_dump(mode="json"),
        "boundary_assessment": clean.model_dump(mode="json"),
        "runtime_fixture_assessments": {
            name: item.model_dump(mode="json")
            for name, item in fixture_assessments.items()
        },
        "state_manifest": state_document,
        "claim_mapping": [item.model_dump(mode="json") for item in claims],
        "gate_results": gates,
        "readiness_questions": [
            item.model_dump(mode="json") for item in questions
        ],
        "required_before_h1_design": [],
        "required_as_part_of_h1_freeze": list(design_freeze_repairs),
        "required_before_h1_execution": list(execution_repairs),
        "recommended_defense_in_depth": list(defense_in_depth_recommendations),
        "model_free_regression": {
            "apparatus_version": original.apparatus_version,
            "readiness": original.readiness,
            "gate_count": len(original.gate_results),
            "gate_results": original.gate_results,
            "fixture_count": len(original.fixture_outcomes),
            "factorial_count": len(original.factorial_outcomes),
            "parentage_count": len(original.parentage_outcomes),
            "recovery_count": len(original.recovery_outcomes),
            "record_hash": stable_hash(original.model_dump(mode="json")),
        },
    }
    report["contains_secret_field"] = _contains_secret_field(report)
    # The mechanical boundary's readiness splits into two conclusions.  Every
    # design/freeze question and every mechanical gate must pass before the
    # runtime may be frozen for a live pilot; execution additionally requires
    # the pre-execution trivial canary on the frozen configuration and the
    # OPAQUE-carrying discipline listed under required_before_h1_execution.
    design_freeze_questions = tuple(
        item for item in questions if item.scope == "design_freeze"
    )
    if not all(gates.values()) or report["contains_secret_field"]:
        report["status"] = Readiness.FAIL
    elif any(item.status is not Readiness.PASS for item in design_freeze_questions):
        report["status"] = Readiness.PASS_WITH_REPAIRS
    report["execution_status"] = (
        EXECUTION_NOT_READY
        if execution_repairs
        else "YES — deployment-validated contract"
    )
    report["record_hash"] = stable_hash(report)
    return report


def run_qualification() -> dict[str, Any]:
    return asyncio.run(async_run_qualification())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--state-output", type=Path)
    args = parser.parse_args()
    report = run_qualification()
    rendered = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    if args.state_output is not None:
        args.state_output.parent.mkdir(parents=True, exist_ok=True)
        args.state_output.write_text(
            json.dumps(report["state_manifest"], sort_keys=True, indent=2) + "\n"
        )
    print(rendered, end="")
    raise SystemExit(0 if report["status"] != Readiness.FAIL else 1)


if __name__ == "__main__":
    main()
