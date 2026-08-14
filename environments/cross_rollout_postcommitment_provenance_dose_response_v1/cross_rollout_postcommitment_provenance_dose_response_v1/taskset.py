"""Native provenance dose-response taskset with the frozen two-turn lifecycle."""

from __future__ import annotations

import json

import verifiers.v1 as vf
from verifiers.v1.harnesses.null import NullHarnessConfig

from . import assignment, randomness
from .constants import PolicyOrder, phase1_prompt, phase2_prompt
from .schedule import (
    MAX_ATTEMPTS,
    SCHEDULE_SEED,
    TARGET_PRIMARY_ELIGIBLE,
    build_schedule,
)
from .servers.facility import DoseResponseToolset, DoseResponseToolsetConfig
from .state import DoseResponseState, DrawRecord, record_event


def activate_r2(state: DoseResponseState) -> None:
    """The only transition that makes R2 available to model-visible tools."""

    if state.phase != "awaiting_r2":
        raise RuntimeError("R2 activation requires awaiting_r2")
    if state.source_condition is None or state.advisory_reliability is None:
        raise RuntimeError("R2 activation requires fixed source and reliability")
    if state.phase2_presentation_order is None:
        raise RuntimeError("R2 activation requires fixed Phase-2 order")
    if state.assignment_status != "assigned_randomized":
        raise RuntimeError("R2 activation requires completed assignment")
    if state.r2_activated:
        raise RuntimeError("R2 has already been activated")
    assigned = (
        state.source_condition,
        state.advisory_reliability,
        state.phase2_presentation_order,
    )
    state.r2_activated = True
    state.phase = "phase2"
    record_event(
        state,
        "env_activate_r2",
        "activate_r2",
        "Resource R2 activated by environment control flow.",
        post_randomization=True,
    )
    if (
        state.source_condition,
        state.advisory_reliability,
        state.phase2_presentation_order,
    ) != assigned:
        raise RuntimeError("R2 activation changed assignment")


class DoseResponseTaskData(vf.TaskData):
    attempt_index: int
    random_seed: str
    assignment_seed: str
    assignment_state_path: str
    phase1_presentation_order: PolicyOrder
    schedule_seed: str
    prompt: str


class DoseResponseTaskConfig(vf.TaskConfig):
    tools: DoseResponseToolsetConfig = DoseResponseToolsetConfig()


