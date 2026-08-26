from __future__ import annotations

import json

import pytest
from verifiers.v1 import AssistantMessage

from constraint_forge_behavioral_runner_r2._r2_world.canonical import canonical_bytes, sha256_bytes
from constraint_forge_behavioral_runner_r2._r2_world.session import ConstraintForgeJobSession
from constraint_forge_behavioral_runner_r2._r2_world.generator import generate_job
from constraint_forge_behavioral_runner_r2.protocol import NEUTRAL_SYSTEM_PROMPT
from constraint_forge_behavioral_runner_r2.requests import round_request
from constraint_forge_behavioral_runner_r2.runner import _raw_assistant_text
from constraint_forge_behavioral_runner_r2.failures import BehavioralCallFailure
from constraint_forge_behavioral_runner_r2.schedule import (
    FAULT_KINDS,
    FormationRunPlan,
    build_run_plan,
)


def test_frozen_plan_contains_14_ordinary_4_fault_and_6_late_probe_slots() -> None:
    plan = build_run_plan(
        sequence_id="sequence-000011",
        sequence_index=11,
        seed_prefix="constraint-forge/test",
    )
    assert [job.job_index for job in plan.jobs if job.category == "ordinary"] == [
        0,
        1,
        2,
        3,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
    ]
    faults = [job for job in plan.jobs if job.category == "fault"]
    assert [job.job_index for job in faults] == [4, 5, 6, 7]
    assert {job.intervention.kind for job in faults} == set(FAULT_KINDS)
    probes = [job for job in plan.jobs if job.category == "rack_probe"]
    assert [job.job_index for job in probes] == [18, 19, 20, 21, 22, 23]
    assert all(job.read_only_probe for job in probes)
    conditions = [job.rack_condition for job in probes]
    assert conditions.count("film_intact") == 3
    assert conditions.count("film_wiped") == 3
    assert all(not job.wipe_rack for job in probes if job.rack_condition == "film_intact")
    assert all(job.wipe_rack for job in probes if job.rack_condition == "film_wiped")
    assert {job.probe_pair_id for job in probes} == {
        "probe-pair-0",
        "probe-pair-1",
        "probe-pair-2",
    }
    for pair_id in {job.probe_pair_id for job in probes}:
        pair = [job for job in probes if job.probe_pair_id == pair_id]
        assert len({job.matched_difficulty_key for job in pair}) == 1
        assert len({job.job_seed for job in pair}) == 2
        assert len({job.expected_job_hash for job in pair}) == 2
    assert len({job.expected_job_hash for job in plan.jobs}) == 24


def test_plan_hash_covers_conditions_not_only_job_payloads() -> None:
    plan = build_run_plan(
        sequence_id="sequence-000000",
        sequence_index=0,
        seed_prefix="constraint-forge/test",
    )
    payload = plan.model_dump(mode="json")
    payload["jobs"][4]["category"] = "ordinary"
    payload["jobs"][4]["intervention"] = None
    with pytest.raises(ValueError):
        FormationRunPlan.model_validate(payload)


def test_model_request_contains_frozen_language_but_no_audit_metadata() -> None:
    job = generate_job("request-test")
    session = ConstraintForgeJobSession.open(
        job, run_id="audit-run", lineage_id="audit-lineage", job_id="audit-job"
    )
    offer = session.begin_round()
    request = round_request(
        role="X",
        job_index=0,
        job_id="audit-job",
        context_epoch=0,
        pre_state_hash=offer.pre_state_hash,
        observation=offer.observation_x,
    )
    assert set(request.model_visible_payload) == {
        "role",
        "phase",
        "round",
        "observation",
        "rack",
        "frames",
        "instructions",
    }
    assert "You operate station X." in request.prompt_text
    assert 'accepts only a round action' in request.prompt_text
    assert '"action":"write","register":int,"symbol":int' in request.instructions
    assert "register is 0–1" in request.instructions
    assert "symbol is 0–3" in request.instructions
    assert "item and target are\n0–5" in request.instructions
    assert "retention start_round is 1–11" in request.instructions
    assert all(
        key not in request.model_visible_payload
        for key in (
            "schema_version",
            "job_index",
            "job_id",
            "context_epoch",
            "pre_state_hash",
            "run_id",
            "lineage_id",
        )
    )
    prompt = json.loads(request.prompt_text)
    assert "source_job_id" not in json.dumps(prompt)
    assert request.request_hash == sha256_bytes(
        canonical_bytes(request.model_visible_payload)
    )


def test_shared_system_prompt_is_role_neutral_and_has_no_literal_placeholder() -> None:
    assert "{X|Y}" not in NEUTRAL_SYSTEM_PROMPT
    assert "You operate one of two stations." in NEUTRAL_SYSTEM_PROMPT
    assert "Each request identifies it as X or Y." in NEUTRAL_SYSTEM_PROMPT


def test_hidden_provider_state_is_retained_but_visible_content_is_accepted() -> None:
    class Segment:
        messages = [
            AssistantMessage(
                content='{"action":"wait"}',
                reasoning_content="hidden",
                provider_state=[{"cursor": "opaque"}],
            )
        ]

    assert _raw_assistant_text(Segment()) == ('{"action":"wait"}', None)


def test_tool_calls_remain_a_fatal_protocol_anomaly() -> None:
    class Segment:
        messages = [
            AssistantMessage(
                content='{"action":"wait"}',
                tool_calls=[],
            )
        ]

    assert _raw_assistant_text(Segment()) == ('{"action":"wait"}', None)

    class ActualToolCallSegment:
        messages = [
            AssistantMessage(
                content='{"action":"wait"}',
                tool_calls=[{"id": "tc", "name": "unexpected", "arguments": "{}"}],
            )
        ]

    with pytest.raises(BehavioralCallFailure):
        _raw_assistant_text(ActualToolCallSegment())
