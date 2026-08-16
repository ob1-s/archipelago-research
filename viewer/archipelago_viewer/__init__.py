"""Archipelago trajectory viewer: read-only replay of existing traces.

The viewer consumes existing trace/archive outputs only.  It never runs an
environment, never writes to the sources, and produces no scientific results.
Raw traces remain canonical evidence; viewer documents are derived and
presentational.
"""

from . import adapters, reduce, schema
from .reduce import reduce
from .schema import (
    EVENT_KINDS,
    ViewerAgent,
    ViewerArtifact,
    ViewerCarrier,
    ViewerEpisode,
    ViewerEvent,
)

__all__ = [
    "adapters",
    "reduce",
    "schema",
    "ViewerAgent",
    "ViewerArtifact",
    "ViewerCarrier",
    "ViewerEpisode",
    "ViewerEvent",
    "EVENT_KINDS",
]