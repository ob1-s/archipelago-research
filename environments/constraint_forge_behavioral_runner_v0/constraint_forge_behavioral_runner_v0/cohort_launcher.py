"""Explicit live launcher for the frozen 12-dyad exploratory formation cohort.

Run `--freeze-only` first to materialize the freeze record before any model
call. A plain `--live` run executes every remaining dyad exactly once under
the frozen provider configuration; aborted dyads are preserved and never
re-executed (a crashed dyad requires an explicit `--resume-crashed INDEX`).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess  # noqa: S404 - only reads the local git revision
from pathlib import Path

import verifiers.v1 as vf
from verifiers.v1.configs.agent import AgentConfig
from verifiers.v1.configs.client import EvalClientConfig
from verifiers.v1.configs.retries import RetryConfig
from verifiers.v1.runtimes.subprocess import SubprocessConfig
from verifiers.v1.types import SamplingConfig

from constraint_forge_formation_v0.canonical import stable_hash

from .audit import AuditLedger
from .cohort import (
    COHORT_MAX_TURNS_PER_ROLE,
    COHORT_NUM_DYADS,
    CONSECUTIVE_INFRA_ABORT_STOP,
    DyadEvidenceBundleV0,
    DyadStatus,
    CohortProviderConfigV0,
    build_cohort_tasks,
    build_manifest,
    dyad_summary_row,
    utc_now,
    write_atomic,
)
from .harness import CALL_TIMEOUT_SECONDS, ConstraintForgeTextHarnessConfig
from .live_canary import _trace_evidence
from .runner import run_behavioral_sequence
from .taskset import ConstraintForgeBehavioralTask

ZEN_BASE_URL = "https://opencode.ai/zen/v1/"
OX_ALPHA_MODEL = "x-preview-f-free"
COHORT_MAX_COMPLETION_TOKENS = 16384
COHORT_REASONING_EFFORT = "low"
DEFAULT_X_KEY_VAR = "OPENCODE_ZEN_API_KEY_X"
DEFAULT_Y_KEY_VAR = "OPENCODE_ZEN_API_KEY_Y"
QUALIFICATION_CANARY_SHA256 = (
    "0669b6c0ef0e83d2ca0a9410c9704dcb3413ba14cee7c6c3d93e9030f7c997fe"
)


def _freeze_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _provider_config(args) -> CohortProviderConfigV0:
    return CohortProviderConfigV0(
        model=OX_ALPHA_MODEL,
        base_url=ZEN_BASE_URL,
        x_key_var=args.x_key_var,
        y_key_var=args.y_key_var,
        shared_credential=True,
        max_completion_tokens=COHORT_MAX_COMPLETION_TOKENS,
        reasoning_effort=COHORT_REASONING_EFFORT,
        call_timeout_seconds=int(CALL_TIMEOUT_SECONDS),
        max_retries=0,
    )


def _agent_config(api_key_var: str) -> AgentConfig:
    return AgentConfig(
        model=OX_ALPHA_MODEL,
        client=EvalClientConfig(base_url=ZEN_BASE_URL, api_key_var=api_key_var),
        harness=ConstraintForgeTextHarnessConfig(),
        runtime=SubprocessConfig(),
        sampling=SamplingConfig(
            max_tokens=COHORT_MAX_COMPLETION_TOKENS,
            reasoning_effort=COHORT_REASONING_EFFORT,
        ),
        max_turns=COHORT_MAX_TURNS_PER_ROLE,
        retries=RetryConfig(max_retries=0),
    )


def _operational_task(task: ConstraintForgeBehavioralTask) -> ConstraintForgeBehavioralTask:
    """Relax only the operational network policy on a task copy (see canary)."""

    data = task.data.model_copy(update={"network_allow": ["*"], "network_block": []})
    return ConstraintForgeBehavioralTask(data, task.config)


def _bundle_from_result(
    result,
    *,
    cohort_id: str,
    dyad_index: int,
    sequence_id: str,
    plan_hash: str,
    freeze_commit: str,
    started_utc: str,
    rerun_after_crash: bool,
) -> DyadEvidenceBundleV0:
    seal = result.ledger.seal_record
    if seal is None:
        raise RuntimeError("dyad returned without a sealed audit ledger")
    return DyadEvidenceBundleV0(
        cohort_id=cohort_id,
        dyad_index=dyad_index,
        sequence_id=sequence_id,
        plan_hash=plan_hash,
        freeze_commit=freeze_commit,
        started_utc=started_utc,
        finished_utc=utc_now(),
        rerun_after_crash=rerun_after_crash,
        handoff=result.handoff,
        audit_events=result.ledger.events,
        audit_seal=seal,
        jobs=result.jobs,
        traces=_trace_evidence(result),
    )


def _invariant_violation(bundle: DyadEvidenceBundleV0) -> str | None:
    """Mechanical post-abort integrity screen for scientific-invariant breaks."""

    if not AuditLedger.verify_events(list(bundle.audit_events), bundle.audit_seal).valid:
        return "audit chain or seal failed verification"
    models = {call.get("model") for trace in bundle.traces for call in trace.native_calls}
    if len(models) > 1:
        return f"multiple provider models observed: {sorted(models)}"
    for role, lineage_field in (("X", "lineage_x"), ("Y", "lineage_y")):
        expected = getattr(bundle.handoff, lineage_field)
        ids = {event.lifecycle_id for event in bundle.audit_events if event.actor == role}
        if ids - {expected}:
            return f"{role} lifecycle drift"
    groups: dict[tuple, set[str]] = {}
    for event in bundle.audit_events:
        if getattr(event.status, "value", event.status) == "completed":
            groups.setdefault(
                (event.job_index, event.phase, event.round), set()
            ).add(event.pre_state_hash)
    if any(len(hashes) != 1 for hashes in groups.values()):
        return "paired pre-state mismatch"
    return None


def _write_freeze_record(directory: Path, manifest, tests: dict) -> Path:
    record = {
        "schema_version": "constraint-forge/cohort-freeze-record/v0",
        "written_utc": utc_now(),
        "statement": (
            "Scientific execution has not started yet: this record was produced "
            "before the first cohort model call."
        ),
        "freeze_commit": manifest.freeze_commit,
        "manifest_hash": manifest.manifest_hash,
        "protocol_version": manifest.protocol_version,
        "seed_prefix": manifest.seed_prefix,
        "num_dyads": manifest.num_dyads,
        "sequences": [
            {
                "dyad_index": row.dyad_index,
                "sequence_id": row.sequence_id,
                "plan_hash": row.plan_hash,
            }
            for row in manifest.sequences
        ],
        "provider_config": manifest.provider_config.model_dump(mode="json"),
        "qualification_canary_sha256": manifest.qualification_canary_sha256,
        "test_results": tests,
        "stop_rule": manifest.stop_rule,
    }
    payload = stable_hash(record)
    path = directory / "freeze_record.json"
    write_atomic(path, json.dumps({**record, "record_hash": payload}, indent=2, sort_keys=True).encode("utf-8"))
    return path


def _run_tests_now() -> dict:
    root = Path(__file__).resolve().parent.parent
    results = {}
    for name, target in (
        ("behavioral_runner", "."),
        ("formation", "../constraint_forge_formation_v0"),
    ):
        proc = subprocess.run(
            ["uv", "run", "pytest", "-q", target],
            capture_output=True,
            text=True,
            cwd=root,
        )
        tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        results[name] = {"returncode": proc.returncode, "summary": tail}
    return results


async def _run(args) -> int:
    if args.freeze_only and args.live:
        raise SystemExit("--freeze-only must not be combined with --live")
    if not args.freeze_only and not args.live:
        raise SystemExit("refusing to make model calls without explicit --live")

    secrets: list[str] = []
    for name in (args.x_key_var, args.y_key_var):
        value = os.environ.get(name)
        if not value:
            raise SystemExit(f"required credential environment variable is unset: {name}")
        secrets.append(value)

    tasks = build_cohort_tasks()
    assert [task.data.idx for task in tasks] == list(range(COHORT_NUM_DYADS))
    manifest = build_manifest(
        cohort_id=args.cohort_id,
        freeze_commit=_freeze_commit(),
        provider_config=_provider_config(args),
        qualification_canary_sha256=QUALIFICATION_CANARY_SHA256,
        tasks=tasks,
    )
    directory = Path(args.output_dir) / args.cohort_id
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"

    resume_crashed = set(args.resume_crashed or ())
    rows = {}
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text())
        if existing["manifest_hash"] != manifest.manifest_hash:
            raise SystemExit("existing cohort manifest does not match this frozen plan")
        for row in existing["dyads"]:
            rows[row["dyad_index"]] = row
    else:
        tests = _run_tests_now() if args.run_tests else {}
        if args.run_tests and any(t["returncode"] != 0 for t in tests.values()):
            raise SystemExit(f"freezing refused: tests failed: {tests}")
        record_path = _write_freeze_record(directory, manifest, tests)
        print(json.dumps({"freeze_record": str(record_path), "manifest_hash": manifest.manifest_hash}))
        write_atomic(manifest_path, json.dumps(_manifest_payload(manifest, rows), indent=2, sort_keys=True).encode())

    if args.freeze_only:
        print(json.dumps({"status": "frozen", "directory": str(directory)}))
        return 0

    # Freeze gate: scientific calls require a pre-existing freeze record for
    # exactly this manifest hash; the launcher never creates one mid-flight.
    record_path = directory / "freeze_record.json"
    if not record_path.exists():
        raise SystemExit(
            "freeze gate: no freeze record found; run --freeze-only before any "
            "scientific model call"
        )
    record = json.loads(record_path.read_text())
    if record.get("manifest_hash") != manifest.manifest_hash:
        raise SystemExit(
            "freeze gate: freeze record does not match this frozen plan hash"
        )

    consecutive_infra_aborts = 0
    for task in tasks:
        dyad_index = task.data.idx
        artifact_path = directory / f"dyad-{dyad_index:02d}.json"
        marker_path = directory / f"dyad-{dyad_index:02d}.started"
        rerun_after_crash = False
        if artifact_path.exists():
            continue
        if marker_path.exists():
            if dyad_index not in resume_crashed:
                raise SystemExit(
                    f"dyad {dyad_index} has a started marker but no evidence; "
                    "pass --resume-crashed explicitly to re-instantiate it after "
                    "a hard crash (the rerun is recorded)"
                )
            rerun_after_crash = True
        started_utc = utc_now()
        marker_path.write_text(started_utc)

        operational = _operational_task(task)
        actor_x = vf.Agent(_agent_config(args.x_key_var))
        actor_y = vf.Agent(_agent_config(args.y_key_var))
        result = await run_behavioral_sequence(
            operational.data,
            actor_x=actor_x,
            actor_y=actor_y,
            task=operational,
        )
        bundle = _bundle_from_result(
            result,
            cohort_id=args.cohort_id,
            dyad_index=dyad_index,
            sequence_id=task.data.sequence_id,
            plan_hash=task.data.plan_hash,
            freeze_commit=manifest.freeze_commit,
            started_utc=started_utc,
            rerun_after_crash=rerun_after_crash,
        )
        payload = bundle.serialization_bytes
        if any(secret.encode("utf-8") in payload for secret in secrets):
            raise RuntimeError("credential bytes unexpectedly appeared in dyad evidence")
        write_atomic(artifact_path, payload)
        marker_path.unlink()

        row = dyad_summary_row(bundle=bundle, evidence_path=artifact_path)
        rows[dyad_index] = row.model_dump(mode="json")
        write_atomic(
            manifest_path,
            json.dumps(_manifest_payload(manifest, rows), indent=2, sort_keys=True).encode(),
        )
        print(json.dumps(json.loads(row.model_dump(mode="json")), sort_keys=True))

        if row.status == DyadStatus.ABORTED:
            violation = _invariant_violation(bundle)
            if violation is not None:
                print(json.dumps({"halted": f"scientific invariant violated at dyad {dyad_index}: {violation}"}))
                return 3
            consecutive_infra_aborts += 1
            if consecutive_infra_aborts >= CONSECUTIVE_INFRA_ABORT_STOP:
                print(json.dumps({"stopped_cleanly": f"{consecutive_infra_aborts} consecutive infrastructure aborts"}))
                return 2
        else:
            consecutive_infra_aborts = 0

    executed = sum(1 for row in rows.values() if row["status"] != DyadStatus.NOT_STARTED.value)
    print(json.dumps({"cohort_complete": True, "executed_dyads": executed}))
    return 0


def _manifest_payload(manifest, rows: dict) -> dict:
    ordered = [rows[index] for index in sorted(rows)]
    return {**manifest.model_dump(mode="json"), "dyads": ordered}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the frozen 12-dyad Constraint Forge formation cohort."
    )
    parser.add_argument("--live", action="store_true", help="required live-inference gate")
    parser.add_argument(
        "--freeze-only",
        action="store_true",
        help="materialize the freeze record and manifest without model calls",
    )
    parser.add_argument("--cohort-id", default="constraint-forge-formation-cohort-ox-v0")
    parser.add_argument("--output-dir", default="cohort_artifacts")
    parser.add_argument("--x-key-var", default=DEFAULT_X_KEY_VAR)
    parser.add_argument("--y-key-var", default=DEFAULT_Y_KEY_VAR)
    parser.add_argument("--resume-crashed", type=int, action="append")
    parser.add_argument(
        "--no-run-tests",
        dest="run_tests",
        action="store_false",
        help="skip the pytest gate when writing the freeze record",
    )
    parser.set_defaults(run_tests=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
