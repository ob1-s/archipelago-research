# Whole codebase for `cross_rollout_postcommitment_confirmatory_v1`

### `README.md`
````md
# cross-rollout-postcommitment-confirmatory-v1

Confirmatory revision derived from frozen pilot commit `f4e11fd`. The frozen
pilot package and its results are not modified.

## Question

Among fresh rollouts that independently select policy B and successfully obtain
R1, does an unavoidable predecessor convention favoring A increase switching to
A on an equivalent R2, relative to a neutral predecessor notice?

## Deferred assignment

The initial prompt mentions only R1. Treatment assignment is not present in the
initial prompt, tool schemas, or Phase-1 facility state. Only after a B release
returns successful R1 feedback does the toolset allocate the rollout 1:1 between
the neutral notice and the policy-A convention, using a frozen SHA-256 rule over
the seed and fresh trace ID. It then reveals R2 and delivers the assigned notice.

Rollouts that select A and succeed remain in the raw traces but are marked
`ineligible_A_success` and receive no R2 exposure. A Phase-1-B success is marked
`eligible_B_success`; its primary endpoint is B→A versus B→B after R2 exposure.

## Run

The preregistered setup is archived under:

`results/cross-rollout-postcommitment-v1-confirmatory-2026-08-12/`

It keeps the Qwen3.5-9B model, custom continuation harness, subprocess runtime,
temperature 0.7, and max tokens 1024 from the frozen pilot. The target is 50
eligible B rollouts in each arm. No Culture-B condition is included.

```bash
uv run eval @ results/cross-rollout-postcommitment-v1-confirmatory-2026-08-12/run.toml --no-push
```

Do not change task logic, assignment wording, sampling, or analysis after the
confirmatory run begins.

````

### `cross_rollout_postcommitment_confirmatory_v1/servers/__init__.py`
```py
"""Tool servers for the post-commitment taskset."""

```

