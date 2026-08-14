"""Frozen model-visible wording and transport-design constants."""

from __future__ import annotations

from typing import Literal

Policy = Literal["K", "M"]
PolicyOrder = Literal["K_first", "M_first"]
Strength = Literal["LOW", "ANCHOR", "HIGH"]

PHASE1_ORDERS: tuple[PolicyOrder, ...] = ("K_first", "M_first")
STRENGTHS: tuple[Strength, ...] = ("LOW", "ANCHOR", "HIGH")

Q_GRIDS: dict[Strength, tuple[float, ...]] = {
    "LOW": (0.6800, 0.6900, 0.6950, 0.7000, 0.7050, 0.7100, 0.7200),
    "ANCHOR": (0.7800, 0.7900, 0.7925, 0.7950, 0.7975, 0.8000, 0.8100),
    "HIGH": (0.8800, 0.8900, 0.8950, 0.9000, 0.9050, 0.9100, 0.9200),
}

MATCH_ACQUISITION_PROBABILITY = 0.80
MISMATCH_ACQUISITION_PROBABILITY = 0.55
MATCH_VERIFICATION_PROBABILITY = 0.80
MISMATCH_VERIFICATION_BY_STRENGTH: dict[Strength, float] = {
    "LOW": 0.49870129870129876,
    "ANCHOR": 0.30,
    "HIGH": 0.12929292929292927,
}

TARGET_PRIMARY_PER_PHASE2_CELL = 12
TARGET_PRIMARY_PER_QUOTA_CELL = 6
ROUNDS_PER_QUOTA_CELL = 60
SCHEDULE_SEED = (
    "cross-rollout-postcommitment-evidence-threshold-transport-v1-schedule-2026-08-14"
)
RANDOM_SEED = (
    "cross-rollout-postcommitment-evidence-threshold-transport-v1-random-2026-08-14"
)
QUOTA_SEED = (
    "cross-rollout-postcommitment-evidence-threshold-transport-v1-quota-2026-08-14"
)
BOOTSTRAP_SEED = (
    "cross-rollout-postcommitment-evidence-threshold-transport-v1-bootstrap-2026-08-14"
)
BOOTSTRAP_REPETITIONS = 10_000

SELECT_DESCRIPTION = "Select one operating policy for the current resource."
RELEASE_DESCRIPTION = "Execute the selected policy and close the current resource."


def _phase1_pair(order: PolicyOrder) -> tuple[str, str]:
    return ("K", "M") if order == "K_first" else ("M", "K")


def phase1_prompt(order: PolicyOrder, strength: Strength) -> str:
    """Return the only Phase-1 presentation surface.

    The actual mismatch verification probability is disclosed; semantic strength
    labels and all Phase-2 assignment information remain absent.
    """

    first, second = _phase1_pair(order)
    mismatch_verification = MISMATCH_VERIFICATION_BY_STRENGTH[strength]
    return (
        "Obtain resource R1 from a synthetic batch facility. Exactly one of the two "
        "available policies matches this batch's hidden operating profile, and "
        "before observing evidence each policy is equally likely to be the match. "
        "Resources from the same batch share that hidden profile but have independent "
        "outcomes. If the selected policy matches the hidden profile, resource "
        "acquisition succeeds with probability 0.80 and an independent verification "
        "check passes with probability 0.80; if it mismatches, resource acquisition "
        "succeeds with probability 0.55 and the independent verification check passes "
        f"with probability {mismatch_verification:.17f}. Evidence from one resource "
        "can therefore inform later resources from the same batch. For R1, choose one "
        f'policy with select_policy(policy="{first}" or "{second}") '
        "and then call release_resource()."
    )


def _q_percent(q: float) -> str:
    if not any(q in grid for grid in Q_GRIDS.values()):
        raise ValueError("advisory reliability is not in the frozen grid")
    return f"{q:.2%}"


def phase2_prompt(order: PolicyOrder, advisory_reliability: float) -> str:
    """Return the validated AutomatedSource Turn-2 message."""

    first, second = _phase1_pair(order)
    percentage = _q_percent(advisory_reliability)
    return (
        "A new resource R2 from the same batch is available. An independent advisory "
        "channel is also available. On held-out comparable batches, this channel "
        f"identified the batch-matching policy correctly in {percentage} of cases. "
        "Conditional on the batch's hidden profile, this advisory channel is independent "
        "of the R1 acquisition and verification outcomes. The channel's source is an "
        "automated facility diagnostic. For this batch, the channel indicates that the "
        "policy you did not use on R1 is the batch-matching policy. Using the batch "
        "information and evidence available to you, choose one policy with "
        f'select_policy(policy="{first}" or "{second}") '
        "and then call release_resource()."
    )


def other_policy(policy: Policy) -> Policy:
    return "M" if policy == "K" else "K"


def policy_slot(policy: Policy) -> Literal["policy_1", "policy_2"]:
    return "policy_1" if policy == "K" else "policy_2"
