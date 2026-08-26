"""Adapter registry: discover and load any supported source format."""

from __future__ import annotations

import os
from typing import Any

from .base import Adapter, AdapterError
from .corpus import PreFrameworkCorpusAdapter
from .runtime_state import RuntimeBoundaryAdapter
from .verifiers_jsonl import VerifiersTracesAdapter

ADAPTERS: list[type[Adapter]] = [
    VerifiersTracesAdapter,
    RuntimeBoundaryAdapter,
    PreFrameworkCorpusAdapter,
]

# First declared adapter wins for an extension (order = priority).
EXTENSION_MAP: dict[str, type[Adapter]] = {}
for _adapter in ADAPTERS:
    for _ext in _adapter.extensions:
        EXTENSION_MAP.setdefault(_ext, _adapter)


def load_episodes(
    path: str,
    limit: int | None = None,
    group_mode: str = "community",
) -> list[Any]:
    """Load a supported source into ViewerEpisodes, or raise AdapterError."""
    if not os.path.isfile(path):
        raise AdapterError(f"not a file: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext == ".gz":
        ext = os.path.splitext(os.path.splitext(path)[0])[1].lower()
    ranked = sorted(
        ADAPTERS, key=lambda a: (0 if ext in a.extensions else 1)
    )
    probed = None
    for adapter in ranked:
        if not adapter.can_load(path):
            continue
        probed = adapter
        episodes = adapter.load(path, limit=limit, group_mode=group_mode)
        if episodes:
            return episodes
    if probed is not None:
        raise AdapterError(f"no episodes found in {path!r} ({probed.name})")
    raise AdapterError(f"no adapter for {path!r}")


def format_summary() -> list[dict[str, str]]:
    return [
        {
            "name": adapter.name,
            "extensions": ", ".join(adapter.extensions),
        }
        for adapter in ADAPTERS
    ]