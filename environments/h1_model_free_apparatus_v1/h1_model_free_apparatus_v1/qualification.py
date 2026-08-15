"""Run model-free qualification and emit the complete machine-readable record."""

from __future__ import annotations

import json

from .analysis import (
    LineageObservation,
    assert_independent_units,
    factorial_mechanics,
    summarize_lineages,
)
from .engine import ALLOWED_PERSISTENT_CARRIERS, run_fixture
from .fixtures import (
    FACTORIAL_MANIFEST,
    FIXTURE_MANIFEST,
    PARENTAGE_MANIFEST,
    oracle_errors,
)
from .interventions import recovery_matrix
from .models import (
    CarrierKind,
    FixtureKind,
    InterventionKind,
    ParentageTopology,
    QualificationResult,
    RecoveryMode,
)

APPARATUS_VERSION = "h1-model-free-apparatus/v1"


def run_qualification() -> QualificationResult:
    fixtures = tuple(run_fixture(case) for case in FIXTURE_MANIFEST)
    factorial = tuple(run_fixture(case) for case in FACTORIAL_MANIFEST)
    parentage = tuple(run_fixture(case) for case in PARENTAGE_MANIFEST)
    recovery = recovery_matrix()
    by_fixture = {item.fixture: item for item in fixtures}
    redundant = [
        item for item in fixtures if item.fixture is FixtureKind.REDUNDANT_PARTIAL
    ]
    parent_by_topology = {
        case.topology: outcome
        for case, outcome in zip(PARENTAGE_MANIFEST, parentage, strict=True)
    }
    lineage_summaries = summarize_lineages(
        (
            LineageObservation(
                population_id="synthetic-pop-1",
                lineage_id="synthetic-lineage-1",
                initialization_id="synthetic-init-1",
                generation_id="g0",
                replicate_id="nested-action-1",
                value=1.0,
                nested_actor_count=2,
                nested_action_count=3,
            ),
            LineageObservation(
                population_id="synthetic-pop-1",
                lineage_id="synthetic-lineage-1",
                initialization_id="synthetic-init-1",
                generation_id="g1",
                replicate_id="nested-action-2",
                value=0.0,
                nested_actor_count=2,
                nested_action_count=3,
            ),
        )
    )
    assert_independent_units(lineage_summaries)
    factor_gates = factorial_mechanics(factorial)
    oracle_pass = all(not oracle_errors(outcome) for outcome in fixtures)
    positive = by_fixture[FixtureKind.COMPLETE_TURNOVER]
    terminal = by_fixture[FixtureKind.TERMINAL_REPLAY]
    researcher = by_fixture[FixtureKind.RESEARCHER_SEEDED]
    rediscovery = by_fixture[FixtureKind.REDISCOVERY]
    hidden = by_fixture[FixtureKind.HIDDEN_LEAK]
    orchestrator = by_fixture[FixtureKind.ORCHESTRATOR]
    recovery_by_kind = {item.intervention: item for item in recovery}

    gates = {
        "fixture_oracles_match": oracle_pass,
        "100_percent_turnover_mechanically_provable": (
            positive.turnover_valid
            and positive.complete_turnover
            and positive.surviving_actor_count == 0
            and positive.actor_action_graph_valid
        ),
        "partial_redundant_distinguished": (
            len(redundant) == 3
            and all(
                item.redundant_continuity
                and not item.complete_turnover
                and not item.turnover_valid
                and not item.causal_transmission_supported
                for item in redundant[:2]
            )
            and redundant[2].complete_turnover
            and not redundant[2].routine_execution_success
        ),
        "allowed_persistent_carriers_enumerated": ALLOWED_PERSISTENT_CARRIERS
        == frozenset({CarrierKind.DECLARED, CarrierKind.BACKUP}),
        "state_and_lineage_independently_manipulable": all(factor_gates.values()),
        "parentage_manipulable": (
            set(parent_by_topology) == set(ParentageTopology)
            and not parent_by_topology[
                ParentageTopology.SHUFFLED_ATTRIBUTION
            ].provenance.valid
            and parent_by_topology[
                ParentageTopology.SHUFFLED_STATE
            ].manipulation_state_detected
        ),
        "common_archive_ambiguity_represented": (
            parent_by_topology[
                ParentageTopology.COMMON_ARCHIVE
            ].common_archive_ambiguity
            and not parent_by_topology[
                ParentageTopology.COMMON_ARCHIVE
            ].parentage_identified
        ),
        "terminal_replay_semantics_correct": (
            terminal.downstream_state_sufficient
            and not terminal.upstream_endogenous_generation
            and not terminal.causal_transmission_supported
            and not terminal.routine_reconstructed
            and not terminal.claims.l3_endogenous_state_production
        ),
        "deletion_and_recovery_work": (
            not recovery_by_kind[InterventionKind.FULL_DELETION].success
            and not recovery_by_kind[InterventionKind.PARTIAL_DELETION].success
            and not recovery_by_kind[InterventionKind.CORRUPTION].success
            and not recovery_by_kind[InterventionKind.RANDOM_REPLACEMENT].success
            and recovery_by_kind[InterventionKind.BACKUP_RESTORE].recovery
            is RecoveryMode.BACKUP_RESTORE
            and recovery_by_kind[InterventionKind.ENDOGENOUS_RECONSTRUCTION].recovery
            is RecoveryMode.ENDOGENOUS_RECONSTRUCTION
        ),
        "rediscovery_distinguished_from_transmission": (
            rediscovery.rediscovery_detected
            and not rediscovery.causal_transmission_supported
        ),
        "researcher_seed_distinguished": (
            researcher.functional_reuse and not researcher.endogenous_state_production
        ),
        "orchestrator_confound_detected": (
            orchestrator.orchestrator_confounded
            and not orchestrator.actor_action_graph_valid
            and not orchestrator.claims.l5_routine_reconstruction
        ),
        "hidden_carrier_leak_detected": (
            hidden.hidden_state_violation
            and not hidden.turnover_valid
            and not hidden.provenance.valid
        ),
        "lineage_is_inferential_unit": (
            len(lineage_summaries) == 1
            and lineage_summaries[0].nested_observation_count == 2
        ),
        "l0_through_l5_mechanically_separated": (
            positive.claims.l5_routine_reconstruction
            and positive.actor_action_graph_valid
            and researcher.claims.l2_functional_reuse
            and not researcher.claims.l3_endogenous_state_production
            and terminal.claims.l2_functional_reuse
            and not terminal.claims.l3_endogenous_state_production
        ),
    }
    readiness = "PASS" if all(gates.values()) else "FAIL"
    return QualificationResult(
        apparatus_version=APPARATUS_VERSION,
        generated_by="deterministic scripted fixtures; no model/provider",
        fixture_outcomes=fixtures,
        factorial_outcomes=factorial,
        parentage_outcomes=parentage,
        recovery_outcomes=recovery,
        analysis_unit_ids=tuple(
            f"{item.population_id}/{item.lineage_id}/{item.initialization_id}"
            for item in lineage_summaries
        ),
        analysis_unit_count=len(lineage_summaries),
        gate_results=gates,
        readiness=readiness,
    )


def main() -> None:
    result = run_qualification()
    print(json.dumps(result.model_dump(mode="json"), sort_keys=True, indent=2))
    raise SystemExit(0 if result.readiness == "PASS" else 1)


if __name__ == "__main__":
    main()
