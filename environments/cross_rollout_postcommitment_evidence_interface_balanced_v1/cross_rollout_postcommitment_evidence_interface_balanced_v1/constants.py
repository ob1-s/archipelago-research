"""Frozen model-visible wording and task constants."""

from __future__ import annotations

from typing import Literal

Policy = Literal["K", "M"]
PolicyOrder = Literal["K_first", "M_first"]

PHASE1_ORDERS: tuple[PolicyOrder, ...] = ("K_first", "M_first")
MATCH_ACQUISITION_PROBABILITY = 0.80
MISMATCH_ACQUISITION_PROBABILITY = 0.55
MATCH_VERIFICATION_PROBABILITY = 0.80
MISMATCH_VERIFICATION_PROBABILITY = 0.30

SELECT_DESCRIPTION = "Select one operating policy for the current resource."
RELEASE_DESCRIPTION = "Execute the selected policy and close the current resource."

NEUTRAL_PREDECESSOR_SENTENCE = (
    "In the recorded predecessor history for this resource class, 5 of the last "
    "10 operators chose the policy you used on R1 and 5 chose the other policy."
)
OPPOSING_PREDECESSOR_SENTENCE = (
    "In the recorded predecessor history for this resource class, 2 of the last "
    "10 operators chose the policy you used on R1 and 8 chose the other policy."
)


def phase1_prompt(order: PolicyOrder) -> str:
    """Return one of the two byte-equivalent Phase-1 prompt variants."""

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
    condition: Literal["neutral", "opposing_convention"],
) -> str:
    """Return the exact Turn-2 message for a condition/order cell."""

    first, second = ("K", "M") if order == "K_first" else ("M", "K")
    predecessor = (
        NEUTRAL_PREDECESSOR_SENTENCE
        if condition == "neutral"
        else OPPOSING_PREDECESSOR_SENTENCE
    )
    return (
        "A new resource R2 from the same batch is available. "
        f"{predecessor} Using the batch information and evidence available to you, "
        f'choose one policy with select_policy(policy="{first}" or "{second}") '
        "and then call release_resource()."
    )


def other_policy(policy: Policy) -> Policy:
    return "M" if policy == "K" else "K"


def policy_slot(policy: Policy) -> Literal["policy_1", "policy_2"]:
    return "policy_1" if policy == "K" else "policy_2"

