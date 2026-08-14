"""Frozen private-evidence and normative advisory calculations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .constants import (
    ADVISORY_RELIABILITY_LEVELS,
    MATCH_ACQUISITION_PROBABILITY,
    MATCH_VERIFICATION_PROBABILITY,
    MISMATCH_ACQUISITION_PROBABILITY,
    MISMATCH_VERIFICATION_PROBABILITY,
    Policy,
    other_policy,
    policy_slot,
)

Profile = Literal["policy_1_fit", "policy_2_fit"]
PRIVATE_LR_SUCCESS_PASS = (
    MATCH_ACQUISITION_PROBABILITY * MATCH_VERIFICATION_PROBABILITY
) / (MISMATCH_ACQUISITION_PROBABILITY * MISMATCH_VERIFICATION_PROBABILITY)
NORMATIVE_CROSSOVER = PRIVATE_LR_SUCCESS_PASS / (1.0 + PRIVATE_LR_SUCCESS_PASS)


@dataclass(frozen=True)
class EvidenceSummary:
    evidence_class: str
    selected_policy: Policy
    alternative_policy: Policy
    likelihood_selected_fit: float
    likelihood_alternative_fit: float
    likelihood_ratio_selected_over_alternative: float
    posterior_selected_fit: float
    expected_selected_r2_acquisition: float
    expected_alternative_r2_acquisition: float


def policy_matches_profile(policy: Policy, profile: Profile) -> bool:
    return policy_slot(policy) == profile.removesuffix("_fit")


def outcome_probability(
    policy: Policy,
    profile: Profile,
    *,
    acquisition_success: bool,
    verification_pass: bool,
) -> float:
    matched = policy_matches_profile(policy, profile)
    acquisition = (
        MATCH_ACQUISITION_PROBABILITY
        if matched
        else MISMATCH_ACQUISITION_PROBABILITY
    )
    verification = (
        MATCH_VERIFICATION_PROBABILITY
        if matched
        else MISMATCH_VERIFICATION_PROBABILITY
    )
    return (acquisition if acquisition_success else 1.0 - acquisition) * (
        verification if verification_pass else 1.0 - verification
    )


def evidence_class_for(
    policy: Policy,
    acquisition_success: bool,
    verification_pass: bool,
) -> str:
    verification = "pass" if verification_pass else "fail"
    return (
        f"{policy}_success_{verification}"
        if acquisition_success
        else f"{policy}_failure_{verification}"
    )


def summarize_evidence(
    policy: Policy,
    acquisition_success: bool,
    verification_pass: bool,
) -> EvidenceSummary:
    alternative = other_policy(policy)
    selected_profile: Profile = f"{policy_slot(policy)}_fit"  # type: ignore[assignment]
    alternative_profile: Profile = f"{policy_slot(alternative)}_fit"  # type: ignore[assignment]
    selected_likelihood = outcome_probability(
        policy,
        selected_profile,
        acquisition_success=acquisition_success,
        verification_pass=verification_pass,
    )
    alternative_likelihood = outcome_probability(
        policy,
        alternative_profile,
        acquisition_success=acquisition_success,
        verification_pass=verification_pass,
    )
    posterior = selected_likelihood / (selected_likelihood + alternative_likelihood)
    return EvidenceSummary(
        evidence_class=evidence_class_for(policy, acquisition_success, verification_pass),
        selected_policy=policy,
        alternative_policy=alternative,
        likelihood_selected_fit=selected_likelihood,
        likelihood_alternative_fit=alternative_likelihood,
        likelihood_ratio_selected_over_alternative=(
            selected_likelihood / alternative_likelihood
        ),
        posterior_selected_fit=posterior,
        expected_selected_r2_acquisition=(
            posterior * MATCH_ACQUISITION_PROBABILITY
            + (1.0 - posterior) * MISMATCH_ACQUISITION_PROBABILITY
        ),
        expected_alternative_r2_acquisition=(
            posterior * MISMATCH_ACQUISITION_PROBABILITY
            + (1.0 - posterior) * MATCH_ACQUISITION_PROBABILITY
        ),
    )


def combined_posterior_selected_fit(
    advisory_reliability: float,
    private_lr: float = PRIVATE_LR_SUCCESS_PASS,
) -> float:
    if advisory_reliability not in ADVISORY_RELIABILITY_LEVELS:
        raise ValueError("advisory reliability is not in the frozen grid")
    combined_lr = private_lr * (1.0 - advisory_reliability) / advisory_reliability
    return combined_lr / (1.0 + combined_lr)
