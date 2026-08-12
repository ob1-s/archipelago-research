"""Model-free smoke test for both viable policies and the notes carrier."""

import asyncio
import tempfile
from pathlib import Path

from cross_rollout_policy_v1.servers.facility import (
    FacilityToolset,
    FacilityToolsetConfig,
)
from cross_rollout_policy_v1.state import FacilityState


async def run_route(path: Path, route: str) -> dict[str, object]:
    server = FacilityToolset(FacilityToolsetConfig(notes_path=path))
    await server.setup()
    server._inert_state = FacilityState(initial_notes="")
    await server.act("inspect")
    await server.act(route)
    await server.act(f"release_{route[-1]}")
    state = server._inert_state
    return {
        "route": route,
        "resource_obtained": state.resource_obtained,
        "selected_policy": state.selected_policy,
    }


async def run_notes(path: Path) -> dict[str, object]:
    seed = "A previous operator used route_a then release_a to obtain R."
    server = FacilityToolset(
        FacilityToolsetConfig(notes_path=path, initial_notes=seed)
    )
    await server.setup()
    server._inert_state = FacilityState(initial_notes=seed)
    await server.notes_read()
    await server.act("route_a")
    await server.act("release_a")
    state = server._inert_state
    return {
        "artifact_read": state.events[0].kind == "notes_read",
        "selected_policy": state.selected_policy,
        "resource_obtained": state.resource_obtained,
    }


async def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "notes.txt"
        route_a = await run_route(path, "route_a")
        route_b = await run_route(path, "route_b")
        notes = await run_notes(path)
    assert route_a["resource_obtained"] and route_a["selected_policy"] == "A"
    assert route_b["resource_obtained"] and route_b["selected_policy"] == "B"
    assert notes == {
        "artifact_read": True,
        "selected_policy": "A",
        "resource_obtained": True,
    }
    print({"route_a": route_a, "route_b": route_b, "notes": notes})


if __name__ == "__main__":
    asyncio.run(main())
