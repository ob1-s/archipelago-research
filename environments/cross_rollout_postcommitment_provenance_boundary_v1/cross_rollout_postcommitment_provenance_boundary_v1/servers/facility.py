"""Minimal two-tool facility for the provenance-boundary assay."""

import verifiers.v1 as vf

from .. import assignment, randomness
from ..constants import (
    MATCH_ACQUISITION_PROBABILITY,
    MATCH_VERIFICATION_PROBABILITY,
    MISMATCH_ACQUISITION_PROBABILITY,
    MISMATCH_VERIFICATION_PROBABILITY,
    Policy,
)
from ..evidence import Profile, policy_matches_profile, summarize_evidence
from ..state import BoundaryState, DrawRecord, record_event

NO_RESOURCE_RESULT = "R1 is complete. No resource is currently available."
ALL_COMPLETE_RESULT = "The resource task is complete. No resource is currently available."


def resource_result(resource: str, policy: Policy, acquired: bool, verified: bool) -> str:
    status = (
        f"Policy {policy} succeeded. Resource {resource} obtained."
        if acquired
        else f"Policy {policy} did not obtain resource {resource}."
    )
    return f"{status} Verification check: {'pass' if verified else 'fail'}."


class BoundaryToolsetConfig(vf.ToolsetConfig):
    """No model-visible configuration knobs are needed."""


