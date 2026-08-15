"""Deterministic fixture engine. It never invokes a model or provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .canonical import stable_hash
from .lifecycle import ActorHandle, LifecycleRegistry
from .models import (
    ArtifactRecord,
    CarrierKind,
    ClaimLadder,
    EventKind,
    FixtureCase,
    FixtureKind,
    FixtureOutcome,
    ParentageTopology,
    Position,
    RecoveryMode,
    StateVariant,
)
from .provenance import ProvenanceLedger, actor_routine_graph_valid
from .routine import (
    artifact_payloads,
    execute_single_actor,
    expected_output,
)
from .scripted_actors import ScriptedActor

ALLOWED_PERSISTENT_CARRIERS = frozenset({CarrierKind.DECLARED, CarrierKind.BACKUP})


@dataclass
class StoredArtifact:
    record: ArtifactRecord
    payload: dict[str, Any]


class CarrierStore:
    def __init__(self) -> None:
        self._items: dict[str, StoredArtifact] = {}

    def put(self, record: ArtifactRecord) -> None:
        self._items[record.artifact_id] = StoredArtifact(record, dict(record.payload))

    def get(self, artifact_id: str) -> StoredArtifact:
        return self._items[artifact_id]

    def delete(self, artifact_id: str) -> None:
        self._items.pop(artifact_id, None)

    def replace_payload(self, artifact_id: str, payload: dict[str, Any]) -> None:
        stored = self._items[artifact_id]
        record = stored.record.model_copy(
            update={"payload": payload, "content_hash": stable_hash(payload)}
        )
        self._items[artifact_id] = StoredArtifact(record, dict(payload))

    @property
    def carriers(self) -> tuple[CarrierKind, ...]:
        return tuple(item.record.carrier for item in self._items.values())

    @property
    def records(self) -> tuple[ArtifactRecord, ...]:
        return tuple(item.record for _, item in sorted(self._items.items()))


def _make_artifact(
    *,
    artifact_id: str,
    carrier: CarrierKind,
    component: Position,
    variant: StateVariant,
    payload: dict[str, Any],
    authors: tuple[str, ...],
    lineage_ids: tuple[str, ...],
    parent_ids: tuple[str, ...] = (),
    terminal: bool = False,
    researcher_seeded: bool = False,
) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=artifact_id,
        carrier=carrier,
        component=component,
        variant=variant,
        payload=payload,
        content_hash=stable_hash(payload),
        authors=authors,
        lineage_ids=lineage_ids,
        parent_ids=parent_ids,
        terminal=terminal,
        researcher_seeded=researcher_seeded,
    )


def _emit_spawn(ledger: ProvenanceLedger, actor: ActorHandle) -> None:
    ledger.emit(
        EventKind.SPAWN,
        actor=actor,
        carrier=CarrierKind.LOCAL,
        authority=actor.write_authority_id,
    )


def _emit_turnover(
    registry: LifecycleRegistry,
    ledger: ProvenanceLedger,
    actor: ActorHandle,
) -> None:
    ledger.emit(
        EventKind.REVOKE,
        actor=actor,
        carrier=CarrierKind.LOCAL,
        authority=actor.write_authority_id,
        action="revoke predecessor write authority",
    )
    ledger.emit(
        EventKind.TERMINATE,
        actor=actor,
        carrier=CarrierKind.LOCAL,
        action="terminate actor/process/session and clear local state",
    )
    registry.terminate(actor)


def _write(
    ledger: ProvenanceLedger,
    store: CarrierStore,
    record: ArtifactRecord,
    actor: ActorHandle | None,
    *,
    authority: str,
) -> None:
    if actor is not None:
        actor.assert_can_write()
    store.put(record)
    ledger.emit(
        EventKind.WRITE,
        actor=actor,
        carrier=record.carrier,
        artifact_id=record.artifact_id,
        content_hash=record.content_hash,
        component=record.component,
        parent_ids=record.parent_ids,
        authority=authority,
        action="materialize successor-facing state",
        lineage_id=record.lineage_ids[0],
    )


def _read(
    ledger: ProvenanceLedger,
    store: CarrierStore,
    artifact_id: str,
    actor: ActorHandle,
) -> dict[str, Any]:
    actor.assert_active()
    stored = store.get(artifact_id)
    ledger.emit(
        EventKind.READ,
        actor=actor,
        carrier=stored.record.carrier,
        artifact_id=stored.record.artifact_id,
        content_hash=stored.record.content_hash,
        component=stored.record.component,
        parent_ids=stored.record.parent_ids,
        action="read declared successor-facing state",
    )
    return dict(stored.payload)


def _act(
    ledger: ProvenanceLedger,
    actor: ActorHandle | None,
    component: Position,
    action: str,
    *,
    lineage_id: str,
    stage: int,
    artifact_id: str,
    content_hash: str,
    parent_ids: tuple[str, ...],
) -> None:
    ledger.emit(
        EventKind.ACT,
        actor=actor,
        carrier=(CarrierKind.LOCAL if actor else CarrierKind.ORCHESTRATOR),
        artifact_id=artifact_id,
        content_hash=content_hash,
        component=component,
        dependency_stage=stage,
        parent_ids=parent_ids,
        action=action,
        endpoint="held-out-relay",
        lineage_id=lineage_id,
        generation=1,
    )


def _claims(
    *,
    turnover_valid: bool,
    complete_turnover: bool,
    carrier_available: bool,
    functional_reuse: bool,
    endogenous: bool,
    causal: bool,
    routine: bool,
    held_out: bool,
    hidden: bool,
    orchestrator: bool,
    provenance_valid: bool,
) -> ClaimLadder:
    l0 = turnover_valid and complete_turnover and not hidden and provenance_valid
    l1 = l0 and carrier_available
    l2 = l1 and functional_reuse and held_out
    l3 = l2 and endogenous
    l4 = l3 and causal
    l5 = l4 and routine and not orchestrator
    return ClaimLadder(
        l0_turnover_validity=l0,
        l1_carrier_continuity=l1,
        l2_functional_reuse=l2,
        l3_endogenous_state_production=l3,
        l4_causal_transmission_or_recovery=l4,
        l5_routine_reconstruction=l5,
    )


def _allowed_claims(claims: ClaimLadder) -> tuple[str, ...]:
    labels = (
        ("L0: complete instrumented turnover", claims.l0_turnover_validity),
        ("L1: declared carrier continuity", claims.l1_carrier_continuity),
        ("L2: held-out functional reuse", claims.l2_functional_reuse),
        ("L3: actor-generated successor state", claims.l3_endogenous_state_production),
        ("L4: causal carrier dependence", claims.l4_causal_transmission_or_recovery),
        ("L5: interdependent routine reconstruction", claims.l5_routine_reconstruction),
    )
    return tuple(label for label, passed in labels if passed)


def run_fixture(case: FixtureCase) -> FixtureOutcome:
    # Defensively revalidate even if a caller used Pydantic's model_construct().
    case = FixtureCase.model_validate(case.model_dump(mode="python"))
    population_id = f"population-{case.case_id}"
    lineage_id = f"lineage-{case.target_lineage.value}-{case.case_id}"
    registry = LifecycleRegistry(population_id)
    ledger = ProvenanceLedger(population_id)
    store = CarrierStore()

    redundant = case.fixture is FixtureKind.REDUNDANT_PARTIAL
    copies = 2 if redundant else 1
    predecessors: list[ActorHandle] = []
    for copy in range(copies):
        for position in (Position.ENCODER, Position.CHECKER):
            actor = registry.spawn(
                lineage_id=lineage_id,
                generation=0,
                position=f"{position.value}-{copy}",
            )
            actor.remember(
                "routine", case.actual_state.value if case.actual_state else None
            )
            predecessors.append(actor)
            _emit_spawn(ledger, actor)

    actual = case.actual_state
    left_payload: dict[str, Any] | None = None
    right_payload: dict[str, Any] | None = None
    endogenously_written = False
    researcher_seeded = case.fixture is FixtureKind.RESEARCHER_SEEDED
    terminal_replay = case.terminal_replay

    should_persist = case.fixture not in {
        FixtureKind.NO_STATE,
        FixtureKind.REDUNDANT_PARTIAL,
        FixtureKind.REDISCOVERY,
        FixtureKind.HIDDEN_LEAK,
    }
    if actual is not None:
        left_payload, right_payload = artifact_payloads(actual)

    if should_persist and left_payload is not None and right_payload is not None:
        carrier = CarrierKind.DECLARED
        if case.fixture is FixtureKind.ORCHESTRATOR:
            writers: tuple[ActorHandle | None, ActorHandle | None] = (None, None)
            authorities = ("orchestrator-authority", "orchestrator-authority")
        elif researcher_seeded or terminal_replay:
            writers = (None, None)
            authorities = ("researcher-authority", "researcher-authority")
        else:
            writers = (predecessors[0], predecessors[1])
            authorities = (
                predecessors[0].write_authority_id,
                predecessors[1].write_authority_id,
            )
            endogenously_written = True

        author_ids = tuple(
            writer.actor_id
            if writer
            else (
                "orchestrator"
                if case.fixture is FixtureKind.ORCHESTRATOR
                else "researcher"
            )
            for writer in writers
        )
        left_authors, right_authors = (author_ids[0],), (author_ids[1],)
        contribution_ids: tuple[str, ...] = ()
        if (
            case.topology is ParentageTopology.MULTIPLE
            and writers[0] is not None
            and writers[1] is not None
        ):
            contributions = []
            for index, writer in enumerate((writers[0], writers[1])):
                contribution_payload = {
                    "schema": "h1-parent-contribution/v1",
                    "variant": actual.value,
                    "source_position": writer.position,
                }
                contribution = _make_artifact(
                    artifact_id=f"{case.case_id}-contribution-{index}",
                    carrier=carrier,
                    component=(Position.ENCODER if index == 0 else Position.CHECKER),
                    variant=actual,
                    payload=contribution_payload,
                    authors=(writer.actor_id,),
                    lineage_ids=(lineage_id,),
                )
                _write(
                    ledger,
                    store,
                    contribution,
                    writer,
                    authority=writer.write_authority_id,
                )
                contributions.append(contribution)
            contribution_ids = tuple(item.artifact_id for item in contributions)
            right_payload = {
                **right_payload,
                "parent_contribution_hashes": [
                    item.content_hash for item in contributions
                ],
            }
            right_authors = tuple(writer.actor_id for writer in writers)
        if case.topology is ParentageTopology.SHUFFLED_ATTRIBUTION:
            left_authors, right_authors = right_authors, left_authors
        if case.topology is ParentageTopology.MULTIPLE:
            right_parents = (f"{case.case_id}-left", *contribution_ids)
        elif case.topology is ParentageTopology.COMMON_ARCHIVE:
            right_parents = ("common-archive-root",)
        elif case.topology is ParentageTopology.BROADCAST:
            right_parents = (f"{case.case_id}-left",)
        else:
            right_parents = (f"{case.case_id}-left",)
        left_parents = (
            ("common-archive-root",)
            if case.topology is ParentageTopology.COMMON_ARCHIVE
            else ()
        )
        left_record = _make_artifact(
            artifact_id=f"{case.case_id}-left",
            carrier=carrier,
            component=Position.ENCODER,
            variant=actual,
            payload=left_payload,
            authors=left_authors,
            lineage_ids=(lineage_id,),
            parent_ids=left_parents,
            terminal=terminal_replay,
            researcher_seeded=researcher_seeded,
        )
        right_record = _make_artifact(
            artifact_id=f"{case.case_id}-right",
            carrier=carrier,
            component=Position.CHECKER,
            variant=actual,
            payload=right_payload,
            authors=right_authors,
            lineage_ids=(lineage_id,),
            parent_ids=right_parents,
            terminal=terminal_replay,
            researcher_seeded=researcher_seeded,
        )
        _write(ledger, store, left_record, writers[0], authority=authorities[0])
        if writers[1] is not None:
            _read(ledger, store, left_record.artifact_id, writers[1])
        _write(ledger, store, right_record, writers[1], authority=authorities[1])

    turnover_count = round(len(predecessors) * case.turnover_fraction)
    terminated = predecessors[:turnover_count]
    survivors = predecessors[turnover_count:]
    for actor in terminated:
        _emit_turnover(registry, ledger, actor)

    if case.fixture is FixtureKind.HIDDEN_LEAK:
        # Known-bad oracle: a predecessor session and its local memory survive.
        leaked = survivors[0] if survivors else predecessors[-1]
        if not leaked.active:
            leaked.active = True
            leaked.authority_active = True
            leaked.local_memory["routine"] = actual.value if actual else "A"

    successors: list[ActorHandle] = []
    if case.turnover_fraction > 0:
        for position in (Position.ENCODER, Position.CHECKER):
            actor = registry.spawn(
                lineage_id=lineage_id,
                generation=1,
                position=position.value,
            )
            successors.append(actor)
            _emit_spawn(ledger, actor)

    redundant_continuity = redundant and any(actor.active for actor in predecessors)

    routine_success = False
    held_out = False
    fidelity = 0.0
    state_followed = False
    functional_reuse = False
    carrier_available = bool(store.carriers)
    rediscovery = case.fixture is FixtureKind.REDISCOVERY
    orchestrator = False

    if redundant_continuity:
        # Continuity is carried by surviving active state, not reconstructed.
        routine_success = True
        held_out = True
        fidelity = 1.0
    elif case.fixture is FixtureKind.HIDDEN_LEAK:
        routine_success = True
        held_out = True
        fidelity = 1.0
        ledger.emit(
            EventKind.READ,
            actor=successors[0],
            carrier=CarrierKind.SESSION,
            artifact_id="forbidden-session-state",
            content_hash=stable_hash({"routine": actual.value if actual else "A"}),
            component=Position.ENCODER,
            action="forbidden hidden-session read",
        )
    elif rediscovery and successors and actual is not None:
        # Same result, independently reconstructed from common prior: no carrier edge.
        rediscovered_left, rediscovered_right = artifact_payloads(actual)
        local_left_id = f"{case.case_id}-rediscovered-left"
        local_right_id = f"{case.case_id}-rediscovered-right"
        ledger.emit(
            EventKind.WRITE,
            actor=successors[0],
            carrier=CarrierKind.LOCAL,
            artifact_id=local_left_id,
            content_hash=stable_hash(rediscovered_left),
            component=Position.ENCODER,
            authority=successors[0].write_authority_id,
            action="independent local derivation from common prior",
        )
        ledger.emit(
            EventKind.WRITE,
            actor=successors[1],
            carrier=CarrierKind.LOCAL,
            artifact_id=local_right_id,
            content_hash=stable_hash(rediscovered_right),
            component=Position.CHECKER,
            parent_ids=(local_left_id,),
            authority=successors[1].write_authority_id,
            action="independent local derivation from common prior",
        )
        encoder = ScriptedActor(successors[0], ledger, case.case_id)
        checker = ScriptedActor(successors[1], ledger, case.case_id)
        intermediate = encoder.encode(rediscovered_left, left_artifact_id=local_left_id)
        acknowledgment = checker.check(
            rediscovered_right,
            intermediate,
            right_artifact_id=local_right_id,
        )
        final = encoder.finalize(intermediate, acknowledgment)
        routine_success = final.value == expected_output(case.target_lineage)
        state_followed = final.value == expected_output(actual)
        held_out = True
    elif carrier_available and actual is not None:
        preliminary_complete = (
            case.turnover_fraction == 1.0 and registry.assert_complete_turnover()
        )
        acting = successors if preliminary_complete else list(survivors[:2])
        if len(acting) < 2:
            acting = (acting + successors)[:2]
        if len(acting) == 2:
            left = _read(ledger, store, f"{case.case_id}-left", acting[0])
            right = _read(ledger, store, f"{case.case_id}-right", acting[1])
            if case.topology is ParentageTopology.BROADCAST:
                _read(ledger, store, f"{case.case_id}-right", acting[0])
                _read(ledger, store, f"{case.case_id}-left", acting[1])
            if case.fixture is FixtureKind.ORCHESTRATOR:
                run = execute_single_actor(left, right, actor_id="orchestrator")
                stage_values = (run.intermediate, run.acknowledgment, run.output)
                stage_components = (
                    Position.ENCODER,
                    Position.CHECKER,
                    Position.ENCODER,
                )
                stage_ids = tuple(f"{case.case_id}-stage-{stage}" for stage in range(3))
                stage_parents = (
                    (f"{case.case_id}-left",),
                    (f"{case.case_id}-right", stage_ids[0]),
                    (stage_ids[0], stage_ids[1]),
                )
                for stage, (component, value, artifact_id, parents) in enumerate(
                    zip(
                        stage_components,
                        stage_values,
                        stage_ids,
                        stage_parents,
                        strict=True,
                    )
                ):
                    _act(
                        ledger,
                        None,
                        component,
                        "orchestrator supplies routine intermediate",
                        lineage_id=lineage_id,
                        stage=stage,
                        artifact_id=artifact_id,
                        content_hash=stable_hash({"stage": stage, "value": value}),
                        parent_ids=parents,
                    )
                final_value = run.output
            else:
                encoder = ScriptedActor(acting[0], ledger, case.case_id)
                checker = ScriptedActor(acting[1], ledger, case.case_id)
                intermediate = encoder.encode(
                    left, left_artifact_id=f"{case.case_id}-left"
                )
                acknowledgment = checker.check(
                    right,
                    intermediate,
                    right_artifact_id=f"{case.case_id}-right",
                )
                final = encoder.finalize(intermediate, acknowledgment)
                final_value = final.value
            routine_success = final_value == expected_output(case.target_lineage)
            state_followed = final_value == expected_output(actual)
            held_out = True

    required = (EventKind.SPAWN,)
    expected_terminated = tuple(actor.lifecycle_id for actor in terminated)
    expected_revoked = tuple(actor.write_authority_id for actor in terminated)
    provenance = ledger.validate(
        required_events=required,
        expected_terminated_lifecycles=expected_terminated,
        expected_revoked_authorities=expected_revoked,
        artifact_records=store.records,
        actor_handles=registry.actors,
    )

    predecessor_state_clean = all(
        not actor.active
        and not actor.authority_active
        and not actor.local_memory
        and not actor.reactivation_attempted
        and not actor.authority_reactivation_attempted
        for actor in predecessors
    )
    predecessor_namespaces = {
        namespace
        for actor in predecessors
        for namespace in (
            actor.actor_id,
            actor.lifecycle_id,
            actor.process_id,
            actor.session_id,
            actor.write_authority_id,
        )
    }
    successor_namespaces = {
        namespace
        for actor in successors
        for namespace in (
            actor.actor_id,
            actor.lifecycle_id,
            actor.process_id,
            actor.session_id,
            actor.write_authority_id,
        )
    }
    predecessor_clean = predecessor_state_clean and predecessor_namespaces.isdisjoint(
        successor_namespaces
    )
    forbidden_state_observed = any(
        event.carrier in {CarrierKind.SESSION, CarrierKind.PROCESS}
        for event in ledger.events
    )
    hidden = case.turnover_fraction == 1.0 and (
        not predecessor_clean or forbidden_state_observed
    )
    requested_turnover_executed = len(terminated) == turnover_count
    complete_turnover = case.turnover_fraction == 1.0 and predecessor_clean
    allowed_carriers = all(
        carrier in ALLOWED_PERSISTENT_CARRIERS for carrier in store.carriers
    )
    turnover_valid = (
        complete_turnover
        and requested_turnover_executed
        and allowed_carriers
        and provenance.valid
        and not hidden
    )
    actor_graph = actor_routine_graph_valid(ledger.events) and provenance.valid
    orchestrator = any(
        event.event is EventKind.ACT and event.actor_id is None
        for event in ledger.events
    )
    fidelity = 1.0 if actor_graph else 0.0
    functional_reuse = carrier_available and actor_graph
    endogenous = endogenously_written and not terminal_replay
    common_archive = case.topology is ParentageTopology.COMMON_ARCHIVE
    parentage_identified = (
        functional_reuse
        and not common_archive
        and case.topology is not ParentageTopology.SHUFFLED_ATTRIBUTION
    )
    causal = endogenous and functional_reuse and parentage_identified
    parentage_effect = parentage_identified and routine_success
    routine_reconstructed = (
        turnover_valid
        and routine_success
        and actor_graph
        and endogenous
        and causal
        and not rediscovery
        and not orchestrator
        and not hidden
    )
    lineage_detected = (
        bool(successors)
        and all(actor.lineage_id == lineage_id for actor in successors)
        and all(
            event.lineage_id == lineage_id
            for event in ledger.events
            if event.event is EventKind.ACT and event.actor_id is not None
        )
    )
    claims = _claims(
        turnover_valid=turnover_valid,
        complete_turnover=complete_turnover,
        carrier_available=carrier_available,
        functional_reuse=functional_reuse,
        endogenous=endogenous,
        causal=causal,
        routine=routine_reconstructed,
        held_out=held_out,
        hidden=hidden,
        orchestrator=orchestrator,
        provenance_valid=provenance.valid,
    )
    disallowed = ["organizational continuity", "endogenous social roles"]
    if terminal_replay:
        disallowed.append("recipient-side generative history was necessary")
    if rediscovery:
        disallowed.extend(("inheritance", "social transmission"))
    if common_archive:
        disallowed.append("unique parentage")
    if redundant_continuity:
        disallowed.append("cross-turnover reconstruction")

    return FixtureOutcome(
        fixture=case.fixture,
        case_id=case.case_id,
        population_id=population_id,
        lineage_id=lineage_id,
        initialization_id=case.initialization_id,
        replicate_id=case.replicate_id,
        target_lineage=case.target_lineage,
        actual_state=actual,
        parentage_topology=case.topology,
        turnover_fraction=case.turnover_fraction,
        requested_turnover_executed=requested_turnover_executed,
        turnover_valid=turnover_valid,
        complete_turnover=complete_turnover,
        surviving_actor_count=len([actor for actor in predecessors if actor.active]),
        redundant_continuity=redundant_continuity,
        carrier_available=carrier_available,
        functional_reuse=functional_reuse,
        endogenous_state_production=endogenous,
        causal_transmission_supported=causal,
        routine_execution_success=routine_success,
        routine_reconstructed=routine_reconstructed,
        actor_action_graph_valid=actor_graph,
        held_out_generalization=held_out,
        deletion_recovery=RecoveryMode.NONE,
        parentage_effect=parentage_effect,
        parentage_identified=parentage_identified,
        common_archive_ambiguity=common_archive,
        terminal_replay=terminal_replay,
        downstream_state_sufficient=terminal_replay and routine_success,
        upstream_endogenous_generation=endogenous,
        rediscovery_detected=rediscovery,
        orchestrator_confounded=orchestrator,
        hidden_state_violation=hidden,
        researcher_seeded=researcher_seeded,
        manipulation_state_detected=(actual is not None and state_followed),
        manipulation_lineage_detected=lineage_detected,
        routine_fidelity=fidelity,
        recovery_steps=0,
        provenance=provenance,
        provenance_events=ledger.events,
        artifact_inventory=store.records,
        claims=claims,
        allowed_claims=_allowed_claims(claims),
        disallowed_claims=tuple(disallowed),
    )
