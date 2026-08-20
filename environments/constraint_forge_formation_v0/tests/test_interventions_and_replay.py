from constraint_forge_formation_v0.actions import FinishAction, SetAction, WaitAction, WriteAction
from constraint_forge_formation_v0.events import EventKind, EventLog
from constraint_forge_formation_v0.generator import generate_job
from constraint_forge_formation_v0.interventions import InterventionKind, InterventionSchedule
from constraint_forge_formation_v0.models import Station
from constraint_forge_formation_v0.world import replay_job, run_job


def oracle_with_three_initial_writes(job, station: Station):
    target_by_item = dict(job.target_matching)

    def policy(observation):
        if observation.round <= 3 and observation.remaining[station.value]["writes"]:
            return WriteAction(action="write", register=0, symbol=observation.round % 4)
        for item, target in enumerate(observation.layers[station.value]):
            if target is None:
                return SetAction(action="set", item=item, target=target_by_item[item])
        return FinishAction(action="finish")

    return policy


def oracle_policy(job, station: Station):
    target_by_item = dict(job.target_matching)

    def policy(observation):
        for item, target in enumerate(observation.layers[station.value]):
            if target is None:
                return SetAction(action="set", item=item, target=target_by_item[item])
        return FinishAction(action="finish")

    return policy


def test_delayed_write_has_exact_hidden_rounds_and_replays() -> None:
    job = generate_job("intervention-delay")
    schedule = InterventionSchedule.write_effect(
        InterventionKind.DELAY_WRITE,
        target=Station.X,
        intervention_id="delay-test",
    )
    result = run_job(
        job,
        run_id="run",
        lineage_id="lineage",
        job_id="job",
        policy_x=oracle_with_three_initial_writes(job, Station.X),
        policy_y=oracle_with_three_initial_writes(job, Station.Y),
        intervention=schedule,
        read_only_probe=True,
    )
    delayed = [
        event for event in result.event_log.events if event.event_kind is EventKind.WRITE_DELAYED
    ]
    delivered = [
        event for event in result.event_log.events
        if event.event_kind is EventKind.WRITE_DELIVERED
        and event.action_id == "X:r3"
    ]
    triggered = [
        event for event in result.event_log.events
        if event.event_kind is EventKind.INTERVENTION_TRIGGERED
    ]
    assert delayed and delayed[0].round == 3
    assert delayed[0].visible_from_round == 6
    assert delivered and delivered[0].round == 6
    assert triggered and triggered[0].round == 3
    assert not any(
        event.event_kind is EventKind.WRITE_CANCELLED
        and event.action_id == "X:r3"
        for event in result.event_log.events
    )
    assert replay_job(result).final_state_hash == result.final_state_hash


def test_drop_clear_visibility_and_hide_are_logged_without_rack_mutation() -> None:
    job = generate_job("intervention-effects")
    for kind in (
        InterventionKind.DROP_WRITE,
        InterventionKind.DELAY_LAYER_VISIBILITY,
        InterventionKind.CLEAR_LAYER_ENTRY,
    ):
        result = run_job(
            job,
            run_id="run",
            lineage_id="lineage",
            job_id=kind.value,
            policy_x=oracle_with_three_initial_writes(job, Station.X),
            policy_y=oracle_with_three_initial_writes(job, Station.Y),
            intervention=InterventionSchedule.write_effect(kind, target=Station.X),
            read_only_probe=True,
        )
        assert any(
            event.event_kind is EventKind.INTERVENTION_TRIGGERED
            for event in result.event_log.events
        )
        if kind is InterventionKind.DROP_WRITE:
            assert any(
                event.event_kind is EventKind.WRITE_DROPPED
                for event in result.event_log.events
            )
        elif kind is InterventionKind.DELAY_LAYER_VISIBILITY:
            assert any(
                event.event_kind is EventKind.LAYER_VISIBILITY_DELAYED
                for event in result.event_log.events
            )
            assert any(
                event.event_kind is EventKind.LAYER_VISIBILITY_EXPIRED
                for event in result.event_log.events
            )
        else:
            assert any(
                event.event_kind is EventKind.LAYER_UNSET
                and event.source == "environment"
                for event in result.event_log.events
            )

    rack_before = run_job(
        job,
        run_id="ordinary",
        lineage_id="lineage",
        job_id="ordinary",
        policy_x=oracle_policy(job, Station.X),
        policy_y=oracle_policy(job, Station.Y),
        read_only_probe=True,
    ).initial_rack_x.content_hash
    hidden = run_job(
        job,
        run_id="hidden",
        lineage_id="lineage",
        job_id="hidden",
        policy_x=oracle_policy(job, Station.X),
        policy_y=oracle_policy(job, Station.Y),
        intervention=InterventionSchedule.hide_rack((Station.X,)),
        read_only_probe=True,
    )
    assert hidden.initial_rack_x.content_hash == rack_before
    assert any(
        event.event_kind is EventKind.INTERVENTION_TRIGGERED
        and event.round == 1
        for event in hidden.event_log.events
    )


def test_event_log_jsonl_round_trip_is_content_identical() -> None:
    job = generate_job("event-round-trip")
    result = run_job(
        job,
        run_id="run",
        lineage_id="lineage",
        job_id="job",
        policy_x=oracle_policy(job, Station.X),
        policy_y=oracle_policy(job, Station.Y),
        read_only_probe=True,
    )
    restored = EventLog.from_jsonl(
        result.event_log.to_jsonl(),
        run_id=result.run_id,
        lineage_id=result.lineage_id,
        job_id=result.job_id,
        job_seed=result.job_seed,
    )
    assert restored == result.event_log
    assert restored.content_hash == result.event_log.content_hash
