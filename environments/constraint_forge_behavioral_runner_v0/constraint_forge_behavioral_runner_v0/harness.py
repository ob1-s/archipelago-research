"""Minimal text-only v1 harness binding.

The actual provider transport remains Verifiers' interception contract. This
specialization keeps the built-in null harness's configuration surface, but
uses a local one-request program with MCP, streaming, and SDK retries disabled;
its explicit ``HarnessSession`` owns the per-job visible-context reset.
"""

from __future__ import annotations

import json

from verifiers.v1.clients import ModelContext
from verifiers.v1.dialects.chat import message_to_wire
from verifiers.v1.harness import HarnessSession
from verifiers.v1.harnesses.null import NullHarness, NullHarnessConfig
from verifiers.v1.runtimes import ProgramResult, Runtime
from verifiers.v1.task import TaskData
from verifiers.v1.trace import Trace
from verifiers.v1.types import Messages


# This is intentionally the smallest possible one-request text program.  It uses
# the native interception endpoint supplied by v1, but disables the OpenAI SDK's
# automatic retries: the runner's closed failure taxonomy owns retry decisions so
# a transport retry can never silently create another behavioral sample.
TEXT_PROGRAM_SOURCE = r'''# /// script
# requires-python = ">=3.11"
# dependencies = ["openai"]
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
        timeout=None,
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


class ConstraintForgeTextHarnessConfig(NullHarnessConfig):
    id: str = "constraint-forge-behavioral-runner-v0"


class ConstraintForgeTextHarnessSession(HarnessSession):
    """One sequence-scoped handle with an explicit model-visible job reset.

    v1's Trace is intentionally append-only, so the referee cannot erase its
    audit history.  This session keeps a separate prompt history for the
    current job and replaces it when the sealed request's context epoch
    changes.  The provider therefore sees ordinary within-job continuity and
    no previous-job messages, while the same native HarnessSession remains
    open for all 24 jobs.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._context_epoch: int | None = None
        self._visible_messages: Messages = []

    @staticmethod
    def _epoch(messages: Messages) -> int:
        for message in reversed(messages):
            if getattr(message, "role", None) != "user":
                continue
            content = getattr(message, "content", None)
            if not isinstance(content, str):
                continue
            payload = json.loads(content)
            if not isinstance(payload, dict) or "context_epoch" not in payload:
                continue
            return int(payload["context_epoch"])
        raise ValueError("Constraint Forge request omitted its context_epoch")

    async def _run(self, messages: Messages | None) -> ProgramResult:
        if messages is None:
            raise ValueError("Constraint Forge interactions require an explicit request")
        epoch = self._epoch(messages)
        if self._context_epoch != epoch:
            self._context_epoch = epoch
            self._visible_messages = []
        candidate = [*self._visible_messages, *messages]
        data = self.data.model_copy(update={"prompt": candidate})
        assistant_count = len(self.trace.assistant_messages)
        result = await self.harness.launch(
            self.ctx,
            self.trace,
            self.runtime,
            self.endpoint,
            self.secret,
            self.mcp_urls,
            data,
        )
        if result.exit_code == 0:
            assistants = self.trace.assistant_messages
            if len(assistants) > assistant_count:
                self._visible_messages = [*candidate, assistants[-1]]
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
        system_prompt, prompt = self.resolve_prompt(data)
        if prompt is None:
            raise ValueError("Constraint Forge text harness requires a prompt")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if isinstance(prompt, str):
            messages.append({"role": "user", "content": prompt})
        else:
            messages.extend(message_to_wire(message) for message in prompt)
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


__all__ = ["ConstraintForgeTextHarness"]
