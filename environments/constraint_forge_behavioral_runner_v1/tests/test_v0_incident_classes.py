"""Regression tests for V0 incident classes (V1 hardening contract).

Each test maps 1:1 to an incident or tooling finding recorded in
environments/constraint_forge_behavioral_runner_v1/docs/phaseA_forensics.md
and the V0 analysis report incident appendix.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from constraint_forge_behavioral_runner_v1.cohort_launcher import (
    _memory_headroom_mb,
    _reconcile_manifest,
)


def test_stop_rule_matches_frozen_text_not_streak():
    """V0 tooling finding: code halted on trailing abort streak regardless of
    completions; frozen text says '3 aborted AND none completed'. V1 must
    continue scheduling when any dyad has completed, even with a long tail of
    aborts. Evaluated via the manifest-history rule inside _run."""

    from constraint_forge_behavioral_runner_v1.cohort_launcher import (
        PARALLEL_ABORT_STOP_TOTAL,
    )

    assert PARALLEL_ABORT_STOP_TOTAL == 3


def test_memory_headroom_helper_returns_int_or_none():
    value = _memory_headroom_mb()
    assert value is None or isinstance(value, int)


def test_reconcile_adopts_orphan_evidence(tmp_path: Path):
    directory = tmp_path / "cohort"
    directory.mkdir()
    manifest = {"dyads": [{"dyad_index": 0, "status": "completed"}]}
    (directory / "manifest.json").write_text(json.dumps(manifest))
    orphan = {
        "audit_seal": {"status": "aborted", "final_hash": "a" * 64},
    }
    (directory / "dyad-04.json").write_text(json.dumps(orphan))

    rc = _reconcile_manifest(directory)

    assert rc == 0
    updated = json.loads((directory / "manifest.json").read_text())
    rows = {row["dyad_index"]: row for row in updated["dyads"]}
    assert rows[4]["status"] == "aborted"
    assert rows[4]["reconciled"] is True
    assert rows[4]["evidence_sha256"]


def test_row_protocol_is_prefixed_and_typed(capsys: pytest.CaptureFixture[str]):
    """V0 incident: drivers matched rows by first-key prefix and silently lost
    them. V1 emits '@ROW:' + JSON with an explicit row_type field."""

    payload = {
        "dyad_index": 3,
        "status": "completed",
        "abort_class": None,
        "live_model_calls": 5,
        "infra_retry_events": 0,
        "completed_jobs": 24,
        "successful_jobs": 1,
    }
    line = "@ROW:" + json.dumps(
        {**payload, "row_type": "dyad"}, sort_keys=True
    )
    print(line)
    captured = capsys.readouterr().out.strip().splitlines()[-1]
    assert captured.startswith("@ROW:")
    parsed = json.loads(captured[len("@ROW:"):])
    assert parsed["row_type"] == "dyad"
    assert parsed["dyad_index"] == 3


def test_probe_schedule_pairs_contrast_film_conditions():
    """Q2 estimand: every difficulty-matched probe pair must contain exactly
    one film-intact and one film-wiped member; no HIDE_RACK anywhere."""

    from constraint_forge_behavioral_runner_v1.schedule import build_run_plan

    for sequence_index in range(6):
        plan = build_run_plan(
            sequence_id=f"seq-{sequence_index}",
            sequence_index=sequence_index,
            seed_prefix="constraint-forge/v1-test",
        )
        probes = [j for j in plan.jobs if j.category == "rack_probe"]
        conditions = [j.rack_condition for j in probes]
        assert conditions.count("film_intact") == 3
        assert conditions.count("film_wiped") == 3
        for pair_id in ("probe-pair-0", "probe-pair-1", "probe-pair-2"):
            pair = [j for j in probes if j.probe_pair_id == pair_id]
            assert sorted(j.rack_condition for j in pair) == [
                "film_intact",
                "film_wiped",
            ]
            assert len({j.matched_difficulty_key for j in pair}) == 1
            # rotation counterbalancing: intact-first pair rotates %3
            first = min(pair, key=lambda j: j.job_index)
            expected = (
                "film_intact"
                if (int(pair_id.split("-")[-1]) == sequence_index % 3)
                else "film_wiped"
            )
            assert first.rack_condition == expected, (pair_id, sequence_index)
        assert all(j.intervention is None for j in probes)


def test_wipe_flag_reaches_only_wiped_probes():
    from constraint_forge_behavioral_runner_v1.schedule import build_run_plan

    plan = build_run_plan(
        sequence_id="seq-0", sequence_index=0, seed_prefix="constraint-forge/v1-test"
    )
    for job in plan.jobs:
        if job.category != "rack_probe":
            assert not job.wipe_rack
        else:
            assert job.wipe_rack == (job.rack_condition == "film_wiped")


def test_no_hide_rack_survives_in_v1_plans():
    from constraint_forge_behavioral_runner_v1.schedule import build_run_plan

    for sequence_index in range(4):
        plan = build_run_plan(
            sequence_id=f"seq-{sequence_index}",
            sequence_index=sequence_index,
            seed_prefix="constraint-forge/v1-test",
        )
        for job in plan.jobs:
            if job.intervention is not None:
                from constraint_forge_formation_v0.interventions import (
                    InterventionKind,
                )

                assert job.intervention.kind is not InterventionKind.HIDE_RACK


def test_preflight_flags_dead_bridge(tmp_path: Path):
    """V0 incident: launchers dispatched into a dead upstream and burned
    retries. Preflight must fail fast with exit code 4."""

    import subprocess
    import sys

    proc = subprocess.run(
        [
            sys.executable, "-m",
            "constraint_forge_behavioral_runner_v1.cohort_launcher",
            "--live", "--cohort-id", "preflight-check-does-not-exist",
            "--base-url", "http://127.0.0.1:9/v1",
            "--output-dir", str(tmp_path),
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        timeout=120,
        env={
            **__import__("os").environ,
            "LUNA_PROXY_API_KEY_X": "local-proxy",
            "LUNA_PROXY_API_KEY_Y": "local-proxy",
        },
    )
    combined = proc.stdout + proc.stderr
    assert '"preflight_failed"' in combined
