"""Focused no-network checks for the live-canary launcher configuration."""

from __future__ import annotations

from types import SimpleNamespace

from verifiers.v1.clients.eval import join_url
from verifiers.v1.dialects.chat import ChatDialect
from verifiers.v1.types import SamplingConfig
from verifiers.v1.utils.compile import resolve_runtime_config

from constraint_forge_behavioral_runner_v0.evidence import TraceEvidenceV0
from constraint_forge_behavioral_runner_v0.live_canary import (
    CANARY_SEED_PREFIX,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    MAX_CALLS_PER_ROLE,
    MAX_COMPLETION_TOKENS,
    OX_ALPHA_MODEL,
    ZEN_BASE_URL,
    ZEN_X_KEY_VAR,
    ZEN_Y_KEY_VAR,
    _agent_config,
    _build_task,
    _native_call_summary,
    _provider_failures,
)
from constraint_forge_behavioral_runner_v0.taskset import (
    ConstraintForgeBehavioralTaskset,
    ConstraintForgeBehavioralTasksetConfig,
)


def test_live_canary_uses_dedicated_throwaway_seeds() -> None:
    canary = _build_task()
    scientific_config = ConstraintForgeBehavioralTasksetConfig(id="scientific-default")
    scientific = next(iter(ConstraintForgeBehavioralTaskset(scientific_config)))

    assert CANARY_SEED_PREFIX != scientific_config.seed_prefix
    assert canary.data.job_seeds[:2] != scientific.data.job_seeds[:2]
    assert [job.category for job in canary.data.run_plan.jobs[:2]] == [
        "ordinary",
        "ordinary",
    ]
    assert canary.data.network_allow == ["*"]
    assert canary.data.network_block == []


def test_gemini_canary_agent_config_is_local_zero_retry_and_key_indirected() -> None:
    task = _build_task()
    x = _agent_config(
        model=DEFAULT_MODEL,
        base_url=DEFAULT_BASE_URL,
        api_key_var="GEMINI_API_KEY",
    )
    y = _agent_config(
        model=DEFAULT_MODEL,
        base_url=DEFAULT_BASE_URL,
        api_key_var="GEMINI_API_KEY_2",
    )

    assert x.model == y.model == "gemini-3.7-flash"
    assert x.client is not None and y.client is not None
    assert x.client.base_url == y.client.base_url == DEFAULT_BASE_URL
    assert x.client.api_key_var == "GEMINI_API_KEY"
    assert y.client.api_key_var == "GEMINI_API_KEY_2"
    assert x.runtime.type == y.runtime.type == "subprocess"
    assert resolve_runtime_config(x.runtime, task).type == "subprocess"
    assert resolve_runtime_config(y.runtime, task).type == "subprocess"
    assert x.max_turns == y.max_turns == MAX_CALLS_PER_ROLE == 19
    assert x.retries.max_retries == y.retries.max_retries == 0
    assert x.sampling is not None and y.sampling is not None
    assert x.sampling.max_tokens == y.sampling.max_tokens == MAX_COMPLETION_TOKENS
    assert x.sampling.temperature is None and y.sampling.temperature is None
    assert x.sampling.top_p is None and y.sampling.top_p is None


def test_live_canary_persists_human_readable_native_provider_error() -> None:
    error = SimpleNamespace(
        model_dump=lambda **_: {
            "type": "ProviderError",
            "message": "429 RESOURCE_EXHAUSTED",
            "status_code": 429,
            "traceback": "do not persist this",
        }
    )
    call = SimpleNamespace(
        finish_reason=None,
        error=error,
        model="gemini-3.7-flash",
        endpoint="/chat/completions",
    )
    summary = _native_call_summary(0, call)

    assert summary == {
        "native_call_index": 0,
        "model": "gemini-3.7-flash",
        "endpoint": "/chat/completions",
        "finish_reason": None,
        "error": {
            "type": "ProviderError",
            "message": "429 RESOURCE_EXHAUSTED",
            "status_code": 429,
        },
    }

    trace = TraceEvidenceV0(
        role="X",
        lifecycle_id="x-life",
        trace_id="x-trace",
        agent_config={},
        native_calls=(summary,),
    )
    bundle = SimpleNamespace(traces=(trace,))
    assert _provider_failures(bundle) == [{"role": "X", **summary}]


