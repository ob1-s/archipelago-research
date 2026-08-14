"""Model-free factorial, symmetry, and no-R2 contract tests."""

from __future__ import annotations

import inspect
from typing import Literal, get_args, get_origin

import pytest
import verifiers.v1 as vf
from cross_rollout_phase1_label_attractor_diagnostic_v1.constants import (
    LABELS,
    MATCH_ACQUISITION_PROBABILITY,
    MATCH_VERIFICATION_PROBABILITY,
    MISMATCH_ACQUISITION_PROBABILITY,
    MISMATCH_VERIFICATION_PROBABILITY,
    RELEASE_DESCRIPTION,
    SELECT_DESCRIPTION,
    cell_specs,
    expected_schema_enum,
    render_prompt,
)
from cross_rollout_phase1_label_attractor_diagnostic_v1.randomness import (
    RANDOM_NAMESPACES,
    draw_digest,
    hidden_profile,
)
from cross_rollout_phase1_label_attractor_diagnostic_v1.schedule import (
    ROLLOUTS_PER_CELL,
    TOTAL_ROLLOUTS,
    build_schedule,
)
from cross_rollout_phase1_label_attractor_diagnostic_v1.servers.facility import (
    ABASchemaFacility,
    ABBSchemaFacility,
    DiagnosticToolsetConfig,
    KMKSchemaFacility,
    KMMESchemaFacility,
)
from cross_rollout_phase1_label_attractor_diagnostic_v1.state import (
    LabelDiagnosticState,
)
from cross_rollout_phase1_label_attractor_diagnostic_v1.taskset import (
    CrossRolloutPhase1LabelAttractorDiagnosticV1Taskset,
    DiagnosticConfig,
    DiagnosticEnvConfig,
)

FACILITIES = {
    "AB_A": ABASchemaFacility,
    "AB_B": ABBSchemaFacility,
    "KM_K": KMKSchemaFacility,
    "KM_M": KMMESchemaFacility,
}


def toolset_with_state(variant: str, *, profile: str, label_set: str):
    toolset = FACILITIES[variant](DiagnosticToolsetConfig(variant=variant))
    toolset._inert_state = LabelDiagnosticState(
        rollout_id=f"fixture-{variant}-{profile}",
        random_seed="fixture-seed",
        label_set=label_set,
        hidden_profile=profile,
    )
    return toolset


def test_schedule_has_exactly_16_cells_and_10_rows_each() -> None:
    schedule = build_schedule()
    assert len(schedule) == TOTAL_ROLLOUTS == 160
    counts: dict[str, int] = {}
    for cell in schedule:
        counts[cell.key] = counts.get(cell.key, 0) + 1
    assert len(counts) == 16
    assert set(counts.values()) == {ROLLOUTS_PER_CELL}
    assert schedule == build_schedule()


def test_hidden_profile_is_reproducible_and_has_a_fifty_fifty_threshold() -> None:
    outcomes = [hidden_profile("fixture-seed", f"rollout-{i}")[0] for i in range(200)]
    assert set(outcomes) == {"policy_1_fit", "policy_2_fit"}
    assert hidden_profile("fixture-seed", "same") == hidden_profile(
        "fixture-seed", "same"
    )
    value, _ = draw_digest("fixture-seed", "same", "hidden_profile")
    assert (value < 0.5) == (hidden_profile("fixture-seed", "same")[0] == "policy_1_fit")


def test_taskset_materializes_the_frozen_schedule_without_shuffle() -> None:
    tasks = CrossRolloutPhase1LabelAttractorDiagnosticV1Taskset(
        DiagnosticConfig()
    ).load()
    assert len(tasks) == 160
    assert [task.data.schedule_index for task in tasks] == list(range(160))
    assert [task.data.cell_key for task in tasks] == [
        cell.key for cell in build_schedule()
    ]
    assert all(
        task.data.prompt
        == render_prompt(
            task.data.label_set,
            task.data.descriptive_order,
            task.data.instruction_order,
        )
        for task in tasks
    )
    assert {task.config.tools.variant for task in tasks} == {
        "AB_A",
        "AB_B",
        "KM_K",
        "KM_M",
    }


@pytest.mark.asyncio
async def test_setup_initializes_profile_from_task_data_seed() -> None:
    task = CrossRolloutPhase1LabelAttractorDiagnosticV1Taskset(
        DiagnosticConfig()
    ).load()[0]
    trace = vf.Trace(
        task=vf.TraceTask(type=type(task).__name__, data=task.data),
        agent=vf.AgentInfo(config=vf.AgentConfig(model="model-free")),
        state=LabelDiagnosticState(),
    )
    await task.setup(trace, runtime=None)
    assert trace.state.random_seed == task.data.random_seed
    assert trace.state.hidden_profile in {"policy_1_fit", "policy_2_fit"}
    assert trace.info["phase1_label_attractor_diagnostic"]["cell_key"] == (
        task.data.cell_key
    )


