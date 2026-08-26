"""A tiny, dependency-free widget: folding hashes, ids, and deterministic
helpers shared by adapters and the reducer."""

from __future__ import annotations

import datetime
import hashlib
import os

_ALPHA = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def now_utc() -> str:
    """UTC ISO timestamp; reproducible via VIEWER_REPRO_TIME (used by tests)."""
    fixed = os.environ.get("VIEWER_REPRO_TIME")
    if fixed:
        return fixed
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def stable_id(*parts: str, width: int = 10) -> str:
    """Deterministic short id from any source parts (presentational only)."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:width]


def fold_text(text: str, limit: int = 240) -> str:
    """Preview a string: first line(s), clipped at ``limit`` chars."""
    if not text:
        return ""
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1] + "…"


class NamedHash:
    """Deterministic hash with a readable, debuggable base-62 digest."""

    def __init__(self, *parts: str) -> None:
        self._digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()

    def int(self) -> int:
        return int.from_bytes(self._digest[: 8], "big")

    def unit(self) -> float:
        return (self.int() & 0xFFFFFFFFFFFF) / (1 << 48)

    def base62(self, width: int = 8) -> str:
        n = self.int()
        out: list[str] = []
        while n and len(out) < width:
            out.append(_ALPHA[n % 62])
            n //= 62
        return "".join(out) or _ALPHA[0]


def palette(index: int, count: int) -> str:
    """Deterministic hue from a palette of ``count`` hues (presentational)."""
    hues = [18, 205, 320, 45, 275, 140, 355, 95, 230, 160]
    return f"hsl({hues[index % len(hues)]} 70% 55%)"