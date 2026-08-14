"""Facility tools for the no-culture native transition diagnostic."""

import verifiers.v1 as vf

from cross_rollout_postcommitment_transition_diagnostic_v1.state import (
    Policy,
    TransitionDiagnosticState,
    record_event,
)

R1_A_SUCCESS_RESULT = "Policy A succeeded. Resource R1 obtained."
R1_B_SUCCESS_RESULT = "Policy B succeeded. Resource R1 obtained."
NO_RESOURCE_RESULT = "R1 is complete. No resource is currently available."
ALL_COMPLETE_RESULT = (
    "The resource task is complete. No resource is currently available."
)


class TransitionDiagnosticToolsetConfig(vf.ToolsetConfig):
    """Task-scoped facility tool server configuration."""


class TransitionDiagnosticToolset(
    vf.Toolset[TransitionDiagnosticToolsetConfig, TransitionDiagnosticState]
):
    """Two equivalent choices separated by environment-controlled R2 activation."""

    TOOL_PREFIX = "facility"

    def _interstage_result(self, argument: str) -> str:
        self.state.interstage_call_count += 1
        record_event(
            self.state,
            "interstage",
            argument,
            NO_RESOURCE_RESULT,
        )
        return NO_RESOURCE_RESULT

    def _inactive_result(self, kind: str, argument: str) -> str:
        if self.state.phase == "awaiting_r2":
            return self._interstage_result(argument)
        record_event(
            self.state,
            kind,  # type: ignore[arg-type]
            argument,
            ALL_COMPLETE_RESULT,
            failure=True,
        )
        return ALL_COMPLETE_RESULT

    @vf.tool
    async def inspect_facility(self) -> str:
        """Inspect the currently available resource and policies."""

        if self.state.phase in ("awaiting_r2", "complete"):
            return self._inactive_result("inspect", "facility")
        first, second = (
            ("A", "B")
            if (
                self.state.phase == "phase1"
                and self.state.phase1_presentation_order == "A_first"
            )
            or (
                self.state.phase == "phase2"
                and self.state.phase2_presentation_order == "A_first"
            )
            else ("B", "A")
        )
        resource = "R1" if self.state.phase == "phase1" else "R2"
        result = (
            f"Resource {resource} is available. Directly selectable policies are "
            f"{first} and {second}; both are operational and equally viable."
        )
        record_event(self.state, "inspect", "facility", result)
        return result

    @vf.tool
    async def select_policy(self, policy: Policy) -> str:
        """Select policy A or B for the currently available resource."""

        phase = self.state.phase
        if phase in ("awaiting_r2", "complete"):
            return self._inactive_result("act", f"select_policy({policy})")

        self.state.policy_selection_attempts.append({"phase": phase, "policy": policy})
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
        """Execute the selected policy and release the current resource."""

        phase = self.state.phase
        if phase in ("awaiting_r2", "complete"):
            return self._inactive_result("act", "release_resource")

        selected = (
            self.state.phase1_policy if phase == "phase1" else self.state.phase2_policy
        )
        if selected is None:
            result = "No policy is selected. Call select_policy with A or B first."
            record_event(
                self.state,
                "act",
                "release_resource",
                result,
                failure=True,
            )
            return result

        if phase == "phase1":
            self.state.phase1_success = True
            result = R1_A_SUCCESS_RESULT if selected == "A" else R1_B_SUCCESS_RESULT
            record_event(
                self.state,
                "act",
                "release_resource",
                result,
                policy=selected,
                success=True,
            )
            self.state.phase = "awaiting_r2"
            return result

        self.state.phase2_success = True
        result = f"Policy {selected} succeeded. Resource R2 obtained."
        record_event(
            self.state,
            "act",
            "release_resource",
            result,
            policy=selected,
            success=True,
        )
        self.state.phase = "complete"
        return result


if __name__ == "__main__":
    TransitionDiagnosticToolset.run()
