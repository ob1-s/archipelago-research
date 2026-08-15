import pytest

from h1_model_free_apparatus_v1.models import Position, StateVariant
from h1_model_free_apparatus_v1.routine import (
    HELD_OUT_MODE,
    HELD_OUT_U,
    HELD_OUT_V,
    artifact_payloads,
    execute_relay,
    execute_single_actor,
    expected_output,
    parse_artifacts,
)


@pytest.mark.parametrize("variant", list(StateVariant))
def test_relay_generalizes_on_held_out_perturbation(variant):
    left, right = artifact_payloads(variant)
    run = execute_relay(left, right, encoder_actor="e", checker_actor="c")
    assert run.output == expected_output(variant)
    assert run.held_out_generalization
    assert run.fidelity == 1.0
    assert run.action_order == (Position.ENCODER, Position.CHECKER, Position.ENCODER)


def test_two_positions_make_distinct_contributions():
    left, right = artifact_payloads(StateVariant.A)
    run = execute_relay(left, right, encoder_actor="e", checker_actor="c")
    assert run.actor_ids == ("e", "c", "e")
    assert len(set(run.actor_ids)) == 2
    assert run.intermediate != run.output


def test_right_artifact_is_bound_to_left():
    left_a, _ = artifact_payloads(StateVariant.A)
    _, right_b = artifact_payloads(StateVariant.B)
    with pytest.raises(ValueError):
        parse_artifacts(left_a, right_b)


def test_single_actor_can_succeed_but_has_zero_routine_fidelity():
    left, right = artifact_payloads(StateVariant.A)
    run = execute_single_actor(left, right, actor_id="one")
    assert run.output == expected_output(StateVariant.A)
    assert run.fidelity == 0.0


def test_held_out_inputs_are_not_artifact_contents():
    left, right = artifact_payloads(StateVariant.A)
    serialized = repr((left, right))
    assert repr(HELD_OUT_U) not in serialized
    assert repr(HELD_OUT_V) not in serialized
    assert f"mode': {HELD_OUT_MODE}" not in serialized
