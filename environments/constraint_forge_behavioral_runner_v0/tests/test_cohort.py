"""No-network checks for the frozen cohort manifest, evidence, and freeze gate."""

from __future__ import annotations

import json
from types import SimpleNamespace

from constraint_forge_behavioral_runner_v0.audit import (
    AuditLedger,
    AuditSeal,
    AuditSealStatus,
    AuditStatus,
)
from constraint_forge_behavioral_runner_v0.cohort import (
    COHORT_MAX_TURNS_PER_ROLE,
    COHORT_NUM_DYADS,
    DyadEvidenceBundleV0,
    build_cohort_tasks,
    build_manifest,
    dyad_summary_row,
    final_eight_nonoccluded_mean,
)
from constraint_forge_behavioral_runner_v0.cohort_launcher import (
    COHORT_MAX_COMPLETION_TOKENS,
    COHORT_REASONING_EFFORT,
    LUNA_BASE_URL,
    LUNA_MODEL,
    _agent_config,
    _declare_boundary,
    _invariant_violation,
    _operational_task,
    _provider_config,
)
from constraint_forge_behavioral_runner_v0.handoff import FormationHandoffV0, FormationJobReceipt


def _frozen_provider() -> dict:
    return {
        "model": "gpt-5.6-luna",
        "base_url": "http://127.0.0.1:10531/v1",
        "x_key_var": "OPENCODE_ZEN_API_KEY_X",
        "y_key_var": "OPENCODE_ZEN_API_KEY_Y",
        "shared_credential": True,
        "max_completion_tokens": COHORT_MAX_COMPLETION_TOKENS,
        "reasoning_effort": COHORT_REASONING_EFFORT,
        "call_timeout_seconds": 300,
        "max_retries": 0,
        "infra_retries": 2,
        "infra_backoff_seconds": (4, 8),
    }


def test_frozen_cohort_manifest_is_twelve_independent_hash_pinned_dyads() -> None:
    tasks = build_cohort_tasks()
    assert len(tasks) == COHORT_NUM_DYADS == 12
    assert [task.data.idx for task in tasks] == list(range(12))
    assert all(
        task.data.sequence_id == f"sequence-{index:06d}"
        for index, task in enumerate(tasks)
    )
    plan_hashes = {task.data.plan_hash for task in tasks}
    assert len(plan_hashes) == 12
    seeds = [seed for task in tasks for seed in task.data.job_seeds]
    assert len(seeds) == 12 * 24 and len(set(seeds)) == len(seeds)
    # The frozen schedule positions hold in every dyad.
    from constraint_forge_behavioral_runner_v0.schedule import (
        FAULT_INDICES,
        ORDINARY_INDICES,
        PROBE_INDICES,
    )

    for task in tasks:
        categories = [job.category for job in task.data.run_plan.jobs]
        assert tuple(
            index for index, category in enumerate(categories) if category == "ordinary"
        ) == ORDINARY_INDICES
        assert tuple(
            index for index, category in enumerate(categories) if category == "fault"
        ) == FAULT_INDICES
        assert tuple(
            index for index, category in enumerate(categories) if category == "rack_probe"
        ) == PROBE_INDICES


def test_manifest_hash_binds_freeze_commit_provider_and_plans() -> None:
    tasks = build_cohort_tasks()
    provider = _provider_config(SimpleNamespace(**_frozen_provider()))
    manifest = build_manifest(
        cohort_id="c",
        freeze_commit="commit-a",
        provider_config=provider,
        qualification_canary_sha256="0" * 64,
        tasks=tasks,
    )
    other_commit = build_manifest(
        cohort_id="c",
        freeze_commit="commit-b",
        provider_config=provider,
        qualification_canary_sha256="0" * 64,
        tasks=tasks,
    )
    other_provider = build_manifest(
        cohort_id="c",
        freeze_commit="commit-a",
        provider_config=provider.model_copy(update={"reasoning_effort": "high"}),
        qualification_canary_sha256="0" * 64,
        tasks=tasks,
    )
    assert manifest.manifest_hash != other_commit.manifest_hash
    assert manifest.manifest_hash != other_provider.manifest_hash
    assert manifest.provider_config.model == "gpt-5.6-luna"
    assert manifest.protocol_version == "constraint-forge/behavioral-runner-v1"


