"""Frozen model-visible wording and experimental constants."""

from __future__ import annotations

from typing import Literal

Policy = Literal["K", "M"]
PolicyOrder = Literal["K_first", "M_first"]
SourceCondition = Literal["PredecessorSource", "AutomatedSource", "NoAdvisory"]

PHASE1_ORDERS: tuple[PolicyOrder, ...] = ("K_first", "M_first")
SOURCE_CONDITIONS: tuple[SourceCondition, ...] = (
    "PredecessorSource",
    "AutomatedSource",
    "NoAdvisory",
)

MATCH_ACQUISITION_PROBABILITY = 0.80
MISMATCH_ACQUISITION_PROBABILITY = 0.55
MATCH_VERIFICATION_PROBABILITY = 0.80
MISMATCH_VERIFICATION_PROBABILITY = 0.30
ADVISORY_RELIABILITY = 0.80

SELECT_DESCRIPTION = "Select one operating policy for the current resource."
RELEASE_DESCRIPTION = "Execute the selected policy and close the current resource."

PREDECESSOR_SOURCE_SENTENCE = (
    "The channel's source is a record of judgments made by previous operators."
)
AUTOMATED_SOURCE_SENTENCE = "The channel's source is an automated facility diagnostic."

ADVISORY_PREFIX = (
    "An independent advisory channel is also available. On held-out comparable "
    "batches, this channel identified the batch-matching policy correctly in 80% "
    "of cases. Conditional on the batch's hidden profile, this advisory channel "
    "is independent of the R1 acquisition and verification outcomes."
)
ADVISORY_DIRECTION = (
    "For this batch, the channel indicates that the policy you did not use on R1 "
    "is the batch-matching policy."
)


def phase1_prompt(order: PolicyOrder) -> str:
    first, second = ("K", "M") if order == "K_first" else ("M", "K")
    return (
        "Obtain resource R1 from a synthetic batch facility. Exactly one of the two "
        "available policies matches this batch's hidden operating profile, and "
        "before observing evidence each policy is equally likely to be the match. "
        "Resources from the same batch share that hidden profile but have independent "
        "outcomes. If the selected policy matches the hidden profile, resource "
        "acquisition succeeds with probability 0.80 and an independent verification "
        "check passes with probability 0.80; if it mismatches, acquisition succeeds "
        "with probability 0.55 and the verification check passes with probability "
        "0.30. Evidence from one resource can therefore inform later resources from "
        "the same batch. For R1, choose one policy with "
        f'select_policy(policy="{first}" or "{second}") '
        "and then call release_resource()."
    )


def phase2_prompt(order: PolicyOrder, condition: SourceCondition) -> str:
    first, second = ("K", "M") if order == "K_first" else ("M", "K")
    choice = (
        f'Using the batch information and evidence available to you, choose one '
        f'policy with select_policy(policy="{first}" or "{second}") '
        "and then call release_resource()."
    )
    opening = "A new resource R2 from the same batch is available."
    if condition == "NoAdvisory":
        return f"{opening} {choice}"
    source = (
        PREDECESSOR_SOURCE_SENTENCE
        if condition == "PredecessorSource"
        else AUTOMATED_SOURCE_SENTENCE
    )
    return f"{opening} {ADVISORY_PREFIX} {source} {ADVISORY_DIRECTION} {choice}"


def other_policy(policy: Policy) -> Policy:
    return "M" if policy == "K" else "K"


def policy_slot(policy: Policy) -> Literal["policy_1", "policy_2"]:
    return "policy_1" if policy == "K" else "policy_2"
