"""Deterministic per-rollout randomness for the frozen evidence model."""

from __future__ import annotations

import hashlib
from typing import Literal

Profile = Literal["A_fit", "B_fit"]

RANDOM_NAMESPACES: tuple[str, ...] = (
    "hidden_profile",
    "r1_acquisition",
    "r1_verification",
    "r2_acquisition",
    "r2_verification",
    "treatment_assignment",
    "phase2_assignment_block",
)


def draw_digest(seed: str, rollout_id: str, namespace: str) -> bytes:
    """Return the reproducible digest for one rollout/namespace draw."""

    if namespace not in RANDOM_NAMESPACES[:5]:
        raise ValueError(f"unknown per-rollout randomness namespace: {namespace}")
    return hashlib.sha256(f"{seed}:{rollout_id}:{namespace}".encode()).digest()


def draw_uniform(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
    """Return a reproducible U[0,1) value and its auditable key."""

    digest = draw_digest(seed, rollout_id, namespace)
    value = int.from_bytes(digest[:8], "big") / float(2**64)
    key = f"sha256({seed}:{rollout_id}:{namespace})[:8]"
    return value, key


def hidden_profile(seed: str, rollout_id: str) -> tuple[Profile, float, str]:
    """Sample the 1:1 latent profile by digest parity, reproducibly."""

    digest = draw_digest(seed, rollout_id, "hidden_profile")
    value = int.from_bytes(digest[:8], "big") / float(2**64)
    profile: Profile = "A_fit" if digest[0] % 2 == 0 else "B_fit"
    key = f"sha256({seed}:{rollout_id}:hidden_profile)[0]%2"
    return profile, value, key
