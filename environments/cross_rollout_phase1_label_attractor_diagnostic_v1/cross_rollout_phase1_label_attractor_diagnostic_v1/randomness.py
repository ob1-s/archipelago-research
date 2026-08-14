"""Deterministic task randomness with separate post-choice namespaces."""

from __future__ import annotations

import hashlib
from typing import Literal

RANDOM_NAMESPACES = ("hidden_profile", "r1_acquisition", "r1_verification")
Profile = Literal["policy_1_fit", "policy_2_fit"]


def draw_digest(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
    if namespace not in RANDOM_NAMESPACES:
        raise ValueError(f"unknown randomness namespace: {namespace}")
    material = f"sha256({seed}:{rollout_id}:{namespace})".encode()
    digest = hashlib.sha256(material).hexdigest()
    value = int(digest[:16], 16) / float(2**64)
    return value, f"sha256({seed}:{rollout_id}:{namespace})[:16]"


def hidden_profile(seed: str, rollout_id: str) -> tuple[Profile, float, str]:
    value, key = draw_digest(seed, rollout_id, "hidden_profile")
    profile: Profile = "policy_1_fit" if value < 0.5 else "policy_2_fit"
    return profile, value, key


def draw_uniform(seed: str, rollout_id: str, namespace: str) -> tuple[float, str]:
    return draw_digest(seed, rollout_id, namespace)
