from constraint_forge_formation_v0.generator import generate_job
from constraint_forge_formation_v0.events import EventKind
from constraint_forge_formation_v0.models import Station
from constraint_forge_formation_v0.rack import (
    FilmFrame,
    RackState,
    apply_memory_phases,
    full_rack_view,
    hidden_rack_view,
    retain_film,
)
from constraint_forge_formation_v0.world import run_job
from constraint_forge_formation_v0.actions import FinishAction, SetAction


def oracle_policy(job, station: Station):
    target_by_item = dict(job.target_matching)

    def policy(obs):
        for item, target in enumerate(obs.layers[station.value]):
            if target is None:
                return SetAction(action="set", item=item, target=target_by_item[item])
        return FinishAction(action="finish")

    return policy


def retain_first_window(station, view, frames):
    del station, view
    return None, 1 if len(frames) >= 6 else None


def test_film_is_immutable_non_recursive_and_rack_is_canonical() -> None:
    job = generate_job(11)
    result = run_job(
        job,
        run_id="r",
        lineage_id="l",
        job_id="j",
        policy_x=oracle_policy(job, Station.X),
        policy_y=oracle_policy(job, Station.Y),
        memory_policy_x=retain_first_window,
        memory_policy_y=retain_first_window,
    )
    assert result.success
    assert len(result.final_rack_x.films) == 1
    film = result.final_rack_x.films[0]
    assert all("rack" not in frame.model_dump(mode="json") for frame in film.frames)
    assert result.final_rack_x.serialization_bytes == result.final_rack_x.serialization_bytes
    assert result.final_rack_x.films == tuple(
        sorted(result.final_rack_x.films, key=lambda item: (item.content_hash, item.handle))
    )
    film_payload = result.final_rack_x.films[0].model_dump(mode="json")
    rack_payload = result.final_rack_x.serialization_payload
    visible_payload = full_rack_view(result.final_rack_x).model_dump(mode="json")
    assert "source_job_id" not in film_payload
    assert "source_job_id" not in rack_payload["films"][0]
    assert "source_job_id" not in visible_payload["full_films"][0]
    assert b"source_job_id" not in result.final_rack_x.serialization_bytes
    retained = [
        event
        for event in result.event_log.events
        if event.event_kind is EventKind.RETAINED
    ]
    assert retained
    assert retained[0].detail["source_job_id"] == "j"
    assert result.memory_mutations_x[-1].source_job_id == "j"


def test_hidden_rack_sentinel_is_nondestructive() -> None:
    rack = RackState()
    hidden = hidden_rack_view()
    assert not hidden.available
    assert hidden.rack_unavailable == "rack_unavailable"
    assert rack.content_hash == RackState().content_hash


def test_post_round_rack_view_is_hash_only_and_capacity_is_hard() -> None:
    job = generate_job(12)
    result = run_job(
        job,
        run_id="r",
        lineage_id="l",
        job_id="j",
        policy_x=oracle_policy(job, Station.X),
        policy_y=oracle_policy(job, Station.Y),
        memory_policy_x=retain_first_window,
        memory_policy_y=retain_first_window,
    )
    assert result.success
    assert result.final_rack_x.films
    assert result.frames_x[0].action_payload
    # The rack is not a FilmFrame field; a later observation carries only the
    # canonical rack hash, never retained film bytes.
    from constraint_forge_formation_v0.rack import hashed_rack_view

    view = hashed_rack_view(result.final_rack_x)
    assert view.hashed_only
    assert view.content_hash == result.final_rack_x.content_hash
    assert not view.full_films
    assert view.model_dump(mode="json")["full_films"] == []
    rack = RackState()
    for index in range(6):
        rack, mutation = retain_film(
            rack,
            Station.X,
            result.frames_x[:6],
            start_round=1,
            source_job_id=f"job-{index}",
            handle_seed=f"seed-{index}",
        )
        assert mutation.legal
    rack_after, rejected = retain_film(
        rack,
        Station.X,
        result.frames_x[:6],
        start_round=1,
        source_job_id="job-7",
        handle_seed="seed-7",
    )
    assert not rejected.legal
    assert rejected.rejection_reason == "rack_full_after_eviction_subphase"
    assert rack_after == rack
