"""Minimal two-tool facility for the evidence-based native lifecycle."""

from typing import Literal

import verifiers.v1 as vf

from cross_rollout_postcommitment_evidence_v1 import randomness
from cross_rollout_postcommitment_evidence_v1.evidence import (
    MATCH_ACQUISITION_PROBABILITY,
    MATCH_VERIFICATION_PROBABILITY,
    MISMATCH_ACQUISITION_PROBABILITY,
    MISMATCH_VERIFICATION_PROBABILITY,
    policy_matches_profile,
    summarize_evidence,
)
from cross_rollout_postcommitment_evidence_v1.state import (
    EvidenceState,
    Policy,
    record_event,
)

NEUTRAL_NOTICE = "No predecessor policy convention is recorded."
CULTURE_A_NOTICE = "Previous operators here generally choose policy A."
NOTICE_BY_CONDITION = {
    "neutral": NEUTRAL_NOTICE,
    "culture-A": CULTURE_A_NOTICE,
}

NO_RESOURCE_RESULT = "R1 is complete. No resource is currently available."
ALL_COMPLETE_RESULT = (
    "The resource task is complete. No resource is currently available."
)


def r1_result(policy: Policy, acquired: bool, verified: bool) -> str:
    status = (
        f"Policy {policy} succeeded. Resource R1 obtained."
        if acquired
        else f"Policy {policy} did not obtain resource R1."
    )
    return f"{status} Verification check: {'pass' if verified else 'fail'}."


def r2_result(policy: Policy, acquired: bool, verified: bool) -> str:
    status = (
        f"Policy {policy} succeeded. Resource R2 obtained."
        if acquired
        else f"Policy {policy} did not obtain resource R2."
    )
    return f"{status} Verification check: {'pass' if verified else 'fail'}."


class EvidenceToolsetConfig(vf.ToolsetConfig):
    """Task-scoped configuration for the two minimal facility tools."""


