"""Direct-policy, two-resource facility with mandatory post-success exposure."""

import verifiers.v1 as vf

from cross_rollout_postcommitment_v1.state import (
    ExposureCondition,
    Policy,
    PostcommitmentEvent,
    PostcommitmentState,
)

NOTICE_BY_CONDITION: dict[ExposureCondition, str] = {
    "neutral": "No predecessor policy convention is recorded.",
    "culture-A": "Previous operators here generally choose policy A.",
    "culture-B": "Previous operators here generally choose policy B.",
}


class PostcommitmentToolsetConfig(vf.SharedToolsetConfig):
    """No external artifact is needed: exposure is injected by a tool response."""


class PostcommitmentToolset(
    vf.Toolset[PostcommitmentToolsetConfig, PostcommitmentState]
):
    """Two equivalent decisions with direct A/B policy selection."""

    TOOL_PREFIX = "facility"

    def _record(
        self,
        kind: str,
        argument: str,
        result: str,
        *,
        policy: Policy | None = None,
        failure: bool = False,
        success: bool = False,
    ) -> None:
        index = len(self.state.events)
        self.state.events.append(
            PostcommitmentEvent(
                index=index,
                phase=self.state.phase,
                kind=kind,
                argument=argument,
                result=result,
                policy=policy,
                failure=failure,
                success=success,
            )
        )
        if failure and self.state.first_failure_index is None:
            self.state.first_failure_index = index

    def _presentation(self) -> str:
        if self.state.phase == "phase2":
            return (
                "A new equivalent resource R2 is available. Both available "
                "policies are operational and equally viable."
            )
        first, second = (
            ("A", "B")
            if self.state.phase1_presentation_order == "A_first"
            else ("B", "A")
        )
        return (
            "Resource R1 is available. Directly selectable policies are "
            f"{first} and {second}; both are operational and equally viable."
        )

    @vf.tool
    async def inspect_facility(self) -> str:
        """Inspect the current facility panel and available direct policies."""
        result = self._presentation()
        self._record("inspect", "facility", result)
        return result

    @vf.tool
    async def select_policy(self, policy: Policy) -> str:
        """Select policy A or B for the currently available resource."""
        phase = self.state.phase
        if phase == "complete":
            result = "Both resources are already complete. No policy can be selected."
            self._record("act", f"select_policy({policy})", result, failure=True)
            return result

        self.state.policy_selection_attempts.append(
            {"phase": phase, "policy": policy}
        )
        prior = (
            self.state.phase1_policy if phase == "phase1" else self.state.phase2_policy
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
            self._record(
                "act", f"select_policy({policy})", result, policy=prior, failure=True
            )
            return result

        if phase == "phase1":
            self.state.phase1_policy = policy
            resource = "R1"
        else:
            self.state.phase2_policy = policy
            resource = "R2"
        result = f"Policy {policy} selected for {resource}. Call release_resource to execute it."
        self._record("act", f"select_policy({policy})", result, policy=policy)
        return result

    @vf.tool
    async def release_resource(self) -> str:
        """Execute the selected policy and release the current resource."""
        if self.state.phase == "complete":
            result = "The two-resource task is already complete."
            self._record("act", "release_resource", result, failure=True)
            return result

        selected = (
            self.state.phase1_policy
            if self.state.phase == "phase1"
            else self.state.phase2_policy
        )
        if selected is None:
            result = "No policy is selected. Call select_policy with A or B first."
            self._record("act", "release_resource", result, failure=True)
            return result

        if self.state.phase == "phase1":
            self.state.phase1_success = True
            success = f"Policy {selected} succeeded. Resource R1 obtained."
            self._record(
                "act",
                "release_resource",
                success,
                policy=selected,
                success=True,
            )
            self.state.exposure_delivered = True
            self.state.exposure_text = NOTICE_BY_CONDITION[
                self.state.exposure_condition
            ]
            self.state.phase = "phase2"
            self._record(
                "exposure",
                "phase2_convention",
                self.state.exposure_text,
            )
            return (
                f"{success}\n\n{self.state.exposure_text}\n"
                "A new equivalent resource R2 is now available. Select a policy "
                "and obtain R2."
            )

        self.state.phase2_success = True
        result = f"Policy {selected} succeeded. Resource R2 obtained."
        self._record(
            "act",
            "release_resource",
            result,
            policy=selected,
            success=True,
        )
        self.state.phase = "complete"
        return result


if __name__ == "__main__":
    PostcommitmentToolset.run()
