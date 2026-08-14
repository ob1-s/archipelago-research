"""Schema-controlled, label-neutral Phase-1 MCP facility."""

# Intentionally no ``from __future__ import annotations`` in this module.  The four
# exposed select_policy signatures must carry concrete Literal objects through FastMCP.

import json
import os
from typing import Literal

import verifiers.v1 as vf

from ..constants import (
    MATCH_ACQUISITION_PROBABILITY,
    MATCH_VERIFICATION_PROBABILITY,
    MISMATCH_ACQUISITION_PROBABILITY,
    MISMATCH_VERIFICATION_PROBABILITY,
)
from ..randomness import draw_uniform
from ..state import DrawRecord, LabelDiagnosticState, record_event


class DiagnosticToolsetConfig(vf.ToolsetConfig):
    variant: Literal["AB_A", "AB_B", "KM_K", "KM_M"] = "AB_A"


class _BaseFacility(vf.Toolset[DiagnosticToolsetConfig, LabelDiagnosticState]):
    TOOL_PREFIX = "policy_facility"

    async def _select(self, policy: str) -> str:
        state = self.state
        if state.phase == "complete":
            result = "The current resource is already closed."
            record_event(state, "select_policy", result, failure=True)
            return result
        state.first_select_call_seen = True
        if state.phase1_policy is not None:
            state.selection_ambiguity = state.phase1_policy != policy
            result = "A policy is already selected for the current resource."
            record_event(
                state,
                "select_policy",
                result,
                policy=policy,
                failure=True,
            )
            return result
        state.phase1_policy = policy
        state.policy_selection_attempts.append({"phase": "phase1", "policy": policy})
        result = "Policy selected for R1. Call release_resource to execute it."
        record_event(state, "select_policy", result, policy=policy)
        return result

    @vf.tool
    async def release_resource(self) -> str:
        """Execute the selected policy and close the current resource."""

        state = self.state
        if state.phase == "complete":
            result = "The current resource is already closed."
            record_event(state, "release_resource", result, failure=True)
            return result
        selected = state.phase1_policy
        if selected is None or state.hidden_profile is None:
            result = "No policy is selected. Call select_policy before releasing."
            record_event(state, "release_resource", result, failure=True)
            return result
        state.phase1_release_attempted = True
        semantic_slot = (
            "policy_1"
            if (state.label_set, selected) in (("AB", "A"), ("KM", "K"))
            else "policy_2"
        )
        matched = (
            semantic_slot == "policy_1"
            and state.hidden_profile == "policy_1_fit"
        ) or (
            semantic_slot == "policy_2"
            and state.hidden_profile == "policy_2_fit"
        )
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
        acquisition, acquisition_key = draw_uniform(
            state.random_seed, state.rollout_id, "r1_acquisition"
        )
        verification, verification_key = draw_uniform(
            state.random_seed, state.rollout_id, "r1_verification"
        )
        acquired = acquisition < acquisition_threshold
        verified = verification < verification_threshold
        state.random_draws["r1_acquisition"] = DrawRecord(
            namespace="r1_acquisition",
            key=acquisition_key,
            value=acquisition,
            threshold=acquisition_threshold,
            outcome="success" if acquired else "failure",
            matched_profile=matched,
        )
        state.random_draws["r1_verification"] = DrawRecord(
            namespace="r1_verification",
            key=verification_key,
            value=verification,
            threshold=verification_threshold,
            outcome="success" if verified else "failure",
            matched_profile=matched,
        )
        state.phase1_acquisition_success = acquired
        state.phase1_verification_pass = verified
        state.phase1_success = acquired
        state.phase = "complete"
        result = (
            "Resource R1 attempt completed. "
            f"Acquisition: {'succeeded' if acquired else 'failed'}. "
            f"Verification: {'pass' if verified else 'fail'}."
        )
        record_event(
            state,
            "release_resource",
            result,
            policy=selected,
            success=acquired,
            failure=not acquired,
        )
        return result


class ABASchemaFacility(_BaseFacility):
    @vf.tool
    async def select_policy(self, policy: Literal["A", "B"]) -> str:
        """Select one operating policy for the current resource."""

        return await self._select(policy)


class ABBSchemaFacility(_BaseFacility):
    @vf.tool
    async def select_policy(self, policy: Literal["B", "A"]) -> str:
        """Select one operating policy for the current resource."""

        return await self._select(policy)


class KMKSchemaFacility(_BaseFacility):
    @vf.tool
    async def select_policy(self, policy: Literal["K", "M"]) -> str:
        """Select one operating policy for the current resource."""

        return await self._select(policy)


class KMMESchemaFacility(_BaseFacility):
    @vf.tool
    async def select_policy(self, policy: Literal["M", "K"]) -> str:
        """Select one operating policy for the current resource."""

        return await self._select(policy)


TOOLSET_BY_VARIANT = {
    "AB_A": ABASchemaFacility,
    "AB_B": ABBSchemaFacility,
    "KM_K": KMKSchemaFacility,
    "KM_M": KMMESchemaFacility,
}


def run_variant_server() -> None:
    raw = os.environ.get("VF_CONFIG", "{}")
    config = DiagnosticToolsetConfig.model_validate(json.loads(raw))
    server_cls = TOOLSET_BY_VARIANT[config.variant]
    server_cls(config)._serve()


if __name__ == "__main__":
    run_variant_server()
