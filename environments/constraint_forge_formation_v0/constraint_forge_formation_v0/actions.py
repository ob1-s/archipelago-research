"""Exact strict-JSON action unions and deterministic parsing."""

from __future__ import annotations

import json
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, TypeAdapter

from .canonical import canonical_json


class ActionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class WriteAction(ActionModel):
    action: Literal["write"]
    register: Annotated[StrictInt, Field(ge=0, le=1)]
    symbol: Annotated[StrictInt, Field(ge=0, le=3)]


class SetAction(ActionModel):
    action: Literal["set"]
    item: Annotated[StrictInt, Field(ge=0, le=5)]
    target: Annotated[StrictInt, Field(ge=0, le=5)]


class UnsetAction(ActionModel):
    action: Literal["unset"]
    item: Annotated[StrictInt, Field(ge=0, le=5)]


class FinishAction(ActionModel):
    action: Literal["finish"]


class WaitAction(ActionModel):
    action: Literal["wait"]


class RetainAction(ActionModel):
    action: Literal["retain"]
    start_round: Annotated[StrictInt, Field(ge=1, le=11)]


class EvictAction(ActionModel):
    action: Literal["evict"]
    fragment_handle: StrictStr = Field(min_length=1)


class KeepUnchangedAction(ActionModel):
    action: Literal["keep_unchanged"]


WorldAction: TypeAlias = Annotated[
    WriteAction | SetAction | UnsetAction | FinishAction | WaitAction,
    Field(discriminator="action"),
]
MemoryAction: TypeAlias = Annotated[
    RetainAction | EvictAction | KeepUnchangedAction,
    Field(discriminator="action"),
]

_WORLD_ADAPTER = TypeAdapter(WorldAction)
_MEMORY_ADAPTER = TypeAdapter(MemoryAction)


class ActionParseError(ValueError):
    """Raised for any malformed, non-canonical, or wrong-phase action."""


def _parse(text: str, adapter: TypeAdapter, *, phase: str) -> BaseModel:
    if not isinstance(text, str) or not text:
        raise ActionParseError("action must be a non-empty JSON object string")
    try:
        decoded = json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-finite JSON constant {value} is forbidden")
        ))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise ActionParseError("action is malformed JSON") from exc
    if not isinstance(decoded, dict):
        raise ActionParseError("action must be exactly one JSON object")
    try:
        # Canonicalization is applied to the typed payload after parsing.  The
        # examples in the frozen protocol intentionally use schema order rather
        # than the hash serializer's lexical key order; surrounding prose and
        # multiple JSON values remain forbidden.
        if text != text.strip():
            raise ActionParseError("action cannot have surrounding whitespace")
        return adapter.validate_python(decoded)
    except ActionParseError:
        raise
    except Exception as exc:
        raise ActionParseError(f"invalid {phase} action") from exc


def parse_world_action(text: str) -> WorldAction:
    return _parse(text, _WORLD_ADAPTER, phase="world")  # type: ignore[return-value]


def parse_memory_action(text: str) -> MemoryAction:
    return _parse(text, _MEMORY_ADAPTER, phase="memory")  # type: ignore[return-value]


def action_payload(action: BaseModel) -> dict:
    return action.model_dump(mode="json")
