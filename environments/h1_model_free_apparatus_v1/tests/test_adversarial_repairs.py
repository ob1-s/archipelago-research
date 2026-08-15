import pytest
from pydantic import ValidationError

from h1_model_free_apparatus_v1 import engine
from h1_model_free_apparatus_v1.canonical import stable_hash
from h1_model_free_apparatus_v1.fixtures import FIXTURE_MANIFEST
from h1_model_free_apparatus_v1.lifecycle import LifecycleRegistry
from h1_model_free_apparatus_v1.models import FixtureCase, FixtureKind
from h1_model_free_apparatus_v1.scripted_actors import ScriptedActor, StageOutput


def test_static_terminal_replay_observes_behavior_without_reconstruction_credit():
    terminal = engine.run_fixture(FIXTURE_MANIFEST[6])
    assert terminal.routine_execution_success
    assert terminal.actor_action_graph_valid
    assert terminal.downstream_state_sufficient
    assert not terminal.routine_reconstructed
    assert not terminal.causal_transmission_supported
    assert not terminal.claims.l3_endogenous_state_production
    assert not terminal.claims.l5_routine_reconstruction


def test_partial_survival_is_not_called_valid_turnover_or_causal_reuse():
    for case in FIXTURE_MANIFEST[1:3]:
        outcome = engine.run_fixture(case)
        assert outcome.requested_turnover_executed
        assert not outcome.turnover_valid
        assert not outcome.complete_turnover
        assert outcome.redundant_continuity
        assert not outcome.causal_transmission_supported
        assert not outcome.routine_reconstructed


def test_missing_turnover_events_suppress_l0_through_l5(monkeypatch):
    def silent_turnover(registry, ledger, actor):
        del ledger
        registry.terminate(actor)

    monkeypatch.setattr(engine, "_emit_turnover", silent_turnover)
    outcome = engine.run_fixture(FIXTURE_MANIFEST[0])
    assert outcome.complete_turnover
    assert not outcome.turnover_valid
    assert not outcome.provenance.valid
    assert not any(outcome.claims.model_dump().values())


def test_post_check_reactivation_suppresses_turnover_credit(monkeypatch):
    original = LifecycleRegistry.assert_complete_turnover

    def reactivate_after_check(self, predecessor_generation=0):
        result = original(self, predecessor_generation)
        if result:
            predecessor = next(
                actor
                for actor in self.actors
                if actor.generation == predecessor_generation
            )
            predecessor.active = True
            predecessor.authority_active = True
            predecessor.local_memory["leak"] = "restored"
        return result

    monkeypatch.setattr(
        LifecycleRegistry, "assert_complete_turnover", reactivate_after_check
    )
    outcome = engine.run_fixture(FIXTURE_MANIFEST[0])
    assert outcome.surviving_actor_count == 1
    assert outcome.hidden_state_violation
    assert not outcome.complete_turnover
    assert not outcome.turnover_valid
    assert not outcome.claims.l5_routine_reconstruction


def test_transient_reactivation_remains_sticky_after_retermination(monkeypatch):
    original = LifecycleRegistry.assert_complete_turnover

    def reactivate_then_hide(self, predecessor_generation=0):
        result = original(self, predecessor_generation)
        if result:
            predecessor = next(
                actor
                for actor in self.actors
                if actor.generation == predecessor_generation
            )
            predecessor.active = True
            predecessor.local_memory["transient-leak"] = "used"
            predecessor.terminate()
        return result

    monkeypatch.setattr(
        LifecycleRegistry, "assert_complete_turnover", reactivate_then_hide
    )
    outcome = engine.run_fixture(FIXTURE_MANIFEST[0])
    assert outcome.surviving_actor_count == 0
    assert outcome.hidden_state_violation
    assert not outcome.complete_turnover
    assert not outcome.turnover_valid
    assert not outcome.claims.l5_routine_reconstruction


