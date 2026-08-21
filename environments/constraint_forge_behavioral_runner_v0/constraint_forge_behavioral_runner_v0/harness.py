"""Minimal text-only v1 harness binding.

The actual provider transport remains Verifiers' interception contract. This
specialization keeps the built-in null harness's configuration surface, but
uses a local one-request program with MCP, streaming, and SDK retries disabled;
its explicit ``HarnessSession`` owns the per-job visible-context reset.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import json
from typing import Iterator

from constraint_forge_formation_v0.canonical import stable_hash
from verifiers.v1.clients import ModelContext
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


# This is intentionally the smallest possible one-request text program. It uses
# the native interception endpoint supplied by v1, but disables the OpenAI SDK's
# automatic retries: the runner's closed failure taxonomy owns retry decisions so
# a transport retry can never silently create another behavioral sample.
TEXT_PROGRAM_SOURCE = f'''# /// script
# requires-python = ">=3.11"
# dependencies = ["openai"]
# ///
"""One plain, non-streaming intercepted chat completion."""

import argparse
import asyncio
import json

from openai import AsyncOpenAI


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--messages-json", required=True)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    client = AsyncOpenAI(
        base_url=args.base_url,
        api_key=args.api_key,
        timeout={CALL_TIMEOUT_SECONDS:.1f},
        max_retries=0,
    )
    await client.chat.completions.create(
        model=args.model,
        messages=json.loads(args.messages_json),
        stream=False,
    )


if __name__ == "__main__":
    asyncio.run(main())
'''


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
    id: str = "constraint-forge-behavioral-runner-v0"


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
        }
        self.trace.info.setdefault("constraint_forge_provider_requests", []).append(
            request_receipt
        )

        assistant_count = len(self.trace.assistant_messages)
        call_count = len(self.trace.calls)
        result = await self.harness.launch(
            self.ctx,
            self.trace,
            self.runtime,
            self.endpoint,
            self.secret,
            self.mcp_urls,
            data,
        )
        if result.exit_code != 0:
            return result

        new_calls = self.trace.calls[call_count:]
        if len(new_calls) != 1:
            raise ValueError(
                "Constraint Forge expected exactly one native model call per harness segment"
            )
        call = new_calls[0]
        finish_reason = getattr(call.finish_reason, "value", call.finish_reason)
        request_receipt["native_call_index"] = call_count
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
        messages = self._wire_messages(data)
        env = {**self.config.resolved_env}
        args = [
            f"--base-url={endpoint}",
            f"--api-key={secret}",
            f"--model={ctx.model}",
            "--messages-json=" + json.dumps(messages, separators=(",", ":")),
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
]