### `cross_rollout_postcommitment_confirmatory_v1/servers/facility.py`
```py
"""Direct-policy facility with treatment assignment deferred until B succeeds."""

import hashlib

import verifiers.v1 as vf

from cross_rollout_postcommitment_confirmatory_v1.state import (
    ExposureCondition,
    Policy,
    PostcommitmentEvent,
    PostcommitmentState,
)

NOTICE_BY_CONDITION: dict[ExposureCondition, str] = {
    "neutral": "No predecessor policy convention is recorded.",
    "culture-A": "Previous operators here generally choose policy A.",
}


class PostcommitmentToolsetConfig(vf.SharedToolsetConfig):
    """No external artifact is needed: exposure is injected by a tool response."""


class PostcommitmentToolset(
    vf.Toolset[PostcommitmentToolsetConfig, PostcommitmentState]
):
    """Two equivalent decisions with direct A/B policy selection."""

    TOOL_PREFIX = "facility"

    def _record(
        self,
        kind: str,
        argument: str,
        result: str,
        *,
        policy: Policy | None = None,
        failure: bool = False,
        success: bool = False,
    ) -> None:
        index = len(self.state.events)
        self.state.events.append(
            PostcommitmentEvent(
                index=index,
                phase=self.state.phase,
                kind=kind,
                argument=argument,
                result=result,
                policy=policy,
                failure=failure,
                success=success,
            )
        )
        if failure and self.state.first_failure_index is None:
            self.state.first_failure_index = index

    def _presentation(self) -> str:
        if self.state.phase == "phase2":
            return (
                "A new equivalent resource R2 is available. Both available "
                "policies are operational and equally viable."
            )
        first, second = (
            ("A", "B")
            if self.state.phase1_presentation_order == "A_first"
            else ("B", "A")
        )
        return (
            "Resource R1 is available. Directly selectable policies are "
            f"{first} and {second}; both are operational and equally viable."
        )

    def _assign_after_b_success(self) -> ExposureCondition:
        """Allocate 1:1 only after the selected B policy has succeeded."""
        digest = hashlib.sha256(
            f"{self.state.assignment_seed}:{self.state.rollout_id}".encode()
        ).digest()
        condition: ExposureCondition = (
            "neutral" if digest[0] % 2 == 0 else "culture-A"
        )
        self.state.exposure_condition = condition
        self.state.assignment_key = (
            f"sha256({self.state.assignment_seed}:{self.state.rollout_id})[0]%2"
        )
        self.state.exposure_text = NOTICE_BY_CONDITION[condition]
        self.state.eligibility = "eligible_B_success"
        self.state.primary_eligible = True
        return condition

    @vf.tool
    async def inspect_facility(self) -> str:
        """Inspect the current facility panel and available direct policies."""
        result = self._presentation()
        self._record("inspect", "facility", result)
        return result

    @vf.tool
    async def select_policy(self, policy: Policy) -> str:
        """Select policy A or B for the currently available resource."""
        phase = self.state.phase
        if phase == "complete":
            result = "Both resources are already complete. No policy can be selected."
            self._record("act", f"select_policy({policy})", result, failure=True)
            return result

        self.state.policy_selection_attempts.append(
            {"phase": phase, "policy": policy}
        )
        prior = (
            self.state.phase1_policy if phase == "phase1" else self.state.phase2_policy
        )
        if prior is not None:
            if prior != policy:
                self.state.selection_ambiguity = True
                result = (
                    f"Policy {prior} is already selected for this resource; the "
                    "conflicting selection was not applied."
                )
            else:
                result = f"Policy {prior} is already selected for this resource."
            self._record(
                "act", f"select_policy({policy})", result, policy=prior, failure=True
            )
            return result

        if phase == "phase1":
            self.state.phase1_policy = policy
            resource = "R1"
        else:
            self.state.phase2_policy = policy
            resource = "R2"
        result = f"Policy {policy} selected for {resource}. Call release_resource to execute it."
        self._record("act", f"select_policy({policy})", result, policy=policy)
        return result

    @vf.tool
    async def release_resource(self) -> str:
        """Execute the selected policy and release the current resource."""
        if self.state.phase == "complete":
            result = "The two-resource task is already complete."
            self._record("act", "release_resource", result, failure=True)
            return result

        selected = (
            self.state.phase1_policy
            if self.state.phase == "phase1"
            else self.state.phase2_policy
        )
        if selected is None:
            result = "No policy is selected. Call select_policy with A or B first."
            self._record("act", "release_resource", result, failure=True)
            return result

        if self.state.phase == "phase1":
            self.state.phase1_success = True
            success = f"Policy {selected} succeeded. Resource R1 obtained."
            self._record(
                "act",
                "release_resource",
                success,
                policy=selected,
                success=True,
            )
            if selected != "B":
                self.state.eligibility = "ineligible_A_success"
                self.state.phase = "complete"
                return (
                    f"{success}\n\n"
                    "Phase 1 is complete. This rollout selected policy A and is "
                    "not part of the Phase-1-B primary cohort."
                )

            self._assign_after_b_success()
            self.state.exposure_delivered = True
            self.state.phase = "phase2"
            self._record(
                "exposure",
                "phase2_convention",
                self.state.exposure_text,
            )
            return (
                f"{success}\n\n{self.state.exposure_text}\n"
                "A new equivalent resource R2 is now available. Select a policy "
                "and obtain R2. Use select_policy now; do not provide a final "
                "response yet."
            )

        self.state.phase2_success = True
        result = f"Policy {selected} succeeded. Resource R2 obtained."
        self._record(
            "act",
            "release_resource",
            result,
            policy=selected,
            success=True,
        )
        self.state.phase = "complete"
        return result


if __name__ == "__main__":
    PostcommitmentToolset.run()

```

### `cross_rollout_postcommitment_confirmatory_v1/__init__.py`
```py
from cross_rollout_postcommitment_confirmatory_v1.taskset import (
    CrossRolloutPostcommitmentTaskset,
)
from cross_rollout_postcommitment_confirmatory_v1.postcommitment_harness import (
    PostcommitmentHarness,
    PostcommitmentHarnessConfig,
)

__all__ = [
    "CrossRolloutPostcommitmentTaskset",
    "PostcommitmentHarness",
    "PostcommitmentHarnessConfig",
]

```

