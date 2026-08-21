"""Explicit live launcher for the non-scientific Constraint Forge V0 canary."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import verifiers.v1 as vf
from verifiers.v1.configs.agent import AgentConfig
from verifiers.v1.configs.client import EvalClientConfig
from verifiers.v1.configs.retries import RetryConfig
from verifiers.v1.runtimes.subprocess import SubprocessConfig
from verifiers.v1.types import SamplingConfig

from constraint_forge_formation_v0.canonical import stable_hash

from .canary import run_throwaway_canary
from .evidence import CanaryEvidenceBundleV0, TraceEvidenceV0
from .harness import ConstraintForgeTextHarnessConfig
from .taskset import (
    ConstraintForgeBehavioralTask,
    ConstraintForgeBehavioralTaskset,
    ConstraintForgeBehavioralTasksetConfig,
)

DEFAULT_MODEL = "gemini-3.7-flash"
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_X_KEY_VAR = "GEMINI_API_KEY"
DEFAULT_Y_KEY_VAR = "GEMINI_API_KEY_2"

# OpenCode Zen / Ox Alpha Free provider boundary. The native Zen API is an
# OpenAI-compatible chat-completions endpoint authenticated with a Bearer Zen
# API key; reasoning arrives out-of-band in `reasoning_content`, so no harness
# change is required beyond these identifiers.
ZEN_BASE_URL = "https://opencode.ai/zen/v1/"
OX_ALPHA_MODEL = "x-preview-f-free"
ZEN_X_KEY_VAR = "OPENCODE_ZEN_API_KEY_X"
ZEN_Y_KEY_VAR = "OPENCODE_ZEN_API_KEY_Y"

CANARY_SEED_PREFIX = "constraint-forge/throwaway-live-canary-v0"
MAX_CALLS_PER_ROLE = 19
MAX_TOTAL_CALLS = 38
MAX_COMPLETION_TOKENS = 4096
# Ox Alpha interleaves extended reasoning before its visible answer; the
# Gemini-tuned 4096 cap is exhausted mid-reasoning (finish_reason=length with
# empty content), so the Zen canary raises only this provider-boundary knob.
ZEN_MAX_COMPLETION_TOKENS = 16384


def _build_task() -> ConstraintForgeBehavioralTask:
    taskset = ConstraintForgeBehavioralTaskset(
        ConstraintForgeBehavioralTasksetConfig(
            id="constraint-forge-throwaway-live-canary-v0",
            seed_prefix=CANARY_SEED_PREFIX,
            num_sequences=1,
        )
    )
    base = next(iter(taskset))
    # The throwaway launcher deliberately uses a local subprocess runtime. The
    # model call itself is made by Verifiers' host-side interception client; the
    # subprocess only talks to that local endpoint and never receives provider
    # credentials. SubprocessConfig cannot enforce TaskData network policies, so
    # relax this operational-only task copy rather than changing the scientific
    # 24-job TaskData or requiring a remote/container runtime for the canary.
    data = base.data.model_copy(update={"network_allow": ["*"], "network_block": []})
    return ConstraintForgeBehavioralTask(data, base.config)


def _agent_config(
    *,
    model: str,
    base_url: str,
    api_key_var: str,
    max_completion_tokens: int = MAX_COMPLETION_TOKENS,
) -> AgentConfig:
    return AgentConfig(
        model=model,
        client=EvalClientConfig(base_url=base_url, api_key_var=api_key_var),
        harness=ConstraintForgeTextHarnessConfig(),
        runtime=SubprocessConfig(),
        sampling=SamplingConfig(max_tokens=max_completion_tokens),
        max_turns=MAX_CALLS_PER_ROLE,
        retries=RetryConfig(max_retries=0),
    )


def _native_call_summary(index: int, call) -> dict:
    finish_reason = getattr(call, "finish_reason", None)
    finish_reason = getattr(finish_reason, "value", finish_reason)
    error = getattr(call, "error", None)
    error_payload = None
    if error is not None:
        if hasattr(error, "model_dump"):
            dumped = error.model_dump(mode="json", exclude_none=True)
            error_payload = {
                key: dumped[key]
                for key in ("type", "message", "status_code")
                if key in dumped
            }
        else:
            error_payload = {
                "type": type(error).__qualname__,
                "message": str(error),
            }
    return {
        "native_call_index": index,
        "model": getattr(call, "model", None),
        "endpoint": getattr(call, "endpoint", None),
        "finish_reason": finish_reason,
        "error": error_payload,
    }


def _trace_evidence(result) -> tuple[TraceEvidenceV0, ...]:
    records: list[TraceEvidenceV0] = []
    lifecycles = {"X": result.handoff.lineage_x, "Y": result.handoff.lineage_y}
    for role, wrapped in zip(("X", "Y"), result.traces, strict=False):
        trace = wrapped.trace
        trace_id = getattr(trace, "id", None)
        if not trace_id:
            continue
        info = getattr(trace, "info", {})
        agent = getattr(trace, "agent", None)
        config = getattr(agent, "config", None)
        config_payload = (
            config.model_dump(mode="json", exclude_none=False)
            if hasattr(config, "model_dump")
            else {"type": type(config).__qualname__ if config is not None else "unknown"}
        )
        native_calls = tuple(
            _native_call_summary(index, call)
            for index, call in enumerate(getattr(trace, "calls", ()))
        )
        records.append(
            TraceEvidenceV0(
                role=role,
                lifecycle_id=lifecycles[role],
                trace_id=trace_id,
                agent_config=config_payload,
                provider_requests=tuple(
                    info.get("constraint_forge_provider_requests", ())
                    if isinstance(info, dict)
                    else ()
                ),
                native_calls=native_calls,
            )
        )
    return tuple(records)


def _build_evidence_bundle(result) -> CanaryEvidenceBundleV0:
    seal = result.ledger.seal_record
    if seal is None:
        raise RuntimeError("canary returned without a sealed audit ledger")
    return CanaryEvidenceBundleV0(
        run_id=result.handoff.run_id,
        dyad_id=result.handoff.dyad_id,
        handoff=result.handoff,
        audit_events=result.ledger.events,
        audit_seal=seal,
        jobs=result.jobs,
        traces=_trace_evidence(result),
    )


def _receipt_checks(bundle: CanaryEvidenceBundleV0) -> tuple[bool, bool, bool]:
    receipts = [receipt for trace in bundle.traces for receipt in trace.provider_requests]
    final = bool(receipts) and all(
        receipt.get("completed") is True and receipt.get("finish_reason") == "stop"
        for receipt in receipts
    )
    integral = bool(receipts) and all(
        receipt.get("request_hash") == stable_hash(receipt.get("request"))
        for receipt in receipts
    )
    fresh_second_context = len(bundle.traces) == 2
    for trace in bundle.traces:
        epoch_one = [
            receipt for receipt in trace.provider_requests if receipt.get("context_epoch") == 1
        ]
        if not epoch_one:
            fresh_second_context = False
            continue
        messages = epoch_one[0].get("request", {}).get("messages", [])
        if [message.get("role") for message in messages] != ["system", "user"]:
            fresh_second_context = False
    return final, integral, fresh_second_context


def _same_prestate_pairs(bundle: CanaryEvidenceBundleV0) -> bool:
    groups: dict[tuple[int, str, int | None], list] = {}
    for event in bundle.audit_events:
        status = getattr(event.status, "value", event.status)
        if status != "completed":
            continue
        groups.setdefault((event.job_index, event.phase, event.round), []).append(event)
    if not groups:
        return False
    for events in groups.values():
        if {event.actor for event in events} != {"X", "Y"}:
            return False
        if len({event.pre_state_hash for event in events}) != 1:
            return False
    return True


def _provider_failures(bundle: CanaryEvidenceBundleV0) -> list[dict]:
    failures: list[dict] = []
    for trace in bundle.traces:
        for call in trace.native_calls:
            if call.get("error") is not None or call.get("finish_reason") != "stop":
                failures.append({"role": trace.role, **call})
    return failures


def _qualification(result, bundle: CanaryEvidenceBundleV0) -> tuple[dict[str, bool], dict]:
    provider_final, request_integral, fresh_second_context = _receipt_checks(bundle)
    no_retry = not any(
        getattr(event.status, "value", event.status) == "safe_retry"
        or ":attempt1" in event.call_id
        for event in bundle.audit_events
    )
    lifecycle_bound = all(
        {event.lifecycle_id for event in bundle.audit_events if event.actor == role}
        == {getattr(result.handoff, f"lineage_{role.lower()}")}
        for role in ("X", "Y")
    )
    rack_crossed_exactly = (
        len(result.jobs) == 2
        and result.jobs[0].rack_x.serialization_bytes == result.jobs[1].rack_x.serialization_bytes
        and result.jobs[0].rack_y.serialization_bytes == result.jobs[1].rack_y.serialization_bytes
    )
    retained_any = bool(
        result.jobs and (result.jobs[0].rack_x.films or result.jobs[0].rack_y.films)
    )
    checks = {
        "clean_completion": (
            result.handoff.aborted is False
            and result.handoff.completed_jobs == 1
            and len(result.jobs) == 2
            and result.jobs[0].complete is True
            and result.jobs[1].complete is False
            and getattr(bundle.audit_seal.status, "value", bundle.audit_seal.status) == "completed"
        ),
        "two_native_lifecycles": len(bundle.traces) == 2 and lifecycle_bound,
        "same_prestate_pairs": _same_prestate_pairs(bundle),
        "provider_completions_final": provider_final,
        "provider_request_hashes_integral": request_integral,
        "fresh_second_job_context": fresh_second_context,
        "no_automatic_retry": no_retry,
        "rack_state_crossed_exactly": rack_crossed_exactly,
        "within_38_call_budget": result.live_model_calls <= MAX_TOTAL_CALLS,
        "scientific_eligible_false": bundle.scientific_eligible is False,
    }
    observations = {
        "first_job_success": bool(
            result.handoff.job_receipts and result.handoff.job_receipts[0].success
        ),
        "retention_observed": retained_any,
        "rack_crossing_inconclusive_without_retention": not retained_any,
        "observed_model_calls": result.live_model_calls,
        "provider_failures": _provider_failures(bundle),
    }
    return checks, observations


def _default_output_path(model: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "-", model)
    return Path("canary_artifacts") / f"constraint-forge-{safe_model}-{stamp}.json"


async def _run(args) -> int:
    if not args.live:
        raise SystemExit("refusing to make model calls without explicit --live")

    secrets: list[str] = []
    for name in (args.x_key_var, args.y_key_var):
        value = os.environ.get(name)
        if not value:
            raise SystemExit(f"required credential environment variable is unset: {name}")
        secrets.append(value)
    shared_credential = secrets[0] == secrets[1]
    if shared_credential and not args.allow_shared_credential:
        raise SystemExit(
            "X and Y credential environment variables resolve to the same value "
            "(pass --allow-shared-credential only for providers where one account "
            "is the intended boundary, e.g. OpenCode Zen)"
        )

    task = _build_task()
    actor_x = vf.Agent(
        _agent_config(
            model=args.model,
            base_url=args.base_url,
            api_key_var=args.x_key_var,
            max_completion_tokens=args.max_completion_tokens,
        )
    )
    actor_y = vf.Agent(
        _agent_config(
            model=args.model,
            base_url=args.base_url,
            api_key_var=args.y_key_var,
            max_completion_tokens=args.max_completion_tokens,
        )
    )

    result = await run_throwaway_canary(
        task.data,
        actor_x=actor_x,
        actor_y=actor_y,
        task=task,
    )
    bundle = _build_evidence_bundle(result)
    payload = bundle.serialization_bytes
    if any(secret.encode("utf-8") in payload for secret in secrets):
        raise RuntimeError("credential bytes unexpectedly appeared in the evidence bundle")

    output = Path(args.output) if args.output else _default_output_path(args.model)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing canary evidence: {output}")
    output.write_bytes(payload)

    checks, observations = _qualification(result, bundle)
    summary = {
        "model": args.model,
        "base_url": args.base_url,
        "x_key_var": args.x_key_var,
        "y_key_var": args.y_key_var,
        "shared_credential": shared_credential,
        "max_completion_tokens": args.max_completion_tokens,
        "seed_prefix": CANARY_SEED_PREFIX,
        "runtime": "subprocess",
        "runtime_task_network_policy": "unrestricted-operational-canary",
        "evidence_path": str(output),
        "evidence_hash": bundle.content_hash,
        "checks": checks,
        "observations": observations,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if all(checks.values()) else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the explicitly non-scientific two-job Constraint Forge live canary."
    )
    parser.add_argument("--live", action="store_true", help="required live-inference gate")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--x-key-var", default=DEFAULT_X_KEY_VAR)
    parser.add_argument("--y-key-var", default=DEFAULT_Y_KEY_VAR)
    parser.add_argument(
        "--allow-shared-credential",
        action="store_true",
        help="permit one shared credential for X and Y (single-account providers)",
    )
    parser.add_argument(
        "--max-completion-tokens",
        type=int,
        default=MAX_COMPLETION_TOKENS,
        help="per-call completion budget (provider-boundary knob; prompts unchanged)",
    )
    parser.add_argument("--output")
    return parser


def main() -> None:
    args = _parser().parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
