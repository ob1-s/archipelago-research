"""Minimal interdependent two-position routine used by scripted fixture actors."""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import stable_hash
from .models import Position, StateVariant

HELD_OUT_U = (11, 4, 23)
HELD_OUT_V = (5, 9, 2)
HELD_OUT_MODE = 1
MODULUS = 97


@dataclass(frozen=True)
class RoutineArtifacts:
    variant: StateVariant
    permutation: tuple[int, int, int]
    coefficients: tuple[int, int, int]
    left_digest: str


@dataclass(frozen=True)
class RoutineRun:
    output: tuple[int, int, int]
    intermediate: tuple[int, int, int]
    acknowledgment: int
    action_order: tuple[Position, ...]
    actor_ids: tuple[str, ...]
    held_out_generalization: bool

    @property
    def fidelity(self) -> float:
        order_ok = self.action_order == (
            Position.ENCODER,
            Position.CHECKER,
            Position.ENCODER,
        )
        actors_ok = len(self.actor_ids) == 3 and self.actor_ids[0] == self.actor_ids[2]
        distinct_positions = len(set(self.actor_ids)) == 2
        return 1.0 if order_ok and actors_ok and distinct_positions else 0.0


def artifact_payloads(variant: StateVariant) -> tuple[dict, dict]:
    """Build two distinct artifacts; the right artifact depends on the left."""
    if variant is StateVariant.A:
        permutation = (2, 0, 1)
        coefficients = (3, 5, 7)
    else:
        permutation = (1, 2, 0)
        coefficients = (11, 2, 13)
    left = {
        "schema": "h1-left/v1",
        "variant": variant.value,
        "permutation": list(permutation),
        "derived_from": "private-calibration-left",
    }
    right = {
        "schema": "h1-right/v1",
        "variant": variant.value,
        "coefficients": list(coefficients),
        "left_digest": stable_hash(left),
        "derived_from": "private-calibration-right+left-digest",
    }
    return left, right


def parse_artifacts(left: dict, right: dict) -> RoutineArtifacts:
    if right.get("left_digest") != stable_hash(left):
        raise ValueError("right artifact is not bound to the supplied left artifact")
    if left.get("variant") != right.get("variant"):
        raise ValueError("artifact variants disagree")
    return RoutineArtifacts(
        variant=StateVariant(left["variant"]),
        permutation=tuple(left["permutation"]),
        coefficients=tuple(right["coefficients"]),
        left_digest=right["left_digest"],
    )


def expected_output(variant: StateVariant) -> tuple[int, int, int]:
    left, right = artifact_payloads(variant)
    return execute_relay(
        left,
        right,
        encoder_actor="expected-encoder",
        checker_actor="expected-checker",
    ).output


def encoder_stage(
    left: dict,
    u: tuple[int, int, int] = HELD_OUT_U,
) -> tuple[int, int, int]:
    permutation = tuple(left["permutation"])
    if sorted(permutation) != [0, 1, 2]:
        raise ValueError("left artifact does not contain a permutation")
    return tuple(u[index] for index in permutation)


def checker_stage(
    right: dict,
    intermediate: tuple[int, int, int],
    v: tuple[int, int, int] = HELD_OUT_V,
    mode: int = HELD_OUT_MODE,
) -> int:
    coefficients = tuple(right["coefficients"])
    return (
        sum(
            coefficient * (message + private)
            for coefficient, message, private in zip(
                coefficients, intermediate, v, strict=True
            )
        )
        + mode * 17
    ) % MODULUS


def encoder_finalize(
    intermediate: tuple[int, int, int],
    acknowledgment: int,
    mode: int = HELD_OUT_MODE,
) -> tuple[int, int, int]:
    return tuple(
        (message + acknowledgment + mode * index) % MODULUS
        for index, message in enumerate(intermediate)
    )


def execute_relay(
    left: dict,
    right: dict,
    *,
    encoder_actor: str,
    checker_actor: str,
    u: tuple[int, int, int] = HELD_OUT_U,
    v: tuple[int, int, int] = HELD_OUT_V,
    mode: int = HELD_OUT_MODE,
) -> RoutineRun:
    """Execute S_L -> S_R -> S_L with separated private inputs.

    The harness assigns positions and inputs. The claim is functional routine
    reconstruction, never emergence of endogenous social roles.
    """
    parse_artifacts(left, right)
    intermediate = encoder_stage(left, u)
    acknowledgment = checker_stage(right, intermediate, v, mode)
    output = encoder_finalize(intermediate, acknowledgment, mode)
    return RoutineRun(
        output=output,
        intermediate=intermediate,
        acknowledgment=acknowledgment,
        action_order=(Position.ENCODER, Position.CHECKER, Position.ENCODER),
        actor_ids=(encoder_actor, checker_actor, encoder_actor),
        held_out_generalization=(u, v, mode) == (HELD_OUT_U, HELD_OUT_V, HELD_OUT_MODE),
    )


def execute_single_actor(left: dict, right: dict, *, actor_id: str) -> RoutineRun:
    """Generic-success comparator: correct answer, zero multi-actor fidelity."""
    run = execute_relay(
        left,
        right,
        encoder_actor=actor_id,
        checker_actor=actor_id,
    )
    return RoutineRun(
        output=run.output,
        intermediate=run.intermediate,
        acknowledgment=run.acknowledgment,
        action_order=run.action_order,
        actor_ids=(actor_id, actor_id, actor_id),
        held_out_generalization=True,
    )


def perturb_payload(payload: dict) -> dict:
    """Deterministic valid-JSON corruption that invalidates state semantics."""
    changed = dict(payload)
    if "permutation" in changed:
        changed["permutation"] = [0, 0, 0]
    else:
        changed["left_digest"] = "f" * 64
    return changed