class DoseResponseTask(
    vf.Task[DoseResponseTaskData, DoseResponseState, DoseResponseTaskConfig]
):
    @classmethod
    def toolsets(cls, config: DoseResponseTaskConfig) -> list[vf.Toolset]:
        return [DoseResponseToolset(config.tools)]

    async def setup(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        state = trace.state
        state.rollout_id = trace.id
        state.random_seed = self.data.random_seed
        state.assignment_seed = self.data.assignment_seed
        state.assignment_state_path = self.data.assignment_state_path
        state.attempt_index = self.data.attempt_index
        state.phase1_presentation_order = self.data.phase1_presentation_order
        assignment.ensure_assignment_state(
            self.data.assignment_state_path, self.data.assignment_seed
        )
        key = "provenance_dose_response"
        trace.info[key] = {
            "attempt_index": self.data.attempt_index,
            "random_seed": self.data.random_seed,
            "assignment_seed": self.data.assignment_seed,
            "assignment_state_path": self.data.assignment_state_path,
            "schedule_seed": self.data.schedule_seed,
            "phase1_presentation_order": self.data.phase1_presentation_order,
            "prompt": self.data.prompt,
            "random_namespaces": list(randomness.ROLLOUT_NAMESPACES),
            "assignment_namespaces": list(assignment.ASSIGNMENT_NAMESPACES),
            "frozen_profile_prior": {"policy_1_fit": 0.5, "policy_2_fit": 0.5},
            "frozen_probabilities": {
                "match_acquisition": 0.80,
                "mismatch_acquisition": 0.55,
                "match_verification": 0.80,
                "mismatch_verification": 0.30,
            },
            "advisory_reliability_levels": [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80],
            "source_conditions": ["PredecessorSource", "AutomatedSource"],
            "stopping_rule": (
                f"{TARGET_PRIMARY_ELIGIBLE} primary eligible or {MAX_ATTEMPTS} "
                "Phase-1 attempts or apparatus failure"
            ),
            "r2_present_before_activation": False,
            "source_visible_before_eligibility": False,
            "custom_harness_present": False,
            "continuation_nudge_present": False,
        }
        current = assignment.current_eligible_count(
            self.data.assignment_state_path, self.data.assignment_seed
        )
        if current >= TARGET_PRIMARY_ELIGIBLE:
            state.stopped_before_attempt = True
            state.stop_reason = "primary_target_reached_before_attempt"
            state.phase = "complete"
            trace.info[key].update(
                {
                    "stopped_before_attempt": True,
                    "stop_reason": state.stop_reason,
                    "primary_eligible_count_at_setup": current,
                }
            )
            return
        profile, value, draw_key = randomness.hidden_profile(
            self.data.random_seed, trace.id
        )
        state.hidden_profile = profile
        state.random_draws["hidden_profile"] = DrawRecord(
            namespace="hidden_profile",
            key=draw_key,
            value=value,
            threshold=0.5,
            outcome=profile,
            matched_profile=None,
        )
        trace.info[key].update(
            {
                "stopped_before_attempt": False,
                "stop_reason": None,
                "primary_eligible_count_at_setup": current,
            }
        )

    async def finalize(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        state = trace.state
        info = trace.info["provenance_dose_response"]
        if state.stopped_before_attempt:
            info.update(
                {
                    "final_phase": state.phase,
                    "phase1_policy": None,
                    "phase2_policy": None,
                    "choice_calls": [],
                    "stop_reason": state.stop_reason,
                }
            )
            return
        if state.eligibility == "pending_phase1":
            if state.phase1_selection_invalid:
                state.eligibility = "invalid_first_policy"
                state.assignment_status = "not_applicable_invalid"
            elif state.phase1_policy is None or not state.phase1_release_attempted:
                state.eligibility = "phase1_not_successful"
                state.assignment_status = "not_applicable_failed"
        if state.primary_eligible:
            state.phase2_missing = state.phase2_policy is None
            state.phase2_incomplete_after_choice = bool(
                state.phase2_policy is not None and not state.phase2_release_attempted
            )
            state.primary_switch = (
                None
                if state.phase2_policy is None
                else state.phase2_policy != state.evidence_supported_policy
            )
            state.primary_itt_switch = bool(
                state.primary_switch and state.phase2_release_attempted
            )
        choice_calls = _extract_choice_calls(trace, state.turn2_message)
        transition = (
            f"{state.evidence_supported_policy}→{state.phase2_policy}"
            if state.primary_eligible
            and state.evidence_supported_policy is not None
            and state.phase2_policy is not None
            else None
        )
        if state.primary_eligible and state.phase2_missing:
            state.stop_reason = "r2_missing"
        elif state.primary_eligible and state.phase2_release_attempted:
            state.stop_reason = "r2_released"
        elif state.primary_eligible and not state.natural_yield_after_r1:
            state.stop_reason = "no_natural_yield_after_r1"
        elif state.primary_eligible:
            state.stop_reason = "r2_incomplete"
        elif state.eligibility == "success_verification_fail":
            state.stop_reason = "r1_success_verification_fail_closed"
        elif state.eligibility == "invalid_first_policy":
            state.stop_reason = "invalid_first_policy"
        elif state.phase1_release_attempted:
            state.stop_reason = "r1_closed_without_primary_evidence"
        else:
            state.stop_reason = "phase1_incomplete"
        info.update(
            {
                "hidden_profile": state.hidden_profile,
                "random_draws": {
                    namespace: draw.model_dump(mode="json")
                    for namespace, draw in state.random_draws.items()
                },
                "events": [event.model_dump(mode="json") for event in state.events],
                "final_phase": state.phase,
                "phase1_policy": state.phase1_policy,
                "phase2_policy": state.phase2_policy,
                "phase1_success": state.phase1_success,
                "phase1_acquisition_success": state.phase1_acquisition_success,
                "phase1_verification_pass": state.phase1_verification_pass,
                "phase2_success": state.phase2_success,
                "phase2_acquisition_success": state.phase2_acquisition_success,
                "phase2_verification_pass": state.phase2_verification_pass,
                "phase1_release_attempted": state.phase1_release_attempted,
                "phase2_release_attempted": state.phase2_release_attempted,
                "evidence_class": state.evidence_class,
                "evidence_supported_policy": state.evidence_supported_policy,
                "alternative_policy": state.alternative_policy,
                "evidence_likelihood_ratio_selected_over_alternative": state.evidence_likelihood_ratio_selected_over_alternative,
                "evidence_posterior_selected_fit": state.evidence_posterior_selected_fit,
                "expected_selected_r2_acquisition": state.expected_selected_r2_acquisition,
                "expected_alternative_r2_acquisition": state.expected_alternative_r2_acquisition,
                "eligibility": state.eligibility,
                "primary_eligible": state.primary_eligible,
                "eligibility_event_index": state.eligibility_event_index,
                "eligible_index": state.eligible_index,
                "assignment_block_index": state.assignment_block_index,
                "assignment_slot": state.assignment_slot,
                "assignment_status": state.assignment_status,
                "assignment_randomized": state.assignment_randomized,
                "assignment_key": state.assignment_key or None,
                "assignment_order_key": state.assignment_order_key or None,
                "source_pair_key": state.source_pair_key or None,
                "pair_id": state.pair_id or None,
                "source_condition": state.source_condition,
                "advisory_reliability": state.advisory_reliability,
                "source_text": state.source_text,
                "advisory_delivered": state.advisory_delivered,
                "assignment_event_index": state.assignment_event_index,
                "exposure_event_index": state.exposure_event_index,
                "phase2_presentation_order": state.phase2_presentation_order,
                "r2_activated": state.r2_activated,
                "turn2_sent_count": state.turn2_sent_count,
                "turn2_message": state.turn2_message or None,
                "natural_yield_after_r1": state.natural_yield_after_r1,
                "interstage_call_count": state.interstage_call_count,
                "phase2_missing": state.phase2_missing,
                "phase2_incomplete_after_choice": state.phase2_incomplete_after_choice,
                "primary_switch": state.primary_switch,
                "primary_itt_switch": state.primary_itt_switch,
                "primary_itt_not_switch": state.primary_eligible and not state.primary_itt_switch,
                "primary_choice_observed": state.primary_eligible and state.phase2_policy is not None,
                "transition": transition,
                "first_phase1_policy_call": state.first_phase1_policy_call,
                "first_phase2_policy_call": state.first_phase2_policy_call,
                "phase1_first_call_valid": state.phase1_first_call_valid,
                "phase2_first_call_valid": state.phase2_first_call_valid,
                "phase1_selection_invalid": state.phase1_selection_invalid,
                "phase2_selection_invalid": state.phase2_selection_invalid,
                "selection_ambiguity": state.selection_ambiguity,
                "policy_selection_attempts": state.policy_selection_attempts,
                "choice_calls": choice_calls,
                "stop_reason": state.stop_reason,
                "stop_condition": trace.stop_condition,
            }
        )

    @vf.reward
    async def protocol_completion(self, trace: vf.Trace) -> float:
        state = trace.state
        return float(
            not state.stopped_before_attempt
            and state.r2_activated
            and state.phase2_policy is not None
            and state.phase2_release_attempted
        )

    @vf.metric
    async def r1_acquisition(self, trace: vf.Trace) -> float:
        return float(trace.state.phase1_acquisition_success)

    @vf.metric
    async def r1_verification(self, trace: vf.Trace) -> float:
        return float(trace.state.phase1_verification_pass)

    @vf.metric
    async def primary_eligible(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_eligible)

    @vf.metric
    async def primary_itt_switch(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_itt_switch is True)

    @vf.metric
    async def primary_itt_not_switch(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_eligible and not trace.state.primary_itt_switch)

    @vf.metric
    async def primary_choice_observed(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_eligible and trace.state.phase2_policy is not None)

    @vf.metric
    async def phase2_missing(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_eligible and trace.state.phase2_missing)

    @vf.metric
    async def phase2_incomplete_after_choice(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_eligible and trace.state.phase2_incomplete_after_choice)

    @vf.metric
    async def r2_policy_k(self, trace: vf.Trace) -> float:
        return float(trace.state.phase2_policy == "K")

    @vf.metric
    async def r2_policy_m(self, trace: vf.Trace) -> float:
        return float(trace.state.phase2_policy == "M")

    @vf.metric
    async def r2_acquisition(self, trace: vf.Trace) -> float:
        return float(trace.state.phase2_acquisition_success)

    @vf.metric
    async def r2_verification(self, trace: vf.Trace) -> float:
        return float(trace.state.phase2_verification_pass)


def _extract_choice_calls(trace: vf.Trace, turn2_message: str) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []
    after_turn2 = False
    for node in getattr(trace, "nodes", []):
        message = getattr(node, "message", node)
        role = getattr(message, "role", None)
        content = getattr(message, "content", None)
        if role == "user" and turn2_message and content == turn2_message:
            after_turn2 = True
        if role != "assistant":
            continue
        for call in getattr(message, "tool_calls", None) or []:
            if not str(getattr(call, "name", "")).endswith("select_policy"):
                continue
            arguments = getattr(call, "arguments", "")
            try:
                parsed = json.loads(arguments)
            except (TypeError, json.JSONDecodeError):
                parsed = None
            calls.append(
                {
                    "phase": "phase2" if after_turn2 else "phase1",
                    "name": getattr(call, "name", ""),
                    "arguments": arguments,
                    "policy": parsed.get("policy") if isinstance(parsed, dict) else None,
                }
            )
    return calls


def segment_ended_naturally(segment: vf.Segment, trace: vf.Trace) -> bool:
    if segment.terminated or trace.stop_condition is not None:
        return False
    last_assistant = next(
        (
            message
            for message in reversed(segment.messages)
            if isinstance(message, vf.AssistantMessage)
        ),
        None,
    )
    return last_assistant is not None and not last_assistant.tool_calls


class DoseResponseConfig(vf.TasksetConfig):
    random_seed: str = (
        "cross-rollout-postcommitment-provenance-dose-response-v1-random-2026-08-14"
    )
    assignment_seed: str = (
        "cross-rollout-postcommitment-provenance-dose-response-v1-assignment-2026-08-14"
    )
    assignment_state_path: str = (
        "/tmp/cross-rollout-postcommitment-provenance-dose-response-v1-assignments-2026-08-14.json"
    )
    schedule_seed: str = SCHEDULE_SEED
    task: DoseResponseTaskConfig = DoseResponseTaskConfig()


class CrossRolloutPostcommitmentProvenanceDoseResponseV1Taskset(
    vf.Taskset[DoseResponseTask, DoseResponseConfig]
):
    def load(self) -> list[DoseResponseTask]:
        schedule = build_schedule(self.config.schedule_seed)
        if len(schedule) != MAX_ATTEMPTS:
            raise RuntimeError("frozen schedule is not exactly 900 attempts")
        return [
            DoseResponseTask(
                DoseResponseTaskData(
                    idx=spec.attempt_index,
                    name=f"provenance-dose-response-{spec.attempt_index:03d}-{spec.phase1_order}",
                    prompt=phase1_prompt(spec.phase1_order),
                    attempt_index=spec.attempt_index,
                    random_seed=self.config.random_seed,
                    assignment_seed=self.config.assignment_seed,
                    assignment_state_path=self.config.assignment_state_path,
                    phase1_presentation_order=spec.phase1_order,
                    schedule_seed=self.config.schedule_seed,
                ),
                self.config.task,
            )
            for spec in schedule
        ]


class DoseResponseEnvConfig(vf.EnvConfig):
    agent: vf.AgentConfig = vf.AgentConfig(
        harness=NullHarnessConfig(id="null"),
        max_turns=14,
    )


class CrossRolloutPostcommitmentProvenanceDoseResponseV1Env(
    vf.Env[DoseResponseEnvConfig]
):
    async def run(self, task: DoseResponseTask, agents: vf.Agents) -> None:
        async with agents.agent.interaction(task) as interaction:
            if interaction.trace.state.stopped_before_attempt:
                return
            phase1_segment = await interaction.turn()
            state = interaction.trace.state
            state.natural_yield_after_r1 = segment_ended_naturally(
                phase1_segment, interaction.trace
            )
            if not state.natural_yield_after_r1:
                return
            if state.phase != "awaiting_r2":
                return
            assigned = (
                state.source_condition,
                state.advisory_reliability,
                state.phase2_presentation_order,
            )
            activate_r2(state)
            if (
                state.source_condition,
                state.advisory_reliability,
                state.phase2_presentation_order,
            ) != assigned:
                raise RuntimeError("R2 activation changed assignment")
            if state.turn2_sent_count != 0:
                raise RuntimeError("Turn 2 was already sent")
            if (
                state.source_condition is None
                or state.advisory_reliability is None
                or state.phase2_presentation_order is None
            ):
                raise RuntimeError("R2 activation lacks assignment")
            state.turn2_sent_count += 1
            state.turn2_message = phase2_prompt(
                state.phase2_presentation_order,
                state.advisory_reliability,
                state.source_condition,
            )
            state.advisory_delivered = True
            exposure_event = record_event(
                state,
                "exposure",
                "turn2_advisory",
                state.source_text,
                post_randomization=True,
            )
            state.exposure_event_index = exposure_event.index
            turn2_event = record_event(
                state,
                "env_turn2",
                "user",
                state.turn2_message,
                post_randomization=True,
            )
            if turn2_event.index != exposure_event.index + 1:
                raise RuntimeError("Turn-2 event ordering changed")
            await interaction.turn(state.turn2_message)


__all__ = [
    "CrossRolloutPostcommitmentProvenanceDoseResponseV1Env",
    "CrossRolloutPostcommitmentProvenanceDoseResponseV1Taskset",
]
