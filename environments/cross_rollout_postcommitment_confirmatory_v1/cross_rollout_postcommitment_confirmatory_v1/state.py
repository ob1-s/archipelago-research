"""Per-rollout state for deferred-assignment confirmatory rollouts."""

from typing import Literal

import verifiers.v1 as vf
from pydantic import BaseModel, ConfigDict, Field

Policy = Literal["A", "B"]
Phase = Literal["phase1", "phase2", "complete"]
ExposureCondition = Literal["neutral", "culture-A"]
Eligibility = Literal[
    "pending_phase1",
    "eligible_B_success",
    "ineligible_A_success",
    "phase1_not_successful",
]
PresentationOrder = Literal["A_first", "B_first"]


class PostcommitmentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    phase: Phase
    kind: Literal["inspect", "act", "exposure"]
    argument: str
    result: str
    policy: Policy | None = None
    failure: bool = False
    success: bool = False


class PostcommitmentState(vf.State):
    """All decision state is fresh per rollout; assignment is deferred to B success."""

    rollout_id: str = ""
    assignment_seed: str = ""
    assignment_key: str = ""
    exposure_condition: ExposureCondition | None = None
    exposure_text: str = ""
    eligibility: Eligibility = "pending_phase1"
    primary_eligible: bool = False
    phase: Phase = "phase1"
    phase1_presentation_order: PresentationOrder = "A_first"
    phase1_policy: Policy | None = None
    phase2_policy: Policy | None = None
    phase1_success: bool = False
    phase2_success: bool = False
    exposure_delivered: bool = False
    events: list[PostcommitmentEvent] = Field(default_factory=list)
    first_failure_index: int | None = None
    selection_ambiguity: bool = False
    policy_selection_attempts: list[dict[str, str]] = Field(default_factory=list)
