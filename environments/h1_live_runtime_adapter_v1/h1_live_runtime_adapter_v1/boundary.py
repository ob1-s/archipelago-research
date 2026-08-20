"""End-to-end mechanical canary and fail-closed L0 boundary assessment."""

from __future__ import annotations

import base64
import importlib.metadata
import platform
import re
import secrets
import subprocess

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .attribution import ActionRegistry
from .canonical import sha256_bytes, stable_hash
from .carrier import (
    DeclaredCarrierStore,
    carrier_read_binding,
    carrier_write_binding,
)
from .crypto import (
    action_identity_binding,
    verify_action,
    verify_gateway_receipt,
    verify_registration,
)
from .isolation import BubblewrapActorFactory
from .lifecycle_journal import (
    LifecycleChainOutcome,
    LifecycleJournal,
    lifecycle_chain_outcome,
)
from .models import (
    ActorIdentity,
    ActorRuntimeRecord,
    ActorSpec,
    AssignmentContractPin,
    BoundaryAssessment,
    CanaryEvidence,
    CarrierCapability,
    GatewayReceipt,
    L0_CLAIM,
    LifecycleEvent,
    ProviderPolicy,
    RuntimeBoundaryEvidence,
    ScheduleContractPin,
    SignedAction,
    StateClass,
)
from .orchestrator import (
    FrozenAssignment,
    FrozenCommonConfig,
    Orchestrator,
    PredeclaredSchedule,
)
from .provider import (
    ProviderGateway,
    ScriptedMechanicalBackend,
    prepare_request,
    random_attempt_id,
)
from .state_manifest import common_prior_hashes, validate_state_manifest


ADAPTER_VERSION = "h1-live-runtime-adapter/v1"
NAMESPACE_NAMES = frozenset({"pid", "mnt", "ipc", "uts", "user", "cgroup", "net"})
CANARY_PATHS = frozenset(
    {
        "/work/private-canary.bin",
        "/home/private-canary.bin",
        "/tmp/private-canary.bin",
        "/dev/shm/private-canary.bin",
        "/cache/private-canary.bin",
        "/env-slot/private-canary.bin",
    }
)
CANARY_SURFACES = frozenset(
    {"workdir", "home", "tmp", "shared_memory", "cache", "env_path"}
)
RESIDUAL_OPAQUE_STATE = (
    "provider weights and inference substrate",
    "provider abuse-monitoring/application-state retention",
    "provider prompt-cache internals",
)


def _action_matches_identity(
    action: object, identities: tuple[ActorIdentity, ...]
) -> bool:
    """Require a signed action to belong to one complete recorded identity."""

    if not isinstance(action, SignedAction):
        return False
    return any(
        action.actor_id == identity.actor_id
        and action.lifecycle_id == identity.lifecycle_id
        and action.session_id == identity.session_id
        and action.generation == identity.generation
        and action.lineage_id == identity.lineage_id
        and action.public_key_b64 == identity.public_key_b64
        for identity in identities
    )


def _actor_spec_hash(identity: ActorIdentity) -> str:
    """Hash exactly the prelaunch fields embedded in an actor identity."""

    return stable_hash(
        ActorSpec(
            actor_id=identity.actor_id,
            lifecycle_id=identity.lifecycle_id,
            generation=identity.generation,
            lineage_id=identity.lineage_id,
            position=identity.position,
            gateway_public_key_b64=identity.gateway_public_key_b64,
        ).model_dump(mode="json")
    )


_LIFECYCLE_OUTCOME_VIOLATIONS: dict[LifecycleChainOutcome, str] = {
    "journal_sequence_invalid": "lifecycle_event_order_invalid",
    "missing_spawn": "predecessor_authorization_not_revoked",
    "missing_teardown": "predecessor_authorization_not_revoked",
    "missing_revocation": "predecessor_authorization_not_revoked",
    "duplicate_event": "lifecycle_event_duplicate",
    "out_of_order": "predecessor_lifecycle_order_invalid",
    "mismatched_metadata": "lifecycle_event_inconsistent_with_runtime_records",
}


def _journal_consistent_with_runtime_records(
    evidence: RuntimeBoundaryEvidence,
) -> bool:
    """Every journal row must map to a recorded runtime identity.

    Journal rows are durable controller entries bound to the frozen
    assignment that drove each transition: each row's attempt identifier,
    actor identity, lineage, and generation must match the recorded runtime
    identity.  A row that matches no record (fabricated lifecycle, actor,
    attempt, lineage, or generation) invalidates the whole lifecycle chain.
    """

    expected: list[tuple[str, str | None, str, str, int]] = []
    for record in evidence.predecessors:
        expected.append(
            (
                record.identity.lifecycle_id,
                evidence.predecessor_attempt_id,
                record.identity.actor_id,
                record.identity.lineage_id,
                record.identity.generation,
            )
        )
    schedule = evidence.schedule_contract
    successor_attempts: dict[str, str] = {}
    if isinstance(schedule, ScheduleContractPin):
        for assignment in schedule.assignments:
            successor_attempts[assignment.actor_spec_hash] = assignment.attempt_id
    for record in evidence.successors:
        expected.append(
            (
                record.identity.lifecycle_id,
                successor_attempts.get(_actor_spec_hash(record.identity)),
                record.identity.actor_id,
                record.identity.lineage_id,
                record.identity.generation,
            )
        )
    for event in evidence.lifecycle_events:
        if not any(
            entry[0] == event.lifecycle_id
            and entry[2] == event.actor_id
            and entry[3] == event.lineage_id
            and entry[4] == event.generation
            and (entry[1] is None or entry[1] == event.attempt_id)
            for entry in expected
        ):
            return False
    return True


