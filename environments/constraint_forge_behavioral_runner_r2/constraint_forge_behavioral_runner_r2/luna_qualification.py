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

from ._r2_world._config import CONFIG, configure

QUALIFICATION_SEED_PREFIX = "constraint-forge/r2-qualification-v0"
LUNA_BASE_URL = "http://127.0.0.1:10531/v1"
LUNA_MODEL = "gpt-5.6-luna"
LUNA_MAX_COMPLETION_TOKENS = 16384
LUNA_CALL_TIMEOUT_SECONDS = 300
LUNA_INFRA_RETRIES = 2
LUNA_INFRA_BACKOFF_SECONDS = (4, 8)
DEFAULT_KEY_VAR = "LUNA_PROXY_API_KEY"


def _runtime():
    """Import runner-side modules lazily so configure() lands first."""

    from .cohort import (
        COHORT_MAX_TURNS_PER_ROLE,
        DyadEvidenceBundleV0,
        dyad_summary_row,
        utc_now,
        write_atomic,
    )
    from .harness import ConstraintForgeTextHarnessConfig
    from .live_canary import _trace_evidence
    from .runner import run_behavioral_sequence
    from .taskset import (
        ConstraintForgeBehavioralTask,
        ConstraintForgeBehavioralTaskset,
        ConstraintForgeBehavioralTasksetConfig,
    )

    return {
        "COHORT_MAX_TURNS_PER_ROLE": COHORT_MAX_TURNS_PER_ROLE,
        "DyadEvidenceBundleV0": DyadEvidenceBundleV0,
        "dyad_summary_row": dyad_summary_row,
        "utc_now": utc_now,
        "write_atomic": write_atomic,
        "ConstraintForgeTextHarnessConfig": ConstraintForgeTextHarnessConfig,
        "_trace_evidence": _trace_evidence,
        "run_behavioral_sequence": run_behavioral_sequence,
        "ConstraintForgeBehavioralTask": ConstraintForgeBehavioralTask,
        "ConstraintForgeBehavioralTaskset": ConstraintForgeBehavioralTaskset,
        "ConstraintForgeBehavioralTasksetConfig": ConstraintForgeBehavioralTasksetConfig,
    }


def _declare_boundary(rt=None) -> None:
    from .harness import configure_text_harness_boundary

    rt = rt or _runtime()

    configure_text_harness_boundary(
        call_timeout_seconds=LUNA_CALL_TIMEOUT_SECONDS,
        infra_retries=LUNA_INFRA_RETRIES,
        infra_backoff_seconds=tuple(float(s) for s in LUNA_INFRA_BACKOFF_SECONDS),
    )


def _build_task(rt=None):
    rt = rt or _runtime()
    taskset = rt["ConstraintForgeBehavioralTaskset"](
        rt["ConstraintForgeBehavioralTasksetConfig"](
            id="constraint-forge-luna-qualification-v0",
            seed_prefix=ARGS.get("seed_prefix", QUALIFICATION_SEED_PREFIX),
            num_sequences=1,
        )
    )
    base = next(iter(taskset))
    data = base.data.model_copy(update={"network_allow": ["*"], "network_block": []})
    return rt["ConstraintForgeBehavioralTask"](data, base.config)


def _agent_config(reasoning_effort: str, rt=None) -> AgentConfig:
    rt = rt or _runtime()
    return AgentConfig(
        model=LUNA_MODEL,
        client=EvalClientConfig(base_url=LUNA_BASE_URL, api_key_var=DEFAULT_KEY_VAR),
        harness=rt["ConstraintForgeTextHarnessConfig"](),
        runtime=SubprocessConfig(),
        sampling=SamplingConfig(
            max_tokens=LUNA_MAX_COMPLETION_TOKENS,
            reasoning_effort=reasoning_effort,
        ),
        max_turns=rt["COHORT_MAX_TURNS_PER_ROLE"],
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
    configure(
        mutation_budget=args.mutation_budget,
        write_budget=args.write_budget,
        max_rounds=args.max_rounds,
    )
    rt = _runtime()
    _declare_boundary(rt)
    directory = Path(args.output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    task = _build_task(rt)
    actor_x = vf.Agent(_agent_config(args.reasoning_effort, rt))
    actor_y = vf.Agent(_agent_config(args.reasoning_effort, rt))

    started_utc = rt["utc_now"]()
    started_monotonic = time.monotonic()
    result = await rt["run_behavioral_sequence"](
        task.data, actor_x=actor_x, actor_y=actor_y, task=task
    )
    elapsed_seconds = round(time.monotonic() - started_monotonic, 1)
    finished_utc = rt["utc_now"]()

    seal = result.ledger.seal_record
    if seal is None:
        raise RuntimeError("qualification dyad returned without a sealed ledger")
    bundle = rt["DyadEvidenceBundleV0"](
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
        traces=rt["_trace_evidence"](result),
    )
    artifact = directory / f"dyad-luna-{args.reasoning_effort}.json"
    rt["write_atomic"](artifact, bundle.serialization_bytes)

    row = rt["dyad_summary_row"](bundle=bundle, evidence_path=artifact)
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
        "seed_prefix": ARGS.get("seed_prefix", QUALIFICATION_SEED_PREFIX),
        "difficulty": dict(CONFIG),
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
    rt["write_atomic"](
        directory / f"summary-luna-{args.reasoning_effort}.json",
        json.dumps(summary, indent=2, sort_keys=True).encode("utf-8"),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if row.status.value == "completed" else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one throwaway full-dyad Luna qualification."
    )
    parser.add_argument("--seed-prefix", default=QUALIFICATION_SEED_PREFIX)
    parser.add_argument("--reasoning-effort", choices=["low", "medium"], default="low")
    parser.add_argument("--cohort-id-suffix", default="v1-qualification",
                        help="qualifier identity; never a scientific cohort")
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--output-dir", default="qual_artifacts")
    parser.add_argument("--mutation-budget", type=int, default=6,
                        help="per-station layer mutation budget (default 6)")
    parser.add_argument("--write-budget", type=int, default=3,
                        help="per-station register write budget (default 3)")
    parser.add_argument("--max-rounds", type=int, default=16,
                        help="round cap per job (default 16)")
    return parser


ARGS: dict = {}


def main() -> None:
    args = _parser().parse_args()
    global ARGS
    ARGS = vars(args)
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