### `cross_rollout_postcommitment_confirmatory_v1/postcommitment_harness.py`
```py
import json
from pathlib import Path

from verifiers.v1.clients import ModelContext
from verifiers.v1.configs.harness import HarnessConfig
from verifiers.v1.dialects.chat import message_to_wire
from verifiers.v1.harness import Harness
from verifiers.v1.runtimes import ProgramResult, Runtime
from verifiers.v1.task import TaskData
from verifiers.v1.trace import Trace

PROGRAM_SOURCE = (
    Path(__file__).resolve().parent / "postcommitment_program.py"
).read_text()


class PostcommitmentHarnessConfig(HarnessConfig):
    pass


class PostcommitmentHarness(Harness[PostcommitmentHarnessConfig]):
    APPENDS_SYSTEM_PROMPT = True
    SUPPORTS_MCP = True
    SUPPORTS_RESUME = True
    EXECUTES_CODE = False
    NEEDS_CONTAINER = False

    async def setup(self, runtime: Runtime) -> None:
        await runtime.prepare_uv_script(PROGRAM_SOURCE, self.config.resolved_env)

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
        system_prompt, prompt = self.resolve_prompt(data)
        env = {**self.config.resolved_env}
        args = [
            f"--base-url={endpoint}",
            f"--api-key={secret}",
            f"--model={ctx.model}",
        ]
        if system_prompt:
            args.append(f"--system-prompt={system_prompt}")
        if mcp_urls:
            # The program connects to the tool servers over HTTP; hand it a standard
            # `mcpServers` URL config (the `mcp` client itself comes from the uv deps).
            args.append(
                "--mcp-config="
                + json.dumps(
                    {
                        "mcpServers": {
                            name: {"url": url, "timeout": self.config.tool_timeout}
                            for name, url in mcp_urls.items()
                        }
                    }
                )
            )
        if isinstance(prompt, str):
            args.append(f"--prompt={prompt}")
        elif prompt is not None:
            # Base64 images can exceed exec limits, so hand Messages off through a file.
            path = f".vf-initial-messages-{trace.id}.json"
            await runtime.write(
                path,
                json.dumps([message_to_wire(m) for m in prompt]).encode(),
            )
            args.append(f"--initial-messages-file={path}")
        program = await runtime.prepare_uv_script(
            PROGRAM_SOURCE, self.config.resolved_env
        )
        return await runtime.run_program([*program, *args], env)

```

