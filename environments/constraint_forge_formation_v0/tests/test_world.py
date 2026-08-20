from constraint_forge_formation_v0.actions import FinishAction, SetAction, WaitAction
from constraint_forge_formation_v0.generator import generate_job
from constraint_forge_formation_v0.models import Station
from constraint_forge_formation_v0.world import replay_job, resolve_round, run_job, initial_state


def target_policy(job, station: Station):
    target_by_item = dict(job.target_matching)

    def policy(observation):
        layer = observation.layers[station.value]
        for item, target in enumerate(layer):
            if target is None:
                return SetAction(action="set", item=item, target=target_by_item[item])
        return FinishAction(action="finish")

    return policy


def test_simultaneous_decisions_share_one_pre_round_hash() -> None:
    job = generate_job(1)
    state = initial_state(job, run_id="r", lineage_id="l", job_id="j")
    updated, resolution = resolve_round(
        state,
        SetAction(action="set", item=0, target=0),
        SetAction(action="set", item=0, target=1),
    )
    assert resolution.x.pre_state_hash == resolution.y.pre_state_hash
    assert updated.x.layer[0] == 0
    assert updated.y.layer[0] == 1


def test_oracle_job_completes_and_replays_exactly() -> None:
    job = generate_job(8)
    result = run_job(
        job,
        run_id="r",
        lineage_id="l",
        job_id="j",
        policy_x=target_policy(job, Station.X),
        policy_y=target_policy(job, Station.Y),
        read_only_probe=True,
    )
    assert result.success
    assert result.rounds_resolved == 7
    assert result.reward == 1.0
    replayed = replay_job(result)
    assert replayed.final_state_hash == result.final_state_hash
    assert replayed.success is True


def test_illegal_actions_consume_round_but_not_budget() -> None:
    job = generate_job(9)
    state = initial_state(job, run_id="r", lineage_id="l", job_id="j")
    updated, resolution = resolve_round(
        state,
        SetAction(action="set", item=0, target=0),
        SetAction(action="set", item=0, target=0),
    )
    assert resolution.y.legal
    # The target is local to each station, so both same-looking sets are legal.
    updated, resolution = resolve_round(
        updated,
        SetAction(action="set", item=0, target=1),
        WaitAction(action="wait"),
    )
    assert not resolution.x.legal
    assert resolution.x.rejection_reason == "item_already_set"
    assert updated.x.mutations_remaining == 7