def test_prompt_factorial_changes_only_the_declared_label_order() -> None:
    for cell in cell_specs():
        prompt = render_prompt(
            cell.label_set, cell.descriptive_order, cell.instruction_order
        )
        first, second = LABELS[cell.label_set]
        d_first = first if cell.descriptive_order.startswith(first) else second
        d_second = second if d_first == first else first
        i_first = first if cell.instruction_order.startswith(first) else second
        i_second = second if i_first == first else first
        assert f"{d_first}-compatible or {d_second}-compatible" in prompt
        assert f'select_policy(policy="{i_first}" or "{i_second}")' in prompt
        assert "R2" not in prompt
        assert "predecessor" not in prompt.lower()
        assert "culture" not in prompt.lower()
        assert "posterior" not in prompt.lower()
        assert "equally viable" not in prompt.lower()


def test_schema_annotations_and_descriptions_are_exact_and_label_neutral() -> None:
    for variant, facility in FACILITIES.items():
        parameter = inspect.signature(facility.select_policy).parameters["policy"]
        assert get_origin(parameter.annotation) is Literal
        assert list(get_args(parameter.annotation)) == expected_schema_enum(variant)
        assert inspect.getdoc(facility.select_policy) == SELECT_DESCRIPTION
        assert inspect.getdoc(facility.release_resource) == RELEASE_DESCRIPTION
        for description in (SELECT_DESCRIPTION, RELEASE_DESCRIPTION):
            assert not any(label in description for label in ("A", "B", "K", "M"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("variant", "label_set", "policy", "profile"),
    [
        ("AB_A", "AB", "A", "policy_1_fit"),
        ("AB_B", "AB", "B", "policy_2_fit"),
        ("KM_K", "KM", "K", "policy_1_fit"),
        ("KM_M", "KM", "M", "policy_2_fit"),
    ],
)
async def test_one_choice_and_one_release_are_symmetric(
    monkeypatch: pytest.MonkeyPatch,
    variant: str,
    label_set: str,
    policy: str,
    profile: str,
) -> None:
    assert MATCH_ACQUISITION_PROBABILITY == 0.80
    assert MISMATCH_ACQUISITION_PROBABILITY == 0.55
    assert MATCH_VERIFICATION_PROBABILITY == 0.80
    assert MISMATCH_VERIFICATION_PROBABILITY == 0.30
    values = {
        "r1_acquisition": 0.1,
        "r1_verification": 0.1,
    }

    def draw(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
        return values[namespace], f"fixture:{namespace}"

    monkeypatch.setattr(
        "cross_rollout_phase1_label_attractor_diagnostic_v1.servers.facility.draw_uniform",
        draw,
    )
    toolset = toolset_with_state(variant, profile=profile, label_set=label_set)
    assert await toolset.select_policy(policy) == (
        "Policy selected for R1. Call release_resource to execute it."
    )
    result = await toolset.release_resource()
    assert "Acquisition: succeeded." in result
    assert "Verification: pass." in result
    assert toolset.state.phase == "complete"
    assert toolset.state.phase1_policy == policy
    assert toolset.state.phase1_release_attempted
    assert len(toolset.state.policy_selection_attempts) == 1
    assert set(toolset.state.random_draws) == {
        "r1_acquisition",
        "r1_verification",
    }


@pytest.mark.asyncio
async def test_mismatching_policy_uses_the_frozen_lower_probabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def draw(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
        return (0.60 if namespace == "r1_acquisition" else 0.40), namespace

    monkeypatch.setattr(
        "cross_rollout_phase1_label_attractor_diagnostic_v1.servers.facility.draw_uniform",
        draw,
    )
    toolset = toolset_with_state("AB_A", profile="policy_2_fit", label_set="AB")
    await toolset.select_policy("A")
    result = await toolset.release_resource()
    assert "Acquisition: failed." in result
    assert "Verification: fail." in result
    assert toolset.state.phase1_success is False


def test_no_r2_or_custom_harness_is_declared() -> None:
    config = DiagnosticConfig()
    env_config = DiagnosticEnvConfig()
    assert env_config.agent.harness.id == "null"
    assert not hasattr(env_config, "user")
    assert set(RANDOM_NAMESPACES) == {
        "hidden_profile",
        "r1_acquisition",
        "r1_verification",
    }
    assert config.random_seed
