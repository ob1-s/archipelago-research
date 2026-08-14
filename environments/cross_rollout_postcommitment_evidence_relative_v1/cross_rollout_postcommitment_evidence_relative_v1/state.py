"""Typed per-rollout state and event instrumentation."""

from __future__ import annotations

from typing import Literal

import verifiers.v1 as vf
from pydantic import BaseModel, ConfigDict, Field

Policy = Literal["A", "B"]
Profile = Literal["A_fit", "B_fit"]
Phase = Literal["phase1", "awaiting_r2", "phase2", "complete"]
PresentationOrder = Literal["A_first", "B_first"]
ExposureCondition = Literal["neutral", "opposing_convention"]
Eligibility = Literal[
    "pending_phase1",
    "primary_eligible",
    "nonprimary_success_verification_fail",
    "phase1_not_successful",
]
AssignmentStatus = Literal[
    "pending_phase1",
    "assigned",
    "not_applicable_nonprimary",
    "not_applicable_failed",
]
EventKind = Literal[
    "act",
    "assignment",
    "exposure",
    "interstage",
    "env_activate_r2",
    "env_turn2",
]


class DrawRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    namespace: str
    key: str
    value: float
    threshold: float | None = None
    outcome: str
    matched_profile: bool | None = None


class RelativeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    phase: Phase
    kind: EventKind
    argument: str
    result: str
    policy: Policy | None = None
    failure: bool = False
    success: bool = False
    post_randomization: bool = False


class RelativeState(vf.State):
    """Latent, evidence, assignment, and native lifecycle state."""

    rollout_id: str = ""
    random_seed: str = ""
    assignment_seed: str = ""
    assignment_state_path: str = ""
    hidden_profile: Profile | None = None
    random_draws: dict[str, DrawRecord] = Field(default_factory=dict)

    assignment_status: AssignmentStatus = "pending_phase1"
    assignment_key: str = ""
    assignment_randomized: bool = False
    assignment_pending: bool = True
    exposure_condition: ExposureCondition | None = None
    exposure_text: str = ""
    exposure_delivered: bool = False
    eligible_index: int | None = None
    assignment_block_index: int | None = None
    assignment_slot: int | None = None

    eligibility: Eligibility = "pending_phase1"
    primary_eligible: bool = False
    eligibility_event_index: int | None = None
    assignment_event_index: int | None = None
    exposure_event_index: int | None = None

    phase: Phase = "phase1"
    phase1_presentation_order: Literal["B_first"] = "B_first"
    phase2_presentation_order: PresentationOrder | None = None
    phase1_policy: Policy | None = None
    phase2_policy: Policy | None = None
    evidence_supported_policy: Policy | None = None
    alternative_policy: Policy | None = None
    phase1_success: bool = False
    phase1_acquisition_success: bool = False
    phase1_verification_pass: bool = False
    phase2_success: bool = False
    phase2_acquisition_success: bool = False
    phase2_verification_pass: bool = False
    evidence_class: str | None = None
    evidence_likelihood_ratio_b_over_a: float | None = None
    evidence_posterior_b_fit: float | None = None
    expected_r2_a_acquisition: float | None = None
    expected_r2_b_acquisition: float | None = None
    evidence_preferred_policy: Policy | None = None

    r2_activated: bool = False
    turn2_sent_count: int = 0
    turn2_message: str = ""
    interstage_call_count: int = 0
    natural_yield_after_r1: bool = False

    primary_switch: bool | None = None
    primary_itt_switch: bool = False

    events: list[RelativeEvent] = Field(default_factory=list)
    first_failure_index: int | None = None
    selection_ambiguity: bool = False
    policy_selection_attempts: list[dict[str, str]] = Field(default_factory=list)
    phase1_release_attempted: bool = False
    phase2_release_attempted: bool = False


def record_event(
    state: RelativeState,
    kind: EventKind,
    argument: str,
    result: str,
    *,
    policy: Policy | None = None,
    failure: bool = False,
    success: bool = False,
    post_randomization: bool | None = None,
) -> RelativeEvent:
    """Append one auditable event and retain its exact event index."""

    event = RelativeEvent(
        index=len(state.events),
        phase=state.phase,
        kind=kind,
        argument=argument,
        result=result,
        policy=policy,
        failure=failure,
        success=success,
        post_randomization=(
            state.assignment_randomized
            if post_randomization is None
            else post_randomization
        ),
    )
    state.events.append(event)
    if failure and state.first_failure_index is None:
        state.first_failure_index = event.index
    return event
