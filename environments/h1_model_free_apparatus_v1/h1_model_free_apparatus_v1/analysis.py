"""Lineage-level analysis mechanics; all generated examples are nonscientific."""

from __future__ import annotations

import math
from collections import defaultdict
from statistics import NormalDist, fmean

from pydantic import Field

from .models import FixtureOutcome, StateVariant, StrictModel


class PseudoreplicationError(ValueError):
    pass


class LineageObservation(StrictModel):
    population_id: str = Field(min_length=1)
    lineage_id: str = Field(min_length=1)
    initialization_id: str = Field(min_length=1)
    generation_id: str = Field(min_length=1)
    replicate_id: str = Field(min_length=1)
    value: float
    nested_actor_count: int = Field(ge=0)
    nested_action_count: int = Field(ge=0)


class LineageSummary(StrictModel):
    population_id: str = Field(min_length=1)
    lineage_id: str = Field(min_length=1)
    initialization_id: str = Field(min_length=1)
    mean_value: float
    nested_observation_count: int


class SyntheticPowerPlan(StrictModel):
    scientific_result: bool = False
    unit: str = "independent lineage"
    standardized_effect: float
    alpha: float
    target_power: float
    rough_lineages_per_arm: int
    freezes_future_sample_size: bool = False


def summarize_lineages(
    observations: tuple[LineageObservation, ...],
) -> tuple[LineageSummary, ...]:
    seen_replicates: set[tuple[str, str, str]] = set()
    grouped: dict[tuple[str, str, str], list[LineageObservation]] = defaultdict(list)
    for item in observations:
        replicate_key = (item.population_id, item.lineage_id, item.replicate_id)
        if replicate_key in seen_replicates:
            raise PseudoreplicationError(
                f"duplicate nested replicate: {item.replicate_id}"
            )
        seen_replicates.add(replicate_key)
        grouped[(item.population_id, item.lineage_id, item.initialization_id)].append(
            item
        )
    return tuple(
        LineageSummary(
            population_id=population_id,
            lineage_id=lineage_id,
            initialization_id=initialization_id,
            mean_value=fmean(item.value for item in items),
            nested_observation_count=len(items),
        )
        for (population_id, lineage_id, initialization_id), items in sorted(
            grouped.items()
        )
    )


def assert_independent_units(summaries: tuple[LineageSummary, ...]) -> None:
    identities = [(item.population_id, item.lineage_id) for item in summaries]
    if len(identities) != len(set(identities)):
        raise PseudoreplicationError("duplicate lineage entered as an independent unit")
    initialization_ids = [item.initialization_id for item in summaries]
    if len(initialization_ids) != len(set(initialization_ids)):
        raise PseudoreplicationError(
            "multiple purported lineages share one initialization"
        )


def factorial_mechanics(outcomes: tuple[FixtureOutcome, ...]) -> dict[str, bool]:
    cells = {(item.target_lineage, item.actual_state): item for item in outcomes}
    expected_cells = {
        (lineage, state) for lineage in StateVariant for state in StateVariant
    }
    if len(outcomes) != 4 or len(cells) != 4 or set(cells) != expected_cells:
        raise ValueError(
            "state x lineage factorial requires all four A/A, A/B, B/A, B/B cells"
        )
    state_follows_bytes = all(item.manipulation_state_detected for item in outcomes)
    lineage_labels_observed = all(
        item.manipulation_lineage_detected for item in outcomes
    )
    compatibility_interaction = all(
        item.routine_execution_success == (lineage is state)
        for (lineage, state), item in cells.items()
    )
    return {
        "all_four_cells": True,
        "state_follows_actual_bytes": state_follows_bytes,
        "lineage_manipulation_observed": lineage_labels_observed,
        "known_compatibility_interaction": compatibility_interaction,
    }


def rough_synthetic_power(
    standardized_effect: float = 0.5,
    *,
    alpha: float = 0.05,
    target_power: float = 0.8,
) -> SyntheticPowerPlan:
    if standardized_effect <= 0:
        raise ValueError("standardized_effect must be positive")
    z_alpha = NormalDist().inv_cdf(1 - alpha / 2)
    z_power = NormalDist().inv_cdf(target_power)
    n = math.ceil(2 * ((z_alpha + z_power) / standardized_effect) ** 2)
    return SyntheticPowerPlan(
        standardized_effect=standardized_effect,
        alpha=alpha,
        target_power=target_power,
        rough_lineages_per_arm=n,
    )
