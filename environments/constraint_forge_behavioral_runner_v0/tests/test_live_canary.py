"""Focused no-network checks for the live-canary launcher configuration."""

from __future__ import annotations

from constraint_forge_behavioral_runner_v0.live_canary import (
    CANARY_SEED_PREFIX,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    MAX_CALLS_PER_ROLE,
    MAX_COMPLETION_TOKENS,
    _agent_config,
    _build_task,
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


def test_gemini_canary_agent_config_is_local_zero_retry_and_key_indirected() -> None:
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
    assert x.max_turns == y.max_turns == MAX_CALLS_PER_ROLE == 19
    assert x.retries.max_retries == y.retries.max_retries == 0
    assert x.sampling is not None and y.sampling is not None
    assert x.sampling.max_tokens == y.sampling.max_tokens == MAX_COMPLETION_TOKENS
    assert x.sampling.temperature is None and y.sampling.temperature is None
    assert x.sampling.top_p is None and y.sampling.top_p is None
