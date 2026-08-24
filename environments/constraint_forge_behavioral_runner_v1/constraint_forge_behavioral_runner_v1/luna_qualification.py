"""Throwaway full-dyad Luna qualification over the local openai-oauth proxy.

Runs ONE complete 24-job dyad on a dedicated throwaway seed prefix — never on
the scientific manifest — through the already-qualified Verifiers
chat-completions boundary against the local openai-oauth proxy. Persists
per-call evidence including token usage so call counts, elapsed time, failure
modes, retry consumption, and approximate provider quota cost are all
reconstructable afterwards.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess  # noqa: S404 - only reads the local git revision
import time
from pathlib import Path

import verifiers.v1 as vf
from verifiers.v1.configs.agent import AgentConfig
from verifiers.v1.configs.client import EvalClientConfig
from verifiers.v1.configs.retries import RetryConfig
from verifiers.v1.runtimes.subprocess import SubprocessConfig
from verifiers.v1.types import SamplingConfig

from .cohort import (
    COHORT_MAX_TURNS_PER_ROLE,
    DyadEvidenceBundleV0,
    dyad_summary_row,
    utc_now,
    write_atomic,
)
from .harness import ConstraintForgeTextHarnessConfig, configure_text_harness_boundary
from .live_canary import _trace_evidence
from .runner import run_behavioral_sequence
from .taskset import (
    ConstraintForgeBehavioralTask,
    ConstraintForgeBehavioralTaskset,
    ConstraintForgeBehavioralTasksetConfig,
)

QUALIFICATION_SEED_PREFIX = "constraint-forge/luna-qualification-v0"
LUNA_BASE_URL = "http://127.0.0.1:10531/v1"
LUNA_MODEL = "gpt-5.6-luna"
LUNA_MAX_COMPLETION_TOKENS = 16384
LUNA_CALL_TIMEOUT_SECONDS = 300
LUNA_INFRA_RETRIES = 2
LUNA_INFRA_BACKOFF_SECONDS = (4, 8)
DEFAULT_KEY_VAR = "LUNA_PROXY_API_KEY"


def _declare_boundary() -> None:
    configure_text_harness_boundary(
        call_timeout_seconds=LUNA_CALL_TIMEOUT_SECONDS,
        infra_retries=LUNA_INFRA_RETRIES,
        infra_backoff_seconds=tuple(float(s) for s in LUNA_INFRA_BACKOFF_SECONDS),
    )


def _build_task() -> ConstraintForgeBehavioralTask:
    taskset = ConstraintForgeBehavioralTaskset(
        ConstraintForgeBehavioralTasksetConfig(
            id="constraint-forge-luna-qualification-v0",
            seed_prefix=QUALIFICATION_SEED_PREFIX,
            num_sequences=1,
        )
    )
    base = next(iter(taskset))
    data = base.data.model_copy(update={"network_allow": ["*"], "network_block": []})
    return ConstraintForgeBehavioralTask(data, base.config)


def _agent_config(reasoning_effort: str) -> AgentConfig:
    return AgentConfig(
        model=LUNA_MODEL,
        client=EvalClientConfig(base_url=LUNA_BASE_URL, api_key_var=DEFAULT_KEY_VAR),
        harness=ConstraintForgeTextHarnessConfig(),
        runtime=SubprocessConfig(),
        sampling=SamplingConfig(
            max_tokens=LUNA_MAX_COMPLETION_TOKENS,
            reasoning_effort=reasoning_effort,
        ),
        max_turns=COHORT_MAX_TURNS_PER_ROLE,
        retries=RetryConfig(max_retries=0),
    )


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def _token_totals(bundle: DyadEvidenceBundleV0) -> dict:
    totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "reasoning_tokens": 0,
        "calls_with_usage": 0,
    }
    for trace in bundle.traces:
        for call in trace.native_calls:
            usage = call.get("usage") or {}
            if not usage:
                continue
            totals["calls_with_usage"] += 1
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                value = usage.get(key)
                if isinstance(value, int):
                    totals[key] += value
            details = usage.get("completion_tokens_details") or {}
            reasoning = details.get("reasoning_tokens")
            if isinstance(reasoning, int):
                totals["reasoning_tokens"] += reasoning
    return totals


async def _run(args) -> int:
    _declare_boundary()
    directory = Path(args.output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    task = _build_task()
    actor_x = vf.Agent(_agent_config(args.reasoning_effort))
    actor_y = vf.Agent(_agent_config(args.reasoning_effort))

    started_utc = utc_now()
    started_monotonic = time.monotonic()
    result = await run_behavioral_sequence(
        task.data, actor_x=actor_x, actor_y=actor_y, task=task
    )
    elapsed_seconds = round(time.monotonic() - started_monotonic, 1)
    finished_utc = utc_now()

    seal = result.ledger.seal_record
    if seal is None:
        raise RuntimeError("qualification dyad returned without a sealed ledger")
    bundle = DyadEvidenceBundleV0(
        cohort_id=f"luna-qualification-{args.reasoning_effort}",
        dyad_index=0,
        sequence_id=task.data.sequence_id,
        plan_hash=task.data.plan_hash,
        freeze_commit=_git_head(),
        started_utc=started_utc,
        finished_utc=finished_utc,
        handoff=result.handoff,
        audit_events=result.ledger.events,
        audit_seal=seal,
        jobs=result.jobs,
        traces=_trace_evidence(result),
    )
    artifact = directory / f"dyad-luna-{args.reasoning_effort}.json"
    write_atomic(artifact, bundle.serialization_bytes)

    row = dyad_summary_row(bundle=bundle, evidence_path=artifact)
    summary = {
        "model": LUNA_MODEL,
        "base_url": LUNA_BASE_URL,
        "endpoint": "/chat/completions",
        "proxy": "openai-oauth@2.0.0",
        "reasoning_effort": args.reasoning_effort,
        "max_completion_tokens": LUNA_MAX_COMPLETION_TOKENS,
        "boundary": {
            "call_timeout_seconds": LUNA_CALL_TIMEOUT_SECONDS,
            "infra_retries": LUNA_INFRA_RETRIES,
            "infra_backoff_seconds": list(LUNA_INFRA_BACKOFF_SECONDS),
        },
        "seed_prefix": QUALIFICATION_SEED_PREFIX,
        "scientific": False,
        "elapsed_seconds": elapsed_seconds,
        "started_utc": started_utc,
        "finished_utc": finished_utc,
        "summary_row": row.model_dump(mode="json"),
        "token_usage": _token_totals(bundle),
        "evidence_path": str(artifact),
        "evidence_sha256": bundle.content_hash,
        "freeze_commit": _git_head(),
        "plan_hash": task.data.plan_hash,
    }
    write_atomic(
        directory / f"summary-luna-{args.reasoning_effort}.json",
        json.dumps(summary, indent=2, sort_keys=True).encode("utf-8"),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if row.status.value == "completed" else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one throwaway full-dyad Luna qualification."
    )
    parser.add_argument("--reasoning-effort", choices=["low", "medium"], default="low")
    parser.add_argument("--output-dir", default="qual_artifacts")
    return parser


def main() -> None:
    args = _parser().parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
