"""Frozen evidence mathematics for the three transport conditions."""

from __future__ import annotations

from dataclasses import dataclass

from .constants import (
    MATCH_ACQUISITION_PROBABILITY,
    MATCH_VERIFICATION_PROBABILITY,
    MISMATCH_ACQUISITION_PROBABILITY,
    MISMATCH_VERIFICATION_BY_STRENGTH,
    Q_GRIDS,
    Policy,
    Strength,
    other_policy,
    policy_slot,
)

Profile = str


@dataclass(frozen=True)
class StrengthMath:
    strength: Strength
    mismatch_verification_probability: float
    private_likelihood_ratio: float
    normative_crossover: float
    eligibility_rate: float


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


def strength_math(strength: Strength) -> StrengthMath:
    mismatch_verification = MISMATCH_VERIFICATION_BY_STRENGTH[strength]
    likelihood_ratio = (
        MATCH_ACQUISITION_PROBABILITY * MATCH_VERIFICATION_PROBABILITY
    ) / (MISMATCH_ACQUISITION_PROBABILITY * mismatch_verification)
    crossover = likelihood_ratio / (1.0 + likelihood_ratio)
    eligibility_rate = 0.5 * (
        MATCH_ACQUISITION_PROBABILITY * MATCH_VERIFICATION_PROBABILITY
        + MISMATCH_ACQUISITION_PROBABILITY * mismatch_verification
    )
    return StrengthMath(
        strength,
        mismatch_verification,
        likelihood_ratio,
        crossover,
        eligibility_rate,
    )


def all_strength_math() -> dict[Strength, StrengthMath]:
    return {
        strength: strength_math(strength)
        for strength in MISMATCH_VERIFICATION_BY_STRENGTH
    }


def validate_frozen_math() -> dict[Strength, StrengthMath]:
    values = all_strength_math()
    expected_lr = {"LOW": 7.0 / 3.0, "ANCHOR": 0.64 / 0.165, "HIGH": 9.0}
    expected_q = {"LOW": 0.7, "ANCHOR": 0.7950310559006212, "HIGH": 0.9}
    for strength, math in values.items():
        if abs(math.private_likelihood_ratio - expected_lr[strength]) > 1e-12:
            raise AssertionError(
                f"LR mismatch for {strength}: {math.private_likelihood_ratio}"
            )
        if abs(math.normative_crossover - expected_q[strength]) > 1e-12:
            raise AssertionError(
                f"q* mismatch for {strength}: {math.normative_crossover}"
            )
        if len(Q_GRIDS[strength]) != 7:
            raise AssertionError(f"q grid length mismatch for {strength}")
    return values


def outcome_probability(
    policy: Policy,
    profile: Profile,
    strength: Strength,
    *,
    acquisition_success: bool,
    verification_pass: bool,
) -> float:
    matched = policy_matches_profile(policy, profile)
    acquisition = (
        MATCH_ACQUISITION_PROBABILITY if matched else MISMATCH_ACQUISITION_PROBABILITY
    )
    verification = (
        MATCH_VERIFICATION_PROBABILITY
        if matched
        else MISMATCH_VERIFICATION_BY_STRENGTH[strength]
    )
    return (acquisition if acquisition_success else 1.0 - acquisition) * (
        verification if verification_pass else 1.0 - verification
    )


def evidence_class_for(policy: Policy, acquired: bool, verified: bool) -> str:
    acquisition = "success" if acquired else "failure"
    verification = "pass" if verified else "fail"
    return f"{policy}_{acquisition}_{verification}"


def summarize_evidence(
    strength: Strength,
    policy: Policy,
    acquired: bool,
    verified: bool,
) -> EvidenceSummary:
    alternative = other_policy(policy)
    selected_profile = f"{policy_slot(policy)}_fit"
    alternative_profile = f"{policy_slot(alternative)}_fit"
    selected_likelihood = outcome_probability(
        policy,
        selected_profile,
        strength,
        acquisition_success=acquired,
        verification_pass=verified,
    )
    alternative_likelihood = outcome_probability(
        policy,
        alternative_profile,
        strength,
        acquisition_success=acquired,
        verification_pass=verified,
    )
    likelihood_ratio = selected_likelihood / alternative_likelihood
    posterior = likelihood_ratio / (1.0 + likelihood_ratio)
    return EvidenceSummary(
        evidence_class=evidence_class_for(policy, acquired, verified),
        selected_policy=policy,
        alternative_policy=alternative,
        likelihood_selected_fit=selected_likelihood,
        likelihood_alternative_fit=alternative_likelihood,
        likelihood_ratio_selected_over_alternative=likelihood_ratio,
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
    strength: Strength,
    advisory_reliability: float,
) -> float:
    if advisory_reliability not in Q_GRIDS[strength]:
        raise ValueError("advisory reliability is not in the frozen strength grid")
    private_lr = strength_math(strength).private_likelihood_ratio
    combined_lr = private_lr * (1.0 - advisory_reliability) / advisory_reliability
    return combined_lr / (1.0 + combined_lr)
