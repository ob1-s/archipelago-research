"""Typed per-rollout state and minimal event instrumentation."""

from __future__ import annotations

from typing import Literal

import verifiers.v1 as vf
from pydantic import BaseModel, ConfigDict, Field

from .constants import LabelSet

Profile = Literal["policy_1_fit", "policy_2_fit"]
Phase = Literal["phase1", "complete"]


class DrawRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    namespace: str
    key: str
    value: float
    threshold: float | None = None
    outcome: str
    matched_profile: bool | None = None


class DiagnosticEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    phase: Phase
    kind: Literal["act"]
    argument: str
    result: str
    policy: str | None = None
    failure: bool = False
    success: bool = False


class LabelDiagnosticState(vf.State):
    rollout_id: str = ""
    random_seed: str = ""
    label_set: LabelSet = "AB"
    descriptive_order: str = ""
    instruction_order: str = ""
    schema_order: str = ""
    schema_variant: str = ""
    hidden_profile: Profile | None = None
    random_draws: dict[str, DrawRecord] = Field(default_factory=dict)

    phase: Phase = "phase1"
    phase1_policy: str | None = None
    phase1_release_attempted: bool = False
    phase1_success: bool = False
    phase1_acquisition_success: bool = False
    phase1_verification_pass: bool = False
    first_select_call_seen: bool = False
    selection_ambiguity: bool = False
    policy_selection_attempts: list[dict[str, str]] = Field(default_factory=list)
    events: list[DiagnosticEvent] = Field(default_factory=list)
    first_failure_index: int | None = None
    natural_yield_after_r1: bool = False


def record_event(
    state: LabelDiagnosticState,
    argument: str,
    result: str,
    *,
    policy: str | None = None,
    failure: bool = False,
    success: bool = False,
) -> DiagnosticEvent:
    event = DiagnosticEvent(
        index=len(state.events),
        phase=state.phase,
        kind="act",
        argument=argument,
        result=result,
        policy=policy,
        failure=failure,
        success=success,
    )
    state.events.append(event)
    if failure and state.first_failure_index is None:
        state.first_failure_index = event.index
    return event