def test_successor_namespace_reuse_suppresses_complete_turnover(monkeypatch):
    original = LifecycleRegistry.spawn

    def spawn_with_reused_runtime(self, *, lineage_id, generation, position):
        actor = original(
            self, lineage_id=lineage_id, generation=generation, position=position
        )
        if generation == 1:
            predecessor = next(item for item in self.actors if item.generation == 0)
            actor.process_id = predecessor.process_id
            actor.session_id = predecessor.session_id
        return actor

    monkeypatch.setattr(LifecycleRegistry, "spawn", spawn_with_reused_runtime)
    outcome = engine.run_fixture(FIXTURE_MANIFEST[0])
    assert outcome.hidden_state_violation
    assert not outcome.complete_turnover
    assert not outcome.turnover_valid
    assert not outcome.provenance.valid
    assert not outcome.claims.l5_routine_reconstruction


def test_actor_outputs_without_action_edges_cannot_earn_l5(monkeypatch):
    def silent_emit(
        self, *, stage, component, value, parent_ids, source_content_hash=None
    ):
        del component, parent_ids
        artifact_id = f"{self.case_id}-stage-{stage}"
        return StageOutput(
            artifact_id=artifact_id,
            value=value,
            content_hash=stable_hash({"stage": stage, "value": value}),
            source_content_hash=source_content_hash,
        )

    monkeypatch.setattr(ScriptedActor, "_emit", silent_emit)
    outcome = engine.run_fixture(FIXTURE_MANIFEST[0])
    assert outcome.routine_execution_success
    assert not outcome.actor_action_graph_valid
    assert not outcome.routine_reconstructed
    assert not outcome.claims.l5_routine_reconstruction


def test_actor_labeled_events_without_actor_attestation_are_invalid():
    from h1_model_free_apparatus_v1.models import CarrierKind, EventKind, Position
    from h1_model_free_apparatus_v1.provenance import ProvenanceLedger

    registry = LifecycleRegistry("forged-action")
    actor = registry.spawn(lineage_id="l", generation=1, position="encoder")
    ledger = ProvenanceLedger("forged-action")
    ledger.emit(
        EventKind.SPAWN,
        actor=actor,
        carrier=CarrierKind.LOCAL,
        authority=actor.write_authority_id,
    )
    ledger.emit(
        EventKind.WRITE,
        actor=actor,
        carrier=CarrierKind.LOCAL,
        artifact_id="input",
        content_hash=stable_hash({"input": 1}),
        component=Position.ENCODER,
        authority=actor.write_authority_id,
        action="input",
    )
    ledger.emit(
        EventKind.ACT,
        actor=actor,
        carrier=CarrierKind.LOCAL,
        artifact_id="forged-stage",
        content_hash=stable_hash({"stage": 0, "value": [1, 2, 3]}),
        component=Position.ENCODER,
        dependency_stage=0,
        parent_ids=("input",),
        action="orchestrator labels an actor",
        endpoint="held-out-relay",
    )
    result = ledger.validate(actor_handles=registry.actors)
    assert not result.valid
    assert any("lacks valid attestation" in error for error in result.errors)


def test_orchestrator_edges_cannot_satisfy_actor_graph():
    outcome = engine.run_fixture(FIXTURE_MANIFEST[9])
    assert outcome.routine_execution_success
    assert outcome.orchestrator_confounded
    assert not outcome.actor_action_graph_valid
    assert not outcome.functional_reuse
    assert not outcome.claims.l5_routine_reconstruction


@pytest.mark.parametrize(
    ("fixture", "terminal_replay"),
    [
        (FixtureKind.COMPLETE_TURNOVER, True),
        (FixtureKind.TERMINAL_REPLAY, False),
    ],
)
def test_terminal_replay_flag_cannot_disagree_with_fixture_kind(
    fixture, terminal_replay
):
    with pytest.raises(ValidationError):
        FixtureCase(
            case_id="inconsistent-terminal-replay",
            initialization_id="init-inconsistent-terminal-replay",
            replicate_id="inconsistent-terminal-replay-0",
            fixture=fixture,
            turnover_fraction=1.0,
            terminal_replay=terminal_replay,
        )


def test_model_construct_cannot_bypass_terminal_replay_guard_at_execution():
    bypass = FixtureCase.model_construct(
        case_id="constructed-terminal-replay",
        initialization_id="init-constructed-terminal-replay",
        replicate_id="constructed-terminal-replay-0",
        fixture=FixtureKind.TERMINAL_REPLAY,
        turnover_fraction=1.0,
        terminal_replay=False,
    )
    with pytest.raises(ValidationError):
        engine.run_fixture(bypass)
