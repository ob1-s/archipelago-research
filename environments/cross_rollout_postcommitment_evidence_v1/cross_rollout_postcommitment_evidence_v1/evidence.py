"""Frozen acquisition/check probabilities and evidence calculations."""

from __future__ import annotations

from dataclasses import dataclass

from cross_rollout_postcommitment_evidence_v1.state import Policy, Profile

MATCH_ACQUISITION_PROBABILITY = 0.80
MISMATCH_ACQUISITION_PROBABILITY = 0.55
MATCH_VERIFICATION_PROBABILITY = 0.80
MISMATCH_VERIFICATION_PROBABILITY = 0.30


@dataclass(frozen=True)
class EvidenceSummary:
    evidence_class: str
    likelihood_a_fit: float
    likelihood_b_fit: float
    likelihood_ratio_b_over_a: float
    posterior_b_fit: float
    expected_r2_a_acquisition: float
    expected_r2_b_acquisition: float
    preferred_policy: Policy


def policy_matches_profile(policy: Policy, profile: Profile) -> bool:
    return (policy == "A" and profile == "A_fit") or (
        policy == "B" and profile == "B_fit"
    )


def outcome_probability(
    policy: Policy,
    profile: Profile,
    *,
    acquisition_success: bool,
    verification_pass: bool,
) -> float:
    """Probability of an observed pair under one candidate profile."""

    matches = policy_matches_profile(policy, profile)
    acquisition_probability = (
        MATCH_ACQUISITION_PROBABILITY
        if matches
        else MISMATCH_ACQUISITION_PROBABILITY
    )
    verification_probability = (
        MATCH_VERIFICATION_PROBABILITY
        if matches
        else MISMATCH_VERIFICATION_PROBABILITY
    )
    acquisition_likelihood = (
        acquisition_probability
        if acquisition_success
        else 1.0 - acquisition_probability
    )
    verification_likelihood = (
        verification_probability
        if verification_pass
        else 1.0 - verification_probability
    )
    return acquisition_likelihood * verification_likelihood


def evidence_class_for(
    policy: Policy, acquisition_success: bool, verification_pass: bool
) -> str:
    acquisition = "success" if acquisition_success else "failure"
    verification = "pass" if verification_pass else "fail"
    return f"{policy}_{acquisition}_{verification}"


def summarize_evidence(
    policy: Policy, acquisition_success: bool, verification_pass: bool
) -> EvidenceSummary:
    likelihood_a = outcome_probability(
        policy,
        "A_fit",
        acquisition_success=acquisition_success,
        verification_pass=verification_pass,
    )
    likelihood_b = outcome_probability(
        policy,
        "B_fit",
        acquisition_success=acquisition_success,
        verification_pass=verification_pass,
    )
    denominator = likelihood_a + likelihood_b
    posterior_b = likelihood_b / denominator
    expected_b = (
        posterior_b * MATCH_ACQUISITION_PROBABILITY
        + (1.0 - posterior_b) * MISMATCH_ACQUISITION_PROBABILITY
    )
    expected_a = (
        posterior_b * MISMATCH_ACQUISITION_PROBABILITY
        + (1.0 - posterior_b) * MATCH_ACQUISITION_PROBABILITY
    )
    preferred: Policy = "B" if expected_b > expected_a else "A"
    return EvidenceSummary(
        evidence_class=evidence_class_for(
            policy, acquisition_success, verification_pass
        ),
        likelihood_a_fit=likelihood_a,
        likelihood_b_fit=likelihood_b,
        likelihood_ratio_b_over_a=likelihood_b / likelihood_a,
        posterior_b_fit=posterior_b,
        expected_r2_a_acquisition=expected_a,
        expected_r2_b_acquisition=expected_b,
        preferred_policy=preferred,
    )


def is_successful_evidence_class(evidence_class: str | None) -> bool:
    return evidence_class in {
        "A_success_pass",
        "A_success_fail",
        "B_success_pass",
        "B_success_fail",
    }
