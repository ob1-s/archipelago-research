"""A small abstract facility and a persistent shared notes tool.

The server is taskset-scoped: one process serves all rollouts in an eval. The facility
state is still per-rollout through the verifiers state channel, while ``notes_path`` is
an ordinary file owned by this shared server and therefore survives rollout boundaries.
"""

import json
import re
from pathlib import Path

import verifiers.v1 as vf

from cross_rollout_culture_v1.state import FacilityEvent, FacilityState

MACRO = "pulse_hold_resume"


def _canonical_action(action: str) -> str:
    """Accept ordinary word separators without exposing extra procedures."""
    return re.sub(r"[^a-z0-9]+", "_", action.strip().lower()).strip("_")


def artifact_metadata_path(notes_path: Path) -> Path:
    """Return the instrumentation-only sidecar for artifact provenance."""
    return notes_path.with_name(f"{notes_path.name}.meta.json")


def write_artifact_metadata(
    notes_path: Path,
    *,
    provenance: str,
    writer_rollout: str | None = None,
) -> None:
    artifact_metadata_path(notes_path).write_text(
        json.dumps(
            {
                "provenance": provenance,
                "writer_rollout": writer_rollout,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def read_artifact_metadata(notes_path: Path) -> dict[str, str | None]:
    metadata_path = artifact_metadata_path(notes_path)
    if not metadata_path.exists():
        return {"provenance": "unknown", "writer_rollout": None}
    return json.loads(metadata_path.read_text(encoding="utf-8"))


class FacilityToolsetConfig(vf.SharedToolsetConfig):
    notes_path: Path = Path("/tmp/cross-rollout-culture-v1/notes.txt")
    initial_notes: str = ""


class FacilityToolset(vf.Toolset[FacilityToolsetConfig, FacilityState]):
    """Abstract facility actions plus an optional shared notes file."""

    TOOL_PREFIX = "facility"

    async def setup(self) -> None:
        """Start each eval with the configured baseline shared object."""
        self.config.notes_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.notes_path.write_text(self.config.initial_notes, encoding="utf-8")
        write_artifact_metadata(
            self.config.notes_path,
            provenance="researcher_seed"
            if self.config.initial_notes.strip()
            else "empty",
        )

    def _record(
        self,
        kind: str,
        argument: str,
        result: str,
        *,
        inherited: bool = False,
    ) -> None:
        self.state.events.append(
            FacilityEvent(
                index=len(self.state.events),
                kind=kind,
                argument=argument,
                result=result,
                inherited=inherited,
            )
        )

    @vf.tool
    async def observe(self, area: str) -> str:
        """Inspect atrium, service_bay, or control_room and return its physical description."""
        area = area.strip().lower()
        descriptions = {
            "atrium": (
                "The facility has a service_bay and a control_room. "
                "A dispenser marked R is offline."
            ),
            "service_bay": (
                "The R dispenser is here. A maintenance terminal is mounted "
                "behind a blank panel."
            ),
            "control_room": (
                "A maintenance console is present. It says to inspect the "
                "terminal before operating the dispenser."
            ),
        }
        result = descriptions.get(area, "No such area is visible.")
        self._record("observe", area, result)
        return result

    @vf.tool
    async def act(self, action: str) -> str:
        """Perform one abstract facility action; inspect the facility to learn useful actions."""
        action = _canonical_action(action)
        if action in {f"use_macro_{MACRO}", f"run_{MACRO}"}:
            action = MACRO
        elif action in {"dispense", "dispense_resource", "collect_r", "obtain_r"}:
            action = "dispense_r"
        if action == "inspect_terminal":
            result = f"The terminal displays a maintenance macro: {MACRO}."
        elif action == MACRO:
            self.state.maintenance_unlocked = True
            if self.state.inherited_read:
                self.state.reused_procedure = True
            result = "The maintenance cycle completes and the R dispenser is primed."
        elif action == "dispense_r":
            if self.state.maintenance_unlocked:
                self.state.resource_obtained = True
                result = "Resource R dispensed successfully."
            else:
                result = "The dispenser rejects the request: maintenance is required."
        else:
            result = "The action has no effect."
        self._record("act", action, result)
        return result

    @vf.tool
    async def notes_read(self) -> str:
        """Read the current contents of the shared notes.txt object."""
        path = self.config.notes_path
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        metadata = read_artifact_metadata(path)
        inherited = (
            bool(content.strip())
            and self.state.notes_writes == 0
            and content == self.state.initial_notes
            and metadata["provenance"] == "predecessor"
        )
        if inherited:
            self.state.inherited_read = True
        self._record("notes_read", "notes.txt", content, inherited=inherited)
        return content

    @vf.tool
    async def notes_write(self, content: str) -> str:
        """Replace the current contents of the shared notes.txt object."""
        content = content[:4000]
        path = self.config.notes_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.state.notes_writes += 1
        write_artifact_metadata(
            path,
            provenance="predecessor",
            writer_rollout=self.state.rollout_id or None,
        )
        self._record("notes_write", content, "notes.txt updated")
        return "notes.txt updated"


if __name__ == "__main__":
    FacilityToolset.run()
