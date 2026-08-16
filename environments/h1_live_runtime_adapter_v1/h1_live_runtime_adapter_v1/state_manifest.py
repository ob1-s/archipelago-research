"""Canonical state-surface inventory for the qualified turnover boundary."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .canonical import sha256_bytes, stable_hash
from .models import EvidenceClass, ProviderPolicy, StateClass, StateLayer


STATE_MANIFEST_VERSION = "h1-live-runtime-state-manifest/v1"
COMMON_PRIOR_VERSION = "h1-live-runtime-common-priors/v1"


def _layer(
    name: str,
    *,
    owner: str,
    scope: str,
    lifetime: str,
    model_visible: str,
    mutable: bool,
    predecessor_write: bool,
    successor_read: bool,
    classification: StateClass,
    reset_or_isolation: str,
    verification: str,
    evidence_class: EvidenceClass,
    residual_uncertainty: str = "none identified within the declared boundary",
) -> StateLayer:
    return StateLayer(
        name=name,
        owner=owner,
        scope=scope,
        lifetime=lifetime,
        model_visible=model_visible,  # type: ignore[arg-type]
        mutable=mutable,
        predecessor_write=predecessor_write,
        successor_read=successor_read,
        classification=classification,
        reset_or_isolation=reset_or_isolation,
        verification=verification,
        evidence_class=evidence_class,
        residual_uncertainty=residual_uncertainty,
    )


STATE_LAYER_MANIFEST: tuple[StateLayer, ...] = (
    _layer(
        "model_weights_and_tokenizer",
        owner="provider",
        scope="pinned provider model",
        lifetime="provider release",
        model_visible="unknown",
        mutable=False,
        predecessor_write=False,
        successor_read=False,
        classification=StateClass.PROVIDER_OPAQUE,
        reset_or_isolation="bind a model identifier in policy; exclude weights from L0",
        verification="configured/reported identifiers only; no exact weight digest",
        evidence_class=EvidenceClass.OPAQUE_UNVERIFIED,
        residual_uncertainty="weights, tokenizer build, routing, and serving substrate are opaque",
    ),
    _layer(
        "common_system_and_developer_instructions",
        owner="experimenter",
        scope="all actors",
        lifetime="frozen pilot",
        model_visible="yes",
        mutable=False,
        predecessor_write=False,
        successor_read=True,
        classification=StateClass.IMMUTABLE_COMMON_PRIOR,
        reset_or_isolation="version and hash before actor launch",
        verification="request carries frozen common-prior hashes",
        evidence_class=EvidenceClass.MECHANICALLY_CONTROLLED,
    ),
    _layer(
        "schemas_and_protocol_contracts",
        owner="experimenter",
        scope="adapter and all actors",
        lifetime="frozen pilot",
        model_visible="no",
        mutable=False,
        predecessor_write=False,
        successor_read=True,
        classification=StateClass.IMMUTABLE_COMMON_PRIOR,
        reset_or_isolation="versioned strict Pydantic schemas and actor protocol",
        verification="extra fields rejected; schema/protocol hashes recorded",
        evidence_class=EvidenceClass.MECHANICALLY_CONTROLLED,
    ),
    _layer(
        "task_and_harness_code",
        owner="experimenter",
        scope="adapter runtime",
        lifetime="frozen pilot",
        model_visible="no",
        mutable=False,
        predecessor_write=False,
        successor_read=True,
        classification=StateClass.IMMUTABLE_COMMON_PRIOR,
        reset_or_isolation="read-only bind plus source/version hash",
        verification="read-only Bubblewrap mount and recorded hashes",
        evidence_class=EvidenceClass.MECHANICALLY_CONTROLLED,
    ),
    _layer(
        "current_assignment",
        owner="orchestrator assignment service",
        scope="one actor generation",
        lifetime="one logical attempt",
        model_visible="yes",
        mutable=False,
        predecessor_write=False,
        successor_read=True,
        classification=StateClass.DECLARED_ASSIGNMENT,
        reset_or_isolation="assigned before launch; outcome-blind and hash pinned",
        verification="signed provider-request semantic hash",
        evidence_class=EvidenceClass.MECHANICALLY_CONTROLLED,
    ),
    _layer(
        "held_out_assignment_pool",
        owner="orchestrator",
        scope="pilot scheduler",
        lifetime="frozen pilot",
        model_visible="no",
        mutable=False,
        predecessor_write=False,
        successor_read=False,
        classification=StateClass.ORCHESTRATOR_ONLY,
        reset_or_isolation="never mounted or sent to actors; expose only current assignment",
        verification="orchestrator allowlist and request-hash audit",
        evidence_class=EvidenceClass.MECHANICALLY_CONTROLLED,
    ),
    _layer(
        "frozen_schedule_actor_request_and_capability_pins",
        owner="orchestrator",
        scope="frozen pilot schedule and each exact assignment",
        lifetime="frozen pilot plus qualification audit",
        model_visible="no",
        mutable=False,
        predecessor_write=False,
        successor_read=False,
        classification=StateClass.ORCHESTRATOR_ONLY,
        reset_or_isolation="freeze before launch; hash exact actor/request/assignment and per-carrier permission contracts",
        verification="schedule pin records policy, common priors, gateway key, attempt, actor-spec, assignment, request, and capability hashes",
        evidence_class=EvidenceClass.MECHANICALLY_CONTROLLED,
    ),
    _layer(
        "gateway_receipt_public_key_pin",
        owner="runtime controller",
        scope="one actor assignment",
        lifetime="one actor lifecycle",
        model_visible="no",
        mutable=False,
        predecessor_write=False,
        successor_read=True,
        classification=StateClass.DECLARED_ASSIGNMENT,
        reset_or_isolation="freeze in ActorSpec before launch; expose no receipt private key",
        verification="schedule contract and ActorIdentity carry the same exact gateway public key",
        evidence_class=EvidenceClass.MECHANICALLY_CONTROLLED,
    ),
    _layer(
        "actor_transcript_and_history",
        owner="actor process",
        scope="one lifecycle",
        lifetime="actor process",
        model_visible="yes",
        mutable=True,
        predecessor_write=True,
        successor_read=False,
        classification=StateClass.TRANSIENT_ACTOR_STATE,
        reset_or_isolation="new process/session and empty in-process history",
        verification="spawn-time history length zero and distinct session identifier; provider output is transiently delivered only to its current actor",
        evidence_class=EvidenceClass.EMPIRICALLY_PROBED,
    ),
    _layer(
        "actor_process_and_pid_namespace",
        owner="actor process",
        scope="one lifecycle",
        lifetime="actor process",
        model_visible="no",
        mutable=True,
        predecessor_write=True,
        successor_read=False,
        classification=StateClass.TRANSIENT_ACTOR_STATE,
        reset_or_isolation="dedicated process as PID 1 in fresh namespace; predecessor killed",
        verification="PID/namespace IDs, process start ticks, teardown and process-group checks",
        evidence_class=EvidenceClass.EMPIRICALLY_PROBED,
    ),
    _layer(
        "actor_worker_thread_pool_and_fork_state",
        owner="actor process",
        scope="one lifecycle",
        lifetime="actor process",
        model_visible="no",
        mutable=True,
        predecessor_write=True,
        successor_read=False,
        classification=StateClass.TRANSIENT_ACTOR_STATE,
        reset_or_isolation="no worker borrowing, thread-pool reuse, or fork/COW spawn path",
        verification="factory always execs a new interpreter; fixture B and fresh start ticks",
        evidence_class=EvidenceClass.MECHANICALLY_CONTROLLED,
    ),
    _layer(
        "actor_heap_and_interpreter_state",
        owner="actor process",
        scope="one lifecycle",
        lifetime="actor process",
        model_visible="no",
        mutable=True,
        predecessor_write=True,
        successor_read=False,
        classification=StateClass.TRANSIENT_ACTOR_STATE,
        reset_or_isolation="no worker reuse; process exit before successor spawn",
        verification="distinct process/lifecycle/session plus predecessor absence",
        evidence_class=EvidenceClass.MECHANICALLY_CONTROLLED,
    ),
    _layer(
        "actor_ipc_and_open_file_descriptors",
        owner="actor process",
        scope="one lifecycle",
        lifetime="actor process",
        model_visible="no",
        mutable=True,
        predecessor_write=True,
        successor_read=False,
        classification=StateClass.TRANSIENT_ACTOR_STATE,
        reset_or_isolation="fresh IPC namespace; exact descriptor audit above stdio",
        verification="distinct IPC namespace and only fresh /dev/urandom may remain open",
        evidence_class=EvidenceClass.EMPIRICALLY_PROBED,
        residual_uncertainty="host-root compromise and malicious kernel are outside the boundary",
    ),
    _layer(
        "actor_mount_and_private_root",
        owner="runtime controller",
        scope="one lifecycle",
        lifetime="actor process plus teardown",
        model_visible="no",
        mutable=True,
        predecessor_write=True,
        successor_read=False,
        classification=StateClass.TRANSIENT_ACTOR_STATE,
        reset_or_isolation="fresh mount namespace/root; private root deleted after exit",
        verification="distinct mount namespace and private-root removal evidence",
        evidence_class=EvidenceClass.EMPIRICALLY_PROBED,
    ),
    *(
        _layer(
            name,
            owner="actor process",
            scope=f"one lifecycle {path}",
            lifetime="actor process",
            model_visible="no",
            mutable=True,
            predecessor_write=True,
            successor_read=False,
            classification=StateClass.TRANSIENT_ACTOR_STATE,
            reset_or_isolation=f"fresh private bind for {path}; predecessor root removed",
            verification="secret-byte canary absent in successor and positive write in predecessor",
            evidence_class=EvidenceClass.EMPIRICALLY_PROBED,
        )
        for name, path in (
            ("actor_workdir", "/work"),
            ("actor_home", "/home"),
            ("actor_tmp", "/tmp"),
            ("actor_shared_memory", "/dev/shm"),
            ("actor_cache", "/cache"),
            ("actor_env_derived_path", "/env-slot"),
        )
    ),
    _layer(
        "actor_environment",
        owner="runtime controller",
        scope="one lifecycle",
        lifetime="actor process",
        model_visible="no",
        mutable=True,
        predecessor_write=True,
        successor_read=False,
        classification=StateClass.TRANSIENT_ACTOR_STATE,
        reset_or_isolation="clear environment then populate exact allowlist and fresh sentinel",
        verification="environment-name equality and predecessor/successor value-hash inequality",
        evidence_class=EvidenceClass.EMPIRICALLY_PROBED,
    ),
    _layer(
        "actor_signing_private_key",
        owner="actor process",
        scope="one lifecycle",
        lifetime="actor process",
        model_visible="no",
        mutable=False,
        predecessor_write=True,
        successor_read=False,
        classification=StateClass.TRANSIENT_ACTOR_STATE,
        reset_or_isolation="Ed25519 key generated inside actor; never serialized; revoke on exit",
        verification="fresh public key, signature verification, revocation, registry private-key count zero",
        evidence_class=EvidenceClass.MECHANICALLY_CONTROLLED,
    ),
    _layer(
        "declared_lineage_carrier",
        owner="carrier controller",
        scope="one lineage",
        lifetime="cross-generation until declared deletion",
        model_visible="yes",
        mutable=False,
        predecessor_write=True,
        successor_read=True,
        classification=StateClass.DECLARED_LINEAGE_CARRIER,
        reset_or_isolation="only enumerate/write/finalize/read API; single write then immutable hash",
        verification="signed writer/reader, lineage/generation checks, durable content hash and provenance",
        evidence_class=EvidenceClass.MECHANICALLY_CONTROLLED,
    ),
    _layer(
        "declared_backup",
        owner="carrier controller",
        scope="one lineage",
        lifetime="cross-generation until declared deletion",
        model_visible="unknown",
        mutable=False,
        predecessor_write=True,
        successor_read=True,
        classification=StateClass.DECLARED_BACKUP,
        reset_or_isolation="same narrow API; exposure requires explicit backup condition",
        verification="signed writer/reader, immutable hash, parentage and carrier-class record",
        evidence_class=EvidenceClass.MECHANICALLY_CONTROLLED,
    ),
    _layer(
        "provider_continuation_and_conversation_identifiers",
        owner="provider gateway",
        scope="all model requests",
        lifetime="request",
        model_visible="yes",
        mutable=False,
        predecessor_write=False,
        successor_read=False,
        classification=StateClass.FORBIDDEN,
        reset_or_isolation="previous_response_id and conversation must be null; new attempt ID",
        verification="strict request/response validation and fixture A",
        evidence_class=EvidenceClass.MECHANICALLY_CONTROLLED,
    ),
    _layer(
        "provider_response_objects",
        owner="provider",
        scope="provider account/project",
        lifetime="provider-controlled retention",
        model_visible="unknown",
        mutable=True,
        predecessor_write=True,
        successor_read=False,
        classification=StateClass.PROVIDER_OPAQUE,
        reset_or_isolation="send store=false and never reference prior response IDs",
        verification="response contract plus provider documentation; no internal deletion proof",
        evidence_class=EvidenceClass.DOCUMENTATION_SUPPORTED,
        residual_uncertainty="provider may retain abuse-monitoring or other non-response-object state",
    ),
    _layer(
        "local_logical_and_wire_attempt_ids",
        owner="provider gateway",
        scope="one logical attempt",
        lifetime="pilot audit retention",
        model_visible="no",
        mutable=False,
        predecessor_write=False,
        successor_read=False,
        classification=StateClass.ORCHESTRATOR_ONLY,
        reset_or_isolation="unique SQLite primary key; never insert into model input",
        verification="durable logical-attempt ledger and monotone wire-attempt suffix",
        evidence_class=EvidenceClass.MECHANICALLY_CONTROLLED,
    ),
    _layer(
        "provider_request_and_response_ids",
        owner="provider",
        scope="one transport attempt and provider logs",
        lifetime="provider-controlled retention",
        model_visible="no",
        mutable=True,
        predecessor_write=True,
        successor_read=False,
        classification=StateClass.PROVIDER_OPAQUE,
        reset_or_isolation="record for audit; never insert into later model input",
        verification="capture when returned; provider-side retention is unobservable",
        evidence_class=EvidenceClass.OPAQUE_UNVERIFIED,
        residual_uncertainty="provider-side creation, retention, and linkage are not controlled",
    ),
    *(
        _layer(
            name,
            owner="provider",
            scope="provider infrastructure",
            lifetime="provider-controlled",
            model_visible="unknown",
            mutable=True,
            predecessor_write=True,
            successor_read=False,
            classification=StateClass.PROVIDER_OPAQUE,
            reset_or_isolation=isolation,
            verification="official provider documentation only; no internal observability",
            evidence_class=EvidenceClass.OPAQUE_UNVERIFIED,
            residual_uncertainty=uncertainty,
        )
        for name, isolation, uncertainty in (
            (
                "provider_prompt_and_prefix_cache",
                "do not treat cache hits/misses as model-visible continuity; pin request contract",
                "cache keys, routing, KV lifetime, and possible influence beyond latency are opaque",
            ),
            (
                "provider_abuse_monitoring_logs",
                "exclude from L0 claim and never request retrieval",
                "retention and downstream uses are provider-controlled",
            ),
            (
                "provider_application_and_routing_state",
                "exclude from L0 claim; use stateless request contract",
                "load balancing, safety systems, and backend-local state are opaque",
            ),
        )
    ),
    _layer(
        "provider_credentials",
        owner="provider gateway",
        scope="provider account/project",
        lifetime="secret rotation period",
        model_visible="no",
        mutable=True,
        predecessor_write=False,
        successor_read=False,
        classification=StateClass.ORCHESTRATOR_ONLY,
        reset_or_isolation="credential remains outside actor namespaces and requests",
        verification="actor exact environment and mount allowlist; gateway-only constructor argument",
        evidence_class=EvidenceClass.MECHANICALLY_CONTROLLED,
    ),
    _layer(
        "provider_gateway_network",
        owner="provider gateway",
        scope="one provider endpoint",
        lifetime="transport attempt",
        model_visible="no",
        mutable=True,
        predecessor_write=False,
        successor_read=False,
        classification=StateClass.ORCHESTRATOR_ONLY,
        reset_or_isolation="actor has unshared deny network; only gateway may reach pinned endpoint",
        verification="policy hash constrains URL in code; no OS endpoint allowlist is yet qualified",
        evidence_class=EvidenceClass.OPAQUE_UNVERIFIED,
        residual_uncertainty="deployment gateway egress must be OS-restricted and requalified",
    ),
    _layer(
        "provider_gateway_receipt_private_key",
        owner="provider gateway",
        scope="frozen gateway configuration",
        lifetime="logical-attempt replay window",
        model_visible="no",
        mutable=False,
        predecessor_write=False,
        successor_read=False,
        classification=StateClass.ORCHESTRATOR_ONLY,
        reset_or_isolation="provision outside actors; never serialize or mount it into an actor",
        verification="domain-separated signatures verify against the separately inventoried assignment public-key pin",
        evidence_class=EvidenceClass.MECHANICALLY_CONTROLLED,
        residual_uncertainty="malicious host/controller binary replacement is outside the qualified threat model",
    ),
    _layer(
        "provider_gateway_receipts",
        owner="provider gateway",
        scope="one accepted provider response",
        lifetime="logical-attempt replay window and qualification audit",
        model_visible="no",
        mutable=True,
        predecessor_write=False,
        successor_read=False,
        classification=StateClass.ORCHESTRATOR_ONLY,
        reset_or_isolation="append signed nonsecret provenance; never use it as later model input",
        verification="signature binds gateway/attempt/assignment/request/response/provider-request/output fields and is revalidated on replay",
        evidence_class=EvidenceClass.MECHANICALLY_CONTROLLED,
    ),
    _layer(
        "orchestrator_plaintext_response_ledger",
        owner="provider gateway",
        scope="one actor- and lifecycle-bound logical attempt",
        lifetime="configured local replay window",
        model_visible="no",
        mutable=True,
        predecessor_write=False,
        successor_read=False,
        classification=StateClass.ORCHESTRATOR_ONLY,
        reset_or_isolation="store only for exact same-actor accepted replay; never expose as a successor input except through a declared carrier",
        verification="SQLite authorization/request/assignment/output/receipt bindings; public dossier emits hashes, not plaintext",
        evidence_class=EvidenceClass.MECHANICALLY_CONTROLLED,
        residual_uncertainty="deployment must choose and access-control an explicit durable ledger path; the default temporary ledger is deleted on close",
    ),
    *(
        _layer(
            name,
            owner="runtime controller",
            scope="all actors",
            lifetime="pilot run",
            model_visible="no",
            mutable=True,
            predecessor_write=False,
            successor_read=False,
            classification=StateClass.ORCHESTRATOR_ONLY,
            reset_or_isolation=isolation,
            verification=verification,
            evidence_class=EvidenceClass.MECHANICALLY_CONTROLLED,
        )
        for name, isolation, verification in (
            (
                "orchestrator_memory_and_logs",
                "never mount or insert logs into actor/model input",
                "narrow actor protocol and request semantic-hash audit",
            ),
            (
                "orchestrator_scheduler_state",
                "assign only frozen inputs/config; forbid output-dependent assignment",
                "predeclared schedule hash and retry ledger",
            ),
            (
                "public_key_registry_and_signed_action_log",
                "public keys/signatures only; no signing method or private key",
                "registration plus carrier write/read, write_canaries, probe_paths, network_probe, provider_request, and provider_response_accept signatures; sequence monotonicity and revocation",
            ),
            (
                "retry_and_lifecycle_ledger",
                "retain accepted response bytes only in orchestrator storage for exact same-actor replay; never replay ambiguous deliveries or resume provider context",
                "actor/lifecycle-bound logical attempt, monotone transport attempts, terminal outcome classes, and receipt revalidation",
            ),
            (
                "lineage_and_parentage_registry",
                "record declared lineage/generation/parent hashes; never synthesize carrier content",
                "signed action identity and carrier provenance validation",
            ),
        )
    ),
    *(
        _layer(
            name,
            owner="actor process",
            scope="all actors",
            lifetime="none",
            model_visible="no",
            mutable=False,
            predecessor_write=False,
            successor_read=False,
            classification=StateClass.FORBIDDEN,
            reset_or_isolation=isolation,
            verification=verification,
            evidence_class=EvidenceClass.MECHANICALLY_CONTROLLED,
        )
        for name, isolation, verification in (
            (
                "general_shell_and_subprocess_tools",
                "not exposed by actor command protocol",
                "unknown commands rejected and no shell binary mounted as a tool interface",
            ),
            (
                "browser_and_general_tool_calls",
                "tools=[] and no actor browser/tool API",
                "strict provider policy/response validation",
            ),
            (
                "mcp_and_plugin_state",
                "no MCP or plugin endpoints mounted or declared",
                "empty actor tool inventory and request schema",
            ),
            (
                "undeclared_external_databases_and_object_stores",
                "no credentials, mounts, tools, or actor egress",
                "exact environment/mount boundary and connectivity probe",
            ),
            (
                "unrestricted_actor_network_and_dns",
                "fresh unshared network namespace with no default route",
                "default-route, external-connect, and DNS probes",
            ),
            (
                "undeclared_cross_generation_files",
                "only declared carrier store is outside disposable actor root",
                "multi-surface file canaries and fixture C/F",
            ),
        )
    ),
)


STATE_LAYER_NAMES = tuple(item.name for item in STATE_LAYER_MANIFEST)
_EXPECTED_LAYER_HASHES = {
    item.name: stable_hash(item.model_dump(mode="json"))
    for item in STATE_LAYER_MANIFEST
}

COMMON_INSTRUCTION_CONTRACT = (
    "Use only the current assignment, immutable common priors, and explicitly "
    "exposed declared carriers. No predecessor transcript or undeclared state."
)
_SOURCE_ROOT = Path(__file__).resolve().parent
_COMMON_PRIOR_SOURCES = {
    "actor_protocol": ("actor_worker.py", "h1-live-runtime-actor-protocol/v1"),
    "boundary_controller": ("isolation.py", "h1-live-runtime-isolation/v1"),
    "carrier_protocol": ("carrier.py", "h1-live-runtime-carrier/v1"),
    "orchestration_contract": ("orchestrator.py", "h1-live-runtime-orchestrator/v1"),
    "provider_gateway": ("provider.py", "h1-live-runtime-provider/v1"),
    "state_schema": ("models.py", "h1-live-runtime-wire-schema/v1"),
    "taskset": ("taskset.py", "h1-live-runtime-taskset/v1"),
}


def common_prior_records(
    policy: ProviderPolicy | None = None,
) -> dict[str, dict[str, str]]:
    policy = policy or ProviderPolicy(
        base_url="https://mechanical.invalid/v1", model="mechanical-no-model"
    )
    records = {
        name: {
            "version": version,
            "source": filename,
            "hash": sha256_bytes((_SOURCE_ROOT / filename).read_bytes()),
        }
        for name, (filename, version) in _COMMON_PRIOR_SOURCES.items()
    }
    records["common_instructions"] = {
        "version": COMMON_PRIOR_VERSION,
        "source": "inline:COMMON_INSTRUCTION_CONTRACT",
        "hash": stable_hash(COMMON_INSTRUCTION_CONTRACT),
    }
    records["provider_policy"] = {
        "version": "openai-responses-stateless-policy/v1",
        "source": "strict:ProviderPolicy",
        "hash": stable_hash(policy.model_dump(mode="json")),
    }
    return dict(sorted(records.items()))


def common_prior_hashes(policy: ProviderPolicy | None = None) -> dict[str, str]:
    return {
        name: record["hash"]
        for name, record in common_prior_records(policy).items()
    }


def validate_state_manifest(
    layers: tuple[StateLayer, ...] = STATE_LAYER_MANIFEST,
) -> None:
    names = tuple(item.name for item in layers)
    if names != STATE_LAYER_NAMES:
        raise ValueError("state manifest is incomplete or not in canonical order")
    duplicates = [name for name, count in Counter(names).items() if count != 1]
    if duplicates:
        raise ValueError(f"duplicate state layers: {duplicates!r}")
    for item in layers:
        if stable_hash(item.model_dump(mode="json")) != _EXPECTED_LAYER_HASHES[item.name]:
            raise ValueError(f"{item.name} differs from its canonical classification")
        if not item.residual_uncertainty:
            raise ValueError(f"{item.name} omits residual-uncertainty disposition")
        if item.classification in {
            StateClass.FORBIDDEN,
            StateClass.PROVIDER_OPAQUE,
            StateClass.ORCHESTRATOR_ONLY,
        } and item.successor_read:
            raise ValueError(f"{item.name} gives successors a prohibited read path")
        if item.classification is StateClass.IMMUTABLE_COMMON_PRIOR and (
            item.mutable or item.predecessor_write
        ):
            raise ValueError(f"{item.name} is not an immutable common prior")
        if item.classification in {
            StateClass.DECLARED_LINEAGE_CARRIER,
            StateClass.DECLARED_BACKUP,
        } and not (item.predecessor_write and item.successor_read):
            raise ValueError(f"{item.name} lacks its declared cross-generation edge")
        if item.classification is StateClass.DECLARED_ASSIGNMENT and (
            item.mutable or item.predecessor_write or not item.successor_read
        ):
            raise ValueError(f"{item.name} is not a frozen declared assignment")


def state_manifest_document(policy: ProviderPolicy | None = None) -> dict[str, Any]:
    validate_state_manifest()
    layers = [item.model_dump(mode="json") for item in STATE_LAYER_MANIFEST]
    document: dict[str, Any] = {
        "manifest_version": STATE_MANIFEST_VERSION,
        "common_prior_version": COMMON_PRIOR_VERSION,
        "layer_count": len(layers),
        "layers": layers,
        "common_priors": common_prior_records(policy),
    }
    document["manifest_hash"] = stable_hash(document)
    return document


def validate_state_manifest_document(
    document: dict[str, Any], policy: ProviderPolicy | None = None
) -> None:
    expected_keys = {
        "manifest_version",
        "common_prior_version",
        "layer_count",
        "layers",
        "common_priors",
        "manifest_hash",
    }
    if set(document) != expected_keys:
        raise ValueError("state manifest document has missing or unexpected keys")
    if document["manifest_version"] != STATE_MANIFEST_VERSION:
        raise ValueError("state manifest version mismatch")
    if document["common_prior_version"] != COMMON_PRIOR_VERSION:
        raise ValueError("common-prior version mismatch")
    layers = tuple(StateLayer.model_validate(item) for item in document["layers"])
    if document["layer_count"] != len(layers):
        raise ValueError("state manifest layer count mismatch")
    validate_state_manifest(layers)
    if document["common_priors"] != common_prior_records(policy):
        raise ValueError("state manifest common-prior source hashes mismatch")
    unsigned = {key: value for key, value in document.items() if key != "manifest_hash"}
    if document["manifest_hash"] != stable_hash(unsigned):
        raise ValueError("state manifest document hash mismatch")


validate_state_manifest()


__all__ = [
    "COMMON_PRIOR_VERSION",
    "STATE_LAYER_MANIFEST",
    "STATE_LAYER_NAMES",
    "STATE_MANIFEST_VERSION",
    "common_prior_hashes",
    "common_prior_records",
    "state_manifest_document",
    "validate_state_manifest",
    "validate_state_manifest_document",
]
