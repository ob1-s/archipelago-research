from __future__ import annotations

import json

from constraint_forge_formation_v0.actions import FinishAction, SetAction
from constraint_forge_formation_v0.generator import generate_job
from constraint_forge_formation_v0.models import Station
from constraint_forge_formation_v0.rack import full_rack_view
from constraint_forge_formation_v0.session import (
    ConstraintForgeJobSession,
    ParseClassification,
    SessionPhaseError,
)
from constraint_forge_formation_v0.world import run_job
from constraint_forge_behavioral_runner_v0.requests import memory_request


def _target_policy(job, station):
    target = dict(job.target_matching)

    def policy(observation):
        for item, current in enumerate(observation.layers[station.value]):
            if current is None:
                return SetAction(action="set", item=item, target=target[item])
        return FinishAction(action="finish")

    return policy


def _target_json(job, observation, station):
    target = dict(job.target_matching)
    for item, current in enumerate(observation.layers[station.value]):
        if current is None:
            return json.dumps(
                {"action": "set", "item": item, "target": target[item]},
                separators=(",", ":"),
            )
    return '{"action":"finish"}'


def _run_session(job, *, rack_x=None, rack_y=None, read_only=True):
    session = ConstraintForgeJobSession.open(
        job,
        run_id="r",
        lineage_id="l",
        job_id="j",
        rack_x=rack_x,
        rack_y=rack_y,
        read_only_probe=read_only,
    )
    while not session.terminal:
        offer = session.begin_round()
        assert len(offer.pre_state_hash) == 64
        assert offer.observation_x.round == offer.observation_y.round
        session.submit_round(
            token=offer.token,
            raw_x=_target_json(job, offer.observation_x, Station.X),
            raw_y=_target_json(job, offer.observation_y, Station.Y),
        )
    if read_only:
        assert session.begin_eviction() is None
    else:
        eviction = session.begin_eviction()
        session.submit_eviction(
            token=eviction.token,
            raw_x='{"action":"keep_unchanged"}',
            raw_y='{"action":"keep_unchanged"}',
        )
        retention = session.begin_retention()
        session.submit_retention(
            token=retention.token,
            raw_x='{"action":"keep_unchanged"}',
            raw_y='{"action":"keep_unchanged"}',
        )
    return session.result()


def test_scripted_batch_and_live_session_have_golden_parity() -> None:
    job = generate_job(8)
    batch = run_job(
        job,
        run_id="r",
        lineage_id="l",
        job_id="j",
        policy_x=_target_policy(job, Station.X),
        policy_y=_target_policy(job, Station.Y),
        read_only_probe=True,
    )
    stepped = _run_session(job)
    assert stepped.final_state_hash == batch.final_state_hash
    assert stepped.event_log.content_hash == batch.event_log.content_hash
    assert stepped.success == batch.success


def test_scripted_batch_and_session_retain_phase_event_semantics_match() -> None:
    job = generate_job(81)
    batch = run_job(
        job,
        run_id="r",
        lineage_id="l",
        job_id="j",
        policy_x=_target_policy(job, Station.X),
        policy_y=_target_policy(job, Station.Y),
        memory_policy_x=lambda *_: (None, None),
        memory_policy_y=lambda *_: (None, None),
    )
    stepped = _run_session(job, read_only=False)
    assert stepped.final_state_hash == batch.final_state_hash
    assert stepped.event_log.content_hash == batch.event_log.content_hash


def test_malformed_behavioral_output_is_one_deterministic_rejected_opportunity() -> None:
    job = generate_job(9)
    session = ConstraintForgeJobSession.open(
        job, run_id="r", lineage_id="l", job_id="j", read_only_probe=True
    )
    offer = session.begin_round()
    before = session.state.x.model_dump(mode="json")
    result = session.submit_round(
        token=offer.token,
        raw_x="not json",
        raw_y=_target_json(job, offer.observation_y, Station.Y),
    )
    assert result.parse_x is ParseClassification.MALFORMED_REJECTED
    assert result.resolution.x.action_payload == {"action": "rejected"}
    assert result.resolution.x.legal is False
    assert result.resolution.x.rejection_reason == "malformed_action"
    after = session.state.x.model_dump(mode="json")
    # The rejected opportunity changes no X-local state or budget. The global
    # round still advances because the opportunity was consumed.
    assert after == before
    assert result.round == 1
    assert session._pending_round is None
    assert session.frames_x[-1].action_payload == {"action": "rejected"}
    assert session.frames_x[-1].action_legal is False
    assert "not json" not in json.dumps(session.frames_x[-1].model_dump(mode="json"))


