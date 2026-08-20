"""Tests for the output-blind lifecycle control plane.

The fakes below stand in for Bubblewrap only where the test needs to exercise
schedule and signature semantics.  The optional smoke test starts the real
Bubblewrap actor but sends no actor command and makes no provider call.
"""

from __future__ import annotations

import base64
import inspect
import shutil
from dataclasses import dataclass
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from h1_live_runtime_adapter_v1.attribution import ActionRegistry
from h1_live_runtime_adapter_v1.canonical import canonical_bytes, stable_hash
from h1_live_runtime_adapter_v1.isolation import BubblewrapActorFactory
from h1_live_runtime_adapter_v1.lifecycle_journal import LifecycleJournal
from h1_live_runtime_adapter_v1.models import (
    ActorIdentity,
    ActorSpec,
    SignedAction,
    TeardownEvidence,
)
from h1_live_runtime_adapter_v1.carrier import CarrierCapability
from h1_live_runtime_adapter_v1.orchestrator import (
    FrozenAssignment,
    FrozenCommonConfig,
    Orchestrator,
    PredeclaredSchedule,
)


ACTION_DOMAIN = b"h1-live-runtime-action/v1\0"


def _public_key(private_key: Ed25519PrivateKey) -> str:
    return base64.b64encode(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode()


def _schedule(*, generations: tuple[int, ...] = (0, 1)) -> PredeclaredSchedule:
    common = FrozenCommonConfig.from_mapping(
        config_id="common-runtime",
        config_version="v1",
        content={"boundary": "mechanical", "tools": []},
    )
    assignments = tuple(
        FrozenAssignment.from_input(
            attempt_id=f"attempt-{generation}",
            actor_spec=ActorSpec(
                actor_id=f"actor-{generation}",
                lifecycle_id=f"lifecycle-{generation}",
                generation=generation,
                lineage_id="lineage-0",
                position="mechanical-probe",
            ),
            input=({"role": "user", "content": f"frozen-{generation}"},),
            instructions="frozen instructions",
            common_config_hash=common.content_hash,
            declared_carrier_ids=("declared-carrier",),
            carrier_capabilities=(
                CarrierCapability.from_fields(
                    attempt_id=f"attempt-{generation}",
                    actor_id=f"actor-{generation}",
                    lifecycle_id=f"lifecycle-{generation}",
                    lineage_id="lineage-0",
                    generation=generation,
                    carrier_id="declared-carrier",
                    carrier_class="DECLARED_LINEAGE_CARRIER",
                    can_read=generation > 0,
                    can_write=generation == 0,
                ),
            ),
        )
        for generation in generations
    )
    return PredeclaredSchedule.from_assignments(
        common_config=common,
        assignments=assignments,
    )


@dataclass
class _FakeActor:
    spec: ActorSpec
    identity: ActorIdentity
    launcher_pid: int


class _FakeFactory:
    def __init__(self) -> None:
        self.counter = 5000
        self.private_keys: dict[str, Ed25519PrivateKey] = {}
        self.live: dict[str, _FakeActor] = {}

    async def spawn(self, spec: ActorSpec) -> _FakeActor:
        self.counter += 1
        private_key = Ed25519PrivateKey.generate()
        identity = ActorIdentity(
            actor_id=spec.actor_id,
            lifecycle_id=spec.lifecycle_id,
            generation=spec.generation,
            lineage_id=spec.lineage_id,
            position=spec.position,
            gateway_public_key_b64=spec.gateway_public_key_b64,
            session_id=f"session-{spec.generation}",
            public_key_b64=_public_key(private_key),
            registration_signature_b64="",
            namespace_pid=1,
            namespace_process_start_ticks=self.counter,
            environment_fingerprint=stable_hash((spec.actor_id, "environment")),
            environment_names=(),
            namespace_ids={
                name: f"{name}-{self.counter}"
                for name in ("pid", "mnt", "ipc", "uts", "user", "cgroup", "net")
            },
            effective_capabilities_hex="0",
            no_new_privileges=True,
            open_extra_fd_count=0,
            open_extra_fd_targets={},
        )
        registration_signature = base64.b64encode(
            private_key.sign(
                b"h1-live-runtime-registration/v1\0"
                + canonical_bytes(
                    identity.model_dump(
                        exclude={"registration_signature_b64"}, mode="json"
                    )
                )
            )
        ).decode()
        identity = identity.model_copy(
            update={"registration_signature_b64": registration_signature}
        )
        actor = _FakeActor(spec=spec, identity=identity, launcher_pid=self.counter)
        self.private_keys[spec.lifecycle_id] = private_key
        self.live[spec.actor_id] = actor
        return actor

    async def stop(self, actor: _FakeActor) -> TeardownEvidence:
        self.live.pop(actor.spec.actor_id, None)
        return TeardownEvidence(
            actor_id=actor.identity.actor_id,
            lifecycle_id=actor.identity.lifecycle_id,
            launcher_pid=actor.launcher_pid,
            runtime_process_id=actor.launcher_pid,
            return_code=0,
            process_absent=True,
            process_group_absent=True,
            private_root_removed=True,
            key_invalidated=True,
        )


def _signed_action(actor: _FakeActor, private_key: Ed25519PrivateKey) -> SignedAction:
    unsigned: dict[str, Any] = {
        "actor_id": actor.identity.actor_id,
        "lifecycle_id": actor.identity.lifecycle_id,
        "session_id": actor.identity.session_id,
        "generation": actor.identity.generation,
        "lineage_id": actor.identity.lineage_id,
        "public_key_b64": actor.identity.public_key_b64,
        "sequence": 1,
        "action_id": f"{actor.identity.lifecycle_id}:1",
        "action": "mechanical-audit",
        "payload_hash": stable_hash("predeclared-mechanical-payload"),
        "parent_hashes": [],
    }
    signature = base64.b64encode(
        private_key.sign(ACTION_DOMAIN + canonical_bytes(unsigned))
    ).decode()
    return SignedAction(**unsigned, signature_b64=signature)


def test_schedule_and_config_are_canonical_and_hash_pinned() -> None:
    schedule = _schedule(generations=(0,))
    assert schedule.schedule_hash == stable_hash(schedule.semantic_payload)
    assert schedule.common_config.content_hash == stable_hash(
        {"boundary": "mechanical", "tools": []}
    )

    tampered = schedule.model_copy(update={"schedule_hash": stable_hash("tampered")})
    with pytest.raises(ValidationError, match="schedule_hash"):
        PredeclaredSchedule.model_validate(tampered.model_dump(mode="python"))

    assignment = schedule.assignments[0]
    with pytest.raises(ValidationError, match="canonical JSON"):
        FrozenAssignment.model_validate(
            assignment.model_copy(update={"input_json": '[{"content": "x", "role": "user"}]'}).model_dump(mode="python")
        )


def test_schedule_requires_explicit_carrier_permissions_and_is_read_only() -> None:
    common = FrozenCommonConfig.from_mapping(
        config_id="common-runtime",
        config_version="v1",
        content={"boundary": "mechanical", "tools": []},
    )
    spec = ActorSpec(
        actor_id="actor-only",
        lifecycle_id="lifecycle-only",
        generation=0,
        lineage_id="lineage-only",
        position="mechanical-probe",
    )
    with pytest.raises(ValueError, match="explicit per-assignment capabilities"):
        FrozenAssignment.from_input(
            attempt_id="attempt-only",
            actor_spec=spec,
            input=({"role": "user", "content": "frozen"},),
            common_config_hash=common.content_hash,
            declared_carrier_ids=("carrier",),
        )

    orchestrator = Orchestrator(_schedule(generations=(0,)), factory=_FakeFactory())
    assert not hasattr(orchestrator, "_assignments")
    assert orchestrator.carrier_capability(
        "attempt-0", "declared-carrier", operation="write"
    ).actor_id == "actor-0"
    with pytest.raises(AttributeError):
        orchestrator.schedule = _schedule(generations=(0,))  # type: ignore[misc]


def test_control_plane_has_no_output_or_mutation_authority() -> None:
    public_names = set(dir(Orchestrator))
    forbidden = {
        "infer",
        "generate",
        "compute_output",
        "compute_intermediate",
        "transform_state",
        "adapt_assignment",
        "assign_from_outcome",
        "sign_action",
        "resume_session",
        "enable_tools",
        "enable_network",
        "provider_call",
    }
    assert not public_names & forbidden
    assert "attempt_id" in str(inspect.signature(Orchestrator.start_actor))
    assert "outcome" not in str(inspect.signature(Orchestrator.start_actor))

    policy = Orchestrator(_schedule(generations=(0,)), factory=_FakeFactory()).policy
    assert policy.network_mode == "unshared-deny"
    assert policy.tools == ()
    assert policy.model_calls is False
    assert policy.session_resume is False
    assert policy.outcome_dependent_assignment is False
    assert policy.orchestrator_signing is False


@pytest.mark.asyncio
async def test_lifecycle_order_signature_verification_and_revocation() -> None:
    factory = _FakeFactory()
    orchestrator = Orchestrator(_schedule(), factory=factory)

    first = await orchestrator.start_actor("attempt-0")
    assert first.identity.actor_id == "actor-0"
    with pytest.raises(RuntimeError, match="predecessor lifecycle"):
        await orchestrator.start_actor("attempt-1")

    actor = factory.live["actor-0"]
    action = _signed_action(actor, factory.private_keys[actor.identity.lifecycle_id])
    verified = orchestrator.verify_signed_action(action)
    assert verified.action_id == action.action_id
    with pytest.raises(ValueError, match="not authorized"):
        orchestrator.verify_signed_action(action)

    first_teardown = await orchestrator.stop_actor("attempt-0")
    assert first_teardown.process_absent
    second = await orchestrator.start_actor("attempt-1")
    assert second.identity.generation == 1
    await orchestrator.stop_all()

    metadata = orchestrator.collect_metadata()
    assert metadata.schedule_hash == orchestrator.schedule_hash
    assert metadata.started_attempt_ids == ("attempt-0", "attempt-1")
    assert metadata.stopped_attempt_ids == ("attempt-0", "attempt-1")
    assert len(metadata.verified_actions) == 1
    assert len(metadata.teardowns) == 2


@pytest.mark.asyncio
async def test_only_declared_carrier_records_are_exposed() -> None:
    orchestrator = Orchestrator(_schedule(generations=(0,)), factory=_FakeFactory())
    assert orchestrator.common_config_bytes == orchestrator.schedule.common_config.content_bytes
    assert orchestrator.enumerate_declared_carrier_records() == ()
    assert orchestrator.collect_metadata().declared_carrier_records == ()


@pytest.mark.asyncio
async def test_real_bubblewrap_start_stop_has_no_model_or_provider_call() -> None:
    if shutil.which("bwrap") is None:
        pytest.skip("Bubblewrap is unavailable")
    orchestrator = Orchestrator(
        _schedule(generations=(0,)),
        factory=BubblewrapActorFactory(),
    )
    try:
        record = await orchestrator.start_actor("attempt-0")
        assert record.identity.namespace_pid == 1
        assert record.identity.no_new_privileges
        teardown = await orchestrator.stop_actor("attempt-0")
        assert teardown.process_absent
        assert teardown.process_group_absent
        assert teardown.private_root_removed
    finally:
        await orchestrator.stop_all()
        orchestrator.close()


class _BlindRevocationRegistry(ActionRegistry):
    """Test-only adversarial registry whose revocation silently never happens."""

    def revoke(self, lifecycle_id: str) -> None:
        return None


@pytest.mark.asyncio
async def test_durable_journal_admission_survives_controller_restart(tmp_path) -> None:
    journal_path = tmp_path / "lifecycle-journal.sqlite"
    schedule = _schedule()
    first = Orchestrator(
        schedule, factory=_FakeFactory(), journal=LifecycleJournal(journal_path)
    )
    predecessor = await first.start_actor("attempt-0")
    teardown = await first.stop_actor("attempt-0")
    assert teardown.key_invalidated
    assert [event.event for event in first.lifecycle_events] == [
        "spawned",
        "teardown_complete",
        "authorization_revoked",
    ]
    first.close()

    second = Orchestrator(
        schedule, factory=_FakeFactory(), journal=LifecycleJournal(journal_path)
    )
    successor = await second.start_actor("attempt-1")
    assert successor.identity.generation == 1
    spawned = [
        event for event in second.lifecycle_events if event.event == "spawned"
    ]
    assert len(spawned) == 2
    assert spawned[-1].lifecycle_id == successor.identity.lifecycle_id
    second.close()


@pytest.mark.asyncio
async def test_completed_attempt_cannot_restart_after_controller_restart(tmp_path) -> None:
    journal_path = tmp_path / "lifecycle-journal.sqlite"
    schedule = _schedule()
    first = Orchestrator(
        schedule, factory=_FakeFactory(), journal=LifecycleJournal(journal_path)
    )
    await first.start_actor("attempt-0")
    await first.stop_actor("attempt-0")
    first.close()

    second = Orchestrator(
        schedule, factory=_FakeFactory(), journal=LifecycleJournal(journal_path)
    )
    with pytest.raises(RuntimeError, match="already has durable history"):
        await second.start_actor("attempt-0")
    second.close()


@pytest.mark.asyncio
async def test_missing_revocation_blocks_successor_after_restart(tmp_path) -> None:
    journal_path = tmp_path / "lifecycle-journal.sqlite"
    schedule = _schedule()
    journal = LifecycleJournal(journal_path)
    assignment = schedule.assignments[0]
    for event in ("spawned", "teardown_complete"):
        journal._append_controller_event(
            lifecycle_id=assignment.actor_spec.lifecycle_id,
            actor_id=assignment.actor_spec.actor_id,
            attempt_id=assignment.attempt_id,
            lineage_id=assignment.actor_spec.lineage_id,
            generation=assignment.actor_spec.generation,
            event=event,
        )
    orchestrator = Orchestrator(
        schedule, factory=_FakeFactory(), journal=journal
    )
    with pytest.raises(RuntimeError, match="complete durable turnover chain"):
        await orchestrator.start_actor("attempt-1")
    orchestrator.close()


@pytest.mark.asyncio
async def test_journal_row_outside_frozen_schedule_blocks_actor_start(tmp_path) -> None:
    journal = LifecycleJournal(tmp_path / "lifecycle-journal.sqlite")
    journal._append_controller_event(
        lifecycle_id="foreign-lifecycle",
        actor_id="foreign-actor",
        attempt_id="foreign-attempt",
        lineage_id="foreign-lineage",
        generation=0,
        event="spawned",
    )
    orchestrator = Orchestrator(_schedule(generations=(0,)), factory=_FakeFactory(), journal=journal)
    with pytest.raises(RuntimeError, match="frozen schedule"):
        await orchestrator.start_actor("attempt-0")
    orchestrator.close()


@pytest.mark.asyncio
async def test_public_journal_append_cannot_forge_successor_admission() -> None:
    journal = LifecycleJournal()
    assignment = _schedule().assignments[0]
    values = {
        "lifecycle_id": assignment.actor_spec.lifecycle_id,
        "actor_id": assignment.actor_spec.actor_id,
        "attempt_id": assignment.attempt_id,
        "lineage_id": assignment.actor_spec.lineage_id,
        "generation": assignment.actor_spec.generation,
        "event": "spawned",
    }
    with pytest.raises(PermissionError, match="controller"):
        journal.append(**values)
    orchestrator = Orchestrator(_schedule(), factory=_FakeFactory(), journal=journal)
    with pytest.raises(RuntimeError, match="complete durable turnover chain"):
        await orchestrator.start_actor("attempt-1")
    orchestrator.close()


def _append_chain(journal: LifecycleJournal, assignment: FrozenAssignment) -> None:
    for event in ("spawned", "teardown_complete", "authorization_revoked"):
        journal._append_controller_event(
            lifecycle_id=assignment.actor_spec.lifecycle_id,
            actor_id=assignment.actor_spec.actor_id,
            attempt_id=assignment.attempt_id,
            lineage_id=assignment.actor_spec.lineage_id,
            generation=assignment.actor_spec.generation,
            event=event,
        )


@pytest.mark.asyncio
async def test_teardown_and_revocation_without_spawn_block_successor(tmp_path) -> None:
    journal_path = tmp_path / "lifecycle-journal.sqlite"
    schedule = _schedule()
    journal = LifecycleJournal(journal_path)
    assignment = schedule.assignments[0]
    for event in ("teardown_complete", "authorization_revoked"):
        journal._append_controller_event(
            lifecycle_id=assignment.actor_spec.lifecycle_id,
            actor_id=assignment.actor_spec.actor_id,
            attempt_id=assignment.attempt_id,
            lineage_id=assignment.actor_spec.lineage_id,
            generation=assignment.actor_spec.generation,
            event=event,
        )
    orchestrator = Orchestrator(
        schedule, factory=_FakeFactory(), journal=journal
    )
    with pytest.raises(RuntimeError, match="missing_spawn"):
        await orchestrator.start_actor("attempt-1")
    orchestrator.close()


@pytest.mark.parametrize(
    "field, wrong",
    [
        ("attempt_id", "attempt-999"),
        ("actor_id", "actor-999"),
        ("lineage_id", "lineage-999"),
        ("generation", 99),
    ],
)
@pytest.mark.asyncio
async def test_mismatched_journal_metadata_blocks_successor(
    tmp_path, field: str, wrong: Any
) -> None:
    journal_path = tmp_path / "lifecycle-journal.sqlite"
    schedule = _schedule()
    assignment = schedule.assignments[0]
    journal = LifecycleJournal(journal_path)
    for event in ("spawned", "teardown_complete", "authorization_revoked"):
        values: dict[str, Any] = {
            "lifecycle_id": assignment.actor_spec.lifecycle_id,
            "actor_id": assignment.actor_spec.actor_id,
            "attempt_id": assignment.attempt_id,
            "lineage_id": assignment.actor_spec.lineage_id,
            "generation": assignment.actor_spec.generation,
            "event": event,
        }
        if event == "spawned":
            values[field] = wrong
        journal._append_controller_event(**values)
    orchestrator = Orchestrator(
        schedule, factory=_FakeFactory(), journal=journal
    )
    with pytest.raises(RuntimeError, match="complete durable turnover chain"):
        await orchestrator.start_actor("attempt-1")
    orchestrator.close()


class _FlawedTeardownFactory(_FakeFactory):
    """Test-only factory that returns one unqualified teardown field."""

    def __init__(self, field: str) -> None:
        super().__init__()
        self.field = field

    async def stop(self, actor: _FakeActor) -> TeardownEvidence:
        evidence = await super().stop(actor)
        value: Any = 73 if self.field == "return_code" else False
        return evidence.model_copy(update={self.field: value})


class _WrongPidTeardownFactory(_FakeFactory):
    async def stop(self, actor: _FakeActor) -> TeardownEvidence:
        evidence = await super().stop(actor)
        return evidence.model_copy(
            update={"launcher_pid": evidence.launcher_pid + 1}
        )


@pytest.mark.parametrize(
    "field",
    [
        "process_absent",
        "process_group_absent",
        "private_root_removed",
        "key_invalidated",
        "return_code",
    ],
)
@pytest.mark.asyncio
async def test_incomplete_teardown_evidence_fails_closed_before_journaling(
    tmp_path, field: str
) -> None:
    journal_path = tmp_path / "lifecycle-journal.sqlite"
    orchestrator = Orchestrator(
        _schedule(),
        factory=_FlawedTeardownFactory(field),
        journal=LifecycleJournal(journal_path),
    )
    await orchestrator.start_actor("attempt-0")
    with pytest.raises(RuntimeError, match="qualified turnover predicate"):
        await orchestrator.stop_actor("attempt-0")
    assert [event.event for event in orchestrator.lifecycle_events] == ["spawned"]
    with pytest.raises(
        RuntimeError,
        match="complete durable turnover chain|still authorized by the registry",
    ):
        await orchestrator.start_actor("attempt-1")
    with pytest.raises(KeyError):
        orchestrator.live_actor("attempt-0")
    orchestrator.close()


@pytest.mark.asyncio
async def test_teardown_process_identity_fails_closed_before_journaling() -> None:
    orchestrator = Orchestrator(
        _schedule(), factory=_WrongPidTeardownFactory()
    )
    await orchestrator.start_actor("attempt-0")
    with pytest.raises(RuntimeError, match="qualified turnover predicate"):
        await orchestrator.stop_actor("attempt-0")
    assert [event.event for event in orchestrator.lifecycle_events] == ["spawned"]
    orchestrator.close()


@pytest.mark.asyncio
async def test_exact_valid_chain_still_admits_successor() -> None:
    orchestrator = Orchestrator(_schedule(), factory=_FakeFactory())
    await orchestrator.start_actor("attempt-0")
    await orchestrator.stop_actor("attempt-0")
    await orchestrator.start_actor("attempt-1")
    assert [event.event for event in orchestrator.lifecycle_events] == [
        "spawned",
        "teardown_complete",
        "authorization_revoked",
        "spawned",
    ]
    await orchestrator.stop_all()
    orchestrator.close()


@pytest.mark.asyncio
async def test_skipped_revocation_fails_closed_on_real_controller_path(tmp_path) -> None:
    if shutil.which("bwrap") is None:
        pytest.skip("Bubblewrap is unavailable")
    journal_path = tmp_path / "lifecycle-journal.sqlite"
    factory = BubblewrapActorFactory()
    orchestrator = Orchestrator(
        _schedule(),
        factory=factory,
        registry=_BlindRevocationRegistry(),
        journal=LifecycleJournal(journal_path),
    )
    try:
        await orchestrator.start_actor("attempt-0")
        with pytest.raises(RuntimeError, match="did not take effect"):
            await orchestrator.stop_actor("attempt-0")
        assert [event.event for event in orchestrator.lifecycle_events] == [
            "spawned",
            "teardown_complete",
        ]
        with pytest.raises(RuntimeError, match="predecessor lifecycle"):
            await orchestrator.start_actor("attempt-1")
    finally:
        await factory.close()
        orchestrator.close()


@pytest.mark.asyncio
async def test_journal_registry_disagreement_fails_closed(tmp_path) -> None:
    journal_path = tmp_path / "lifecycle-journal.sqlite"
    schedule = _schedule()
    first = Orchestrator(
        schedule, factory=_FakeFactory(), journal=LifecycleJournal(journal_path)
    )
    predecessor = await first.start_actor("attempt-0")
    await first.stop_actor("attempt-0")
    first.close()

    second = Orchestrator(
        schedule, factory=_FakeFactory(), journal=LifecycleJournal(journal_path)
    )
    second.registry.register(predecessor.identity)
    with pytest.raises(RuntimeError, match="still authorized by the registry"):
        await second.start_actor("attempt-1")
    second.close()


@pytest.mark.asyncio
async def test_all_earlier_generations_require_complete_chains_before_successor(
    tmp_path,
) -> None:
    journal_path = tmp_path / "lifecycle-journal.sqlite"
    schedule = _schedule(generations=(0, 1, 2))
    journal = LifecycleJournal(journal_path)
    _append_chain(journal, schedule.assignments[0])
    orchestrator = Orchestrator(
        schedule, factory=_FakeFactory(), journal=journal
    )
    with pytest.raises(RuntimeError, match="complete durable turnover chain"):
        await orchestrator.start_actor("attempt-2")
    _append_chain(journal, schedule.assignments[1])
    successor = await orchestrator.start_actor("attempt-2")
    assert successor.identity.generation == 2
    await orchestrator.stop_all()
    orchestrator.close()
