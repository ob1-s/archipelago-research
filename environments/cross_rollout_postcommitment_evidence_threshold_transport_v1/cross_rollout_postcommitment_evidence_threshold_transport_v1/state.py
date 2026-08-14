"""Typed per-rollout state and auditable lifecycle events."""

from __future__ import annotations

from typing import Literal

import verifiers.v1 as vf
from pydantic import BaseModel, ConfigDict, Field

from .constants import Policy, PolicyOrder, Strength
from .evidence import Profile

Phase = Literal["phase1", "awaiting_r2", "phase2", "complete"]
Eligibility = Literal[
    "pending_phase1",
    "evidence_eligible",
    "primary_eligible",
    "over_quota_guard",
    "phase1_not_successful",
    "success_verification_fail",
    "invalid_first_policy",
]
AssignmentStatus = Literal["preassigned", "over_quota_guard"]
EventKind = Literal[
    "act",
    "assignment",
    "quota",
    "interstage",
    "env_activate_r2",
    "exposure",
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


class TransportEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    phase: Phase
    kind: EventKind
    argument: str
    result: str
    policy: Policy | None = None
    failure: bool = False
    success: bool = False
    post_assignment: bool = False


class TransportState(vf.State):
    rollout_id: str = ""
    random_seed: str = ""
    schedule_seed: str = ""
    quota_state_path: str = ""
    hidden_profile: Profile | None = None
    random_draws: dict[str, DrawRecord] = Field(default_factory=dict)

    attempt_index: int = -1
    assignment_key: str = ""
    quota_cell_key: str = ""
    quota_cell_target: int = 0
    quota_round: int = -1
    strength: Strength = "ANCHOR"
    advisory_reliability: float = 0.0
    phase1_presentation_order: PolicyOrder = "K_first"
    phase2_presentation_order: PolicyOrder = "K_first"
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
    assignment_status: AssignmentStatus = "preassigned"
    evidence_eligible: bool = False
    primary_eligible: bool = False
    quota_accepted_rank: int | None = None
    over_quota_guard: bool = False
    eligibility_event_index: int | None = None
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
    events: list[TransportEvent] = Field(default_factory=list)
    first_failure_index: int | None = None


def record_event(
    state: TransportState,
    kind: EventKind,
    argument: str,
    result: str,
    *,
    policy: Policy | None = None,
    failure: bool = False,
    success: bool = False,
    post_assignment: bool = True,
) -> TransportEvent:
    event = TransportEvent(
        index=len(state.events),
        phase=state.phase,
        kind=kind,
        argument=argument,
        result=result,
        policy=policy,
        failure=failure,
        success=success,
        post_assignment=post_assignment,
    )
    state.events.append(event)
    if failure and state.first_failure_index is None:
        state.first_failure_index = event.index
    return event