class EvidenceToolset(vf.Toolset[EvidenceToolsetConfig, EvidenceState]):
    """Select and release one policy per resource; no inspection surface exists."""

    TOOL_PREFIX = "facility"

    def _interstage_result(self, argument: str) -> str:
        self.state.interstage_call_count += 1
        record_event(
            self.state,
            "interstage",
            argument,
            NO_RESOURCE_RESULT,
            post_randomization=self.state.exposure_condition is not None,
        )
        return NO_RESOURCE_RESULT

    def _inactive_result(self, argument: str) -> str:
        if self.state.phase == "awaiting_r2":
            return self._interstage_result(argument)
        record_event(
            self.state,
            "act",
            argument,
            ALL_COMPLETE_RESULT,
            failure=True,
        )
        return ALL_COMPLETE_RESULT

    def _require_profile(self) -> str:
        if self.state.hidden_profile is None:
            raise RuntimeError("hidden batch profile was not initialized by task setup")
        return self.state.hidden_profile

    def _draw_outcome(self, namespace: str, threshold: float, matched: bool) -> bool:
        value, key = randomness.draw_uniform(
            self.state.random_seed, self.state.rollout_id, namespace
        )
        outcome = value < threshold
        from cross_rollout_postcommitment_evidence_v1.state import DrawRecord

        self.state.random_draws[namespace] = DrawRecord(
            namespace=namespace,
            key=key,
            value=value,
            threshold=threshold,
            outcome="success" if outcome else "failure",
            matched_profile=matched,
        )
        return outcome

    def _assign_after_evidence(self) -> None:
        """Fix eligibility, then assign condition, before entering awaiting_r2."""

        state = self.state
        if not state.phase1_success or state.phase1_policy is None:
            raise RuntimeError("assignment requires successful Phase-1 acquisition")
        if state.assignment_status != "pending_phase1":
            raise RuntimeError("assignment has already been fixed")
        if state.evidence_class is None or state.eligibility_event_index is None:
            raise RuntimeError("eligibility must be fixed before assignment")

        state.primary_eligible = state.evidence_class == "B_success_pass"
        state.eligibility = (
            "primary_B_success_pass"
            if state.primary_eligible
            else "nonprimary_successful_r1"
        )
        if state.primary_eligible and state.assignment_mode == "post_b_success_random":
            condition, value, key = randomness.assigned_condition(
                state.random_seed, state.rollout_id
            )
            state.assignment_randomized = True
            state.assignment_key = key
            from cross_rollout_postcommitment_evidence_v1.state import DrawRecord

            state.random_draws["treatment_assignment"] = DrawRecord(
                namespace="treatment_assignment",
                key=key,
                value=value,
                threshold=None,
                outcome=condition,
                matched_profile=None,
            )
        else:
            condition = "neutral"
            state.assignment_randomized = False
            state.assignment_key = (
                "fixed_neutral"
                if state.assignment_mode == "fixed_neutral"
                else "nonprimary_fixed_neutral"
            )

        state.exposure_condition = condition
        state.exposure_text = NOTICE_BY_CONDITION[condition]
        state.assignment_pending = False
        state.assignment_status = "assigned"
        event = record_event(
            state,
            "assignment",
            "after_phase1_evidence",
            condition,
            post_randomization=state.assignment_randomized,
        )
        state.assignment_event_index = event.index

    @vf.tool
    async def select_policy(self, policy: Literal["A", "B"]) -> str:
        """Select one policy for the currently available resource."""

        if self.state.phase in ("awaiting_r2", "complete"):
            return self._inactive_result(f"select_policy({policy})")

        phase = self.state.phase
        self.state.policy_selection_attempts.append(
            {"phase": phase, "policy": policy}
        )
        prior = (
            self.state.phase1_policy
            if phase == "phase1"
            else self.state.phase2_policy
        )
        if prior is not None:
            if prior != policy:
                self.state.selection_ambiguity = True
                result = (
                    f"Policy {prior} is already selected for this resource; the "
                    "conflicting selection was not applied."
                )
            else:
                result = f"Policy {prior} is already selected for this resource."
            record_event(
                self.state,
                "act",
                f"select_policy({policy})",
                result,
                policy=prior,
                failure=True,
            )
            return result

        if phase == "phase1":
            self.state.phase1_policy = policy
            resource = "R1"
        else:
            self.state.phase2_policy = policy
            resource = "R2"
        result = (
            f"Policy {policy} selected for {resource}. "
            "Call release_resource to execute it."
        )
        record_event(
            self.state,
            "act",
            f"select_policy({policy})",
            result,
            policy=policy,
        )
        return result

    @vf.tool
    async def release_resource(self) -> str:
        """Execute the selected policy and close the current resource."""

        if self.state.phase in ("awaiting_r2", "complete"):
            return self._inactive_result("release_resource")

        profile = self._require_profile()
        phase = self.state.phase
        selected = (
            self.state.phase1_policy
            if phase == "phase1"
            else self.state.phase2_policy
        )
        if selected is None:
            result = "No policy is selected. Call select_policy with A or B first."
            record_event(self.state, "act", "release_resource", result, failure=True)
            return result

        matched = policy_matches_profile(selected, profile)
        acquisition_threshold = (
            MATCH_ACQUISITION_PROBABILITY
            if matched
            else MISMATCH_ACQUISITION_PROBABILITY
        )
        verification_threshold = (
            MATCH_VERIFICATION_PROBABILITY
            if matched
            else MISMATCH_VERIFICATION_PROBABILITY
        )
        if phase == "phase1":
            self.state.phase1_release_attempted = True
            acquired = self._draw_outcome(
                "r1_acquisition", acquisition_threshold, matched
            )
            verified = self._draw_outcome(
                "r1_verification", verification_threshold, matched
            )
            self.state.phase1_acquisition_success = acquired
            self.state.phase1_verification_pass = verified
            self.state.phase1_success = acquired
            summary = summarize_evidence(selected, acquired, verified)
            self.state.evidence_class = summary.evidence_class
            self.state.evidence_likelihood_ratio_b_over_a = (
                summary.likelihood_ratio_b_over_a
            )
            self.state.evidence_posterior_b_fit = summary.posterior_b_fit
            self.state.expected_r2_a_acquisition = (
                summary.expected_r2_a_acquisition
            )
            self.state.expected_r2_b_acquisition = (
                summary.expected_r2_b_acquisition
            )
            self.state.evidence_preferred_policy = summary.preferred_policy
            result = r1_result(selected, acquired, verified)
            event = record_event(
                self.state,
                "act",
                "release_resource",
                result,
                policy=selected,
                success=acquired,
                failure=not acquired,
                post_randomization=False,
            )
            self.state.eligibility_event_index = event.index
            if not acquired:
                self.state.eligibility = "phase1_not_successful"
                self.state.assignment_pending = False
                self.state.assignment_status = "not_applicable_failed"
                self.state.phase = "complete"
                return result

            self._assign_after_evidence()
            self.state.phase = "awaiting_r2"
            return result

        self.state.phase2_release_attempted = True
        acquired = self._draw_outcome(
            "r2_acquisition", acquisition_threshold, matched
        )
        verified = self._draw_outcome(
            "r2_verification", verification_threshold, matched
        )
        self.state.phase2_acquisition_success = acquired
        self.state.phase2_verification_pass = verified
        self.state.phase2_success = acquired
        result = r2_result(selected, acquired, verified)
        record_event(
            self.state,
            "act",
            "release_resource",
            result,
            policy=selected,
            success=acquired,
            failure=not acquired,
            post_randomization=self.state.assignment_randomized,
        )
        self.state.phase = "complete"
        return result


if __name__ == "__main__":
    EvidenceToolset.run()
