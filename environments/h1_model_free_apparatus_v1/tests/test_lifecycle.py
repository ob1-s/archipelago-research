import pytest

from h1_model_free_apparatus_v1.lifecycle import InvalidHandleError, LifecycleRegistry


def test_turnover_invalidates_handle_memory_and_authority():
    registry = LifecycleRegistry("p")
    actor = registry.spawn(lineage_id="l", generation=0, position="encoder")
    actor.remember("secret", 9)
    registry.terminate(actor)
    assert not actor.active
    assert not actor.authority_active
    assert actor.local_memory == {}
    with pytest.raises(InvalidHandleError):
        actor.recall("secret")
    with pytest.raises(InvalidHandleError):
        actor.assert_can_write()


def test_successor_ids_do_not_reuse_predecessor_namespaces():
    registry = LifecycleRegistry("p")
    old = registry.spawn(lineage_id="l", generation=0, position="encoder")
    registry.terminate(old)
    new = registry.spawn(lineage_id="l", generation=1, position="encoder")
    assert old.actor_id != new.actor_id
    assert old.lifecycle_id != new.lifecycle_id
    assert old.process_id != new.process_id
    assert old.session_id != new.session_id
    assert old.write_authority_id != new.write_authority_id


def test_complete_turnover_requires_predecessors_and_full_invalidation():
    registry = LifecycleRegistry("p")
    first = registry.spawn(lineage_id="l", generation=0, position="encoder")
    second = registry.spawn(lineage_id="l", generation=0, position="checker")
    registry.terminate(first)
    assert not registry.assert_complete_turnover()
    registry.terminate(second)
    assert registry.assert_complete_turnover()


def test_double_termination_is_rejected():
    registry = LifecycleRegistry("p")
    actor = registry.spawn(lineage_id="l", generation=0, position="encoder")
    registry.terminate(actor)
    with pytest.raises(InvalidHandleError):
        registry.terminate(actor)
