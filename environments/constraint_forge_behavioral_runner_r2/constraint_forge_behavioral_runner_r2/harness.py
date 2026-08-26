"""Minimal text-only v1 harness binding.

The actual provider transport remains Verifiers' interception contract. This
specialization keeps the built-in null harness's configuration surface, but
uses a local one-request program with MCP, streaming, and SDK retries disabled;
its explicit ``HarnessSession`` owns the per-job visible-context reset.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import asyncio
import json
import time
from uuid import uuid4
from typing import Iterator

from constraint_forge_behavioral_runner_r2._r2_world.canonical import stable_hash
from verifiers.v1.clients import ModelContext

from .failures import RETRYABLE_INFRA_STATUSES, native_error_status
from verifiers.v1.dialects.chat import message_to_wire
from verifiers.v1.harness import HarnessSession
from verifiers.v1.harnesses.null import NullHarness, NullHarnessConfig
from verifiers.v1.runtimes import ProgramResult, Runtime
from verifiers.v1.task import TaskData
from verifiers.v1.trace import Trace
from verifiers.v1.types import AssistantMessage, Messages


# One finite timeout owns both the embedded SDK client and the runner boundary.
# Provider-side retries remain disabled; a timeout is still abort-only.
CALL_TIMEOUT_SECONDS = 120.0

TEXT_PROGRAM_TEMPLATE = '''# /// script
# requires-python = ">=3.11"
# dependencies = ["openai"]
# ///
"""One plain, non-streaming intercepted chat completion."""

import argparse
import asyncio
import json
from pathlib import Path

from openai import AsyncOpenAI


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--messages-file", required=True)
    parser.add_argument("--timeout", type=float, default={timeout:.1f})
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    client = AsyncOpenAI(
        base_url=args.base_url,
        api_key=args.api_key,
        timeout=args.timeout,
        max_retries=0,
    )
    await client.chat.completions.create(
        model=args.model,
        messages=json.loads(Path(args.messages_file).read_text(encoding="utf-8")),
        stream=False,
    )


if __name__ == "__main__":
    asyncio.run(main())
'''

def text_program_source(timeout_seconds: float = CALL_TIMEOUT_SECONDS) -> str:
    return TEXT_PROGRAM_TEMPLATE.format(timeout=timeout_seconds)


TEXT_PROGRAM_SOURCE = text_program_source()


# This is an out-of-band referee control. It is set in the runner's task
# context before the paired turn is dispatched and is never encoded in a user
# message, system prompt, trace message, or provider request.
_CURRENT_CONTEXT_EPOCH: ContextVar[int | None] = ContextVar(
    "constraint_forge_context_epoch", default=None
)


@contextmanager
def context_epoch_scope(epoch: int) -> Iterator[None]:
    token = _CURRENT_CONTEXT_EPOCH.set(epoch)
    try:
        yield
    finally:
        _CURRENT_CONTEXT_EPOCH.reset(token)


class ConstraintForgeTextHarnessConfig(NullHarnessConfig):
    id: str = "constraint-forge-behavioral-runner-r2"


# Operational boundary knobs for the text harness. They intentionally do NOT
# ride the pydantic config schema: verifiers reconstructs pinned harness configs
# through its plugin registry, so unknown declared fields break config
# validation. Launchers declare them once per process before any agent runs;
# the values are persisted in each launcher's freeze record / provider config.
_TEXT_HARNESS_BOUNDARY: dict[str, float | int | tuple[float, ...]] = {}


def configure_text_harness_boundary(
    *,
    call_timeout_seconds: float | None = None,
    infra_retries: int | None = None,
    infra_backoff_seconds: tuple[float, ...] | None = None,
) -> None:
    """Declare process-local boundary knobs (v0 semantics when unset)."""

    if call_timeout_seconds is not None:
        _TEXT_HARNESS_BOUNDARY["call_timeout_seconds"] = float(call_timeout_seconds)
    if infra_retries is not None:
        _TEXT_HARNESS_BOUNDARY["infra_retries"] = int(infra_retries)
    if infra_backoff_seconds is not None:
        _TEXT_HARNESS_BOUNDARY["infra_backoff_seconds"] = tuple(
            float(s) for s in infra_backoff_seconds
        )


def text_harness_boundary() -> tuple[float, int, tuple[float, ...]]:
    """The (timeout, infra_retries, backoff) triple currently in force."""

    return (
        float(_TEXT_HARNESS_BOUNDARY.get("call_timeout_seconds", CALL_TIMEOUT_SECONDS)),
        int(_TEXT_HARNESS_BOUNDARY.get("infra_retries", 0)),
        tuple(
            float(s)
            for s in _TEXT_HARNESS_BOUNDARY.get("infra_backoff_seconds", (4.0, 8.0))
        ),
    )


class ConstraintForgeTextHarnessSession(HarnessSession):
    """One sequence-scoped handle with an explicit model-visible job reset.

    v1's Trace is intentionally append-only, so the referee cannot erase its
    audit history. This session keeps a separate prompt history for the current
    job and replaces it at the runner's out-of-band job boundary. The provider
    therefore sees ordinary within-job continuity and no previous-job messages,
    while the same native HarnessSession remains open for all jobs.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._context_epoch: int | None = None
        self._visible_messages: Messages = []

    async def _run(self, messages: Messages | None) -> ProgramResult:
        if messages is None:
            raise ValueError("Constraint Forge interactions require an explicit request")
        epoch = _CURRENT_CONTEXT_EPOCH.get()
        if epoch is None:
            raise ValueError("Constraint Forge context reset was not supplied out of band")
        if self._context_epoch != epoch:
            self._context_epoch = epoch
            self._visible_messages = []

        candidate = [*self._visible_messages, *messages]
        data = self.data.model_copy(update={"prompt": candidate})
        wire_request = self.harness.provider_visible_request(self.ctx, data)
        request_receipt = {
            "request_hash": stable_hash(wire_request),
            "request": wire_request,
            "context_epoch": epoch,
            "native_call_index": None,
            "finish_reason": None,
            "completed": False,
            "attempts": [],
        }
        self.trace.info.setdefault("constraint_forge_provider_requests", []).append(
            request_receipt
        )

        assistant_count = len(self.trace.assistant_messages)
        call_count = len(self.trace.calls)
        result = await self._launch_with_infra_retries(
            ctx=self.ctx,
            runtime=self.runtime,
            endpoint=self.endpoint,
            secret=self.secret,
            data=data,
            request_receipt=request_receipt,
            call_count=call_count,
        )
        if result.exit_code != 0:
            return result

        new_calls = self.trace.calls[call_count:]
        if not new_calls:
            raise ValueError(
                "Constraint Forge segment produced no native provider call"
            )
        for earlier in new_calls[:-1]:
            finish_reason = getattr(earlier.finish_reason, "value", earlier.finish_reason)
            error_status = native_error_status(earlier)
            if finish_reason is not None or error_status is None:
                raise ValueError(
                    "intermediate behavioral attempt was not an infrastructure failure"
                )
        call = new_calls[-1]
        finish_reason = getattr(call.finish_reason, "value", call.finish_reason)
        request_receipt["native_call_index"] = call_count + len(new_calls) - 1
        request_receipt["finish_reason"] = finish_reason
        request_receipt["completed"] = call.error is None and finish_reason == "stop"
        if call.error is not None:
            raise ValueError("provider call completed with a native call error")
        if finish_reason != "stop":
            raise ValueError(
                f"provider completion was not final ordinary stop: {finish_reason!r}"
            )

        assistants = self.trace.assistant_messages
        if len(assistants) != assistant_count + 1:
            raise ValueError("provider segment did not produce exactly one assistant message")
        last = assistants[-1]
        if not isinstance(last, AssistantMessage):
            raise ValueError("provider response was not an assistant message")
        if last.tool_calls:
            raise ValueError(
                "provider returned tool calls; Constraint Forge only accepts ordinary assistant text"
            )
        # The native Trace retains reasoning/provider fields for audit. Copy only
        # visible content into the next turn; never replay reasoning, tool calls,
        # or provider continuation state.
        self._visible_messages = [
            *candidate,
            AssistantMessage(content=last.content or ""),
        ]
        return result

    async def _launch_with_infra_retries(
        self,
        *,
        ctx,
        runtime: Runtime,
        endpoint: str,
        secret: str,
        data: TaskData,
        request_receipt: dict,
        call_count: int,
    ) -> ProgramResult:
        """Launch the identical wire request until it delivers or budget ends.

        Re-launches happen inside the still-open harness session, so the v1
        interaction is never re-entered after a failed exchange. Every attempt
        lands as its own native call and receipt entry.
        """

        program = await runtime.prepare_uv_script(
            text_program_source(text_harness_boundary()[0]),
            self.harness.config.resolved_env,
        )
        messages_file = await self.harness._write_messages_file(runtime, data)
        args = [
            f"--base-url={endpoint}",
            f"--api-key={secret}",
            f"--model={ctx.model}",
            f"--timeout={text_harness_boundary()[0]:.1f}",
            f"--messages-file={messages_file}",
        ]
        _, infra_retries, infra_backoff_seconds = text_harness_boundary()
        attempts_allowed = 1 + max(0, infra_retries)
        attempt = 0
        while True:
            started_at = time.monotonic()
            result = await runtime.run_program([*program, *args], self.harness.config.resolved_env)
            duration_seconds = round(time.monotonic() - started_at, 3)
            calls = self.trace.calls[call_count:]
            last_call = calls[-1] if calls else None
            status = native_error_status(last_call) if last_call is not None else None
            finish_reason = (
                getattr(last_call.finish_reason, "value", last_call.finish_reason)
                if last_call is not None
                else None
            )
            stderr_tail = " ".join(
                (result.stderr or "").split()
            )[-400:]
            request_receipt["attempts"].append(
                {
                    "attempt": attempt,
                    "native_call_index": call_count + len(calls) - 1 if calls else None,
                    "exit_code": result.exit_code,
                    "finish_reason": finish_reason,
                    "error_status": status,
                    "duration_seconds": duration_seconds,
                    "stderr_tail": stderr_tail,
                }
            )
            retryable = (
                result.exit_code != 0
                and last_call is not None
                and finish_reason is None
                and status in RETRYABLE_INFRA_STATUSES
            )
            attempt += 1
            if not retryable or attempt >= attempts_allowed:
                return result
            backoff = infra_backoff_seconds[
                min(attempt - 1, len(infra_backoff_seconds) - 1)
            ]
            if backoff > 0:
                await asyncio.sleep(backoff)


