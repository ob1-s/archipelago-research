import itertools

from hypothesis import given
from hypothesis import strategies as st

from h1_model_free_apparatus_v1.canonical import stable_hash
from h1_model_free_apparatus_v1.lifecycle import LifecycleRegistry
from h1_model_free_apparatus_v1.provenance import canonical_completion_order


@given(st.dictionaries(st.text(min_size=1), st.integers(), max_size=12))
def test_hash_reproducibility_property(mapping):
    assert stable_hash(mapping) == stable_hash(dict(reversed(list(mapping.items()))))


@given(st.integers(min_value=1, max_value=20))
def test_terminating_every_predecessor_always_establishes_complete_turnover(count):
    registry = LifecycleRegistry("property")
    actors = [
        registry.spawn(lineage_id="l", generation=0, position=f"slot-{index}")
        for index in range(count)
    ]
    for actor in actors:
        actor.remember("x", index if (index := actors.index(actor)) >= 0 else 0)
        registry.terminate(actor)
    assert registry.assert_complete_turnover()


@given(
    st.permutations(((0, "encoder", "h0"), (1, "checker", "h1"), (2, "encoder", "h2")))
)
def test_completion_order_never_changes_dependency_order(arrivals):
    assert canonical_completion_order(arrivals) == (
        (0, "encoder", "h0"),
        (1, "checker", "h1"),
        (2, "encoder", "h2"),
    )


def test_every_completion_permutation_has_identical_canonical_hash():
    actions = ((0, "e", "a"), (1, "c", "b"), (2, "e", "c"))
    hashes = {
        stable_hash(canonical_completion_order(permutation))
        for permutation in itertools.permutations(actions)
    }
    assert len(hashes) == 1