def test_zen_ox_alpha_config_targets_native_chat_completions_with_bearer_keys() -> None:
    """The Zen boundary is the native OpenAI-compatible endpoint, not a proxy."""

    x = _agent_config(
        model=OX_ALPHA_MODEL,
        base_url=ZEN_BASE_URL,
        api_key_var=ZEN_X_KEY_VAR,
    )
    y = _agent_config(
        model=OX_ALPHA_MODEL,
        base_url=ZEN_BASE_URL,
        api_key_var=ZEN_Y_KEY_VAR,
    )

    assert x.model == y.model == OX_ALPHA_MODEL == "x-preview-f-free"
    assert x.client is not None and y.client is not None
    assert x.client.base_url == y.client.base_url == ZEN_BASE_URL
    assert ZEN_X_KEY_VAR != ZEN_Y_KEY_VAR
    dialect = ChatDialect()
    assert join_url(ZEN_BASE_URL, dialect.upstream_path) == (
        "https://opencode.ai/zen/v1/chat/completions"
    )
    assert dialect.auth_headers("zen-key") == {"Authorization": "Bearer zen-key"}
    # Same zero-retry, bounded, non-streaming posture as the Gemini canary.
    assert x.retries.max_retries == y.retries.max_retries == 0
    assert x.max_turns == y.max_turns == MAX_CALLS_PER_ROLE
    assert x.sampling.max_tokens == y.sampling.max_tokens == MAX_COMPLETION_TOKENS
    assert x.sampling.reasoning_effort is None and y.sampling.reasoning_effort is None

    # The Zen canary raises only the completion budget and pins an explicit
    # reasoning effort (the provider's silent default currently produces
    # long-form reasoning the free endpoint cannot serve reliably); prompts,
    # rules, and retry budgets are unchanged, and both roles share one config.
    zx = _agent_config(
        model=OX_ALPHA_MODEL,
        base_url=ZEN_BASE_URL,
        api_key_var=ZEN_X_KEY_VAR,
        max_completion_tokens=16384,
        reasoning_effort="low",
    )
    zy = _agent_config(
        model=OX_ALPHA_MODEL,
        base_url=ZEN_BASE_URL,
        api_key_var=ZEN_Y_KEY_VAR,
        max_completion_tokens=16384,
        reasoning_effort="low",
    )
    assert zx.sampling.max_tokens == zy.sampling.max_tokens == 16384
    assert zx.retries.max_retries == zy.retries.max_retries == 0
    assert zx.sampling.reasoning_effort == zy.sampling.reasoning_effort == "low"


def test_zen_reasoning_effort_is_an_explicit_sampling_override_only() -> None:
    """Ox Alpha exposes effort levels low/high/max via `reasoning_effort`.

    The chat dialect overlays sampling fields onto the outbound body, so
    `reasoning_effort: "max"` reaches Zen as a top-level request field while an
    unset knob stays absent from the wire request entirely.
    """

    dialect = ChatDialect()
    default_body = dialect.apply_overrides(
        {"model": "ignored", "messages": []},
        OX_ALPHA_MODEL,
        SamplingConfig(max_tokens=MAX_COMPLETION_TOKENS),
    )
    assert "reasoning_effort" not in default_body
    assert default_body["model"] == OX_ALPHA_MODEL
    assert default_body["max_tokens"] == MAX_COMPLETION_TOKENS

    max_reasoning = dialect.apply_overrides(
        {"model": "ignored", "messages": []},
        OX_ALPHA_MODEL,
        SamplingConfig(max_tokens=MAX_COMPLETION_TOKENS, reasoning_effort="max"),
    )
    assert max_reasoning["reasoning_effort"] == "max"
