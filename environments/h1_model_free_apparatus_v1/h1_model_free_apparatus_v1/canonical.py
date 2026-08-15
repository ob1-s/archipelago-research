"""Deterministic serialization and content addressing."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def _validate_json_shape(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise TypeError(f"canonical JSON requires string keys at {path}")
            _validate_json_shape(nested, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _validate_json_shape(nested, f"{path}[{index}]")


def canonical_json(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    _validate_json_shape(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