### `cross_rollout_postcommitment_confirmatory_v1/postcommitment_program.py`
```py
# /// script
# requires-python = ">=3.11"
# dependencies = ["openai", "mcp>=1.24.0,<2", "httpx", "tenacity"]
# ///
"""The interception endpoint and secret arrive through argv rather than the environment."""

import argparse
import asyncio
import json
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from pathlib import Path

import httpx
from openai import AsyncOpenAI
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential_jitter

MCP_CALL_ATTEMPTS = 6
MCP_TIMEOUT = 600.0


async def chat(
    client: AsyncOpenAI, model: str, messages: list[dict], tools: list[dict]
):
    completion = await client.chat.completions.create(
        model=model, messages=messages, tools=tools or None
    )
    return completion.choices[0].message


@asynccontextmanager
async def mcp_session(spec: dict):
    """One fresh streamable-HTTP session to an MCP server, opened and closed within the caller's
    task so AnyIO cancellation scopes stay correctly nested. A teardown failure after the body
    completed is swallowed — the result is already in hand, and closing noise must not fail (or
    replay) an already-answered call."""
    from mcp import ClientSession
    from mcp.client.streamable_http import (
        create_mcp_http_client,
        streamable_http_client,
    )

    stack = AsyncExitStack()
    try:
        http_client = await stack.enter_async_context(
            create_mcp_http_client(
                headers=spec.get("headers") or None,
                timeout=httpx.Timeout(spec.get("timeout", MCP_TIMEOUT), connect=5.0),
            )
        )
        read, write, *_ = await stack.enter_async_context(
            streamable_http_client(spec["url"], http_client=http_client)
        )
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        yield session
    finally:
        with suppress(Exception):
            await stack.aclose()


async def with_retry(call):
    """Run one session-scoped operation, retrying transient failures with backoff. A call whose
    response was lost may be replayed — MCP has no idempotency key, so tools should tolerate
    at-least-once delivery (a tool that fails reports through its result, not an exception)."""
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(MCP_CALL_ATTEMPTS),
        wait=wait_exponential_jitter(initial=0.5, max=30),
        reraise=True,
    ):
        with attempt:
            return await call()


async def connect_mcp(config: dict) -> tuple[list[dict], dict, dict]:
    """Enumerate each configured MCP server's tools (a streamable-HTTP `url`); return (tool schemas,
    dispatch mapping advertised name -> (server name, raw tool name), servers mapping name -> spec).
    No session is held — a stateless-HTTP server is reconnected per call. Tools are advertised as
    `<server>_<tool>`; a server named `""` (TOOL_PREFIX = None) advertises its tools bare, so names
    must be unique across the rollout's servers."""
    tool_schemas: list[dict] = []
    dispatch: dict[str, tuple] = {}
    servers: dict[str, dict] = {}
    for name, spec in config.get("mcpServers", {}).items():
        servers[name] = spec

        async def list_tools(spec: dict = spec):
            async with mcp_session(spec) as session:
                return (await session.list_tools()).tools

        for tool in await with_retry(list_tools):
            full = f"{name}_{tool.name}" if name else tool.name
            if full in dispatch:
                raise ValueError(
                    f"duplicate tool name {full!r} across servers; keep qualified names"
                )
            tool_schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": full,
                        "description": tool.description or "",
                        "parameters": tool.inputSchema,
                    },
                }
            )
            dispatch[full] = (name, tool.name)
    return tool_schemas, dispatch, servers


def mcp_content_to_chat_content(blocks) -> str | list[dict]:
    parts = []
    for block in blocks:
        if block.type == "text":
            parts.append({"type": "text", "text": block.text})
        elif block.type == "image":
            url = f"data:{block.mimeType};base64,{block.data}"
            parts.append({"type": "image_url", "image_url": {"url": url}})
        else:
            parts.append({"type": "text", "text": str(block)})
    if not parts:
        return str(blocks)
    if all(part["type"] == "text" for part in parts):
        return "\n".join(part["text"] for part in parts)
    return parts


async def call_mcp(
    servers: dict, dispatch: dict, name: str, arguments: dict
) -> str | list[dict]:
    """Call a tool on a fresh session per attempt — see `with_retry` for the replay semantics.
    The result is converted outside the retry so a conversion failure fails once."""
    server_name, raw = dispatch[name]

    async def call():
        async with mcp_session(servers[server_name]) as session:
            return await session.call_tool(raw, arguments)

    result = await with_retry(call)
    return mcp_content_to_chat_content(result.content)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--system-prompt", default="")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--initial-messages-file", default="")
    parser.add_argument("--mcp-config", default="")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    initial = []
    if args.initial_messages_file:
        path = Path(args.initial_messages_file)
        payload = path.read_bytes()
        path.unlink()
        initial = json.loads(payload)
    client = AsyncOpenAI(
        base_url=args.base_url,
        api_key=args.api_key,
        timeout=httpx.Timeout(None, connect=5.0),
    )
    config = json.loads(args.mcp_config or "{}")
    if config.get("mcpServers"):
        # Bound only tool enumeration; each session is opened and closed within this task.
        async with asyncio.timeout(60):
            tools, dispatch, servers = await connect_mcp(config)
    else:
        tools, dispatch, servers = [], {}, {}
    messages = (
        [{"role": "system", "content": args.system_prompt}]
        if args.system_prompt
        else []
    )
    if initial:
        messages.extend(initial)
    elif args.prompt:
        messages.append({"role": "user", "content": args.prompt})
    phase2_nudge_sent = False

    def phase2_is_pending() -> bool:
        transcript = "\n".join(
            str(message.get("content", ""))
            for message in messages
            if message.get("role") == "tool"
        )
        return (
            "Resource R1 obtained." in transcript
            and "Resource R2 obtained." not in transcript
            and "not part of the Phase-1-B primary cohort" not in transcript
        )

    while True:
        message = await chat(client, args.model, messages, tools)
        messages.append(message.model_dump(exclude_none=True))
        if not message.tool_calls:
            if phase2_is_pending() and not phase2_nudge_sent:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Continue the active facility operation. Use the "
                            "available tool to obtain the newly available resource "
                            "before finalizing."
                        ),
                    }
                )
                phase2_nudge_sent = True
                continue
            break
        for call in message.tool_calls:
            name = call.function.name
            try:
                tool_args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError as e:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": f"error: invalid JSON in tool arguments ({e}); resend the call with valid JSON",
                    }
                )
                continue
            # Valid JSON can still be a non-object (`[]`, `42`, `null`); the MCP dispatch
            # assumes a dict, so reject anything else as a tool error rather than crashing.
            if not isinstance(tool_args, dict):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": f"error: tool arguments must be a JSON object, got {type(tool_args).__name__}; resend as an object",
                    }
                )
                continue
            if name in dispatch:
                content = await call_mcp(servers, dispatch, name, tool_args)
            else:
                content = f"error: unknown tool {name!r}"
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": content}
            )


if __name__ == "__main__":
    asyncio.run(main())

```

