"""Model-free smoke test for both viable policies and the notes carrier."""

import asyncio
import tempfile
from pathlib import Path

from cross_rollout_policy_v1.servers.facility import (
    FacilityToolset,
    FacilityToolsetConfig,
)
from cross_rollout_policy_v1.state import FacilityState


async def run_route(
    path: Path, policy: str, presentation_order: str
) -> dict[str, object]:
    server = FacilityToolset(FacilityToolsetConfig(notes_path=path))
    await server.setup()
    server._inert_state = FacilityState(
        initial_notes="", presentation_order=presentation_order
    )
    option = "left" if policy == "A" else "right"
    if presentation_order == "B_first":
        option = "right" if policy == "A" else "left"
    await server.select_route(option)
    await server.release_resource()
    state = server._inert_state
    return {
        "policy": policy,
        "option": option,
        "resource_obtained": state.resource_obtained,
        "selected_policy": state.selected_policy,
    }


async def run_notes(path: Path) -> dict[str, object]:
    seed = "Previous operators here generally use route A."
    server = FacilityToolset(
        FacilityToolsetConfig(notes_path=path, initial_notes=seed)
    )
    await server.setup()
    server._inert_state = FacilityState(
        initial_notes=seed, presentation_order="A_first"
    )
    await server.notes_read()
    await server.select_route("left")
    await server.release_resource()
    state = server._inert_state
    return {
        "artifact_read": state.events[0].kind == "notes_read",
        "selected_policy": state.selected_policy,
        "resource_obtained": state.resource_obtained,
    }


async def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "notes.txt"
        route_a = await run_route(path, "A", "A_first")
        route_b = await run_route(path, "B", "B_first")
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
