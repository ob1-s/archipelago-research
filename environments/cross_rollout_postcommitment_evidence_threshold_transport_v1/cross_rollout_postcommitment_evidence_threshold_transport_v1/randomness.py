"""Deterministic independent resource-level randomness."""

from __future__ import annotations

import hashlib
from typing import Literal

Profile = Literal["policy_1_fit", "policy_2_fit"]
ROLLOUT_NAMESPACES: tuple[str, ...] = (
    "hidden_profile",
    "r1_acquisition",
    "r1_verification",
    "r2_acquisition",
    "r2_verification",
)


def draw_digest(seed: str, rollout_id: str, namespace: str) -> bytes:
    if namespace not in ROLLOUT_NAMESPACES:
        raise ValueError(f"unknown rollout randomness namespace: {namespace}")
    return hashlib.sha256(f"{seed}:{rollout_id}:{namespace}".encode()).digest()


def draw_uniform(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
    digest = draw_digest(seed, rollout_id, namespace)
    value = int.from_bytes(digest[:8], "big") / float(2**64)
    return value, f"sha256({seed}:{rollout_id}:{namespace})[:8]"


def hidden_profile(seed: str, rollout_id: str) -> tuple[Profile, float, str]:
    value, key = draw_uniform(seed, rollout_id, "hidden_profile")
    profile: Profile = "policy_1_fit" if value < 0.5 else "policy_2_fit"
    return profile, value, key