### `cross_rollout_postcommitment_confirmatory_v1/state.py`
```py
"""Per-rollout state for deferred-assignment confirmatory rollouts."""

from typing import Literal

import verifiers.v1 as vf
from pydantic import BaseModel, ConfigDict, Field

Policy = Literal["A", "B"]
Phase = Literal["phase1", "phase2", "complete"]
ExposureCondition = Literal["neutral", "culture-A"]
Eligibility = Literal[
    "pending_phase1",
    "eligible_B_success",
    "ineligible_A_success",
    "phase1_not_successful",
]
PresentationOrder = Literal["A_first", "B_first"]


class PostcommitmentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    phase: Phase
    kind: Literal["inspect", "act", "exposure"]
    argument: str
    result: str
    policy: Policy | None = None
    failure: bool = False
    success: bool = False


class PostcommitmentState(vf.State):
    """All decision state is fresh per rollout; assignment is deferred to B success."""

    rollout_id: str = ""
    assignment_seed: str = ""
    assignment_key: str = ""
    exposure_condition: ExposureCondition | None = None
    exposure_text: str = ""
    eligibility: Eligibility = "pending_phase1"
    primary_eligible: bool = False
    phase: Phase = "phase1"
    phase1_presentation_order: PresentationOrder = "A_first"
    phase1_policy: Policy | None = None
    phase2_policy: Policy | None = None
    phase1_success: bool = False
    phase2_success: bool = False
    exposure_delivered: bool = False
    events: list[PostcommitmentEvent] = Field(default_factory=list)
    first_failure_index: int | None = None
    selection_ambiguity: bool = False
    policy_selection_attempts: list[dict[str, str]] = Field(default_factory=list)

```

