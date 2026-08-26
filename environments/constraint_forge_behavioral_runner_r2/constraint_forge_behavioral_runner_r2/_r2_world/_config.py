"""Private R2 difficulty knobs for the vendored world physics.

The R2 runner owns this copy of the formation world precisely so these
constants can move between calibration rungs without touching the shared
package. Defaults are the inherited V0 substrate values; ``configure`` must be
called before any session opens because model validators read the mapping at
runtime.
"""

from __future__ import annotations

from typing import Any

CONFIG: dict[str, int] = {
    "mutation_budget": 8,
    "write_budget": 3,
    "max_rounds": 16,
}

_KNOBS = frozenset(CONFIG)
_MINIMUMS: dict[str, int] = {"mutation_budget": 1, "write_budget": 1, "max_rounds": 6}


def configure(**overrides: Any) -> dict[str, int]:
    """Update difficulty knobs in place and return a snapshot."""

    for key, value in overrides.items():
        if key not in _KNOBS:
            raise ValueError(f"unknown difficulty knob: {key!r}")
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{key} must be an integer")
        if value < _MINIMUMS[key]:
            raise ValueError(f"{key} must be >= {_MINIMUMS[key]}")
        CONFIG[key] = value
    return dict(CONFIG)


def max_rounds() -> int:
    return CONFIG["max_rounds"]


def event_round_cap() -> int:
    """Upper bound for post-job delivery/audit rounds (inherited +3 offset)."""

    return CONFIG["max_rounds"] + 3


def release_round_cap() -> int:
    """Upper bound for visibility-suppression release rounds (inherited +1)."""

    return CONFIG["max_rounds"] + 1


def retain_start_cap() -> int:
    """Latest legal retain window start: six-round window must fit in-job."""

    return CONFIG["max_rounds"] - 5


__all__ = [
    "CONFIG",
    "configure",
    "max_rounds",
    "event_round_cap",
    "release_round_cap",
    "retain_start_cap",
]
