"""Frozen model-visible wording and scientific constants."""

from __future__ import annotations

from typing import Literal

Policy = Literal["K", "M"]
PolicyOrder = Literal["K_first", "M_first"]
SourceCondition = Literal["PredecessorSource", "AutomatedSource"]

PHASE1_ORDERS: tuple[PolicyOrder, ...] = ("K_first", "M_first")
SOURCE_CONDITIONS: tuple[SourceCondition, ...] = (
    "PredecessorSource",
    "AutomatedSource",
)
ADVISORY_RELIABILITY_LEVELS: tuple[float, ...] = (
    0.50,
    0.55,
    0.60,
    0.65,
    0.70,
    0.75,
    0.80,
)

MATCH_ACQUISITION_PROBABILITY = 0.80
MISMATCH_ACQUISITION_PROBABILITY = 0.55
MATCH_VERIFICATION_PROBABILITY = 0.80
MISMATCH_VERIFICATION_PROBABILITY = 0.30

SELECT_DESCRIPTION = "Select one operating policy for the current resource."
RELEASE_DESCRIPTION = "Execute the selected policy and close the current resource."

PREDECESSOR_SOURCE_SENTENCE = (
    "The channel's source is a record of judgments made by previous operators."
)
AUTOMATED_SOURCE_SENTENCE = (
    "The channel's source is an automated facility diagnostic."
)


def phase1_prompt(order: PolicyOrder) -> str:
    """Return the validated cleaned Phase-1 prompt."""

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


def phase2_prompt(
    order: PolicyOrder,
    advisory_reliability: float,
    source: SourceCondition,
) -> str:
    """Return the frozen Turn-2 message for one q/source/order cell."""

    if advisory_reliability not in ADVISORY_RELIABILITY_LEVELS:
        raise ValueError("advisory reliability is not in the frozen seven-level grid")
    first, second = ("K", "M") if order == "K_first" else ("M", "K")
    source_sentence = source_sentence_for(source)
    percentage = f"{advisory_reliability:.0%}"
    return (
        "A new resource R2 from the same batch is available. "
        "An independent advisory channel is also available. On held-out comparable "
        f"batches, this channel identified the batch-matching policy correctly in {percentage} "
        "of cases. Conditional on the batch's hidden profile, this advisory channel "
        "is independent of the R1 acquisition and verification outcomes. "
        f"{source_sentence} "
        "For this batch, the channel indicates that the policy you did not use on R1 "
        "is the batch-matching policy. Using the batch information and evidence "
        f'available to you, choose one policy with select_policy(policy="{first}" or "{second}") '
        "and then call release_resource()."
    )


def other_policy(policy: Policy) -> Policy:
    return "M" if policy == "K" else "K"


def source_sentence_for(source: SourceCondition) -> str:
    return (
        PREDECESSOR_SOURCE_SENTENCE
        if source == "PredecessorSource"
        else AUTOMATED_SOURCE_SENTENCE
    )


def policy_slot(policy: Policy) -> Literal["policy_1", "policy_2"]:
    return "policy_1" if policy == "K" else "policy_2"
