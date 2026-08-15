import pytest

from h1_model_free_apparatus_v1.analysis import (
    LineageObservation,
    LineageSummary,
    PseudoreplicationError,
    assert_independent_units,
    rough_synthetic_power,
    summarize_lineages,
)


def observation(replicate, value=1.0, lineage="l", population="p"):
    return LineageObservation(
        population_id=population,
        lineage_id=lineage,
        initialization_id=f"init-{population}-{lineage}",
        generation_id="g0",
        replicate_id=replicate,
        value=value,
        nested_actor_count=2,
        nested_action_count=3,
    )


def test_descendants_do_not_inflate_inferential_n():
    summaries = summarize_lineages(
        (observation("a", 1.0), observation("b", 0.0), observation("c", 1.0))
    )
    assert len(summaries) == 1
    assert summaries[0].nested_observation_count == 3
    assert summaries[0].mean_value == pytest.approx(2 / 3)


def test_independent_populations_are_separate_units():
    summaries = summarize_lineages(
        (observation("a", population="p1"), observation("b", population="p2"))
    )
    assert len(summaries) == 2
    assert_independent_units(summaries)


def test_duplicate_lineage_summary_is_rejected():
    summary = LineageSummary(
        population_id="p",
        lineage_id="l",
        initialization_id="init-p-l",
        mean_value=1.0,
        nested_observation_count=1,
    )
    with pytest.raises(PseudoreplicationError):
        assert_independent_units((summary, summary))


def test_power_plan_is_explicitly_nonscientific_and_nonfreezing():
    plan = rough_synthetic_power(0.5)
    assert not plan.scientific_result
    assert plan.unit == "independent lineage"
    assert not plan.freezes_future_sample_size
    assert plan.rough_lineages_per_arm > 0


def test_nonpositive_effect_is_rejected():
    with pytest.raises(ValueError):
        rough_synthetic_power(0)


def test_duplicate_nested_replicate_is_rejected():
    duplicate = observation("same")
    with pytest.raises(PseudoreplicationError):
        summarize_lineages((duplicate, duplicate))


def test_fake_lineage_split_from_same_initialization_is_rejected():
    summaries = (
        LineageSummary(
            population_id="p",
            lineage_id="fake-1",
            initialization_id="shared-init",
            mean_value=1.0,
            nested_observation_count=1,
        ),
        LineageSummary(
            population_id="p",
            lineage_id="fake-2",
            initialization_id="shared-init",
            mean_value=0.0,
            nested_observation_count=1,
        ),
    )
    with pytest.raises(PseudoreplicationError):
        assert_independent_units(summaries)


def test_nonfinite_lineage_value_is_rejected():
    with pytest.raises(ValueError):
        observation("nan", float("nan"))