class ConstraintForgeTextHarness(NullHarness):
    APPENDS_SYSTEM_PROMPT = True
    SUPPORTS_MCP = False
    SUPPORTS_RESUME = True
    EXECUTES_CODE = False
    NEEDS_CONTAINER = False

    async def setup(self, runtime: Runtime) -> None:
        await runtime.prepare_uv_script(TEXT_PROGRAM_SOURCE, self.config.resolved_env)

    async def session(
        self,
        ctx: ModelContext,
        trace: Trace,
        runtime: Runtime,
        endpoint: str,
        secret: str,
        mcp_urls: dict[str, str],
        data: TaskData,
    ) -> HarnessSession:
        if mcp_urls:
            raise ValueError("Constraint Forge behavioral text harness forbids MCP")
        return ConstraintForgeTextHarnessSession(
            self, ctx, trace, runtime, endpoint, secret, mcp_urls, data
        )

    def _wire_messages(self, data: TaskData) -> list[dict]:
        system_prompt, prompt = self.resolve_prompt(data)
        if prompt is None:
            raise ValueError("Constraint Forge text harness requires a prompt")
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if isinstance(prompt, str):
            messages.append({"role": "user", "content": prompt})
        else:
            messages.extend(message_to_wire(message) for message in prompt)
        return messages

    async def _write_messages_file(self, runtime: Runtime, data: TaskData) -> str:
        """Stage the model-visible request in the runtime workspace.

        Command-line argument lists are capped by the kernel (~128 KiB per
        string), so the conversation rides in a workspace file instead of an
        argv value; long jobs otherwise fail to spawn their interpreter.
        """

        messages = self._wire_messages(data)
        payload = json.dumps(messages, separators=(",", ":")).encode("utf-8")
        name = f"cf-messages-{uuid4().hex}.json"
        await runtime.write(name, payload)
        return name

    def provider_visible_request(self, ctx: ModelContext, data: TaskData) -> dict:
        """Canonical audit representation of the complete model-visible request."""

        sampling = getattr(ctx, "sampling", None)
        if hasattr(sampling, "model_dump"):
            sampling = sampling.model_dump(mode="json", exclude_none=False)
        return {
            "endpoint_path": "/chat/completions",
            "model": ctx.model,
            "sampling": sampling,
            "stream": False,
            "messages": self._wire_messages(data),
        }

    async def launch(
        self,
        ctx: ModelContext,
        trace: Trace,
        runtime: Runtime,
        endpoint: str,
        secret: str,
        mcp_urls: dict[str, str],
        data: TaskData,
    ) -> ProgramResult:
        if mcp_urls:
            raise ValueError("Constraint Forge behavioral text harness forbids MCP")
        messages_path = self._write_messages_file(runtime, data)
        env = {**self.config.resolved_env}
        args = [
            f"--base-url={endpoint}",
            f"--api-key={secret}",
            f"--model={ctx.model}",
            f"--messages-file={messages_path}",
        ]
        program = await runtime.prepare_uv_script(
            TEXT_PROGRAM_SOURCE, self.config.resolved_env
        )
        return await runtime.run_program([*program, *args], env)


__all__ = [
    "ConstraintForgeTextHarness",
    "ConstraintForgeTextHarnessConfig",
    "ConstraintForgeTextHarnessSession",
    "CALL_TIMEOUT_SECONDS",
    "TEXT_PROGRAM_SOURCE",
    "context_epoch_scope",
    "text_program_source",
    "configure_text_harness_boundary",
    "text_harness_boundary",
]
