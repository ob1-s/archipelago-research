"""Strict wire models for the deterministic H1 qualification apparatus."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


QUALIFICATION_GATE_NAMES = frozenset(
    {
        "fixture_oracles_match",
        "100_percent_turnover_mechanically_provable",
        "partial_redundant_distinguished",
        "allowed_persistent_carriers_enumerated",
        "state_and_lineage_independently_manipulable",
        "parentage_manipulable",
        "common_archive_ambiguity_represented",
        "terminal_replay_semantics_correct",
        "deletion_and_recovery_work",
        "rediscovery_distinguished_from_transmission",
        "researcher_seed_distinguished",
        "orchestrator_confound_detected",
        "hidden_carrier_leak_detected",
        "lineage_is_inferential_unit",
        "l0_through_l5_mechanically_separated",
    }
)


class FixtureKind(StrEnum):
    COMPLETE_TURNOVER = "complete_turnover_positive"
    REDUNDANT_PARTIAL = "redundant_partial_turnover"
    NO_STATE = "no_state_negative"
    RESEARCHER_SEEDED = "researcher_seeded"
    TERMINAL_REPLAY = "frozen_terminal_replay"
    REDISCOVERY = "independent_rediscovery"
    HIDDEN_LEAK = "hidden_state_leak"
    ORCHESTRATOR = "orchestrator_confound"


class Position(StrEnum):
    ENCODER = "encoder"
    CHECKER = "checker"


class StateVariant(StrEnum):
    A = "A"
    B = "B"


class CarrierKind(StrEnum):
    DECLARED = "declared_persistent_carrier"
    BACKUP = "declared_backup"
    COMMON_PRIOR = "common_prior"
    LOCAL = "actor_local"
    SESSION = "session"
    PROCESS = "process"
    ORCHESTRATOR = "orchestrator"
    NONE = "none"


class EventKind(StrEnum):
    SPAWN = "spawn"
    WRITE = "write"
    READ = "read"
    ACT = "act"
    TERMINATE = "terminate"
    REVOKE = "revoke_write_authority"
    DELETE = "delete"
    CORRUPT = "corrupt"
    RESTORE = "restore"
    RECONSTRUCT = "reconstruct"


class ParentageTopology(StrEnum):
    UNIQUE = "unique"
    MULTIPLE = "multiple"
    COMMON_ARCHIVE = "common_archive"
    BROADCAST = "broadcast"
    SHUFFLED_ATTRIBUTION = "shuffled_attribution"
    SHUFFLED_STATE = "shuffled_actual_state"


class RecoveryMode(StrEnum):
    NONE = "none"
    FAILED = "failed"
    BACKUP_RESTORE = "backup_restore"
    ENDOGENOUS_RECONSTRUCTION = "endogenous_reconstruction"
    INDEPENDENT_REDISCOVERY = "independent_rediscovery"


class InterventionKind(StrEnum):
    INTACT = "intact"
    FULL_DELETION = "full_deletion"
    PARTIAL_DELETION = "partial_deletion"
    CORRUPTION = "corruption"
    RANDOM_REPLACEMENT = "random_replacement"
    BACKUP_RESTORE = "frozen_backup_restore"
    ENDOGENOUS_RECONSTRUCTION = "endogenous_reconstruction"


class ArtifactRecord(StrictModel):
    artifact_id: str
    carrier: CarrierKind
    component: Position
    variant: StateVariant
    payload: dict[str, Any]
    content_hash: str
    authors: tuple[str, ...]
    parent_ids: tuple[str, ...] = ()
    lineage_ids: tuple[str, ...]
    terminal: bool = False
    researcher_seeded: bool = False


class ProvenanceEvent(StrictModel):
    sequence: int
    logical_time: int
    event: EventKind
    actor_id: str | None
    lifecycle_id: str | None
    process_id: str | None
    session_id: str | None
    generation: int
    lineage_id: str | None
    population_id: str
    carrier: CarrierKind
    artifact_id: str | None
    content_hash: str | None
    component: Position | None
    dependency_stage: int | None = Field(default=None, ge=0)
    parent_ids: tuple[str, ...] = ()
    write_authority_id: str | None = None
    actor_action_attestation: str | None = None
    action: str | None = None
    endpoint: str | None = None
    previous_event_hash: str
    event_hash: str


class ProvenanceValidation(StrictModel):
    valid: bool
    inventory_complete: bool
    errors: tuple[str, ...] = ()
    observed_reads: tuple[str, ...] = ()
    observed_writes: tuple[str, ...] = ()


class ClaimLadder(StrictModel):
    l0_turnover_validity: bool
    l1_carrier_continuity: bool
    l2_functional_reuse: bool
    l3_endogenous_state_production: bool
    l4_causal_transmission_or_recovery: bool
    l5_routine_reconstruction: bool


class FixtureOutcome(StrictModel):
    fixture: FixtureKind
    case_id: str
    population_id: str
    lineage_id: str
    initialization_id: str
    replicate_id: str
    target_lineage: StateVariant
    actual_state: StateVariant | None
    parentage_topology: ParentageTopology
    turnover_fraction: float = Field(ge=0.0, le=1.0)
    requested_turnover_executed: bool
    turnover_valid: bool
    complete_turnover: bool
    surviving_actor_count: int = Field(ge=0)
    redundant_continuity: bool
    carrier_available: bool
    functional_reuse: bool
    endogenous_state_production: bool
    causal_transmission_supported: bool
    routine_execution_success: bool
    routine_reconstructed: bool
    actor_action_graph_valid: bool
    held_out_generalization: bool
    deletion_recovery: RecoveryMode
    parentage_effect: bool
    parentage_identified: bool
    common_archive_ambiguity: bool
    terminal_replay: bool
    downstream_state_sufficient: bool
    upstream_endogenous_generation: bool
    rediscovery_detected: bool
    orchestrator_confounded: bool
    hidden_state_violation: bool
    researcher_seeded: bool
    manipulation_state_detected: bool
    manipulation_lineage_detected: bool
    routine_fidelity: float = Field(ge=0.0, le=1.0)
    recovery_steps: int = Field(ge=0)
    provenance: ProvenanceValidation
    provenance_events: tuple[ProvenanceEvent, ...]
    artifact_inventory: tuple[ArtifactRecord, ...]
    claims: ClaimLadder
    allowed_claims: tuple[str, ...]
    disallowed_claims: tuple[str, ...]

    @model_validator(mode="after")
    def l5_requires_complete_evidence_bundle(self) -> FixtureOutcome:
        if self.claims.l5_routine_reconstruction and not (
            self.turnover_valid
            and self.complete_turnover
            and self.functional_reuse
            and self.endogenous_state_production
            and self.causal_transmission_supported
            and self.routine_reconstructed
            and self.actor_action_graph_valid
            and self.provenance.valid
            and self.provenance_events
            and self.artifact_inventory
        ):
            raise ValueError(
                "L5 requires the complete lifecycle, causal, routine, and provenance bundle"
            )
        return self


class FixtureCase(StrictModel):
    case_id: str = Field(min_length=1)
    initialization_id: str = Field(min_length=1)
    replicate_id: str = Field(min_length=1)
    fixture: FixtureKind
    turnover_fraction: float = Field(ge=0.0, le=1.0)
    target_lineage: StateVariant = StateVariant.A
    actual_state: StateVariant | None = StateVariant.A
    topology: ParentageTopology = ParentageTopology.UNIQUE
    terminal_replay: bool = False

    @model_validator(mode="after")
    def terminal_replay_matches_fixture_kind(self) -> FixtureCase:
        expected = self.fixture is FixtureKind.TERMINAL_REPLAY
        if self.terminal_replay is not expected:
            raise ValueError(
                "terminal_replay must be true exactly for the frozen terminal-replay fixture"
            )
        return self


class RecoveryOutcome(StrictModel):
    intervention: InterventionKind
    success: bool
    recovery: RecoveryMode
    recovery_steps: int = Field(ge=0)
    routine_fidelity: float = Field(ge=0.0, le=1.0)
    artifact_provenance: str
    backup_used: bool
    rediscovery: bool


class QualificationResult(StrictModel):
    apparatus_version: str
    generated_by: str
    scientific_result: Literal[False] = False
    fixture_outcomes: tuple[FixtureOutcome, ...]
    factorial_outcomes: tuple[FixtureOutcome, ...] = ()
    parentage_outcomes: tuple[FixtureOutcome, ...] = ()
    recovery_outcomes: tuple[RecoveryOutcome, ...] = ()
    analysis_unit_ids: tuple[str, ...] = ()
    analysis_unit_count: int = Field(default=0, ge=0)
    gate_results: dict[str, bool]
    readiness: Literal["PASS", "PASS WITH REPAIRS", "FAIL"]
    repairs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def pass_requires_every_gate(self) -> QualificationResult:
        if self.readiness == "PASS":
            if set(self.gate_results) != QUALIFICATION_GATE_NAMES or not all(
                self.gate_results.values()
            ):
                raise ValueError(
                    "PASS requires the exact canonical qualification gates"
                )
            if not (
                len(self.fixture_outcomes) == 10
                and len(self.factorial_outcomes) == 4
                and len(self.parentage_outcomes) == 6
                and len(self.recovery_outcomes) == 7
                and self.analysis_unit_count > 0
            ):
                raise ValueError("PASS requires the complete qualification payload")
        if self.analysis_unit_count != len(self.analysis_unit_ids):
            raise ValueError("analysis_unit_count must match analysis_unit_ids")
        return self
