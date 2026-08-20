"""Minimal text-only v1 harness binding.

The actual provider transport remains Verifiers' interception contract.  This
specialization deliberately inherits the built-in null text loop, disables MCP,
and makes its rollout handle explicit so a job interaction uses the native
``HarnessSession`` lifecycle without tools, streaming, or provider-managed
continuation state.
"""

from __future__ import annotations

from verifiers.v1.clients import ModelContext
from verifiers.v1.configs.harness import HarnessConfig
from verifiers.v1.harness import Harness, HarnessSession
from verifiers.v1.harnesses.null import NullHarness, NullHarnessConfig
from verifiers.v1.runtimes import ProgramResult, Runtime
from verifiers.v1.task import TaskData
from verifiers.v1.trace import Trace


class ConstraintForgeTextHarnessConfig(NullHarnessConfig):
    id: str = "constraint-forge-behavioral-runner-v0"


class ConstraintForgeTextHarnessSession(HarnessSession):
    """The stock v1 rollout-scoped handle, named for audit/source clarity."""


class ConstraintForgeTextHarness(NullHarness):
    APPENDS_SYSTEM_PROMPT = True
    SUPPORTS_MCP = False
    SUPPORTS_RESUME = True
    EXECUTES_CODE = False
    NEEDS_CONTAINER = False

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
        return await super().launch(ctx, trace, runtime, endpoint, secret, mcp_urls, data)


__all__ = ["ConstraintForgeTextHarness"]
