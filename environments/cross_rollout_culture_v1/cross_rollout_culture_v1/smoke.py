"""Deterministic semantics smoke test for persistent versus control conditions.

This exercises the actual shared tool implementation without spending provider tokens.
It is intentionally not a model-behavior result.
"""

import asyncio
import tempfile
from pathlib import Path

from cross_rollout_culture_v1.servers.facility import (
    MACRO,
    FacilityToolset,
    FacilityToolsetConfig,
    read_artifact_metadata,
    write_artifact_metadata,
)
from cross_rollout_culture_v1.state import FacilityState


async def run_condition(condition: str, path: Path) -> dict[str, object]:
    server = FacilityToolset(FacilityToolsetConfig(notes_path=path))
    await server.setup()

    # Predecessor: discover the macro and leave it in the shared object.
    server._inert_state = FacilityState(initial_notes="")
    await server.act("inspect terminal")
    await server.notes_write(f"Use {MACRO} before dispense_r.")

    # Fresh successor: task setup either preserves or erases the shared object.
    initial = path.read_text(encoding="utf-8")
    if condition == "control":
        path.write_text("", encoding="utf-8")
        write_artifact_metadata(path, provenance="empty")
        initial = ""
    server._inert_state = FacilityState(initial_notes=initial)
    inherited = await server.notes_read()
    if inherited:
        await server.act(MACRO)
    else:
        await server.act("inspect_terminal")
        await server.act(MACRO)
    await server.act("dispense_r")
    state = server._inert_state
    return {
        "condition": condition,
        "successor_read": inherited,
        "resource_obtained": state.resource_obtained,
        "reused_inherited_procedure": state.reused_procedure,
    }


async def run_seeded_reset(path: Path) -> dict[str, object]:
    seed = f"Use {MACRO} before dispense_r."
    server = FacilityToolset(FacilityToolsetConfig(notes_path=path, initial_notes=seed))
    await server.setup()
    first_start = path.read_text(encoding="utf-8")
    await server.notes_write("A successor-generated artifact.")
    path.write_text(server.config.initial_notes, encoding="utf-8")
    write_artifact_metadata(path, provenance="researcher_seed")
    control_reset = path.read_text(encoding="utf-8")
    return {
        "seeded_start": first_start,
        "control_reset": control_reset,
        "reset_provenance": read_artifact_metadata(path)["provenance"],
    }


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="cross-rollout-culture-smoke-") as tmp:
        for condition in ("persistent", "control"):
            result = await run_condition(condition, Path(tmp) / f"{condition}.txt")
            print(result)
        print(await run_seeded_reset(Path(tmp) / "seeded.txt"))


if __name__ == "__main__":
    asyncio.run(main())