def _retained_action_log_is_contiguous(actions: tuple[object, ...]) -> bool:
    """Reject spliced, duplicated, or gapped retained actor action logs."""

    by_lifecycle: dict[str, list[SignedAction]] = {}
    for action in actions:
        if not isinstance(action, SignedAction):
            return False
        if action.action_id != f"{action.lifecycle_id}:{action.sequence}":
            return False
        by_lifecycle.setdefault(action.lifecycle_id, []).append(action)
    for lifecycle_id, lifecycle_actions in by_lifecycle.items():
        sequences = [action.sequence for action in lifecycle_actions]
        if len(sequences) != len(set(sequences)):
            return False
        if sorted(sequences) != list(range(1, max(sequences) + 1)):
            return False
    return True


def common_prior_manifest(policy: ProviderPolicy | None = None) -> dict[str, str]:
    """Hashes exact local sources and the exact signed provider policy."""

    return common_prior_hashes(policy)


def assess_boundary(evidence: RuntimeBoundaryEvidence) -> BoundaryAssessment:
    validate_state_manifest()
    violations: list[str] = []
    hash_pattern = re.compile(r"^[0-9a-f]{64}$")
    predecessor_ids = {record.identity.actor_id for record in evidence.predecessors}
    successor_ids = {record.identity.actor_id for record in evidence.successors}
    predecessor_identities = tuple(
        record.identity for record in evidence.predecessors
    )
    successor_identities = tuple(record.identity for record in evidence.successors)
    if not evidence.predecessors or not evidence.successors:
        violations.append("missing_turnover_population")
    if predecessor_ids & successor_ids:
        violations.append("actor_identity_reuse")
    for field in ("lifecycle_id", "session_id", "public_key_b64"):
        before = {getattr(record.identity, field) for record in evidence.predecessors}
        after = {getattr(record.identity, field) for record in evidence.successors}
        if before & after:
            violations.append(f"{field}_reuse")
    # A host PID can be recycled and the kernel start-tick clock is coarse.
    # Neither field is a sufficient process identity on its own.  The
    # evidence identity is their pair: this catches exact reuse while
    # allowing two distinct processes that happened to start in one tick.
    before_process_identities = {
        (record.runtime_process_id, record.identity.namespace_process_start_ticks)
        for record in evidence.predecessors
    }
    after_process_identities = {
        (record.runtime_process_id, record.identity.namespace_process_start_ticks)
        for record in evidence.successors
    }
    if before_process_identities & after_process_identities or not evidence.process_namespace_fresh:
        violations.append("runtime_process_reuse")
    for record in (*evidence.predecessors, *evidence.successors):
        identity = record.identity
        if (
            identity.namespace_pid != 1
            or int(identity.effective_capabilities_hex, 16) != 0
            or not identity.no_new_privileges
            or not verify_registration(identity)
            or not isinstance(identity.open_extra_fd_targets, dict)
            or identity.open_extra_fd_count != len(identity.open_extra_fd_targets)
        ):
            violations.append("actor_os_isolation_invalid")
        if set(identity.namespace_ids) != NAMESPACE_NAMES or any(
            not value for value in identity.namespace_ids.values()
        ):
            violations.append("namespace_inventory_invalid")
        if any(
            target != "/dev/urandom"
            for target in identity.open_extra_fd_targets.values()
        ):
            violations.append("actor_open_handle_violation")
    predecessor_lineages = {
        record.identity.lineage_id for record in evidence.predecessors
    }
    predecessor_lifecycles = {
        record.identity.lifecycle_id for record in evidence.predecessors
    }
    successor_lineages = {record.identity.lineage_id for record in evidence.successors}
    if predecessor_lineages != successor_lineages:
        violations.append("lineage_mismatch")
    if evidence.predecessors and evidence.successors and max(
        record.identity.generation for record in evidence.predecessors
    ) >= min(record.identity.generation for record in evidence.successors):
        violations.append("generation_order_invalid")
    if not evidence.teardowns or any(
        not (
            item.process_absent
            and item.process_group_absent
            and item.private_root_removed
            and item.key_invalidated
        )
        for item in evidence.teardowns
    ):
        violations.append("predecessor_teardown_incomplete")
    if any(item.return_code != 0 for item in evidence.teardowns):
        violations.append("predecessor_crash_unqualified")
    teardown_lifecycles = {item.lifecycle_id for item in evidence.teardowns}
    if not {
        record.identity.lifecycle_id for record in evidence.predecessors
    }.issubset(teardown_lifecycles):
        violations.append("predecessor_teardown_unmatched")
    expected_teardowns = {
        (record.identity.actor_id, record.identity.lifecycle_id)
        for record in (*evidence.predecessors, *evidence.successors)
    }
    expected_process_ids = {
        (record.identity.actor_id, record.identity.lifecycle_id): record.runtime_process_id
        for record in (*evidence.predecessors, *evidence.successors)
    }
    observed_teardowns = [
        (item.actor_id, item.lifecycle_id) for item in evidence.teardowns
    ]
    if len(observed_teardowns) != len(set(observed_teardowns)) or set(
        observed_teardowns
    ) != expected_teardowns:
        violations.append("teardown_actor_correspondence_invalid")
    if any(
        (item.actor_id, item.lifecycle_id) in expected_process_ids
        and (
            item.launcher_pid
            != expected_process_ids[(item.actor_id, item.lifecycle_id)]
            or item.runtime_process_id
            != expected_process_ids[(item.actor_id, item.lifecycle_id)]
        )
        for item in evidence.teardowns
    ):
        violations.append("teardown_process_identity_invalid")
    # Controller-side lifecycle journal: revocation of a predecessor's
    # public-key authorization is L0 evidence distinct from the teardown's
    # factory-scoped key_invalidated flag.  A skipped registry.revoke() must
    # fail L0 even when every teardown record is mechanically complete.  The
    # journal is the same durable, append-only controller journal the reusable
    # runtime produces, so rows carry the frozen assignment identity, must be
    # globally ordered and unique, must appear exactly once per lifecycle
    # event, and must be falsifiable against the recorded runtime identities.
    event_sequences = [item.sequence for item in evidence.lifecycle_events]
    if len(event_sequences) != len(set(event_sequences)) or any(
        sequence != index for index, sequence in enumerate(event_sequences)
    ):
        violations.append("lifecycle_event_order_invalid")
    else:
        events_by_lifecycle: dict[str, list[LifecycleEvent]] = {}
        for event in evidence.lifecycle_events:
            events_by_lifecycle.setdefault(event.lifecycle_id, []).append(event)
        if any(
            len({item.event for item in items}) != len(items)
            for items in events_by_lifecycle.values()
        ):
            violations.append("lifecycle_event_duplicate")
        elif any(
            [item.event for item in items]
            != ["spawned", "teardown_complete", "authorization_revoked"][: len(items)]
            for items in events_by_lifecycle.values()
        ):
            violations.append("lifecycle_event_order_invalid")
        if not _journal_consistent_with_runtime_records(evidence):
            violations.append("lifecycle_event_inconsistent_with_runtime_records")
        predecessor_chain_ok = True
        for record in evidence.predecessors:
            outcome = lifecycle_chain_outcome(
                evidence.lifecycle_events,
                lifecycle_id=record.identity.lifecycle_id,
                attempt_id=evidence.predecessor_attempt_id,
                actor_id=record.identity.actor_id,
                lineage_id=record.identity.lineage_id,
                generation=record.identity.generation,
            )
            if outcome != "complete":
                predecessor_chain_ok = False
                violation = _LIFECYCLE_OUTCOME_VIOLATIONS[outcome]
                if violation not in violations:
                    violations.append(violation)
                break
        successor_lifecycles = {
            record.identity.lifecycle_id for record in evidence.successors
        }
        successor_spawn_events = [
            event
            for event in evidence.lifecycle_events
            if event.event == "spawned"
            and event.lifecycle_id in successor_lifecycles
        ]
        if len(successor_spawn_events) != len(successor_lifecycles) or {
            event.lifecycle_id for event in successor_spawn_events
        } != successor_lifecycles:
            violations.append("successor_spawn_event_missing")
        if predecessor_chain_ok:
            revoked_sequences = {
                event.sequence
                for event in evidence.lifecycle_events
                if event.event == "authorization_revoked"
                and event.lifecycle_id in predecessor_lifecycles
            }
            successor_spawn_sequences = [
                event.sequence
                for event in evidence.lifecycle_events
                if event.event == "spawned"
                and event.lifecycle_id in successor_lifecycles
            ]
            if successor_spawn_sequences and revoked_sequences and not all(
                revoked < successor_spawn_sequences[0]
                for revoked in revoked_sequences
            ):
                violations.append("predecessor_revocation_not_before_successor_start")
    canary = evidence.predecessor_canary
    canary_payload = {
        "actor_id": canary.actor_id,
        "path_hashes": canary.path_hashes,
        "environment_value_hash": canary.environment_value_hash,
        "paths": list(canary.paths),
        "history_length": canary.history_length,
    }
    if (
        canary.actor_id not in predecessor_ids
        or set(canary.paths) != CANARY_PATHS
        or set(canary.path_hashes) != CANARY_SURFACES
        or any(not hash_pattern.fullmatch(value) for value in canary.path_hashes.values())
        or not hash_pattern.fullmatch(canary.environment_value_hash)
        or canary.history_length <= 0
        or not isinstance(canary.action, SignedAction)
        or not verify_action(canary.action)
        or canary.action.action != "write_canaries"
        or tuple(canary.action.parent_hashes) != ()
        or not _action_matches_identity(canary.action, predecessor_identities)
        or canary.action.payload_hash != stable_hash(canary_payload)
    ):
        violations.append("predecessor_canary_evidence_invalid")
    if any(evidence.successor_path_probes.values()):
        violations.append("predecessor_private_file_visible")
    if set(evidence.successor_path_probes) != set(evidence.predecessor_canary.paths):
        violations.append("filesystem_probe_surface_incomplete")
    probe_payload = {
        "path_probes": evidence.successor_path_probes,
        "environment_value_hash": evidence.successor_environment_value_hash,
        "history_length": evidence.successor_history_length_at_spawn,
    }
    if (
        not isinstance(evidence.successor_path_probe_action, SignedAction)
        or not verify_action(evidence.successor_path_probe_action)
        or evidence.successor_path_probe_action.action != "probe_paths"
        or tuple(evidence.successor_path_probe_action.parent_hashes) != ()
        or not _action_matches_identity(
            evidence.successor_path_probe_action, successor_identities
        )
        or evidence.successor_path_probe_action.payload_hash
        != stable_hash(probe_payload)
    ):
        violations.append("successor_probe_action_invalid")
    if evidence.successor_history_length_at_spawn != 0:
        violations.append("predecessor_history_visible")
    if (
        evidence.successor_environment_value_hash
        == evidence.predecessor_canary.environment_value_hash
        or evidence.env_or_cache_reused
    ):
        violations.append("environment_or_cache_reuse")
    if evidence.private_mount_reused:
        violations.append("private_mount_reuse")
    if evidence.stale_worker_reused:
        violations.append("stale_worker_reuse")
    if evidence.signing_key_reused:
        violations.append("signing_key_reuse")
    if evidence.undeclared_external_carrier:
        violations.append("undeclared_external_carrier")
    if evidence.provider_continuation_present:
        violations.append("provider_continuation_present")
    if evidence.provider_store_requested is not False:
        violations.append("provider_store_request_not_false")
    if evidence.provider_storage_observed is True:
        violations.append("provider_storage_observed_true")
    if evidence.provider_status != "completed":
        violations.append("provider_response_not_completed")
    if evidence.actor_network_mode != "unshared-deny" or evidence.actor_tools:
        violations.append("actor_egress_or_tools_enabled")
    if evidence.network_probe.get("default_route") is not False:
        violations.append("actor_default_route_present")
    if evidence.network_probe.get("external_connect") is not False:
        violations.append("actor_external_network_reachable")
    if evidence.network_probe.get("dns_resolved") is not False:
        violations.append("actor_dns_reachable")
    if set(evidence.network_probe) != {
        "default_route",
        "external_connect",
        "dns_resolved",
        "route_hash",
    } or not isinstance(evidence.network_probe.get("route_hash"), str) or not hash_pattern.fullmatch(
        evidence.network_probe["route_hash"]
    ):
        violations.append("network_probe_surface_incomplete")
    if (
        not isinstance(evidence.network_probe_action, SignedAction)
        or not verify_action(evidence.network_probe_action)
        or evidence.network_probe_action.action != "network_probe"
        or tuple(evidence.network_probe_action.parent_hashes) != ()
        or not _action_matches_identity(
            evidence.network_probe_action, successor_identities
        )
        or evidence.network_probe_action.payload_hash
        != stable_hash(evidence.network_probe)
    ):
        violations.append("network_probe_action_invalid")
    if evidence.registry_private_key_count != 0:
        violations.append("orchestrator_signing_capability")
    if not evidence.carrier_positive_read:
        violations.append("declared_carrier_positive_control_failed")
    if not evidence.carrier_records:
        violations.append("declared_carrier_record_missing")
    raw_carrier_capabilities = evidence.carrier_capabilities
    carrier_capabilities = (
        tuple(
            capability
            for capability in raw_carrier_capabilities
            if isinstance(capability, CarrierCapability)
        )
        if isinstance(raw_carrier_capabilities, (tuple, list))
        else ()
    )
    used_capability_hashes: set[str] = set()
    if (
        not carrier_capabilities
        or not isinstance(raw_carrier_capabilities, tuple)
        or len(carrier_capabilities) != len(raw_carrier_capabilities)
        or len(
            {capability.capability_hash for capability in carrier_capabilities}
        )
        != len(carrier_capabilities)
        or any(
            capability.can_read == capability.can_write
            for capability in carrier_capabilities
        )
        or any(
            capability.capability_hash != stable_hash(capability.semantic_payload)
            for capability in carrier_capabilities
        )
    ):
        violations.append("carrier_capability_inventory_invalid")
    for record in evidence.carrier_records:
        writer = record.writer
        writer_binding_valid = False
        write_authority_valid = False
        if isinstance(writer, SignedAction):
            try:
                expected_binding = carrier_write_binding(
                    carrier_id=record.carrier_id,
                    carrier_class=record.carrier_class,
                    lineage_id=record.lineage_id,
                    generation=record.generation,
                    content_hash=record.content_hash,
                    parent_hashes=tuple(record.parent_hashes),
                )
            except (TypeError, ValueError):
                expected_binding = None
            if expected_binding is not None:
                writer_binding_valid = tuple(writer.parent_hashes) == (
                    *record.parent_hashes,
                    expected_binding,
                )
            write_authority_valid = record.write_authority == stable_hash(
                {
                    "lifecycle_id": writer.lifecycle_id,
                    "public_key": writer.public_key_b64,
                }
            )
        if (
            not record.finalized
            or not hash_pattern.fullmatch(record.content_hash)
            or not isinstance(writer, SignedAction)
            or not verify_action(writer)
            or writer.action != "carrier_write"
            or not _action_matches_identity(writer, predecessor_identities)
            or writer.actor_id not in predecessor_ids
            or writer.lifecycle_id not in predecessor_lifecycles
            or writer.lineage_id != record.lineage_id
            or writer.generation != record.generation
            or writer.payload_hash != record.content_hash
            or not writer_binding_valid
            or not write_authority_valid
            or not set(record.read_by) & successor_ids
            or not record.read_actions
            or any(not isinstance(action, SignedAction) for action in record.read_actions)
            or record.read_by
            != tuple(action.actor_id for action in record.read_actions)
            or any(
                not verify_action(action)
                or not _action_matches_identity(action, successor_identities)
                or action.actor_id not in successor_ids
                or action.payload_hash != record.content_hash
                or action.lineage_id != record.lineage_id
                or action.generation <= record.generation
                or tuple(action.parent_hashes)
                != (record.content_hash, carrier_read_binding(record))
                for action in record.read_actions
            )
        ):
            violations.append("declared_carrier_provenance_invalid")
        writer_capabilities = (
            tuple(
                capability
                for capability in carrier_capabilities
                if capability.can_write
                and capability.attempt_id == evidence.predecessor_attempt_id
                and capability.actor_id == writer.actor_id
                and capability.lifecycle_id == writer.lifecycle_id
                and capability.lineage_id == record.lineage_id
                and capability.generation == record.generation
                and capability.carrier_id == record.carrier_id
                and capability.carrier_class == record.carrier_class
            )
            if isinstance(writer, SignedAction)
            else ()
        )
        read_capabilities_by_action = tuple(
            tuple(
                capability
                for capability in carrier_capabilities
                if capability.can_read
                and capability.carrier_id == record.carrier_id
                and capability.carrier_class == record.carrier_class
                and capability.actor_id == action.actor_id
                and capability.lifecycle_id == action.lifecycle_id
                and capability.lineage_id == action.lineage_id
                and capability.generation == action.generation
            )
            for action in record.read_actions
        )
        if len(writer_capabilities) == 1:
            used_capability_hashes.add(writer_capabilities[0].capability_hash)
        for matches in read_capabilities_by_action:
            if len(matches) == 1:
                used_capability_hashes.add(matches[0].capability_hash)
        expected_read_capability_hashes = tuple(
            matches[0].capability_hash
            for matches in read_capabilities_by_action
            if len(matches) == 1
        )
        if (
            len(writer_capabilities) != 1
            or any(len(matches) != 1 for matches in read_capabilities_by_action)
            or record.write_capability_hash
            != (
                writer_capabilities[0].capability_hash
                if len(writer_capabilities) == 1
                else None
            )
            or record.read_capability_hashes != expected_read_capability_hashes
        ):
            violations.append("carrier_capability_binding_invalid")
    if used_capability_hashes != {
        capability.capability_hash for capability in carrier_capabilities
    }:
        violations.append("carrier_capability_inventory_invalid")
    retained_actions: list[object] = [canary.action]
    for record in evidence.carrier_records:
        retained_actions.append(record.writer)
        retained_actions.extend(record.read_actions)
    retained_actions.extend(
        [
            evidence.successor_path_probe_action,
            evidence.network_probe_action,
        ]
    )
    if not hash_pattern.fullmatch(evidence.provider_request_hash):
        violations.append("provider_request_hash_invalid")
    if not hash_pattern.fullmatch(evidence.provider_assignment_hash):
        violations.append("provider_assignment_hash_invalid")
    provider_request_action = evidence.provider_request_action
    if (
        not isinstance(provider_request_action, SignedAction)
        or not verify_action(provider_request_action)
        or provider_request_action.action != "provider_request"
        or not _action_matches_identity(provider_request_action, successor_identities)
        or provider_request_action.payload_hash != evidence.provider_request_hash
        or tuple(provider_request_action.parent_hashes) != ()
    ):
        violations.append("provider_request_action_invalid")
    retained_actions.append(provider_request_action)
    acceptance = evidence.provider_response_acceptance
    receipt = evidence.provider_gateway_receipt
    if not isinstance(receipt, GatewayReceipt) or any(
        capability.can_read and capability.attempt_id != receipt.logical_attempt_id
        for capability in carrier_capabilities
    ):
        violations.append("carrier_capability_attempt_invalid")
    successor_lifecycles = {
        record.identity.lifecycle_id for record in evidence.successors
    }
    if (
        not isinstance(receipt, GatewayReceipt)
        or not isinstance(acceptance, SignedAction)
        or not isinstance(provider_request_action, SignedAction)
        or not verify_gateway_receipt(receipt)
        or receipt.output_hash != evidence.provider_output_hash
        or receipt.request_hash != evidence.provider_request_hash
        or receipt.assignment_hash != evidence.provider_assignment_hash
        or receipt.response_id != evidence.provider_response_id
        or receipt.provider_request_id != evidence.provider_request_id
        or receipt.recipient_binding
        != action_identity_binding(provider_request_action)
        or receipt.public_key_b64
        not in {
            record.identity.gateway_public_key_b64
            for record in evidence.successors
        }
        or not verify_action(acceptance)
        or acceptance.action != "provider_response_accept"
        or acceptance.actor_id not in successor_ids
        or acceptance.lifecycle_id not in successor_lifecycles
        or not _action_matches_identity(acceptance, successor_identities)
        or any(
            getattr(acceptance, field) != getattr(provider_request_action, field)
            for field in (
                "actor_id",
                "lifecycle_id",
                "session_id",
                "generation",
                "lineage_id",
                "public_key_b64",
            )
        )
        or acceptance.payload_hash != evidence.provider_output_hash
        or tuple(acceptance.parent_hashes)
        != (
            evidence.provider_request_hash,
            stable_hash(receipt.model_dump(mode="json")),
        )
    ):
        violations.append("provider_response_acceptance_invalid")
    retained_actions.append(acceptance)
    if not _retained_action_log_is_contiguous(tuple(retained_actions)):
        violations.append("actor_action_log_invalid")
    if not evidence.provider_response_id:
        violations.append("provider_response_id_missing")
    if not evidence.retry_attempts:
        violations.append("provider_attempt_record_missing")
    else:
        expected_logical_attempt_id = (
            receipt.logical_attempt_id if isinstance(receipt, GatewayReceipt) else None
        )
        successor_pairs = {
            (identity.actor_id, identity.lifecycle_id)
            for identity in successor_identities
        }
        if not any(
            attempt.outcome == "accepted_completed"
            and attempt.request_hash == evidence.provider_request_hash
            and (attempt.actor_id, attempt.lifecycle_id) in successor_pairs
            and attempt.logical_attempt_id == expected_logical_attempt_id
            and attempt.provider_request_id == evidence.provider_request_id
            and attempt.provider_response_id == evidence.provider_response_id
            and attempt.dispatch_phase == "response_received"
            and attempt.retryable is False
            for attempt in evidence.retry_attempts
        ):
            violations.append("provider_attempt_record_invalid")
    if evidence.scientific_result:
        violations.append("scientific_result_present")
    if evidence.live_model_calls != 0:
        violations.append("live_model_calls_nonzero")
    if evidence.residual_opaque_state != RESIDUAL_OPAQUE_STATE:
        violations.append("opaque_state_inventory_invalid")
    if not evidence.common_prior_hashes or any(
        not hash_pattern.fullmatch(value)
        for value in evidence.common_prior_hashes.values()
    ):
        violations.append("common_prior_hashes_invalid")
    elif evidence.common_prior_hashes != common_prior_manifest(
        evidence.provider_policy
    ):
        violations.append("common_prior_hashes_mismatch")
    if evidence.model != evidence.provider_policy.model:
        violations.append("provider_policy_model_mismatch")
    receipt_attempt_id = (
        receipt.logical_attempt_id if isinstance(receipt, GatewayReceipt) else ""
    )
    receipt_public_key = (
        receipt.public_key_b64 if isinstance(receipt, GatewayReceipt) else ""
    )
    schedule = evidence.schedule_contract
    schedule_invalid = not isinstance(schedule, ScheduleContractPin)
    if isinstance(schedule, ScheduleContractPin):
        assignment_pins = {item.attempt_id: item for item in schedule.assignments}
        capability_hashes_by_attempt = {
            attempt_id: tuple(
                sorted(
                    capability.capability_hash
                    for capability in carrier_capabilities
                    if capability.attempt_id == attempt_id
                )
            )
            for attempt_id in assignment_pins
        }
        expected_attempt_ids = {
            evidence.predecessor_attempt_id,
            receipt_attempt_id,
        }
        predecessor_pin = assignment_pins.get(evidence.predecessor_attempt_id)
        successor_pin = assignment_pins.get(receipt_attempt_id)
        expected_predecessor_assignment_hash = stable_hash(
            {
                "attempt_id": evidence.predecessor_attempt_id,
                "actor_spec_hashes": sorted(
                    _actor_spec_hash(identity) for identity in predecessor_identities
                ),
                "common_prior_hashes": evidence.common_prior_hashes,
                "carrier_capability_hashes": list(
                    capability_hashes_by_attempt.get(
                        evidence.predecessor_attempt_id, ()
                    )
                ),
            }
        )
        schedule_invalid = (
            set(assignment_pins) != expected_attempt_ids
            or schedule.schedule_hash != stable_hash(schedule.semantic_payload)
            or schedule.provider_policy_hash
            != stable_hash(evidence.provider_policy.model_dump(mode="json"))
            or schedule.common_prior_hashes != evidence.common_prior_hashes
            or schedule.gateway_public_key_b64 != receipt_public_key
            or any(
                identity.gateway_public_key_b64 != schedule.gateway_public_key_b64
                for identity in (*predecessor_identities, *successor_identities)
            )
            or predecessor_pin is None
            or predecessor_pin.assignment_hash
            != expected_predecessor_assignment_hash
            or predecessor_pin.actor_spec_hash
            not in {_actor_spec_hash(identity) for identity in predecessor_identities}
            or predecessor_pin.request_hash is not None
            or predecessor_pin.capability_hashes
            != capability_hashes_by_attempt.get(evidence.predecessor_attempt_id, ())
            or successor_pin is None
            or successor_pin.assignment_hash != evidence.provider_assignment_hash
            or successor_pin.actor_spec_hash
            not in {_actor_spec_hash(identity) for identity in successor_identities}
            or successor_pin.request_hash != evidence.provider_request_hash
            or successor_pin.capability_hashes
            != capability_hashes_by_attempt.get(receipt_attempt_id, ())
        )
    if schedule_invalid:
        violations.append("schedule_contract_invalid")
    clean = not violations
    return BoundaryAssessment(
        clean=clean,
        l0_supported=clean,
        l0_claim=L0_CLAIM if clean else None,
        violations=tuple(violations),
        predecessor_actor_ids=tuple(sorted(predecessor_ids)),
        successor_actor_ids=tuple(sorted(successor_ids)),
    )