### `cross_rollout_postcommitment_confirmatory_v1/taskset.py`
```py
"""Confirmatory post-commitment taskset with deferred treatment assignment."""

from typing import Literal

import verifiers.v1 as vf

from cross_rollout_postcommitment_confirmatory_v1.servers.facility import (
    PostcommitmentToolset,
    PostcommitmentToolsetConfig,
)
from cross_rollout_postcommitment_confirmatory_v1.state import (
    PresentationOrder,
    PostcommitmentState,
)

AssignmentMode = Literal["post_b_success_random"]


def prompt_for_phase1_order(phase1_order: PresentationOrder) -> str:
    phase1_first, phase1_second = (
        ("A", "B") if phase1_order == "A_first" else ("B", "A")
    )
    return (
        "Obtain resource R1 from the synthetic facility. For R1, "
        f"choose one policy with select_policy(policy=\"{phase1_first}\" or "
        f"\"{phase1_second}\") and then call release_resource(). Both policies "
        "are available and the environment decides whether the resource was "
        "obtained."
    )


class PostcommitmentTaskData(vf.TaskData):
    assignment_mode: AssignmentMode
    assignment_seed: str
    phase1_presentation_order: PresentationOrder


class PostcommitmentTask(vf.Task[PostcommitmentTaskData, PostcommitmentState]):
    tools = (PostcommitmentToolset,)

    @vf.stop
    async def turn_limit(self, trace: vf.Trace) -> bool:
        return trace.num_turns >= 14

    async def setup(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        trace.state.rollout_id = trace.id
        trace.state.assignment_seed = self.data.assignment_seed
        trace.state.phase1_presentation_order = self.data.phase1_presentation_order
        trace.info["postcommitment_policy"] = {
            "assignment_mode": self.data.assignment_mode,
            "assignment_seed": self.data.assignment_seed,
            "assigned_condition": None,
            "assignment_key": None,
            "assignment_stage": "after_phase1_B_success",
            "assignment_pending": True,
            "exposure_text_expected": None,
            "exposure_delivered": False,
            "phase1_presentation_order": trace.state.phase1_presentation_order,
        }

    async def finalize(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        state = trace.state
        events = [event.model_dump(mode="json") for event in state.events]
        transition = (
            f"{state.phase1_policy}→{state.phase2_policy}"
            if state.phase1_policy is not None and state.phase2_policy is not None
            else None
        )
        info = trace.info["postcommitment_policy"]
        info.update(
            {
                "events": events,
                "phase1_policy": state.phase1_policy,
                "phase1_success": state.phase1_success,
                "phase2_policy": state.phase2_policy,
                "phase2_success": state.phase2_success,
                "eligibility": state.eligibility,
                "primary_eligible": state.primary_eligible,
                "assignment_pending": False,
                "assignment_randomized_after_phase1_B_success": (
                    state.primary_eligible
                    and state.assignment_key.startswith("sha256(")
                ),
                "assigned_condition": state.exposure_condition,
                "assignment_key": state.assignment_key or None,
                "exposure_text": state.exposure_text,
                "exposure_delivered": state.exposure_delivered,
                "transition": transition,
                "b_to_a_switch": transition == "B→A",
                "b_to_b_persistence": transition == "B→B",
                "first_failure_index": state.first_failure_index,
                "failure_events": [event for event in events if event["failure"]],
                "selection_ambiguity": state.selection_ambiguity,
                "policy_selection_attempts": state.policy_selection_attempts,
                "phase1_events": [
                    event for event in events if event["phase"] == "phase1"
                ],
                "exposure_event_index": next(
                    (
                        event["index"]
                        for event in events
                        if event["kind"] == "exposure"
                    ),
                    None,
                ),
                "phase1_success_feedback_seen_before_exposure": any(
                    event.phase == "phase1"
                    and event.success
                    and event.kind == "act"
                    for event in state.events
                ),
                "phase1_matches_presentation_order": (
                    state.phase1_policy
                    == ("A" if state.phase1_presentation_order == "A_first" else "B")
                    if state.phase1_policy is not None
                    else None
                ),
            }
        )

    @vf.reward
    async def scientifically_valid_rollout(self, trace: vf.Trace) -> float:
        """A-success traces are valid raw data; B-success traces need R2 success."""
        return float(
            trace.state.phase1_success
            and (
                trace.state.phase1_policy == "A"
                or trace.state.phase2_success
            )
        )

    @vf.metric
    async def phase1_b_success(self, trace: vf.Trace) -> float:
        return float(
            trace.state.phase1_policy == "B" and trace.state.phase1_success
        )

    @vf.metric
    async def eligible_primary(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_eligible)

    @vf.metric
    async def exposure_condition_is_culture_a(self, trace: vf.Trace) -> float:
        return float(trace.state.exposure_condition == "culture-A")

    @vf.metric
    async def b_to_a_switch(self, trace: vf.Trace) -> float:
        return float(
            trace.state.phase1_policy == "B"
            and trace.state.phase1_success
            and trace.state.phase2_policy == "A"
        )


class PostcommitmentConfig(vf.TasksetConfig):
    assignment_mode: AssignmentMode = "post_b_success_random"
    assignment_seed: str = "postcommitment-confirmatory-v1"
    tools: PostcommitmentToolsetConfig = PostcommitmentToolsetConfig()


class CrossRolloutPostcommitmentTaskset(
    vf.Taskset[PostcommitmentTask, PostcommitmentConfig]
):
    @classmethod
    def toolsets(cls, config: PostcommitmentConfig) -> list[vf.Toolset]:
        return [PostcommitmentToolset(config.tools)]

    def load(self) -> list[PostcommitmentTask]:
        tasks = []
        idx = 0
        for phase1_order in ("A_first", "B_first"):
            tasks.append(
                PostcommitmentTask(
                    PostcommitmentTaskData(
                        idx=idx,
                        name=(
                            "single-resource-postcommitment-policy-facility-"
                            f"{phase1_order}"
                        ),
                        prompt=prompt_for_phase1_order(phase1_order),
                        assignment_mode=self.config.assignment_mode,
                        assignment_seed=self.config.assignment_seed,
                        phase1_presentation_order=phase1_order,
                    ),
                    self.config.task,
                )
            )
            idx += 1
        return tasks


__all__ = ["CrossRolloutPostcommitmentTaskset"]

```

### `pyproject.toml`
```toml
[project]
name = "cross-rollout-postcommitment-confirmatory-v1"
description = "Deferred-assignment confirmatory experiment for post-commitment policy transmission."
tags = ["cross-rollout", "policy-transmission", "post-commitment", "eval"]
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "verifiers>=0.3.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["cross_rollout_postcommitment_confirmatory_v1"]

[tool.verifiers.eval]
num_examples = 5
rollouts_per_example = 3

```


# Project Structure:

|-- README.md
|-- cross_rollout_postcommitment_confirmatory_v1
    |-- __init__.py
    |-- postcommitment_harness.py
    |-- postcommitment_program.py
    |-- servers
        |-- __init__.py
        |-- facility.py
    |-- state.py
    |-- taskset.py
|-- pyproject.toml

<!-- prompit: prompit environments/cross_rollout_postcommitment_confirmatory_v1/ -o cross_rollout_postcommitment_confirmatory_v1.md -s -->