def test_cohort_agent_config_is_zero_retry_high_turn_and_luna_pinned() -> None:
    from types import SimpleNamespace as NS

    args = NS(
        model=LUNA_MODEL,
        base_url=LUNA_BASE_URL,
        reasoning_effort="low",
        max_completion_tokens=16384,
        call_timeout_seconds=300,
    )
    x = _agent_config(args, "LUNA_PROXY_API_KEY_X")
    y = _agent_config(args, "LUNA_PROXY_API_KEY_Y")
    assert x.model == y.model == LUNA_MODEL == "gpt-5.6-luna"
    assert x.client.base_url == y.client.base_url == LUNA_BASE_URL
    assert x.retries.max_retries == y.retries.max_retries == 0
    assert x.max_turns == y.max_turns == COHORT_MAX_TURNS_PER_ROLE == 24 * 18
    assert x.sampling.max_tokens == y.sampling.max_tokens == 16384
    assert x.sampling.reasoning_effort == y.sampling.reasoning_effort == "low"


def test_declared_boundary_knobs_reach_the_harness_process_state(monkeypatch) -> None:
    """The freeze record's knobs must actually govern the running harness."""

    from constraint_forge_behavioral_runner_v0.harness import text_harness_boundary
    from constraint_forge_behavioral_runner_v0 import cohort_launcher

    from constraint_forge_behavioral_runner_v0.harness import _TEXT_HARNESS_BOUNDARY

    monkeypatch.setattr(
        "constraint_forge_behavioral_runner_v0.harness._TEXT_HARNESS_BOUNDARY", {}
    )
    cohort_launcher._declare_boundary(SimpleNamespace(**_frozen_provider()))
    assert text_harness_boundary() == (300.0, 2, (4.0, 8.0))
    provider = _provider_config(SimpleNamespace(**_frozen_provider()))
    assert provider.call_timeout_seconds == 300.0
    assert provider.infra_retries == 2
    assert tuple(provider.infra_backoff_seconds) == (4.0, 8.0)
    # The declared provider config and the live boundary must never diverge.
    timeout, retries, backoff = text_harness_boundary()
    assert (
        float(provider.call_timeout_seconds) == timeout
        and provider.infra_retries == retries
        and tuple(provider.infra_backoff_seconds) == backoff
    )


def test_operational_task_relaxes_only_network_policy() -> None:
    frozen = build_cohort_tasks()[0]
    operational = _operational_task(frozen)
    assert operational.data.network_allow == ["*"]
    assert operational.data.network_block == []
    assert frozen.data.network_allow == [] and frozen.data.network_block == ["*"]
    frozen_payload = frozen.data.run_plan.serialization_payload
    assert operational.data.run_plan.serialization_payload == frozen_payload
    assert operational.data.plan_hash == frozen.data.plan_hash


def _bundle(
    status: AuditSealStatus,
    aborted: bool,
    *,
    lineage_x="lx",
    lineage_y="ly",
    event_lineage_x="lx",
    event_lineage_y="ly",
):
    ledger = AuditLedger(run_id="r", dyad_id="d")
    for actor, lineage in (
        ("X", event_lineage_x),
        ("Y", event_lineage_y),
    ):
        ledger.append(
            actor=actor,
            actor_id=f"{actor}-id",
            lifecycle_id=lineage,
            context_epoch=0,
            job_index=0,
            job_id="j",
            phase="round",
            round=1,
            call_id=f"j:round:1:{actor}:attempt0",
            retry_of=None,
            pre_state_hash="a" * 64,
            world_event_sequence_before=0,
            request_hash="b" * 64,
            model_hash="c" * 64,
            provider_hash="d" * 64,
            config_hash="e" * 64,
            provider_status="completed",
            raw_output="{}",
            raw_output_hash="f" * 64,
            parse_classification="valid",
            world_event_sequence_start=0,
            world_event_sequence_end=1,
            post_state_hash="a" * 64,
            status=AuditStatus.COMPLETED,
        )
    seal = ledger.seal(status)
    handoff = FormationHandoffV0(
        run_id="r",
        dyad_id="d",
        lineage_x=lineage_x,
        lineage_y=lineage_y,
        run_valid=False,
        planned_jobs=24,
        accepted=False,
        aborted=aborted,
        abort_class="DyadAbort" if aborted else None,
        completed_jobs=0,
        successful_jobs=0,
        job_success_mean=0.0,
        audit_chain_hash=ledger.final_hash,
        audit_seal_hash="0" * 64,
        final_state_hash_x="a" * 64,
        final_state_hash_y="a" * 64,
        final_rack_x_bytes=b"",
        final_rack_y_bytes=b"",
    )
    return DyadEvidenceBundleV0(
        cohort_id="c",
        dyad_index=0,
        sequence_id="sequence-000000",
        plan_hash="0" * 64,
        freeze_commit="commit-a",
        started_utc="t0",
        finished_utc="t1",
        handoff=handoff,
        audit_events=ledger.events,
        audit_seal=seal,
        jobs=(),
        traces=(),
    )


