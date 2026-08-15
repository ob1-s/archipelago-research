"""Frozen deterministic fixture manifest and ground-truth oracles."""

from __future__ import annotations

from typing import Any

from .models import (
    FixtureCase,
    FixtureKind,
    FixtureOutcome,
    ParentageTopology,
    StateVariant,
)

FIXTURE_MANIFEST: tuple[FixtureCase, ...] = (
    FixtureCase(
        case_id="A-complete-positive",
        initialization_id="init-A-complete-positive",
        replicate_id="oracle-A-0",
        fixture=FixtureKind.COMPLETE_TURNOVER,
        turnover_fraction=1.0,
    ),
    FixtureCase(
        case_id="B-redundant-0",
        initialization_id="init-B-redundant-0",
        replicate_id="oracle-B-0",
        fixture=FixtureKind.REDUNDANT_PARTIAL,
        turnover_fraction=0.0,
    ),
    FixtureCase(
        case_id="B-redundant-50",
        initialization_id="init-B-redundant-50",
        replicate_id="oracle-B-50",
        fixture=FixtureKind.REDUNDANT_PARTIAL,
        turnover_fraction=0.5,
    ),
    FixtureCase(
        case_id="B-redundant-100",
        initialization_id="init-B-redundant-100",
        replicate_id="oracle-B-100",
        fixture=FixtureKind.REDUNDANT_PARTIAL,
        turnover_fraction=1.0,
    ),
    FixtureCase(
        case_id="C-no-state",
        initialization_id="init-C-no-state",
        replicate_id="oracle-C-0",
        fixture=FixtureKind.NO_STATE,
        turnover_fraction=1.0,
    ),
    FixtureCase(
        case_id="D-researcher-seeded",
        initialization_id="init-D-researcher-seeded",
        replicate_id="oracle-D-0",
        fixture=FixtureKind.RESEARCHER_SEEDED,
        turnover_fraction=1.0,
    ),
    FixtureCase(
        case_id="E-terminal-replay",
        initialization_id="init-E-terminal-replay",
        replicate_id="oracle-E-0",
        fixture=FixtureKind.TERMINAL_REPLAY,
        turnover_fraction=1.0,
        terminal_replay=True,
    ),
    FixtureCase(
        case_id="F-rediscovery",
        initialization_id="init-F-rediscovery",
        replicate_id="oracle-F-0",
        fixture=FixtureKind.REDISCOVERY,
        turnover_fraction=1.0,
    ),
    FixtureCase(
        case_id="G-hidden-leak",
        initialization_id="init-G-hidden-leak",
        replicate_id="oracle-G-0",
        fixture=FixtureKind.HIDDEN_LEAK,
        turnover_fraction=1.0,
    ),
    FixtureCase(
        case_id="H-orchestrator",
        initialization_id="init-H-orchestrator",
        replicate_id="oracle-H-0",
        fixture=FixtureKind.ORCHESTRATOR,
        turnover_fraction=1.0,
    ),
)


FACTORIAL_MANIFEST: tuple[FixtureCase, ...] = tuple(
    FixtureCase(
        case_id=f"factorial-{lineage.value}{state.value}",
        initialization_id=f"init-factorial-{lineage.value}{state.value}",
        replicate_id=f"factorial-{lineage.value}{state.value}-0",
        fixture=FixtureKind.COMPLETE_TURNOVER,
        turnover_fraction=1.0,
        target_lineage=lineage,
        actual_state=state,
        topology=(
            ParentageTopology.SHUFFLED_STATE
            if lineage is not state
            else ParentageTopology.UNIQUE
        ),
    )
    for lineage in StateVariant
    for state in StateVariant
)


PARENTAGE_MANIFEST: tuple[FixtureCase, ...] = tuple(
    FixtureCase(
        case_id=f"parentage-{topology.value}",
        initialization_id=f"init-parentage-{topology.value}",
        replicate_id=f"parentage-{topology.value}-0",
        fixture=FixtureKind.COMPLETE_TURNOVER,
        turnover_fraction=1.0,
        topology=topology,
        actual_state=(
            StateVariant.B
            if topology is ParentageTopology.SHUFFLED_STATE
            else StateVariant.A
        ),
    )
    for topology in ParentageTopology
)


ORACLES: dict[str, dict[str, Any]] = {
    "A-complete-positive": {
        "turnover_valid": True,
        "complete_turnover": True,
        "routine_execution_success": True,
        "routine_reconstructed": True,
        "actor_action_graph_valid": True,
        "l5": True,
    },
    "B-redundant-0": {
        "turnover_valid": False,
        "complete_turnover": False,
        "redundant_continuity": True,
        "routine_execution_success": True,
        "l5": False,
    },
    "B-redundant-50": {
        "turnover_valid": False,
        "complete_turnover": False,
        "redundant_continuity": True,
        "routine_execution_success": True,
        "l5": False,
    },
    "B-redundant-100": {
        "complete_turnover": True,
        "redundant_continuity": False,
        "routine_execution_success": False,
        "l5": False,
    },
    "C-no-state": {
        "complete_turnover": True,
        "carrier_available": False,
        "routine_execution_success": False,
        "l5": False,
    },
    "D-researcher-seeded": {
        "functional_reuse": True,
        "endogenous_state_production": False,
        "researcher_seeded": True,
        "causal_transmission_supported": False,
        "routine_reconstructed": False,
        "l5": False,
    },
    "E-terminal-replay": {
        "terminal_replay": True,
        "downstream_state_sufficient": True,
        "upstream_endogenous_generation": False,
        "causal_transmission_supported": False,
        "routine_reconstructed": False,
        "l5": False,
    },
    "F-rediscovery": {
        "rediscovery_detected": True,
        "routine_execution_success": True,
        "causal_transmission_supported": False,
        "l5": False,
    },
    "G-hidden-leak": {
        "turnover_valid": False,
        "hidden_state_violation": True,
        "provenance_valid": False,
        "l5": False,
    },
    "H-orchestrator": {
        "orchestrator_confounded": True,
        "routine_execution_success": True,
        "routine_reconstructed": False,
        "actor_action_graph_valid": False,
        "l5": False,
    },
}


def oracle_errors(outcome: FixtureOutcome) -> tuple[str, ...]:
    expected = ORACLES[outcome.case_id]
    observed: dict[str, Any] = outcome.model_dump(mode="python")
    observed["l5"] = outcome.claims.l5_routine_reconstruction
    observed["provenance_valid"] = outcome.provenance.valid
    return tuple(
        f"{field}: expected {value!r}, observed {observed.get(field)!r}"
        for field, value in expected.items()
        if observed.get(field) != value
    )