def test_round_offer_seals_identical_prestate_before_dispatch() -> None:
    job = generate_job(12)
    session = ConstraintForgeJobSession.open(
        job, run_id="r", lineage_id="l", job_id="j", read_only_probe=True
    )
    offer = session.begin_round()
    result = session.submit_round(
        token=offer.token,
        raw_x=_target_json(job, offer.observation_x, Station.X),
        raw_y=_target_json(job, offer.observation_y, Station.Y),
    )
    assert offer.pre_state_hash == result.pre_state_hash
    assert result.resolution.x.pre_state_hash == result.resolution.y.pre_state_hash


def test_memory_offer_exposes_only_binary_job_outcome() -> None:
    session = ConstraintForgeJobSession.open(
        generate_job(13), run_id="r", lineage_id="l", job_id="j"
    )
    offer = session.begin_round()
    session.submit_round(
        token=offer.token,
        raw_x='{"action":"finish"}',
        raw_y='{"action":"finish"}',
    )
    memory = session.begin_eviction()
    assert memory is not None
    assert memory.success is False
    assert "failure_reason" not in memory.model_dump(mode="json")
    assert "target_matching" not in memory.model_dump(mode="json")
    request = memory_request(
        role="X",
        phase="eviction",
        job_index=0,
        job_id="j",
        context_epoch=0,
        pre_state_hash=memory.state_hash,
        rack=memory.rack_view_x,
        frames=memory.frames_x,
        success=memory.success,
    )
    assert request.visible_payload["success"] is False
    assert "failure_reason" not in request.visible_payload
    assert "target_matching" not in request.visible_payload


def test_malformed_and_wrong_phase_memory_choices_are_rejected_without_rack_change() -> None:
    job = generate_job(83)
    session = ConstraintForgeJobSession.open(job, run_id="r", lineage_id="l", job_id="j")
    while not session.terminal:
        offer = session.begin_round()
        session.submit_round(
            token=offer.token,
            raw_x=_target_json(job, offer.observation_x, Station.X),
            raw_y=_target_json(job, offer.observation_y, Station.Y),
        )
    before_x = session.rack_x.serialization_bytes
    before_y = session.rack_y.serialization_bytes
    eviction = session.begin_eviction()
    evicted = session.submit_eviction(
        token=eviction.token,
        raw_x="not json",
        raw_y='{"action":"retain","start_round":1}',
    )
    assert evicted.parse_x is ParseClassification.MALFORMED_REJECTED
    assert evicted.parse_y is ParseClassification.WRONG_PHASE_REJECTED
    assert evicted.mutation_x.legal is False
    assert evicted.mutation_x.rejection_reason == "malformed_action"
    assert evicted.mutation_y.legal is False
    assert evicted.mutation_y.rejection_reason == "wrong_phase"
    assert session.rack_x.serialization_bytes == before_x
    assert session.rack_y.serialization_bytes == before_y
    attempted = [
        event
        for event in session.event_log.events
        if event.event_kind.value == "EVICT_ATTEMPTED"
    ]
    assert all(event.action_payload == {"action": "rejected"} for event in attempted[-2:])


def test_eviction_precedes_retention_and_retention_sees_resulting_rack() -> None:
    job = generate_job(14)
    seeded = run_job(
        job,
        run_id="seed",
        lineage_id="seed",
        job_id="seed-job",
        policy_x=_target_policy(job, Station.X),
        policy_y=_target_policy(job, Station.Y),
        memory_policy_x=lambda *_: (None, 1),
        memory_policy_y=lambda *_: (None, 1),
    )
    handle = seeded.final_rack_x.films[0].handle
    session = ConstraintForgeJobSession.open(
        job,
        run_id="r",
        lineage_id="l",
        job_id="j",
        rack_x=seeded.final_rack_x,
        rack_y=seeded.final_rack_y,
    )
    while not session.terminal:
        offer = session.begin_round()
        session.submit_round(
            token=offer.token,
            raw_x=_target_json(job, offer.observation_x, Station.X),
            raw_y=_target_json(job, offer.observation_y, Station.Y),
        )
    eviction = session.begin_eviction()
    assert eviction.rack_view_x.full_films
    assert eviction.success is True
    session.submit_eviction(
        token=eviction.token,
        raw_x=json.dumps({"action": "evict", "fragment_handle": handle}, separators=(",", ":")),
        raw_y="{\"action\":\"keep_unchanged\"}",
    )
    retention = session.begin_retention()
    assert retention.rack_view_x.full_films == ()
    assert retention.rack_view_y.full_films
    assert retention.success is True
    result = session.submit_retention(
        token=retention.token,
        raw_x="{\"action\":\"keep_unchanged\"}",
        raw_y="{\"action\":\"keep_unchanged\"}",
    )
    assert result.phase == "retention"
    assert session.complete
    assert session.result().final_rack_x.films == ()
    kinds = [event.event_kind.value for event in session.event_log.events]
    assert kinds.index("EVICT_ATTEMPTED") < kinds.index("RETAIN_ATTEMPTED")


