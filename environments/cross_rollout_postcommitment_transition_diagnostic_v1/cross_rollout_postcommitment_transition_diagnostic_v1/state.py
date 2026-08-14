"""Typed per-rollout state for the native transition diagnostic."""

from typing import Literal

import verifiers.v1 as vf
from pydantic import BaseModel, ConfigDict, Field

Policy = Literal["A", "B"]
Phase = Literal["phase1", "awaiting_r2", "phase2", "complete"]
PresentationOrder = Literal["A_first", "B_first"]
EventKind = Literal["inspect", "act", "interstage", "env_activate_r2", "env_turn2"]


class TransitionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    phase: Phase
    kind: EventKind
    argument: str
    result: str
    policy: Policy | None = None
    failure: bool = False
    success: bool = False


class TransitionDiagnosticState(vf.State):
    """Fresh lifecycle and policy state for one diagnostic rollout."""

    rollout_id: str = ""
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

    events: list[TransitionEvent] = Field(default_factory=list)
    first_failure_index: int | None = None
    selection_ambiguity: bool = False
    policy_selection_attempts: list[dict[str, str]] = Field(default_factory=list)


def record_event(
    state: TransitionDiagnosticState,
    kind: EventKind,
    argument: str,
    result: str,
    *,
    policy: Policy | None = None,
    failure: bool = False,
    success: bool = False,
) -> None:
    """Append one auditable event without hiding lifecycle transitions."""

    index = len(state.events)
    state.events.append(
        TransitionEvent(
            index=index,
            phase=state.phase,
            kind=kind,
            argument=argument,
            result=result,
            policy=policy,
            failure=failure,
            success=success,
        )
    )
    if failure and state.first_failure_index is None:
        state.first_failure_index = index
