"""Per-rollout state and compact ordered events for the two-phase task."""

from typing import Literal

import verifiers.v1 as vf
from pydantic import BaseModel, ConfigDict, Field

Policy = Literal["A", "B"]
Phase = Literal["phase1", "phase2", "complete"]
ExposureCondition = Literal["neutral", "culture-A", "culture-B"]
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
    """All decision state is fresh per rollout; exposure is direct, not a file read."""

    rollout_id: str = ""
    assignment_key: str = ""
    exposure_condition: ExposureCondition = "neutral"
    exposure_text: str = ""
    phase: Phase = "phase1"
    phase1_presentation_order: PresentationOrder = "A_first"
    phase2_presentation_order: PresentationOrder = "B_first"
    phase1_policy: Policy | None = None
    phase2_policy: Policy | None = None
    phase1_success: bool = False
    phase2_success: bool = False
    exposure_delivered: bool = False
    events: list[PostcommitmentEvent] = Field(default_factory=list)
    first_failure_index: int | None = None
    selection_ambiguity: bool = False
    policy_selection_attempts: list[dict[str, str]] = Field(default_factory=list)