class BoundaryToolset(vf.Toolset[BoundaryToolsetConfig, BoundaryState]):
    """Select and release exactly one policy for each available resource."""

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
        record_event(self.state, "act", argument, ALL_COMPLETE_RESULT, failure=True)
        return ALL_COMPLETE_RESULT

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

    def _profile(self) -> Profile:
        if self.state.hidden_profile is None:
            raise RuntimeError("hidden batch profile was not initialized")
        return self.state.hidden_profile

    def _set_evidence(self, policy: Policy, acquired: bool, verified: bool) -> None:
        summary = summarize_evidence(policy, acquired, verified)
        self.state.evidence_class = summary.evidence_class
        self.state.evidence_supported_policy = summary.selected_policy
        self.state.alternative_policy = summary.alternative_policy
        self.state.evidence_likelihood_ratio_selected_over_alternative = (
            summary.likelihood_ratio_selected_over_alternative
        )
        self.state.evidence_posterior_selected_fit = summary.posterior_selected_fit
        self.state.expected_selected_r2_acquisition = (
            summary.expected_selected_r2_acquisition
        )
        self.state.expected_alternative_r2_acquisition = (
            summary.expected_alternative_r2_acquisition
        )

    def _assign_primary(self) -> None:
        state = self.state
        if state.eligibility != "primary_eligible":
            raise RuntimeError("source assignment requires fixed primary eligibility")
        allocation = assignment.claim_assignment(
            state.assignment_state_path, state.assignment_seed
        )
        state.eligible_index = allocation.eligible_index
        state.assignment_block_index = allocation.block_index
        state.assignment_slot = allocation.slot
        state.assignment_status = "assigned_randomized"
        state.assignment_randomized = True
        state.assignment_key = allocation.assignment_order_key
        state.source_pair_id = allocation.pair_id
        state.source_pair_key = allocation.source_pair_key
        state.assignment_order_key = allocation.assignment_order_key
        state.advisory_reliability = allocation.advisory_reliability
        state.source_condition = allocation.source_condition
        state.phase2_presentation_order = allocation.phase2_order
        record = record_event(
            state,
            "assignment",
            "after_primary_evidence",
            allocation.source_condition,
            post_randomization=True,
        )
        state.assignment_event_index = record.index

    @vf.tool
    async def select_policy(self, policy: str) -> str:
        """Select one operating policy for the current resource."""

        state = self.state
        if state.phase in ("awaiting_r2", "complete"):
            return self._inactive_result(f"select_policy({policy})")

        state.policy_selection_attempts.append(
            {"phase": state.phase, "policy": policy}
        )
        if state.phase == "phase1":
            if state.first_phase1_policy_call is None:
                state.first_phase1_policy_call = policy
                if policy not in ("K", "M"):
                    state.phase1_selection_invalid = True
                    state.eligibility = "invalid_first_policy"
                    result = (
                        "The first policy selection was invalid. R1 cannot be "
                        "selected after an invalid first choice."
                    )
                    record_event(state, "act", "select_policy", result, failure=True)
                    return result
                state.phase1_first_call_valid = True
                state.phase1_policy = policy
                result = (
                    f"Policy {policy} selected for R1. "
                    "Call release_resource to execute it."
                )
                record_event(state, "act", "select_policy", result, policy=policy)
                return result
            prior = state.phase1_policy
            if prior != policy:
                state.selection_ambiguity = True
            result = "The first R1 policy selection remains authoritative."
            record_event(state, "act", "select_policy", result, policy=prior, failure=True)
            return result

        if state.first_phase2_policy_call is None:
            state.first_phase2_policy_call = policy
            if policy not in ("K", "M"):
                state.phase2_selection_invalid = True
                result = (
                    "The first policy selection was invalid. R2 cannot be selected "
                    "after an invalid first choice."
                )
                record_event(state, "act", "select_policy", result, failure=True)
                return result
            state.phase2_first_call_valid = True
            state.phase2_policy = policy
            state.primary_switch = policy != state.evidence_supported_policy
            state.primary_itt_switch = bool(state.primary_switch)
            result = (
                f"Policy {policy} selected for R2. "
                "Call release_resource to execute it."
            )
            record_event(state, "act", "select_policy", result, policy=policy)
            return result
        prior = state.phase2_policy
        if prior != policy:
            state.selection_ambiguity = True
        result = "The first R2 policy selection remains authoritative."
        record_event(state, "act", "select_policy", result, policy=prior, failure=True)
        return result

    @vf.tool
    async def release_resource(self) -> str:
        """Execute the selected policy and close the current resource."""

        state = self.state
        if state.phase in ("awaiting_r2", "complete"):
            return self._inactive_result("release_resource")

        profile = self._profile()
        if state.phase == "phase1":
            state.phase1_release_attempted = True
            if state.phase1_policy is None or state.phase1_selection_invalid:
                state.assignment_status = "not_applicable_invalid"
                state.phase = "complete"
                result = "R1 could not be executed after the invalid first policy selection."
                record_event(state, "act", "release_resource", result, failure=True)
                return result
            selected = state.phase1_policy
            matched = policy_matches_profile(selected, profile)
            acquired = self._draw_outcome(
                "r1_acquisition",
                MATCH_ACQUISITION_PROBABILITY
                if matched
                else MISMATCH_ACQUISITION_PROBABILITY,
                matched,
            )
            verified = self._draw_outcome(
                "r1_verification",
                MATCH_VERIFICATION_PROBABILITY
                if matched
                else MISMATCH_VERIFICATION_PROBABILITY,
                matched,
            )
            state.phase1_acquisition_success = acquired
            state.phase1_verification_pass = verified
            state.phase1_success = acquired
            self._set_evidence(selected, acquired, verified)
            result = resource_result("R1", selected, acquired, verified)
            event = record_event(
                state,
                "act",
                "release_resource",
                result,
                policy=selected,
                success=acquired,
                failure=not acquired,
                post_randomization=False,
            )
            state.eligibility_event_index = event.index
            if not acquired:
                state.eligibility = "phase1_not_successful"
                state.assignment_status = "not_applicable_failed"
                state.phase = "complete"
                return result
            if not verified:
                state.eligibility = "success_verification_fail"
                state.assignment_status = "not_applicable_failed"
                state.phase = "complete"
                return result
            state.primary_eligible = True
            state.eligibility = "primary_eligible"
            self._assign_primary()
            state.phase = "awaiting_r2"
            return result

        state.phase2_release_attempted = True
        if state.phase2_policy is None or state.phase2_selection_invalid:
            state.phase = "complete"
            state.phase2_missing = True
            result = "R2 could not be executed after the invalid first policy selection."
            record_event(state, "act", "release_resource", result, failure=True)
            return result
        selected = state.phase2_policy
        matched = policy_matches_profile(selected, profile)
        acquired = self._draw_outcome(
            "r2_acquisition",
            MATCH_ACQUISITION_PROBABILITY
            if matched
            else MISMATCH_ACQUISITION_PROBABILITY,
            matched,
        )
        verified = self._draw_outcome(
            "r2_verification",
            MATCH_VERIFICATION_PROBABILITY
            if matched
            else MISMATCH_VERIFICATION_PROBABILITY,
            matched,
        )
        state.phase2_acquisition_success = acquired
        state.phase2_verification_pass = verified
        state.phase2_success = acquired
        result = resource_result("R2", selected, acquired, verified)
        record_event(
            state,
            "act",
            "release_resource",
            result,
            policy=selected,
            success=acquired,
            failure=not acquired,
            post_randomization=True,
        )
        state.phase = "complete"
        state.primary_switch = selected != state.evidence_supported_policy
        state.primary_itt_switch = bool(state.primary_switch)
        return result


if __name__ == "__main__":
    BoundaryToolset.run()