def test_batch_eviction_path_and_live_session_both_handle_a_real_eviction() -> None:
    job = generate_job(82)
    seeded = run_job(
        job,
        run_id="seed",
        lineage_id="seed",
        job_id="seed-job",
        policy_x=_target_policy(job, Station.X),
        policy_y=_target_policy(job, Station.Y),
        memory_policy_x=lambda *_: (None, 1),
        memory_policy_y=lambda *_: (None, 1),
    )
    handle = seeded.final_rack_x.films[0].handle
    batch = run_job(
        job,
        run_id="r",
        lineage_id="l",
        job_id="j",
        rack_x=seeded.final_rack_x,
        rack_y=seeded.final_rack_y,
        policy_x=_target_policy(job, Station.X),
        policy_y=_target_policy(job, Station.Y),
        memory_policy_x=lambda *_: (handle, 1),
        memory_policy_y=lambda *_: (handle, 1),
    )
    session = ConstraintForgeJobSession.open(
        job,
        run_id="r",
        lineage_id="l",
        job_id="j",
        rack_x=seeded.final_rack_x,
        rack_y=seeded.final_rack_y,
    )
    while not session.terminal:
        offer = session.begin_round()
        session.submit_round(
            token=offer.token,
            raw_x=_target_json(job, offer.observation_x, Station.X),
            raw_y=_target_json(job, offer.observation_y, Station.Y),
        )
    eviction = session.begin_eviction()
    session.submit_eviction(
        token=eviction.token,
        raw_x=json.dumps({"action": "evict", "fragment_handle": handle}, separators=(",", ":")),
        raw_y=json.dumps({"action": "evict", "fragment_handle": handle}, separators=(",", ":")),
    )
    retention = session.begin_retention()
    session.submit_retention(
        token=retention.token,
        raw_x='{"action":"retain","start_round":1}',
        raw_y='{"action":"retain","start_round":1}',
    )
    stepped = session.result()
    assert batch.final_state_hash == stepped.final_state_hash
    assert batch.final_rack_x.content_hash == stepped.final_rack_x.content_hash
    assert batch.final_rack_y.content_hash == stepped.final_rack_y.content_hash


def test_read_only_probe_never_opens_memory_and_preserves_rack_bytes() -> None:
    job = generate_job(16)
    seeded = run_job(
        job,
        run_id="seed",
        lineage_id="seed",
        job_id="seed-job",
        policy_x=_target_policy(job, Station.X),
        policy_y=_target_policy(job, Station.Y),
        memory_policy_x=lambda *_: (None, 1),
        memory_policy_y=lambda *_: (None, 1),
    )
    result = _run_session(
        job,
        rack_x=seeded.final_rack_x,
        rack_y=seeded.final_rack_y,
        read_only=True,
    )
    assert result.final_rack_x.serialization_bytes == seeded.final_rack_x.serialization_bytes
    assert result.final_rack_y.serialization_bytes == seeded.final_rack_y.serialization_bytes
    assert all(
        event.event_kind.value not in {"MEMORY_PHASE_START", "EVICT_ATTEMPTED", "RETAIN_ATTEMPTED"}
        for event in result.event_log.events
    )


def test_session_phase_barriers_are_explicit() -> None:
    session = ConstraintForgeJobSession.open(
        generate_job(18), run_id="r", lineage_id="l", job_id="j", read_only_probe=True
    )
    try:
        session.begin_retention()
    except SessionPhaseError:
        pass
    else:
        raise AssertionError("retention must not be available before eviction")


def test_film_and_model_visible_rack_do_not_expose_a_source_job_id() -> None:
    job = generate_job(20)
    result = _run_session(job)
    rack_payload = result.final_rack_x.serialization_payload
    assert "source_job_id" not in json.dumps(rack_payload)
    assert all("source_job_id" not in frame.model_dump(mode="json") for film in result.final_rack_x.films for frame in film.frames)
    assert "full_films" in full_rack_view(result.final_rack_x).model_dump(mode="json")
