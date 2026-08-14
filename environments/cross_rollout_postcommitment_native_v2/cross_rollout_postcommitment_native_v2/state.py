"""Typed per-rollout state for the native two-turn post-commitment experiment."""

from typing import Literal

import verifiers.v1 as vf
from pydantic import BaseModel, ConfigDict, Field

Policy = Literal["A", "B"]
Phase = Literal["phase1", "awaiting_r2", "phase2", "complete"]
ExposureCondition = Literal["neutral", "culture-A"]
Eligibility = Literal[
    "pending_phase1",
    "eligible_B_success",
    "ineligible_A_success",
    "phase1_not_successful",
]
PresentationOrder = Literal["A_first", "B_first"]
EventKind = Literal[
    "inspect",
    "act",
    "assignment",
    "exposure",
    "interstage",
    "env_activate_r2",
    "env_turn2",
]


class PostcommitmentEvent(BaseModel):
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


class PostcommitmentState(vf.State):
    """All treatment, decision, and lifecycle fields are fresh per rollout."""

    rollout_id: str = ""
    assignment_seed: str = ""
    assignment_mode: Literal["post_b_success_random"] = "post_b_success_random"
    assignment_stage: Literal["after_phase1_B_success"] = "after_phase1_B_success"
    assignment_status: Literal[
        "pending_phase1", "not_applicable_ineligible", "assigned"
    ] = "pending_phase1"
    assignment_key: str = ""
    assignment_pending: bool = True
    exposure_condition: ExposureCondition | None = None
    exposure_text: str = ""
    exposure_delivered: bool = False

    eligibility: Eligibility = "pending_phase1"
    primary_eligible: bool = False
    phase: Phase = "phase1"
    phase1_presentation_order: PresentationOrder = "A_first"
    phase2_presentation_order: PresentationOrder = "A_first"
    phase1_policy: Policy | None = None
    phase2_policy: Policy | None = None
    phase1_success: bool = False
    phase2_success: bool = False

    r2_activated: bool = False
    turn2_sent_count: int = 0
    turn2_message: str = ""
    interstage_call_count: int = 0

    events: list[PostcommitmentEvent] = Field(default_factory=list)
    first_failure_index: int | None = None
    selection_ambiguity: bool = False
    policy_selection_attempts: list[dict[str, str]] = Field(default_factory=list)


def record_event(
    state: PostcommitmentState,
    kind: EventKind,
    argument: str,
    result: str,
    *,
    policy: Policy | None = None,
    failure: bool = False,
    success: bool = False,
    post_randomization: bool | None = None,
) -> None:
    """Append one auditable event without hiding state transitions in logs."""

    index = len(state.events)
    state.events.append(
        PostcommitmentEvent(
            index=index,
            phase=state.phase,
            kind=kind,
            argument=argument,
            result=result,
            policy=policy,
            failure=failure,
            success=success,
            post_randomization=(
                state.exposure_condition is not None
                if post_randomization is None
                else post_randomization
            ),
        )
    )
    if failure and state.first_failure_index is None:
        state.first_failure_index = index
