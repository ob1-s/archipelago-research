"""Minimal facility tools for the evidence-relative native lifecycle."""

from typing import Literal

import verifiers.v1 as vf

from cross_rollout_postcommitment_evidence_relative_v1 import assignment, randomness
from cross_rollout_postcommitment_evidence_relative_v1.assignment import Condition
from cross_rollout_postcommitment_evidence_relative_v1.evidence import (
    MATCH_ACQUISITION_PROBABILITY,
    MATCH_VERIFICATION_PROBABILITY,
    MISMATCH_ACQUISITION_PROBABILITY,
    MISMATCH_VERIFICATION_PROBABILITY,
    policy_matches_profile,
    summarize_evidence,
)
from cross_rollout_postcommitment_evidence_relative_v1.state import (
    DrawRecord,
    Policy,
    RelativeState,
    record_event,
)

NEUTRAL_PREDECESSOR_SENTENCE = (
    "In the recorded predecessor history for this resource class, 5 of the last "
    "10 operators chose policy A and 5 chose policy B."
)
OPPOSING_A_PREDECESSOR_SENTENCE = (
    "In the recorded predecessor history for this resource class, 2 of the last "
    "10 operators chose policy A and 8 chose policy B."
)
OPPOSING_B_PREDECESSOR_SENTENCE = (
    "In the recorded predecessor history for this resource class, 8 of the last "
    "10 operators chose policy A and 2 chose policy B."
)

NO_RESOURCE_RESULT = "R1 is complete. No resource is currently available."
ALL_COMPLETE_RESULT = (
    "The resource task is complete. No resource is currently available."
)


def predecessor_sentence(condition: Condition, evidence_policy: Policy) -> str:
    if condition == "neutral":
        return NEUTRAL_PREDECESSOR_SENTENCE
    return (
        OPPOSING_A_PREDECESSOR_SENTENCE
        if evidence_policy == "A"
        else OPPOSING_B_PREDECESSOR_SENTENCE
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


class RelativeToolsetConfig(vf.ToolsetConfig):
    """Task-scoped configuration for the two minimal facility tools."""


class RelativeToolset(vf.Toolset[RelativeToolsetConfig, RelativeState]):
    """Select and release one policy per resource; no inspection surface exists."""

    TOOL_PREFIX = "facility"

    def _interstage_result(self, argument: str) -> str:
        self.state.interstage_call_count += 1
        record_event(
            self.state,
            "interstage",
            argument,
            NO_RESOURCE_RESULT,
            post_randomization=self.state.assignment_randomized,
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
        self.state.random_draws[namespace] = DrawRecord(
            namespace=namespace,
            key=key,
            value=value,
            threshold=threshold,
            outcome="success" if outcome else "failure",
            matched_profile=matched,
        )
        return outcome

    def _close_nonprimary(self, status: Literal[
        "not_applicable_nonprimary", "not_applicable_failed"
    ]) -> None:
        self.state.primary_eligible = False
        self.state.assignment_pending = False
        self.state.assignment_status = status
        self.state.phase = "complete"

    def _assign_after_primary_evidence(self) -> None:
        """Fix eligibility, then claim one blocked randomized assignment."""

        state = self.state
        if not state.phase1_success or not state.phase1_verification_pass:
            raise RuntimeError("primary assignment requires success and verification pass")
        if state.phase1_policy is None or state.evidence_class is None:
            raise RuntimeError("primary assignment requires a selected Phase-1 policy")
        if state.assignment_status != "pending_phase1":
            raise RuntimeError("assignment has already been fixed")
        if state.eligibility_event_index is None:
            raise RuntimeError("eligibility must be fixed before assignment")

        state.primary_eligible = True
        state.eligibility = "primary_eligible"
        selected = state.phase1_policy
        state.evidence_supported_policy = selected
        state.alternative_policy = "B" if selected == "A" else "A"
        allocated = assignment.claim_assignment(
            state.assignment_state_path, state.assignment_seed
        )
        state.eligible_index = allocated.eligible_index
        state.assignment_block_index = allocated.block_index
        state.assignment_slot = allocated.slot
        state.exposure_condition = allocated.condition
        state.phase2_presentation_order = allocated.phase2_order
        state.assignment_randomized = True
        state.assignment_key = (
            f"eligible_index={allocated.eligible_index};"
            f"block={allocated.block_index};slot={allocated.slot}"
        )
        state.random_draws["treatment_assignment"] = DrawRecord(
            namespace="treatment_assignment",
            key=allocated.treatment_key,
            value=allocated.treatment_value,
            threshold=None,
            outcome=allocated.condition,
            matched_profile=None,
        )
        state.random_draws["phase2_assignment_block"] = DrawRecord(
            namespace="phase2_assignment_block",
            key=allocated.phase2_key,
            value=allocated.phase2_value,
            threshold=None,
            outcome=allocated.phase2_order,
            matched_profile=None,
        )
        state.exposure_text = predecessor_sentence(
            allocated.condition, selected
        )
        state.assignment_pending = False
        state.assignment_status = "assigned"
        event = record_event(
            state,
            "assignment",
            "after_primary_evidence",
            allocated.condition,
            post_randomization=True,
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
            self.state.expected_r2_a_acquisition = summary.expected_r2_a_acquisition
            self.state.expected_r2_b_acquisition = summary.expected_r2_b_acquisition
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
                self._close_nonprimary("not_applicable_failed")
                self.state.eligibility = "phase1_not_successful"
                return result
            if not verified:
                self._close_nonprimary("not_applicable_nonprimary")
                self.state.eligibility = "nonprimary_success_verification_fail"
                return result

            self._assign_after_primary_evidence()
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
        self.state.primary_switch = selected != self.state.evidence_supported_policy
        self.state.primary_itt_switch = bool(self.state.primary_switch)
        return result


if __name__ == "__main__":
    RelativeToolset.run()
