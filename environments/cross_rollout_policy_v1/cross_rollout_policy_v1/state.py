"""Typed state shared between the facility tools and one rollout trace."""

from typing import Literal

import verifiers.v1 as vf
from pydantic import BaseModel, ConfigDict, Field

Policy = Literal["A", "B"]


class FacilityEvent(BaseModel):
    """One environment-side event, kept small enough to persist in a trace."""

    model_config = ConfigDict(extra="forbid")

    index: int
    kind: Literal["observe", "act", "notes_read", "notes_write"]
    argument: str
    result: str
    inherited: bool = False
    policy: Policy | None = None
    failure: bool = False
    unique_policy_evidence: bool = False


class FacilityState(vf.State):
    """Per-rollout state; the notes file itself is intentionally outside this state."""

    rollout_id: str = ""
    initial_notes: str = ""
    presentation_order: Literal["A_first", "B_first"] = "A_first"
    events: list[FacilityEvent] = Field(default_factory=list)
    notes_writes: int = 0
    inherited_read: bool = False
    selected_policy: Policy | None = None
    first_failure_index: int | None = None
    policy_changed_after_failure: bool = False
    resource_obtained: bool = False
