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
READINESS_SCOPE = "ready only to DESIGN/FREEZE a bounded H1 pilot"
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
    repair = Readiness.PASS_WITH_REPAIRS
    passed = Readiness.PASS
    design_freeze = "design_freeze"
    execution = "execution"
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
            status=repair,
            scope=execution,
            answer="Not yet on a deployment host. Code pins the HTTPS base_url in the signed policy and records the policy hash. Under the qualified threat model (no actor egress, small trusted gateway, pinned and logged request contract, no causal route from predecessor to successor through arbitrary gateway networking) OS egress allowlisting is defense-in-depth rather than a validity prerequisite; it remains recommended deployment hardening before live execution.",
            evidence=("gateway policy hash", "no actor egress", "defense-in-depth deployment hardening"),
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
            status=repair,
            scope=execution,
            answer="No; choosing and pinning the real endpoint/model snapshot/auth scope is part of the H1 design/freeze itself, and live qualification deliberately used a no-model backend (zero live calls). The mechanical boundary is ready to freeze such a pin; the frozen configuration must be exercised before execution.",
            evidence=("provider=none", "model=mechanical-no-model", "live_model_calls=0"),
        ),
        ReadinessQuestion(
            question_id="Q14",
            question="Have provider response/session semantics been mechanically checked on the frozen endpoint?",
            status=repair,
            scope=execution,
            answer="No live request was made; the request/response contract is mechanically enforced and documented, and a nonempty server x-request-id is now required in the evidence contract. The trivial live canary on the frozen endpoint remains an execution gate.",
            evidence=("documentation-supported", "trivial live canary remains"),
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
            question="Do known-bad runtime fixtures A-F fail while clean fixture G passes?",
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
        "known_bad_A_through_F_rejected": all(
            not fixture_assessments[name].clean for name in RUNTIME_FIXTURES[:6]
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
        "provider_response_identity_recorded": bool(
            evidence.provider_request_id and evidence.provider_response_id
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
    # claim.  A deployment that cannot obtain these identifiers proves only
    # that its provider contract differs from the qualified one; it cannot
    # broaden the claim.
    execution_repairs = (
        "Pin the real provider HTTPS endpoint, exact model snapshot, project/auth scope, and data-control configuration as part of the H1 freeze.",
        "Run the gateway in an OS network boundary that allowlists only the pinned provider endpoint (defense-in-depth; recommended before execution).",
        "Run and archive one semantically trivial, non-H1 live Responses canary on the frozen configuration; it must return a nonempty response-body ID and server x-request-id, a completed status, and no continuation/conversation/tools.",
        "Carry provider caches, logs, routing, retention, and serving state as OPAQUE/UNVERIFIED; never broaden L0 with a canary result.",
    )
    design_freeze_repairs: tuple[str, ...] = ()
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
        "required_before_design_freeze": list(design_freeze_repairs),
        "required_before_execution": list(execution_repairs),
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
    # The mechanical boundary's readiness splits into two gates.  Every
    # design/freeze question must pass and every mechanical gate must pass
    # before the runtime may be frozen for a live pilot; execution additionally
    # requires the deployment/response validation listed above.
    design_freeze_questions = tuple(
        item for item in questions if item.scope == "design_freeze"
    )
    execution_questions = tuple(item for item in questions if item.scope == "execution")
    if not all(gates.values()) or report["contains_secret_field"]:
        report["status"] = Readiness.FAIL
    elif any(item.status is not Readiness.PASS for item in design_freeze_questions):
        report["status"] = Readiness.PASS_WITH_REPAIRS
    if any(item.status is not Readiness.PASS for item in execution_questions):
        report["execution_status"] = EXECUTION_NOT_READY
    else:
        report["execution_status"] = "YES — deployment-validated contract"
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