async def run_clean_mechanical_canary() -> RuntimeBoundaryEvidence:
    factory = BubblewrapActorFactory()
    registry = ActionRegistry()
    gateway_private_key = Ed25519PrivateKey.generate()
    gateway_public_key_b64 = base64.b64encode(
        gateway_private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode()
    policy = ProviderPolicy(
        base_url="https://mechanical.invalid/v1", model="mechanical-no-model"
    )
    priors = common_prior_manifest(policy)
    provider_input = (
        {"role": "user", "content": "mechanical request-shape canary only"},
    )
    provider_instructions = "Return is not scientific evidence."
    attempt_id = random_attempt_id()
    predecessor_attempt_id = "mechanical-generation-0"
    predecessor_spec = ActorSpec(
        actor_id="generation-0-probe",
        lifecycle_id=f"lifecycle-{secrets.token_hex(8)}",
        generation=0,
        lineage_id="mechanical-lineage",
        position="boundary-probe",
        gateway_public_key_b64=gateway_public_key_b64,
    )
    successor_spec = ActorSpec(
        actor_id="generation-1-probe",
        lifecycle_id=f"lifecycle-{secrets.token_hex(8)}",
        generation=1,
        lineage_id="mechanical-lineage",
        position="boundary-probe",
        gateway_public_key_b64=gateway_public_key_b64,
    )
    writer_capability = CarrierCapability.from_fields(
        attempt_id=predecessor_attempt_id,
        actor_id=predecessor_spec.actor_id,
        lifecycle_id=predecessor_spec.lifecycle_id,
        lineage_id=predecessor_spec.lineage_id,
        generation=predecessor_spec.generation,
        carrier_id="declared-positive",
        carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
        can_write=True,
    )
    reader_capability = CarrierCapability.from_fields(
        attempt_id=attempt_id,
        actor_id=successor_spec.actor_id,
        lifecycle_id=successor_spec.lifecycle_id,
        lineage_id=successor_spec.lineage_id,
        generation=successor_spec.generation,
        carrier_id="declared-positive",
        carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
        can_read=True,
    )
    carrier = DeclaredCarrierStore(
        registry,
        capabilities=(writer_capability, reader_capability),
    )
    common_config = FrozenCommonConfig.from_mapping(
        config_id="mechanical-boundary-canary",
        config_version="v1",
        content={
            "boundary": "mechanical-canary",
            "common_prior_hashes": priors,
            "policy": policy.model_dump(mode="json"),
        },
    )
    predecessor_assignment = FrozenAssignment.from_input(
        attempt_id=predecessor_attempt_id,
        actor_spec=predecessor_spec,
        input=(),
        instructions="Mechanical boundary canary generation 0; not a scientific experiment.",
        common_config_hash=common_config.content_hash,
        declared_carrier_ids=("declared-positive",),
        carrier_capabilities=(writer_capability,),
    )
    successor_assignment = FrozenAssignment.from_input(
        attempt_id=attempt_id,
        actor_spec=successor_spec,
        input=provider_input,
        instructions=provider_instructions,
        common_config_hash=common_config.content_hash,
        declared_carrier_ids=("declared-positive",),
        carrier_capabilities=(reader_capability,),
    )
    schedule = PredeclaredSchedule.from_assignments(
        common_config=common_config,
        assignments=(predecessor_assignment, successor_assignment),
    )
    orchestrator = Orchestrator(
        schedule,
        factory=factory,
        carrier_store=carrier,
        registry=registry,
        journal=LifecycleJournal(),
    )
    await orchestrator.start_actor(predecessor_attempt_id)
    predecessor = orchestrator.live_actor(predecessor_attempt_id)
    predecessor_record = ActorRuntimeRecord(
        identity=predecessor.identity, runtime_process_id=predecessor.launcher_pid
    )
    try:
        await predecessor.command("append_history", value=secrets.token_hex(32))
        raw_canary = await predecessor.command("write_canaries")
        canary_action = predecessor.validate_action(raw_canary.pop("action"))
        if not registry.verify(canary_action):
            raise ValueError("predecessor canary action is not registry-authorized")
        canary = CanaryEvidence(
            actor_id=predecessor.spec.actor_id,
            action=canary_action,
            **raw_canary,
        )
        created = await predecessor.command(
            "create_mechanical_carrier",
            carrier_id="declared-positive",
            carrier_class=StateClass.DECLARED_LINEAGE_CARRIER.value,
            parent_hashes=[],
        )
        content = base64.b64decode(created["content_b64"])
        content_hash = created["content_hash"]
        writer = predecessor.validate_action(created["action"])
        carrier.write(
            carrier_id=created["carrier_id"],
            carrier_class=created["carrier_class"],
            content=content,
            writer=writer,
            parent_hashes=tuple(created["parent_hashes"]),
            capability=writer_capability,
        )
        carrier.finalize_and_hash(
            "declared-positive", capability=writer_capability
        )
    except BaseException:
        await factory.close()
        raise
    predecessor_teardown = await orchestrator.stop_actor(predecessor_attempt_id)

    provider_assignment_hash = stable_hash(
        {
            "actor": successor_spec.model_dump(mode="json"),
            "input": list(provider_input),
            "instructions": provider_instructions,
            "common_prior_hashes": priors,
            "carrier_capability_hashes": [reader_capability.capability_hash],
        }
    )
    expected_request_hash = stable_hash(
        {
            "policy": policy.model_dump(mode="json"),
            "input": list(provider_input),
            "instructions": provider_instructions,
            "attempt_id": attempt_id,
            "assignment_hash": provider_assignment_hash,
            "common_prior_hashes": priors,
        }
    )
    predecessor_assignment_hash = stable_hash(
        {
            "attempt_id": predecessor_attempt_id,
            "actor_spec_hashes": [stable_hash(predecessor_spec.model_dump(mode="json"))],
            "common_prior_hashes": priors,
            "carrier_capability_hashes": [writer_capability.capability_hash],
        }
    )
    schedule_contract = ScheduleContractPin.from_fields(
        provider_policy_hash=stable_hash(policy.model_dump(mode="json")),
        common_prior_hashes=priors,
        gateway_public_key_b64=gateway_public_key_b64,
        assignments=(
            AssignmentContractPin(
                attempt_id=predecessor_attempt_id,
                assignment_hash=predecessor_assignment_hash,
                actor_spec_hash=stable_hash(predecessor_spec.model_dump(mode="json")),
                capability_hashes=(writer_capability.capability_hash,),
            ),
            AssignmentContractPin(
                attempt_id=attempt_id,
                assignment_hash=provider_assignment_hash,
                actor_spec_hash=stable_hash(successor_spec.model_dump(mode="json")),
                request_hash=expected_request_hash,
                capability_hashes=(reader_capability.capability_hash,),
            ),
        ),
    )
    gateway = ProviderGateway(
        registry,
        expected_policy=policy,
        expected_common_prior_hashes=priors,
        expected_assignment_hashes={attempt_id: provider_assignment_hash},
        expected_request_hashes={attempt_id: expected_request_hash},
        expected_actor_specs={attempt_id: successor_spec},
        receipt_private_key=gateway_private_key,
    )
    await orchestrator.start_actor(attempt_id)
    successor = orchestrator.live_actor(attempt_id)
    successor_record = ActorRuntimeRecord(
        identity=successor.identity, runtime_process_id=successor.launcher_pid
    )
    try:
        probe = await successor.command("probe_paths", paths=list(canary.paths))
        successor_path_probe_action = successor.validate_action(probe.pop("action"))
        if not registry.verify(successor_path_probe_action):
            raise ValueError("successor probe action is not registry-authorized")
        network_probe = await successor.command("network_probe")
        network_probe_action = successor.validate_action(network_probe.pop("action"))
        if not registry.verify(network_probe_action):
            raise ValueError("network probe action is not registry-authorized")
        record, read_content = carrier.read(
            "declared-positive",
            capability=reader_capability,
            recipient=successor.identity,
        )
        read_raw = await successor.command(
            "carrier_read",
            carrier_id=record.carrier_id,
            content_b64=base64.b64encode(read_content).decode(),
            content_hash=record.content_hash,
            provenance_hash=carrier_read_binding(record),
        )
        reader = successor.validate_action(read_raw["action"])
        carrier.record_read(
            "declared-positive", reader, capability=reader_capability
        )

        request = await prepare_request(
            successor,
            policy=policy,
            input=provider_input,
            instructions=provider_instructions,
            attempt_id=attempt_id,
            assignment_hash=provider_assignment_hash,
            common_prior_hashes=priors,
        )
        if request.semantic_hash() != expected_request_hash:
            raise AssertionError("mechanical request semantic hash mismatch")
        response = await gateway.execute(request, ScriptedMechanicalBackend())
        assert response.gateway_receipt is not None
        accepted = await successor.command(
            "accept_provider_response",
            output_text=response.output_text,
            output_hash=response.output_hash,
            request_hash=response.request_hash,
            assignment_hash=request.assignment_hash,
            gateway_receipt=response.gateway_receipt.model_dump(mode="json"),
        )
        accepted_action = successor.validate_action(accepted["action"])
        registry.verify(accepted_action)
        successor_history_at_spawn = probe["history_length"]
        successor_env_hash = probe["environment_value_hash"]
        successor_path_probes = {
            path: value["exists"] for path, value in probe["probes"].items()
        }
    except BaseException:
        await factory.close()
        raise
    successor_teardown = await orchestrator.stop_actor(attempt_id)
    carrier_records = carrier.enumerate(capability=reader_capability)
    lifecycle_events = orchestrator.lifecycle_events
    evidence = RuntimeBoundaryEvidence(
        adapter_version=ADAPTER_VERSION,
        backend="scripted-mechanical-through-live-request-boundary",
        backend_version="scripted-mechanical/v1",
        provider="none",
        model="mechanical-no-model",
        runtime="bubblewrap-unshare-all",
        runtime_versions={
            "adapter_package": importlib.metadata.version("h1-live-runtime-adapter-v1"),
            "python": platform.python_version(),
            "bubblewrap": subprocess.check_output(
                ["bwrap", "--version"], text=True
            ).strip(),
            "verifiers": importlib.metadata.version("verifiers"),
            "openai": importlib.metadata.version("openai"),
            "cryptography": importlib.metadata.version("cryptography"),
        },
        schedule_contract=schedule_contract,
        predecessors=(predecessor_record,),
        successors=(successor_record,),
        teardowns=(predecessor_teardown, successor_teardown),
        lifecycle_events=lifecycle_events,
        predecessor_attempt_id=predecessor_attempt_id,
        predecessor_canary=canary,
        successor_path_probes=successor_path_probes,
        successor_path_probe_action=successor_path_probe_action,
        successor_history_length_at_spawn=successor_history_at_spawn,
        successor_environment_value_hash=successor_env_hash,
        network_probe_action=network_probe_action,
        carrier_capabilities=(writer_capability, reader_capability),
        carrier_records=carrier_records,
        carrier_positive_read=bool(carrier_records[0].read_by),
        provider_policy=policy,
        provider_assignment_hash=provider_assignment_hash,
        provider_request_hash=request.semantic_hash(),
        provider_request_action=request.action,
        provider_output_hash=response.output_hash,
        provider_gateway_receipt=response.gateway_receipt,
        provider_response_acceptance=accepted_action,
        provider_response_id=response.response_id,
        provider_request_id=response.request_id,
        provider_status=response.status,
        provider_store_requested=response.store_requested,
        provider_storage_observed=response.provider_storage_observed,
        provider_continuation_present=False,
        network_probe=network_probe,
        process_namespace_fresh=(
            (
                predecessor_record.runtime_process_id,
                predecessor.identity.namespace_process_start_ticks,
            )
            != (
                successor_record.runtime_process_id,
                successor.identity.namespace_process_start_ticks,
            )
            and predecessor.identity.namespace_pid
            == successor.identity.namespace_pid
            == 1
        ),
        private_mount_reused=False,
        env_or_cache_reused=False,
        stale_worker_reused=False,
        signing_key_reused=(
            predecessor.identity.public_key_b64 == successor.identity.public_key_b64
        ),
        undeclared_external_carrier=False,
        actor_network_mode="unshared-deny",
        actor_tools=(),
        registry_private_key_count=registry.private_key_count,
        common_prior_hashes=priors,
        retry_attempts=tuple(gateway.attempts),
        live_model_calls=0,
        residual_opaque_state=RESIDUAL_OPAQUE_STATE,
    )
    gateway.close()
    orchestrator.close()
    carrier.close()
    return evidence


def adversarial_fixture(
    clean: RuntimeBoundaryEvidence, case: str
) -> RuntimeBoundaryEvidence:
    mutations = {
        "A-session-continuation": {"provider_continuation_present": True},
        "B-reused-worker": {"stale_worker_reused": True},
        "C-filesystem-leak": {
            "successor_path_probes": {
                **clean.successor_path_probes,
                next(iter(clean.successor_path_probes)): True,
            }
        },
        "D-env-cache-leak": {"env_or_cache_reused": True},
        "E-signing-key-reuse": {"signing_key_reused": True},
        "F-undeclared-carrier": {"undeclared_external_carrier": True},
        "G-clean-declared-carrier": {},
        "H-skip-revocation": {
            "lifecycle_events": tuple(
                event.model_copy(update={"sequence": index})
                for index, event in enumerate(
                    candidate
                    for candidate in clean.lifecycle_events
                    if not (
                        candidate.event == "authorization_revoked"
                        and candidate.lifecycle_id
                        in {
                            record.identity.lifecycle_id
                            for record in clean.predecessors
                        }
                    )
                )
            )
        },
    }
    if case not in mutations:
        raise KeyError(case)
    return clean.model_copy(update=mutations[case])


RUNTIME_FIXTURES = (
    "A-session-continuation",
    "B-reused-worker",
    "C-filesystem-leak",
    "D-env-cache-leak",
    "E-signing-key-reuse",
    "F-undeclared-carrier",
    "G-clean-declared-carrier",
    "H-skip-revocation",
)