def test_invariant_screen_passes_clean_abort_and_flags_lifecycle_drift() -> None:
    clean = _bundle(AuditSealStatus.ABORTED, aborted=True)
    assert _invariant_violation(clean) is None
    drift = _bundle(
        AuditSealStatus.ABORTED, aborted=True, event_lineage_y="other"
    )
    assert _invariant_violation(drift) == "Y lifecycle drift"


def test_gate_one_input_counts_final_eight_writable_ordinary_jobs() -> None:
    def receipt(index: int, success: bool) -> FormationJobReceipt:
        return FormationJobReceipt(
            job_index=index,
            job_id=f"sequence-000000:job-{index:02d}",
            job_seed=f"seed-{index}",
            success=success,
            final_state_hash="a" * 64,
            event_log_hash="b" * 64,
            final_rack_x_hash="c" * 64,
            final_rack_y_hash="d" * 64,
        )

    def handoff_with(successes: dict[int, bool]) -> FormationHandoffV0:
        return FormationHandoffV0(
            run_id="r",
            dyad_id="d",
            lineage_x="lx",
            lineage_y="ly",
            run_valid=True,
            planned_jobs=24,
            accepted=True,
            aborted=False,
            abort_class=None,
            completed_jobs=len(successes),
            successful_jobs=sum(successes.values()),
            job_success_mean=sum(successes.values()) / len(successes),
            job_receipts=tuple(
                receipt(index, success) for index, success in sorted(successes.items())
            ),
            audit_chain_hash="0" * 64,
            audit_seal_hash="0" * 64,
            final_state_hash_x="a" * 64,
            final_state_hash_y="a" * 64,
            final_rack_x_bytes=b"",
            final_rack_y_bytes=b"",
        )

    full = handoff_with({i: i % 2 == 0 for i in range(24)})
    assert final_eight_nonoccluded_mean(full) == 0.5
    partial = handoff_with({9: True, 10: True})
    assert final_eight_nonoccluded_mean(partial) == 1.0


def test_dyad_summary_row_reports_execution_facts_only(tmp_path) -> None:
    bundle = _bundle(AuditSealStatus.COMPLETED, aborted=False)
    row = dyad_summary_row(bundle=bundle, evidence_path=tmp_path / "dyad-00.json")
    payload = row.model_dump(mode="json")
    assert payload["status"] == "completed"
    # The fixture carries audit events but no native v1 traces, so the call
    # count comes out as the honest zero rather than an inferred number.
    assert payload["live_model_calls"] == 0
    assert payload["final_eight_nonoccluded_success_mean"] == 0.0
    assert payload["evidence_sha256"]


def test_luna_qualification_boundary_and_config_are_proxy_local() -> None:
    from verifiers.v1.dialects.chat import ChatDialect
    from verifiers.v1.clients.eval import join_url
    from constraint_forge_behavioral_runner_v0.taskset import (
        ConstraintForgeBehavioralTaskset,
        ConstraintForgeBehavioralTasksetConfig,
    )
    from constraint_forge_behavioral_runner_v0.luna_qualification import (
        LUNA_BASE_URL,
        LUNA_MODEL,
        _agent_config,
        _build_task,
        _declare_boundary,
    )
    from constraint_forge_behavioral_runner_v0.harness import text_harness_boundary
    from constraint_forge_behavioral_runner_v0.harness import (
        _TEXT_HARNESS_BOUNDARY as _boundary,
    )

    saved = dict(_boundary)
    try:
        monkey = None  # no fixture here; restore manually below
        _declare_boundary()
        assert text_harness_boundary() == (300.0, 2, (4.0, 8.0))
        agent = _agent_config("low")
        assert agent.model == LUNA_MODEL == "gpt-5.6-luna"
        assert agent.client.base_url == LUNA_BASE_URL == "http://127.0.0.1:10531/v1"
        assert join_url(LUNA_BASE_URL, ChatDialect().upstream_path) == (
            "http://127.0.0.1:10531/v1/chat/completions"
        )
        assert ChatDialect().auth_headers("k") == {"Authorization": "Bearer k"}
        assert agent.sampling.reasoning_effort == "low"
        assert agent.sampling.max_tokens == 16384
        assert agent.max_turns == COHORT_MAX_TURNS_PER_ROLE
        assert agent.retries.max_retries == 0
        task = _build_task()
        # Throwaway seeds: never the scientific manifest.
        scientific = next(
            iter(
                ConstraintForgeBehavioralTaskset(
                    ConstraintForgeBehavioralTasksetConfig(id="sci")
                )
            )
        )
        assert task.data.job_seeds != scientific.data.job_seeds
        assert len(task.data.job_seeds) == 24
    finally:
        _boundary.clear()
        _boundary.update(saved)
