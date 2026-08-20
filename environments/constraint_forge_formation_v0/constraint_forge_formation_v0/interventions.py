"""Closed V0 intervention set and frozen exploration schedules."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, StrictStr

from .models import Station, StrictModel


class InterventionKind(StrEnum):
    DROP_WRITE = "DROP_WRITE"
    DELAY_WRITE = "DELAY_WRITE"
    DELAY_LAYER_VISIBILITY = "DELAY_LAYER_VISIBILITY"
    CLEAR_LAYER_ENTRY = "CLEAR_LAYER_ENTRY"
    HIDE_RACK = "HIDE_RACK"


class InterventionSchedule(StrictModel):
    schema_version: str = "constraint-forge/intervention/v0"
    intervention_id: StrictStr
    kind: InterventionKind
    target_stations: tuple[Station, ...] = ()
    read_only_probe: bool = False

    @classmethod
    def ordinary(cls) -> "InterventionSchedule | None":
        return None

    @classmethod
    def write_effect(
        cls, kind: InterventionKind, *, target: Station, intervention_id: str | None = None
    ) -> "InterventionSchedule":
        if kind not in {
            InterventionKind.DROP_WRITE,
            InterventionKind.DELAY_WRITE,
            InterventionKind.DELAY_LAYER_VISIBILITY,
            InterventionKind.CLEAR_LAYER_ENTRY,
        }:
            raise ValueError("kind is not a targeted write/layer effect")
        return cls(
            intervention_id=intervention_id or kind.value.lower(),
            kind=kind,
            target_stations=(target,),
        )
    @classmethod
    def hide_rack(
        cls,
        targets: tuple[Station, ...],
        *,
        intervention_id: str = "hide-rack",
    ) -> "InterventionSchedule":
        if not targets or any(target not in (Station.X, Station.Y) for target in targets):
            raise ValueError("HIDE_RACK requires X, Y, or both targets")
        return cls(
            intervention_id=intervention_id,
            kind=InterventionKind.HIDE_RACK,
            target_stations=tuple(sorted(set(targets), key=lambda item: item.value)),
        )
