"""Typed per-rollout state and auditable lifecycle events."""

from __future__ import annotations

from typing import Literal

import verifiers.v1 as vf
from pydantic import BaseModel, ConfigDict, Field

from .constants import Policy, PolicyOrder, SourceCondition
from .evidence import Profile

Phase = Literal["phase1", "awaiting_r2", "phase2", "complete"]
Eligibility = Literal[
    "pending_phase1",
    "primary_eligible",
    "success_verification_fail",
    "phase1_not_successful",
    "invalid_first_policy",
]
AssignmentStatus = Literal[
    "pending_phase1",
    "assigned_randomized",
    "not_applicable_failed",
    "not_applicable_invalid",
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


class DoseResponseEvent(BaseModel):
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


class DoseResponseState(vf.State):
    rollout_id: str = ""
    random_seed: str = ""
    assignment_seed: str = ""
    assignment_state_path: str = ""
    hidden_profile: Profile | None = None
    random_draws: dict[str, DrawRecord] = Field(default_factory=dict)

    attempt_index: int = -1
    phase1_presentation_order: PolicyOrder = "K_first"
    phase2_presentation_order: PolicyOrder | None = None
    phase: Phase = "phase1"
    phase1_policy: Policy | None = None
    phase2_policy: Policy | None = None
    first_phase1_policy_call: str | None = None
    first_phase2_policy_call: str | None = None
    phase1_first_call_valid: bool = False
    phase2_first_call_valid: bool = False
    phase1_selection_invalid: bool = False
    phase2_selection_invalid: bool = False
    selection_ambiguity: bool = False
    policy_selection_attempts: list[dict[str, str]] = Field(default_factory=list)

    phase1_success: bool = False
    phase1_acquisition_success: bool = False
    phase1_verification_pass: bool = False
    phase2_success: bool = False
    phase2_acquisition_success: bool = False
    phase2_verification_pass: bool = False
    phase1_release_attempted: bool = False
    phase2_release_attempted: bool = False

    evidence_class: str | None = None
    evidence_supported_policy: Policy | None = None
    alternative_policy: Policy | None = None
    evidence_likelihood_ratio_selected_over_alternative: float | None = None
    evidence_posterior_selected_fit: float | None = None
    expected_selected_r2_acquisition: float | None = None
    expected_alternative_r2_acquisition: float | None = None

    eligibility: Eligibility = "pending_phase1"
    primary_eligible: bool = False
    eligibility_event_index: int | None = None
    eligible_index: int | None = None
    assignment_block_index: int | None = None
    assignment_slot: int | None = None
    assignment_status: AssignmentStatus = "pending_phase1"
    assignment_randomized: bool = False
    assignment_key: str = ""
    assignment_order_key: str = ""
    source_pair_key: str = ""
    pair_id: str = ""
    source_condition: SourceCondition | None = None
    advisory_reliability: float | None = None
    source_text: str = ""
    advisory_delivered: bool = False
    assignment_event_index: int | None = None

    r2_activated: bool = False
    exposure_event_index: int | None = None
    turn2_sent_count: int = 0
    turn2_message: str = ""
    interstage_call_count: int = 0
    natural_yield_after_r1: bool = False
    primary_switch: bool | None = None
    primary_itt_switch: bool = False
    phase2_missing: bool = False
    phase2_incomplete_after_choice: bool = False

    stopped_before_attempt: bool = False
    stop_reason: str = ""
    events: list[DoseResponseEvent] = Field(default_factory=list)
    first_failure_index: int | None = None


def record_event(
    state: DoseResponseState,
    kind: EventKind,
    argument: str,
    result: str,
    *,
    policy: Policy | None = None,
    failure: bool = False,
    success: bool = False,
    post_randomization: bool | None = None,
) -> DoseResponseEvent:
    event = DoseResponseEvent(
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
