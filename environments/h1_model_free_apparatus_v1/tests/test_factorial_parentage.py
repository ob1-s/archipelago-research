import pytest

from h1_model_free_apparatus_v1.analysis import factorial_mechanics
from h1_model_free_apparatus_v1.engine import run_fixture
from h1_model_free_apparatus_v1.fixtures import FACTORIAL_MANIFEST, PARENTAGE_MANIFEST
from h1_model_free_apparatus_v1.models import ParentageTopology


def test_full_state_by_lineage_factorial_follows_actual_bytes():
    outcomes = tuple(run_fixture(case) for case in FACTORIAL_MANIFEST)
    assert factorial_mechanics(outcomes) == {
        "all_four_cells": True,
        "state_follows_actual_bytes": True,
        "lineage_manipulation_observed": True,
        "known_compatibility_interaction": True,
    }


def test_state_swap_changes_behavior_without_relabeling_lineage():
    outcomes = {case.case_id: run_fixture(case) for case in FACTORIAL_MANIFEST}
    assert outcomes["factorial-AA"].routine_execution_success
    assert not outcomes["factorial-AB"].routine_execution_success
    assert (
        outcomes["factorial-AA"].lineage_id.split("-A-")[0]
        == outcomes["factorial-AB"].lineage_id.split("-A-")[0]
    )
    assert outcomes["factorial-AB"].manipulation_state_detected


def test_duplicate_factorial_cell_is_rejected_instead_of_overwritten():
    outcomes = tuple(run_fixture(case) for case in FACTORIAL_MANIFEST)
    with pytest.raises(ValueError):
        factorial_mechanics((*outcomes, outcomes[0]))


def test_all_parentage_topologies_are_materialized():
    assert {case.topology for case in PARENTAGE_MANIFEST} == set(ParentageTopology)
    inventories = {
        case.topology: tuple(
            record.parent_ids for record in run_fixture(case).artifact_inventory
        )
        for case in PARENTAGE_MANIFEST
    }
    assert (
        inventories[ParentageTopology.UNIQUE] != inventories[ParentageTopology.MULTIPLE]
    )
    assert (
        inventories[ParentageTopology.COMMON_ARCHIVE]
        != inventories[ParentageTopology.BROADCAST]
    )


def test_common_archive_never_invents_unique_parentage():
    case = next(
        case
        for case in PARENTAGE_MANIFEST
        if case.topology is ParentageTopology.COMMON_ARCHIVE
    )
    outcome = run_fixture(case)
    assert outcome.common_archive_ambiguity
    assert not outcome.parentage_identified
    assert not outcome.claims.l4_causal_transmission_or_recovery


def test_broadcast_topology_records_both_carriers_reaching_both_successors():
    case = next(
        case
        for case in PARENTAGE_MANIFEST
        if case.topology is ParentageTopology.BROADCAST
    )
    outcome = run_fixture(case)
    reads = [
        event
        for event in outcome.provenance_events
        if event.event.value == "read" and event.generation == 1
    ]
    assert len(reads) == 4
    by_actor = {}
    for event in reads:
        by_actor.setdefault(event.actor_id, set()).add(event.artifact_id)
    assert len(by_actor) == 2
    assert all(len(artifact_ids) == 2 for artifact_ids in by_actor.values())


def test_shuffled_attribution_is_rejected():
    case = next(
        case
        for case in PARENTAGE_MANIFEST
        if case.topology is ParentageTopology.SHUFFLED_ATTRIBUTION
    )
    outcome = run_fixture(case)
    assert not outcome.provenance.valid
    assert not outcome.parentage_identified
    assert not outcome.claims.l0_turnover_validity


def test_shuffled_actual_state_is_observed_not_silently_relabelled():
    case = next(
        case
        for case in PARENTAGE_MANIFEST
        if case.topology is ParentageTopology.SHUFFLED_STATE
    )
    outcome = run_fixture(case)
    assert outcome.manipulation_state_detected
    assert not outcome.routine_execution_success
