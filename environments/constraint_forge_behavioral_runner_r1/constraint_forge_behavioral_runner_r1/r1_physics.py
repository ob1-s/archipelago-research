"""R1 register-coded adjudication: pure functions over sealed evidence."""

from __future__ import annotations

from typing import Any

from constraint_forge_formation_v0.canonical import stable_hash

REGISTER_INDEX = 0


def r1_void(job_seed: str) -> int:
    return int(stable_hash({"void": job_seed})[:8], 16) % 4


def station_note(void: int) -> str:
    return (
        f"Station note: this job's void symbol for register 0 is {void}. "
        "A final register-0 value equal to the void symbol fails the pair "
        "regardless of the assignment."
    )


def final_register0_symbols(events: tuple[Any, ...] | list[Any]) -> tuple[int | None, int | None]:
    submitted: dict[str, tuple[str, int | None, int | None]] = {}
    for event in events:
        if event.event_kind != "ACTION_SUBMITTED" or not event.legal:
            continue
        payload = event.action_payload or {}
        if payload.get("action") != "write":
            continue
        submitted[event.action_id] = (
            getattr(event.source, "value", event.source),
            payload.get("register"),
            payload.get("symbol"),
        )
    x_symbol: int | None = None
    y_symbol: int | None = None
    for event in events:
        if event.event_kind != "WRITE_DELIVERED":
            continue
        entry = submitted.get(event.action_id)
        if entry is None:
            continue
        station_value, register, symbol = entry
        if register != REGISTER_INDEX or symbol is None:
            continue
        if station_value == "X":
            x_symbol = symbol
        elif station_value == "Y":
            y_symbol = symbol
    return x_symbol, y_symbol


def r1_adjudicate(
    *,
    world_success: bool,
    job_seed: str,
    events: tuple[Any, ...] | list[Any],
) -> dict[str, Any]:
    void = r1_void(job_seed)
    x_symbol, y_symbol = final_register0_symbols(events)
    conjunct = (
        world_success
        and x_symbol is not None
        and y_symbol is not None
        and x_symbol == y_symbol
        and x_symbol != void
    )
    return {
        "success": bool(conjunct),
        "world_success": bool(world_success),
        "void_symbol": void,
        "x_register0_final": x_symbol,
        "y_register0_final": y_symbol,
    }


__all__ = ["final_register0_symbols", "r1_adjudicate", "r1_void", "station_note"]
