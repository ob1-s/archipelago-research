"""End-to-end, model-free tests for the turnover/L0 boundary.

``run_clean_mechanical_canary`` starts real Bubblewrap actor processes, but the
provider backend is scripted and the canary makes zero model calls.  The
mutation matrix below is intentionally fail-closed: each state, credential,
network, retry, and lifecycle violation must make the assessment non-clean.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from functools import lru_cache
from typing import Any

import pytest

from h1_live_runtime_adapter_v1.boundary import (
    L0_CLAIM,
    RUNTIME_FIXTURES,
    assess_boundary,
    adversarial_fixture,
    run_clean_mechanical_canary,
)
from h1_live_runtime_adapter_v1.models import (
    ActorRuntimeRecord,
    RuntimeBoundaryEvidence,
)


@lru_cache(maxsize=1)
def _clean() -> RuntimeBoundaryEvidence:
    """Run exactly one real mechanical turnover canary for this test module."""

    return asyncio.run(run_clean_mechanical_canary())


def _assessment(evidence: RuntimeBoundaryEvidence):
    return assess_boundary(evidence)


def _replace_identity(
    evidence: RuntimeBoundaryEvidence,
    side: str,
    index: int,
    **changes: Any,
) -> RuntimeBoundaryEvidence:
    records = list(getattr(evidence, side))
    record = records[index]
    identity = record.identity.model_copy(update=changes)
    records[index] = record.model_copy(update={"identity": identity})
    return evidence.model_copy(update={side: tuple(records)})


def _one_teardown(evidence: RuntimeBoundaryEvidence, **changes: Any):
    return (evidence.teardowns[0].model_copy(update=changes),)


def _replace_runtime_record(
    evidence: RuntimeBoundaryEvidence,
    side: str,
    index: int,
    **changes: Any,
) -> RuntimeBoundaryEvidence:
    records = list(getattr(evidence, side))
    records[index] = records[index].model_copy(update=changes)
    return evidence.model_copy(update={side: tuple(records)})


def test_clean_real_canary_supports_only_exact_mechanical_l0() -> None:
    evidence = _clean()
    assessment = _assessment(evidence)
    assert assessment.clean is True
    assert assessment.l0_supported is True
    assert assessment.l0_claim == L0_CLAIM
    assert assessment.l0_claim == (
        "complete turnover within the controlled and documented model-visible state boundary"
    )
    assert evidence.live_model_calls == 0
    assert evidence.scientific_result is False
    assert evidence.provider == "none"
    assert evidence.backend == "scripted-mechanical-through-live-request-boundary"
    assert evidence.provider_continuation_present is False
    assert evidence.provider_store_requested is False
    assert evidence.actor_tools == ()
    assert evidence.registry_private_key_count == 0
    assert evidence.residual_opaque_state
    assert evidence.predecessor_canary.history_length > 0
    assert evidence.predecessor_canary.action.action == "write_canaries"
    assert evidence.successor_path_probe_action.action == "probe_paths"
    assert evidence.network_probe_action.action == "network_probe"
    assert evidence.provider_request_action.action == "provider_request"

    predecessor = evidence.predecessors[0]
    successor = evidence.successors[0]
    assert predecessor.identity.actor_id != successor.identity.actor_id
    assert predecessor.identity.lifecycle_id != successor.identity.lifecycle_id
    assert predecessor.identity.session_id != successor.identity.session_id
    assert predecessor.identity.public_key_b64 != successor.identity.public_key_b64
    assert predecessor.runtime_process_id != successor.runtime_process_id
    assert predecessor.identity.namespace_ids.keys() == successor.identity.namespace_ids.keys()
    # Namespace inode numbers may be recycled after predecessor teardown;
    # freshness is established by the fixed unshare/exec path, PID1 status,
    # process-start identity, and complete namespace inventory—not inequality
    # of a recyclable kernel display identifier.
    assert all(predecessor.identity.namespace_ids.values())
    assert all(successor.identity.namespace_ids.values())
    assert all(item.process_absent for item in evidence.teardowns)
    assert all(item.process_group_absent for item in evidence.teardowns)
    assert all(item.private_root_removed for item in evidence.teardowns)
    assert all(item.key_invalidated for item in evidence.teardowns)
    assert evidence.network_probe == {
        "default_route": False,
        "external_connect": False,
        "dns_resolved": False,
        "route_hash": evidence.network_probe["route_hash"],
    }


@pytest.mark.parametrize("case", RUNTIME_FIXTURES)
def test_original_a_to_h_runtime_fixture_matrix(case: str) -> None:
    assessment = _assessment(adversarial_fixture(_clean(), case))
    if case == "G-clean-declared-carrier":
        assert assessment.clean is True
        assert assessment.l0_claim == L0_CLAIM
    else:
        assert assessment.clean is False, (case, assessment.violations)
        assert assessment.l0_supported is False
        assert assessment.l0_claim is None


def test_skipped_predecessor_revocation_fails_l0() -> None:
    evidence = _clean()
    assessment = _assessment(adversarial_fixture(evidence, "H-skip-revocation"))
    assert assessment.clean is False
    assert "predecessor_authorization_not_revoked" in assessment.violations
    missing_journal = _assessment(evidence.model_copy(update={"lifecycle_events": ()}))
    assert missing_journal.clean is False
    assert "predecessor_authorization_not_revoked" in missing_journal.violations


def test_revocation_before_successor_start_is_required_and_verified() -> None:
    evidence = _clean()
    predecessor_ids = {
        record.identity.lifecycle_id for record in evidence.predecessors
    }
    successor_ids = {record.identity.lifecycle_id for record in evidence.successors}
    events = list(evidence.lifecycle_events)
    successor_spawn_events = [
        event
        for event in events
        if event.event == "spawned" and event.lifecycle_id in successor_ids
    ]
    predecessor_revocation_events = [
        event
        for event in events
        if event.event == "authorization_revoked"
        and event.lifecycle_id in predecessor_ids
    ]
    rest = [
        event
        for event in events
        if event not in successor_spawn_events
        and event not in predecessor_revocation_events
    ]
    reordered = successor_spawn_events + predecessor_revocation_events + rest
    reordered = [
        event.model_copy(update={"sequence": index})
        for index, event in enumerate(reordered)
    ]
    assessment = _assessment(
        evidence.model_copy(update={"lifecycle_events": tuple(reordered)})
    )
    assert assessment.clean is False
    assert "predecessor_revocation_not_before_successor_start" in assessment.violations


def test_lifecycle_event_sequences_must_be_contiguous_and_unique() -> None:
    evidence = _clean()
    events = list(evidence.lifecycle_events)
    events[1] = events[1].model_copy(update={"sequence": events[0].sequence})
    assessment = _assessment(
        evidence.model_copy(update={"lifecycle_events": tuple(events)})
    )
    assert assessment.clean is False
    assert "lifecycle_event_order_invalid" in assessment.violations


def test_receipt_provider_request_id_is_signature_bound() -> None:
    evidence = _clean()
    receipt = evidence.provider_gateway_receipt.model_copy(
        update={"provider_request_id": "forged-provider-request-id"}
    )
    assessment = _assessment(
        evidence.model_copy(update={"provider_gateway_receipt": receipt})
    )
    assert assessment.clean is False
    assert "provider_response_acceptance_invalid" in assessment.violations


def test_empty_carrier_surface_is_not_clean() -> None:
    evidence = _clean().model_copy(
        update={"carrier_records": (), "carrier_positive_read": False}
    )
    assessment = _assessment(evidence)
    assert assessment.clean is False
    assert {"declared_carrier_positive_control_failed", "declared_carrier_record_missing"}.issubset(
        assessment.violations
    )


def test_empty_retry_surface_is_not_clean() -> None:
    evidence = _clean().model_copy(update={"retry_attempts": ()})
    assessment = _assessment(evidence)
    assert assessment.clean is False
    assert "provider_attempt_record_missing" in assessment.violations


def test_opaque_state_inventory_is_required() -> None:
    evidence = _clean().model_copy(update={"residual_opaque_state": ()})
    assessment = _assessment(evidence)
    assert assessment.clean is False
    assert "opaque_state_inventory_invalid" in assessment.violations


@pytest.mark.parametrize(
    "mutation",
    [
        lambda e: e.model_copy(
            update={
                "predecessor_canary": e.predecessor_canary.model_copy(
                    update={"actor_id": "forged-predecessor"}
                )
            }
        ),
        lambda e: e.model_copy(
            update={
                "predecessor_canary": e.predecessor_canary.model_copy(
                    update={"paths": ()}
                )
            }
        ),
        lambda e: e.model_copy(
            update={
                "predecessor_canary": e.predecessor_canary.model_copy(
                    update={"path_hashes": {}}
                )
            }
        ),
        lambda e: e.model_copy(
            update={
                "predecessor_canary": e.predecessor_canary.model_copy(
                    update={"path_hashes": {"workdir": "not-a-hash"}}
                )
            }
        ),
        lambda e: e.model_copy(
            update={
                "predecessor_canary": e.predecessor_canary.model_copy(
                    update={"environment_value_hash": "not-a-hash"}
                )
            }
        ),
        lambda e: e.model_copy(
            update={
                "predecessor_canary": e.predecessor_canary.model_copy(
                    update={"action": None}
                )
            }
        ),
        lambda e: e.model_copy(
            update={
                "predecessor_canary": e.predecessor_canary.model_copy(
                    update={"history_length": 0}
                )
            }
        ),
    ],
    ids=[
        "wrong-canary-actor",
        "empty-canary-paths",
        "empty-canary-hashes",
        "malformed-canary-hash",
        "malformed-environment-hash",
        "missing-canary-action",
        "missing-predecessor-history",
    ],
)
def test_canary_attribution_and_exact_surfaces_fail_closed(
    mutation: Callable[[RuntimeBoundaryEvidence], RuntimeBoundaryEvidence],
) -> None:
    assessment = _assessment(mutation(_clean()))
    assert assessment.clean is False
    assert "predecessor_canary_evidence_invalid" in assessment.violations


@pytest.mark.parametrize(
    "mutation, expected",
    [
        (
            lambda e: e.model_copy(update={"provider_request_hash": "not-a-sha256"}),
            "provider_request_hash_invalid",
        ),
        (
            lambda e: e.model_copy(
                update={
                    "carrier_records": (
                        e.carrier_records[0].model_copy(update={"content_hash": "bad"}),
                    )
                }
            ),
            "declared_carrier_provenance_invalid",
        ),
        (
            lambda e: e.model_copy(
                update={
                    "common_prior_hashes": {
                        **e.common_prior_hashes,
                        "runtime": "0" * 64,
                    }
                }
            ),
            "common_prior_hashes_mismatch",
        ),
    ],
    ids=["malformed-request-hash", "malformed-carrier-hash", "common-prior-hash-mismatch"],
)
def test_malformed_hashes_and_common_prior_mismatch_fail_closed(
    mutation: Callable[[RuntimeBoundaryEvidence], RuntimeBoundaryEvidence],
    expected: str,
) -> None:
    assessment = _assessment(mutation(_clean()))
    assert assessment.clean is False
    assert expected in assessment.violations


@pytest.mark.parametrize(
    "mutation, expected",
    [
        (
            lambda e: _replace_identity(
                e,
                "successors",
                0,
                lineage_id=e.predecessors[0].identity.lineage_id + "-other",
            ),
            "lineage_mismatch",
        ),
        (
            lambda e: _replace_identity(e, "successors", 0, generation=0),
            "generation_order_invalid",
        ),
        (
            lambda e: e.model_copy(update={"successor_history_length_at_spawn": 1}),
            "predecessor_history_visible",
        ),
        (
            lambda e: e.model_copy(update={"provider_continuation_present": True}),
            "provider_continuation_present",
        ),
        (
            lambda e: _replace_identity(
                e,
                "successors",
                0,
                session_id=e.predecessors[0].identity.session_id,
            ),
            "session_id_reuse",
        ),
        (
            lambda e: _replace_identity(
                e,
                "successors",
                0,
                public_key_b64=e.predecessors[0].identity.public_key_b64,
            ),
            "public_key_b64_reuse",
        ),
    ],
    ids=[
        "lineage",
        "generation",
        "history",
        "provider-session-continuation",
        "session-id",
        "signing-key",
    ],
)
def test_lineage_generation_session_and_history_mutations_fail_closed(
    mutation: Callable[[RuntimeBoundaryEvidence], RuntimeBoundaryEvidence],
    expected: str,
) -> None:
    assessment = _assessment(mutation(_clean()))
    assert assessment.clean is False
    assert expected in assessment.violations


@pytest.mark.parametrize(
    "mutation, expected",
    [
        (
            lambda e: e.model_copy(
                update={
                    "successor_path_probes": {
                        **e.successor_path_probes,
                        next(iter(e.successor_path_probes)): True,
                    }
                }
            ),
            "predecessor_private_file_visible",
        ),
        (
            lambda e: e.model_copy(update={"env_or_cache_reused": True}),
            "environment_or_cache_reuse",
        ),
        (
            lambda e: e.model_copy(
                update={
                    "successor_environment_value_hash": e.predecessor_canary.environment_value_hash
                }
            ),
            "environment_or_cache_reuse",
        ),
        (
            lambda e: e.model_copy(update={"private_mount_reused": True}),
            "private_mount_reuse",
        ),
        (
            lambda e: e.model_copy(update={"stale_worker_reused": True}),
            "stale_worker_reuse",
        ),
        (
            lambda e: e.model_copy(update={"undeclared_external_carrier": True}),
            "undeclared_external_carrier",
        ),
    ],
    ids=["filesystem", "env-cache-flag", "env-value", "private-mount", "stale-worker", "external-carrier"],
)
def test_filesystem_environment_worker_and_carrier_mutations_fail_closed(
    mutation: Callable[[RuntimeBoundaryEvidence], RuntimeBoundaryEvidence],
    expected: str,
) -> None:
    assessment = _assessment(mutation(_clean()))
    assert assessment.clean is False
    assert expected in assessment.violations


def test_incomplete_namespace_inventory_is_not_clean() -> None:
    evidence = _replace_identity(_clean(), "successors", 0, namespace_ids={"pid": "pid:[1]"})
    assessment = _assessment(evidence)
    assert assessment.clean is False
    assert "namespace_inventory_invalid" in assessment.violations


def test_fd_inventory_count_must_match_retained_targets() -> None:
    clean = _clean()
    evidence = _replace_identity(
        clean,
        "successors",
        0,
        open_extra_fd_count=clean.successors[0].identity.open_extra_fd_count + 1,
    )
    assessment = _assessment(evidence)
    assert assessment.clean is False
    assert "actor_os_isolation_invalid" in assessment.violations


def test_process_namespace_fresh_flag_is_required() -> None:
    assessment = _assessment(_clean().model_copy(update={"process_namespace_fresh": False}))
    assert assessment.clean is False
    assert "runtime_process_reuse" in assessment.violations


def test_process_identity_is_pid_and_start_tick_pair() -> None:
    clean = _clean()
    predecessor = clean.predecessors[0]
    successor_pid_reuse = _replace_runtime_record(
        clean,
        "successors",
        0,
        runtime_process_id=predecessor.runtime_process_id,
    )
    # A recycled host PID with a different actor-recorded start tick is a
    # distinct process identity and must not trigger a tick-only/PID-only
    # reuse violation.
    assessment = _assessment(successor_pid_reuse)
    assert "runtime_process_reuse" not in assessment.violations

    exact_pair_reuse = _replace_identity(
        successor_pid_reuse,
        "successors",
        0,
        namespace_process_start_ticks=predecessor.identity.namespace_process_start_ticks,
    )
    assessment = _assessment(exact_pair_reuse)
    assert assessment.clean is False
    assert "runtime_process_reuse" in assessment.violations
    assert "process_start_identity_reuse" not in assessment.violations


@pytest.mark.parametrize(
    "network_update, expected",
    [
        ({"default_route": True, "external_connect": False, "dns_resolved": False, "route_hash": "x"}, "actor_default_route_present"),
        ({"default_route": False, "external_connect": True, "dns_resolved": False, "route_hash": "x"}, "actor_external_network_reachable"),
        ({"default_route": False, "external_connect": False, "dns_resolved": True, "route_hash": "x"}, "actor_dns_reachable"),
        ({"default_route": False, "external_connect": False, "dns_resolved": False}, "network_probe_surface_incomplete"),
        ({"default_route": False, "external_connect": False, "dns_resolved": False, "route_hash": "not-a-hash"}, "network_probe_surface_incomplete"),
    ],
    ids=[
        "default-route",
        "external-connect",
        "dns",
        "omitted-route-hash",
        "malformed-route-hash",
    ],
)
def test_network_default_dns_external_and_missing_key_mutations_fail_closed(
    network_update: dict[str, Any], expected: str
) -> None:
    assessment = _assessment(_clean().model_copy(update={"network_probe": network_update}))
    assert assessment.clean is False
    assert expected in assessment.violations


def test_network_mode_and_tool_allowlist_are_fail_closed() -> None:
    no_network = _assessment(_clean().model_copy(update={"actor_network_mode": "unshared-allow"}))
    assert no_network.clean is False
    assert "actor_egress_or_tools_enabled" in no_network.violations

    tools = _assessment(_clean().model_copy(update={"actor_tools": ("shell",)}))
    assert tools.clean is False
    assert "actor_egress_or_tools_enabled" in tools.violations


@pytest.mark.parametrize(
    "mutation, expected",
    [
        (
            lambda e: e.model_copy(update={"provider_store_requested": True}),
            "provider_store_request_not_false",
        ),
        (
            lambda e: e.model_copy(update={"provider_storage_observed": True}),
            "provider_storage_observed_true",
        ),
        (
            lambda e: e.model_copy(update={"registry_private_key_count": 1}),
            "orchestrator_signing_capability",
        ),
        (
            lambda e: e.model_copy(update={"scientific_result": True}),
            "scientific_result_present",
        ),
    ],
    ids=["provider-store", "provider-storage-observed", "private-key", "scientific-result"],
)
def test_provider_credential_and_scientific_flags_fail_closed(
    mutation: Callable[[RuntimeBoundaryEvidence], RuntimeBoundaryEvidence], expected: str
) -> None:
    assessment = _assessment(mutation(_clean()))
    assert assessment.clean is False
    assert expected in assessment.violations


def test_live_model_call_count_is_nonscientific_gate() -> None:
    """A canary with a nonzero live count must never qualify as mechanical."""

    assessment = _assessment(_clean().model_copy(update={"live_model_calls": 1}))
    assert assessment.clean is False
    assert "live_model_calls_nonzero" in assessment.violations


@pytest.mark.parametrize(
    "teardown_update, expected",
    [
        ({"lifecycle_id": "unmatched-lifecycle"}, "predecessor_teardown_unmatched"),
        ({"actor_id": "unmatched-actor"}, "teardown_actor_correspondence_invalid"),
        ({"process_absent": False}, "predecessor_teardown_incomplete"),
        ({"process_group_absent": False}, "predecessor_teardown_incomplete"),
        ({"private_root_removed": False}, "predecessor_teardown_incomplete"),
        ({"key_invalidated": False}, "predecessor_teardown_incomplete"),
        ({"return_code": 70}, "predecessor_crash_unqualified"),
    ],
    ids=[
        "unmatched-lifecycle",
        "unmatched-actor",
        "live-process",
        "live-group",
        "root-retained",
        "key-retained",
        "crash",
    ],
)
def test_teardown_correspondence_and_crash_semantics_fail_closed(
    teardown_update: dict[str, Any], expected: str
) -> None:
    evidence = _clean().model_copy(
        update={"teardowns": _one_teardown(_clean(), **teardown_update)}
    )
    assessment = _assessment(evidence)
    assert assessment.clean is False
    assert expected in assessment.violations


def test_missing_teardown_population_fails_closed() -> None:
    assessment = _assessment(_clean().model_copy(update={"teardowns": ()}))
    assert assessment.clean is False
    assert "predecessor_teardown_incomplete" in assessment.violations
    assert "predecessor_teardown_unmatched" in assessment.violations


def test_duplicate_teardown_evidence_fails_closed() -> None:
    clean = _clean()
    duplicate = (clean.teardowns[0], clean.teardowns[0])
    assessment = _assessment(clean.model_copy(update={"teardowns": duplicate}))
    assert assessment.clean is False
    assert "teardown_actor_correspondence_invalid" in assessment.violations


def test_retry_attempt_with_wrong_request_or_response_cannot_support_l0() -> None:
    clean = _clean()
    attempt = clean.retry_attempts[-1]
    bad_hash = attempt.model_copy(update={"request_hash": "0" * 64})
    assessment = _assessment(clean.model_copy(update={"retry_attempts": (bad_hash,)}))
    assert assessment.clean is False
    assert "provider_attempt_record_invalid" in assessment.violations

    bad_response = attempt.model_copy(update={"provider_response_id": "other-response"})
    assessment = _assessment(clean.model_copy(update={"retry_attempts": (bad_response,)}))
    assert assessment.clean is False
    assert "provider_attempt_record_invalid" in assessment.violations


def test_carrier_reader_must_be_successor_and_lineage_bound() -> None:
    clean = _clean()
    record = clean.carrier_records[0]
    mutated = record.model_copy(update={"read_by": (clean.predecessors[0].identity.actor_id,)})
    assessment = _assessment(clean.model_copy(update={"carrier_records": (mutated,)}))
    assert assessment.clean is False
    assert "declared_carrier_provenance_invalid" in assessment.violations


@pytest.mark.parametrize(
    "record_update",
    [
        lambda record: record.model_copy(
            update={
                "read_actions": (
                    record.read_actions[0].model_copy(
                        update={"parent_hashes": (record.content_hash,)}
                    ),
                )
            }
        ),
        lambda record: record.model_copy(
            update={
                "read_actions": (
                    record.read_actions[0].model_copy(
                        update={"generation": record.generation}
                    ),
                )
            }
        ),
        lambda record: record.model_copy(
            update={
                "read_actions": (
                    record.read_actions[0].model_copy(
                        update={"session_id": "spliced-session"}
                    ),
                )
            }
        ),
    ],
    ids=["reader-parent-tuple", "reader-generation", "reader-identity"],
)
def test_carrier_reader_exact_signed_binding_fail_closed(
    record_update: Callable[[Any], Any],
) -> None:
    clean = _clean()
    mutated = record_update(clean.carrier_records[0])
    assessment = _assessment(clean.model_copy(update={"carrier_records": (mutated,)}))
    assert assessment.clean is False
    assert "declared_carrier_provenance_invalid" in assessment.violations


@pytest.mark.parametrize(
    "record_update",
    [
        lambda record: record.model_copy(
            update={
                "writer": record.writer.model_copy(
                    update={"payload_hash": "0" * 64}
                )
            }
        ),
        lambda record: record.model_copy(
            update={
                "writer": record.writer.model_copy(update={"parent_hashes": ()})
            }
        ),
        lambda record: record.model_copy(update={"write_authority": "0" * 64}),
        lambda record: record.model_copy(update={"writer": None}),
        lambda record: record.model_copy(update={"carrier_id": "relabelled"}),
        lambda record: record.model_copy(
            update={
                "writer": record.writer.model_copy(
                    update={"session_id": "spliced-session"}
                )
            }
        ),
    ],
    ids=[
        "writer-content-binding",
        "writer-parent-binding",
        "write-authority",
        "missing-writer",
        "carrier-id-relabel",
        "writer-identity-splice",
    ],
)
def test_carrier_writer_edge_and_binding_fail_closed(
    record_update: Callable[[Any], Any],
) -> None:
    clean = _clean()
    mutated = record_update(clean.carrier_records[0])
    assessment = _assessment(clean.model_copy(update={"carrier_records": (mutated,)}))
    assert assessment.clean is False
    assert "declared_carrier_provenance_invalid" in assessment.violations


@pytest.mark.parametrize(
    "mutation, expected",
    [
        (
            lambda e: e.model_copy(update={"carrier_capabilities": ()}),
            "carrier_capability_inventory_invalid",
        ),
        (
            lambda e: e.model_copy(
                update={
                    "carrier_capabilities": (
                        *e.carrier_capabilities,
                        e.carrier_capabilities[0],
                    )
                }
            ),
            "carrier_capability_inventory_invalid",
        ),
        (
            lambda e: e.model_copy(
                update={
                    "carrier_capabilities": (
                        e.carrier_capabilities[0].model_copy(update={"can_read": True}),
                        e.carrier_capabilities[1],
                    )
                }
            ),
            "carrier_capability_inventory_invalid",
        ),
        (
            lambda e: e.model_copy(
                update={
                    "carrier_capabilities": (
                        e.carrier_capabilities[0].model_copy(
                            update={"actor_id": "spliced-writer"}
                        ),
                        e.carrier_capabilities[1],
                    )
                }
            ),
            "carrier_capability_binding_invalid",
        ),
        (
            lambda e: e.model_copy(
                update={
                    "carrier_capabilities": (
                        e.carrier_capabilities[0],
                        e.carrier_capabilities[1].model_copy(
                            update={"attempt_id": "spliced-attempt"}
                        ),
                    )
                }
            ),
            "carrier_capability_attempt_invalid",
        ),
    ],
    ids=[
        "missing-inventory",
        "duplicate-capability",
        "mixed-permission",
        "writer-identity-splice",
        "reader-attempt-splice",
    ],
)
def test_carrier_capability_inventory_and_bindings_fail_closed(
    mutation: Callable[[RuntimeBoundaryEvidence], RuntimeBoundaryEvidence],
    expected: str,
) -> None:
    assessment = _assessment(mutation(_clean()))
    assert assessment.clean is False
    assert expected in assessment.violations


def test_one_reader_capability_can_authorize_multiple_signed_reads() -> None:
    clean = _clean()
    record = clean.carrier_records[0]
    repeated = record.model_copy(
        update={
            "read_by": (*record.read_by, record.read_by[0]),
            "read_actions": (*record.read_actions, record.read_actions[0]),
            "read_capability_hashes": (
                *record.read_capability_hashes,
                record.read_capability_hashes[0],
            ),
        }
    )
    assessment = _assessment(
        clean.model_copy(update={"carrier_records": (repeated,)})
    )
    assert "carrier_capability_binding_invalid" not in assessment.violations
    assert "carrier_capability_inventory_invalid" not in assessment.violations


@pytest.mark.parametrize(
    "schedule_update",
    [
        lambda schedule: schedule.model_copy(update={"schedule_hash": "0" * 64}),
        lambda schedule: schedule.model_copy(
            update={"provider_policy_hash": "0" * 64}
        ),
        lambda schedule: schedule.model_copy(
            update={"gateway_public_key_b64": "spliced-gateway-key"}
        ),
        lambda schedule: schedule.model_copy(
            update={"assignments": schedule.assignments[:-1]}
        ),
        lambda schedule: schedule.model_copy(
            update={
                "assignments": (
                    schedule.assignments[0],
                    schedule.assignments[1].model_copy(
                        update={"request_hash": "0" * 64}
                    ),
                )
            }
        ),
        lambda schedule: schedule.model_copy(
            update={
                "assignments": (
                    schedule.assignments[0].model_copy(
                        update={"actor_spec_hash": "0" * 64}
                    ),
                    schedule.assignments[1],
                )
            }
        ),
    ],
    ids=[
        "schedule-hash",
        "policy-pin",
        "gateway-key-pin",
        "missing-assignment",
        "request-pin",
        "actor-spec-pin",
    ],
)
def test_frozen_schedule_contract_fail_closed(
    schedule_update: Callable[[Any], Any],
) -> None:
    clean = _clean()
    mutated = schedule_update(clean.schedule_contract)
    assessment = _assessment(clean.model_copy(update={"schedule_contract": mutated}))
    assert assessment.clean is False
    assert "schedule_contract_invalid" in assessment.violations


@pytest.mark.parametrize(
    "mutation, expected",
    [
        (
            lambda e: e.model_copy(update={"schedule_contract": None}),
            "schedule_contract_invalid",
        ),
        (
            lambda e: e.model_copy(
                update={"carrier_capabilities": (*e.carrier_capabilities, None)}
            ),
            "carrier_capability_inventory_invalid",
        ),
        (
            lambda e: e.model_copy(update={"carrier_capabilities": None}),
            "carrier_capability_inventory_invalid",
        ),
    ],
    ids=["missing-schedule", "malformed-capability", "missing-capabilities"],
)
def test_malformed_nested_capability_evidence_returns_violation(
    mutation: Callable[[RuntimeBoundaryEvidence], RuntimeBoundaryEvidence],
    expected: str,
) -> None:
    assessment = _assessment(mutation(_clean()))
    assert assessment.clean is False
    assert expected in assessment.violations


@pytest.mark.parametrize(
    "mutation",
    [
        lambda e: e.model_copy(
            update={
                "provider_gateway_receipt": e.provider_gateway_receipt.model_copy(
                    update={"signature_b64": "forged-signature"}
                )
            }
        ),
        lambda e: e.model_copy(
            update={
                "provider_gateway_receipt": e.provider_gateway_receipt.model_copy(
                    update={"request_hash": "0" * 64}
                )
            }
        ),
        lambda e: e.model_copy(update={"provider_gateway_receipt": None}),
        lambda e: e.model_copy(
            update={
                "provider_response_acceptance": e.provider_response_acceptance.model_copy(
                    update={"payload_hash": "0" * 64}
                )
            }
        ),
        lambda e: e.model_copy(update={"provider_response_acceptance": None}),
    ],
    ids=[
        "gateway-receipt-signature",
        "gateway-receipt-request-binding",
        "missing-gateway-receipt",
        "provider-acceptance-payload",
        "missing-provider-acceptance",
    ],
)
def test_gateway_receipt_and_provider_acceptance_chain_fail_closed(
    mutation: Callable[[RuntimeBoundaryEvidence], RuntimeBoundaryEvidence],
) -> None:
    assessment = _assessment(mutation(_clean()))
    assert assessment.clean is False
    assert "provider_response_acceptance_invalid" in assessment.violations


@pytest.mark.parametrize(
    "field, update, expected",
    [
        (
            "provider_request_action",
            None,
            "provider_request_action_invalid",
        ),
        (
            "provider_request_action",
            {"actor_id": "spliced-actor"},
            "provider_request_action_invalid",
        ),
        (
            "successor_path_probe_action",
            None,
            "successor_probe_action_invalid",
        ),
        (
            "network_probe_action",
            {"payload_hash": "0" * 64},
            "network_probe_action_invalid",
        ),
        (
            "predecessor_canary",
            {"action": None},
            "predecessor_canary_evidence_invalid",
        ),
        (
            "successor_path_probe_action",
            {"parent_hashes": ("0" * 64,)},
            "successor_probe_action_invalid",
        ),
    ],
    ids=[
        "missing-provider-request-action",
        "spliced-provider-request-action",
        "missing-probe-action",
        "forged-network-action",
        "missing-canary-action-again",
        "probe-parent-tuple",
    ],
)
def test_signed_load_bearing_actor_actions_fail_closed(
    field: str, update: Any, expected: str
) -> None:
    clean = _clean()
    current = getattr(clean, field)
    replacement = None if update is None else current.model_copy(update=update)
    assessment = _assessment(clean.model_copy(update={field: replacement}))
    assert assessment.clean is False
    assert expected in assessment.violations


@pytest.mark.parametrize(
    "attempt_update",
    [
        {"lifecycle_id": "other-lifecycle"},
        {"logical_attempt_id": "other-attempt"},
        {"provider_request_id": "other-request"},
        {"dispatch_phase": "sent"},
        {"retryable": True},
    ],
    ids=["retry-lifecycle", "retry-logical-attempt", "retry-request-id", "retry-phase", "retryable"],
)
def test_accepted_retry_record_requires_exact_receipt_binding(
    attempt_update: dict[str, Any],
) -> None:
    clean = _clean()
    attempt = clean.retry_attempts[-1].model_copy(update=attempt_update)
    assessment = _assessment(clean.model_copy(update={"retry_attempts": (attempt,)}))
    assert assessment.clean is False
    assert "provider_attempt_record_invalid" in assessment.violations


def test_action_log_splicing_and_gaps_fail_closed() -> None:
    clean = _clean()
    forged = clean.provider_request_action.model_copy(
        update={"sequence": 99, "action_id": f"{clean.provider_request_action.lifecycle_id}:99"}
    )
    assessment = _assessment(clean.model_copy(update={"provider_request_action": forged}))
    assert assessment.clean is False
    assert "actor_action_log_invalid" in assessment.violations


def test_provider_acceptance_requires_exact_parent_tuple() -> None:
    clean = _clean()
    acceptance = clean.provider_response_acceptance.model_copy(
        update={
            "parent_hashes": (
                *clean.provider_response_acceptance.parent_hashes,
                "0" * 64,
            )
        }
    )
    assessment = _assessment(
        clean.model_copy(update={"provider_response_acceptance": acceptance})
    )
    assert assessment.clean is False
    assert "provider_response_acceptance_invalid" in assessment.violations


def test_clean_canary_is_not_a_behavioral_or_model_state_result() -> None:
    evidence = _clean()
    assert evidence.live_model_calls == 0
    assert evidence.scientific_result is False
    assert evidence.backend.startswith("scripted-")
    assert evidence.provider == "none"
    assert any(item.startswith("provider weights") for item in evidence.residual_opaque_state)
