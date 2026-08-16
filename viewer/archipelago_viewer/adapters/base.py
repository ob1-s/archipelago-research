"""Adapter protocol: existing trace/archive format -> ViewerEpisode.

Adapters are read-only: they never write to the source, never run the
environment, and never alter experiment data.  The raw trace remains the
canonical evidence; a ViewerEpisode is derived, presentational data.
"""

from __future__ import annotations

import os
from typing import Any


class AdapterError(Exception):
    pass


class Adapter:
    """Base class for source formats.

    Subclasses declare ``name`` (also used as ``source_kind``), ``extensions``
    used for cheap discovery, and implement ``load``.  ``can_load`` sniffs a
    path: extension first, then a cheap content probe (overridable).
    """

    name: str = "base"
    extensions: tuple[str, ...] = ()

    @classmethod
    def can_load(cls, path: str, kind: str | None = None) -> bool:
        """Probe-confirmed support.  The probe is cheap and decisive: it reads
        the first line (or the whole small JSON doc) and checks a signature
        that only this adapter's format has, so extension collisions between
        JSONL formats resolve to the correct adapter."""
        if kind is not None and kind != cls.name:
            return False
        try:
            return cls._probe(path)
        except OSError:
            return False

    @classmethod
    def _probe(cls, path: str) -> bool:
        return False

    @classmethod
    def load(cls, path: str, limit: int | None = None, group_mode: str = "community") -> list[Any]:
        raise NotImplementedError

    @staticmethod
    def describe(path: str) -> str:
        return f"{os.path.basename(path)} ({os.path.getsize(path)} bytes)"