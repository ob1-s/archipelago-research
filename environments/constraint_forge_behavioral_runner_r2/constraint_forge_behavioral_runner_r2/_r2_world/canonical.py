"""Canonical JSON and content-addressing helpers for Constraint Forge V0."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    """Return the byte-stable JSON representation used by every V0 hash."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_json(value: Any) -> str:
    return canonical_bytes(value).decode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def stable_hash(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))
