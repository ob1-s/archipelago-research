"""Native two-turn evidence-threshold transport taskset."""

from __future__ import annotations

import json

import verifiers.v1 as vf
from verifiers.v1.harnesses.null import NullHarnessConfig

from . import assignment, randomness
from .constants import (
    MATCH_ACQUISITION_PROBABILITY,
    MATCH_VERIFICATION_PROBABILITY,
    MISMATCH_ACQUISITION_PROBABILITY,
    Q_GRIDS,
    RANDOM_SEED,
    SCHEDULE_SEED,
    PolicyOrder,
    Strength,
    phase1_prompt,
    phase2_prompt,
)
from .evidence import all_strength_math, validate_frozen_math
from .servers.facility import TransportToolset, TransportToolsetConfig
from .state import DrawRecord, TransportState, record_event


def activate_r2(state: TransportState) -> None:
    """The only transition that makes R2 available to model-visible tools."""

    if state.phase != "awaiting_r2":
        raise RuntimeError("R2 activation requires awaiting_r2")
    if state.assignment_status != "preassigned":
        raise RuntimeError("R2 activation requires a preassigned condition")
    assigned = (
        state.strength,
        state.advisory_reliability,
        state.phase2_presentation_order,
    )
    if state.r2_activated:
        raise RuntimeError("R2 has already been activated")
    state.r2_activated = True
    state.phase = "phase2"
    record_event(
        state,
        "env_activate_r2",
        "activate_r2",
        "Resource R2 activated by environment control flow.",
    )
    if (
        state.strength,
        state.advisory_reliability,
        state.phase2_presentation_order,
    ) != assigned:
        raise RuntimeError("R2 activation changed the preassigned condition")


class TransportTaskData(vf.TaskData):
    attempt_index: int
    random_seed: str
    schedule_seed: str
    quota_state_path: str
    strength: Strength
    advisory_reliability: float
    phase1_presentation_order: PolicyOrder
    phase2_presentation_order: PolicyOrder
    quota_cell_key: str
    quota_cell_target: int
    quota_round: int
    assignment_key: str
    prompt: str


class TransportTaskConfig(vf.TaskConfig):
    tools: TransportToolsetConfig = TransportToolsetConfig()


class TransportTask(vf.Task[TransportTaskData, TransportState, TransportTaskConfig]):
    @classmethod
    def toolsets(cls, config: TransportTaskConfig) -> list[vf.Toolset]:
        return [TransportToolset(config.tools)]

    async def setup(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        del runtime
        validate_frozen_math()
        state = trace.state
        state.rollout_id = trace.id
        state.random_seed = self.data.random_seed
        state.schedule_seed = self.data.schedule_seed
        state.quota_state_path = self.data.quota_state_path
        state.attempt_index = self.data.attempt_index
        state.assignment_key = self.data.assignment_key
        state.quota_cell_key = self.data.quota_cell_key
        state.quota_cell_target = self.data.quota_cell_target
        state.quota_round = self.data.quota_round
        state.strength = self.data.strength
        state.advisory_reliability = self.data.advisory_reliability
        state.phase1_presentation_order = self.data.phase1_presentation_order
        state.phase2_presentation_order = self.data.phase2_presentation_order

        assignment.ensure_quota_state(
            self.data.quota_state_path,
            self.data.schedule_seed,
        )
        math = all_strength_math()[self.data.strength]
        assay = {
            "schema_version": "evidence_threshold_transport_v1.trace_info.v1",
            "attempt_index": self.data.attempt_index,
            "random_seed": self.data.random_seed,
            "schedule_seed": self.data.schedule_seed,
            "quota_state_path": self.data.quota_state_path,
            "assignment_key": self.data.assignment_key,
            "condition_assigned_before_phase1": True,
            "condition_assignment_is_completion_order_independent": True,
            "strength_internal": self.data.strength,
            "advisory_reliability_internal": self.data.advisory_reliability,
            "phase1_presentation_order": self.data.phase1_presentation_order,
            "phase2_presentation_order_internal": self.data.phase2_presentation_order,
            "quota_cell_key": self.data.quota_cell_key,
            "quota_cell_target": self.data.quota_cell_target,
            "quota_round": self.data.quota_round,
            "prompt": self.data.prompt,
            "random_namespaces": list(randomness.ROLLOUT_NAMESPACES),
            "assignment_namespaces": list(assignment.ASSIGNMENT_NAMESPACES),
            "frozen_profile_prior": {"policy_1_fit": 0.5, "policy_2_fit": 0.5},
            "frozen_probabilities": {
                "match_acquisition": MATCH_ACQUISITION_PROBABILITY,
                "mismatch_acquisition": MISMATCH_ACQUISITION_PROBABILITY,
                "match_verification": MATCH_VERIFICATION_PROBABILITY,
                "mismatch_verification": math.mismatch_verification_probability,
            },
            "private_likelihood_ratio": math.private_likelihood_ratio,
            "normative_crossover": math.normative_crossover,
            "eligibility_rate": math.eligibility_rate,
            "all_q_grids": {
                strength: list(values) for strength, values in Q_GRIDS.items()
            },
            "target_primary_eligible": assignment.TARGET_PRIMARY_ELIGIBLE,
            "max_attempts": assignment.MAX_ATTEMPTS,
            "quota_cell_count": assignment.QUOTA_CELL_COUNT,
            "rounds_per_quota_cell": assignment.ROUNDS_PER_QUOTA_CELL,
            "primary_eligibility": "R1 acquisition success and verification pass, accepted by preassigned cell quota",
            "r2_present_before_activation": False,
            "q_and_phase2_order_visible_before_turn2": False,
            "custom_harness_present": False,
            "continuation_nudge_present": False,
            "r2_choice_is_primary_endpoint": True,
            "advisory_source": "AutomatedSource",
        }
        trace.info["evidence_threshold_transport_assay"] = assay

        if assignment.cell_is_complete(
            self.data.quota_state_path,
            self.data.schedule_seed,
            self.data.quota_cell_key,
        ):
            state.stopped_before_attempt = True
            state.stop_reason = "quota_cell_complete_before_attempt"
            state.phase = "complete"
            assay.update(
                {
                    "stopped_before_attempt": True,
                    "stop_reason": state.stop_reason,
                    "over_quota_guard": True,
                }
            )
            return

        profile, value, key = randomness.hidden_profile(self.data.random_seed, trace.id)
        state.hidden_profile = profile
        state.random_draws["hidden_profile"] = DrawRecord(
            namespace="hidden_profile",
            key=key,
            value=value,
            threshold=0.5,
            outcome=profile,
            matched_profile=None,
        )
        assay.update(
            {
                "stopped_before_attempt": False,
                "stop_reason": None,
                "over_quota_guard": False,
            }
        )
        record_event(
            state,
            "assignment",
            "pre_phase1_condition",
            "Experimental condition was fixed from attempt identity before Phase 1.",
            post_assignment=False,
        )

    async def finalize(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        del runtime
        state = trace.state
        info = trace.info["evidence_threshold_transport_assay"]
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

        if state.phase == "phase1" and state.eligibility == "pending_phase1":
            if state.phase1_selection_invalid:
                state.eligibility = "invalid_first_policy"
            elif state.phase1_policy is None or not state.phase1_release_attempted:
                state.eligibility = "phase1_not_successful"

        if state.primary_eligible:
            if state.phase2_policy is None:
                state.phase2_missing = True
            elif not state.phase2_release_attempted:
                state.phase2_incomplete_after_choice = True
            if state.phase2_policy is not None:
                state.primary_switch = state.phase2_policy != state.phase1_policy
                state.primary_itt_switch = bool(state.primary_switch)

        choice_calls = _extract_choice_calls(trace, state.turn2_message)
        r1_call = choice_calls[0] if choice_calls else None
        r2_call = choice_calls[1] if len(choice_calls) > 1 else None
        transition = (
            f"{state.phase1_policy}→{state.phase2_policy}"
            if state.primary_eligible
            and state.phase1_policy is not None
            and state.phase2_policy is not None
            else None
        )
        if state.primary_eligible and not state.natural_yield_after_r1:
            state.stop_reason = "no_natural_yield_after_r1"
        elif state.primary_eligible and state.phase2_missing:
            state.stop_reason = "r2_missing"
        elif state.primary_eligible and state.phase2_release_attempted:
            state.stop_reason = "r2_released"
        elif state.primary_eligible and state.phase2_policy is not None:
            state.stop_reason = "r2_incomplete_after_choice"
        elif state.over_quota_guard:
            state.stop_reason = "evidence_eligible_over_quota_guard"
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
                "evidence_eligible": state.evidence_eligible,
                "primary_eligible": state.primary_eligible,
                "quota_accepted_rank": state.quota_accepted_rank,
                "over_quota_guard": state.over_quota_guard,
                "eligibility_event_index": state.eligibility_event_index,
                "assignment_event_index": state.assignment_event_index,
                "r2_activated": state.r2_activated,
                "turn2_sent_count": state.turn2_sent_count,
                "turn2_message": state.turn2_message or None,
                "natural_yield_after_r1": state.natural_yield_after_r1,
                "interstage_call_count": state.interstage_call_count,
                "phase2_missing": state.phase2_missing,
                "phase2_incomplete_after_choice": state.phase2_incomplete_after_choice,
                "primary_switch": state.primary_switch,
                "primary_itt_switch": state.primary_itt_switch,
                "primary_itt_not_switch": state.primary_eligible
                and not state.primary_itt_switch,
                "primary_choice_observed": state.primary_eligible
                and state.phase2_policy is not None,
                "transition": transition,
                "first_phase1_policy_call": state.first_phase1_policy_call,
                "first_phase2_policy_call": state.first_phase2_policy_call,
                "phase1_first_call_valid": state.phase1_first_call_valid,
                "phase2_first_call_valid": state.phase2_first_call_valid,
                "phase1_selection_invalid": state.phase1_selection_invalid,
                "phase2_selection_invalid": state.phase2_selection_invalid,
                "selection_ambiguity": state.selection_ambiguity,
                "policy_selection_attempts": state.policy_selection_attempts,
                "choice_calls": [r1_call, r2_call],
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
    async def evidence_eligible(self, trace: vf.Trace) -> float:
        return float(trace.state.evidence_eligible)

    @vf.metric
    async def primary_eligible(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_eligible)

    @vf.metric
    async def primary_itt_switch(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_itt_switch is True)

    @vf.metric
    async def primary_itt_not_switch(self, trace: vf.Trace) -> float:
        return float(
            trace.state.primary_eligible and not trace.state.primary_itt_switch
        )

    @vf.metric
    async def primary_choice_observed(self, trace: vf.Trace) -> float:
        return float(
            trace.state.primary_eligible and trace.state.phase2_policy is not None
        )

    @vf.metric
    async def phase2_missing(self, trace: vf.Trace) -> float:
        return float(trace.state.primary_eligible and trace.state.phase2_missing)

    @vf.metric
    async def phase2_incomplete_after_choice(self, trace: vf.Trace) -> float:
        return float(
            trace.state.primary_eligible and trace.state.phase2_incomplete_after_choice
        )

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


def _extract_choice_calls(
    trace: vf.Trace, turn2_message: str
) -> list[dict[str, object]]:
    """Extract actual first-choice calls split at the real Turn-2 user node."""

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
                    "policy": parsed.get("policy")
                    if isinstance(parsed, dict)
                    else None,
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


class TransportTaskConfigRoot(vf.TasksetConfig):
    random_seed: str = RANDOM_SEED
    schedule_seed: str = SCHEDULE_SEED
    quota_state_path: str = "/tmp/cross-rollout-postcommitment-evidence-threshold-transport-v1-quota-2026-08-14.json"
    task: TransportTaskConfig = TransportTaskConfig()


class CrossRolloutPostcommitmentEvidenceThresholdTransportV1Taskset(
    vf.Taskset[TransportTask, TransportTaskConfigRoot]
):
    def load(self) -> list[TransportTask]:
        validate_frozen_math()
        plan = assignment.build_attempt_plan(self.config.schedule_seed)
        if len(plan) != assignment.MAX_ATTEMPTS:
            raise RuntimeError("frozen preassignment plan has unexpected length")
        return [
            TransportTask(
                TransportTaskData(
                    idx=spec.attempt_index,
                    name=(
                        f"evidence-threshold-transport-{spec.attempt_index:04d}-"
                        f"{spec.strength}-{spec.advisory_reliability:.4f}-"
                        f"{spec.phase1_order}-{spec.phase2_order}"
                    ),
                    prompt=phase1_prompt(spec.phase1_order, spec.strength),
                    attempt_index=spec.attempt_index,
                    random_seed=self.config.random_seed,
                    schedule_seed=self.config.schedule_seed,
                    quota_state_path=self.config.quota_state_path,
                    strength=spec.strength,
                    advisory_reliability=spec.advisory_reliability,
                    phase1_presentation_order=spec.phase1_order,
                    phase2_presentation_order=spec.phase2_order,
                    quota_cell_key=spec.quota_cell_key,
                    quota_cell_target=spec.quota_cell_target,
                    quota_round=spec.quota_round,
                    assignment_key=spec.assignment_key,
                ),
                self.config.task,
            )
            for spec in plan
        ]


class TransportEnvConfig(vf.EnvConfig):
    agent: vf.AgentConfig = vf.AgentConfig(
        harness=NullHarnessConfig(id="null"),
        max_turns=14,
    )


class CrossRolloutPostcommitmentEvidenceThresholdTransportV1Env(
    vf.Env[TransportEnvConfig]
):
    async def run(self, task: TransportTask, agents: vf.Agents) -> None:
        async with agents.agent.interaction(task) as interaction:
            if interaction.trace.state.stopped_before_attempt:
                return
            phase1_segment = await interaction.turn()
            state = interaction.trace.state
            state.natural_yield_after_r1 = segment_ended_naturally(
                phase1_segment, interaction.trace
            )
            if not state.natural_yield_after_r1 or state.phase != "awaiting_r2":
                return
            activate_r2(state)
            if state.turn2_sent_count != 0:
                raise RuntimeError("Turn 2 was already sent")
            state.turn2_sent_count += 1
            state.turn2_message = phase2_prompt(
                state.phase2_presentation_order,
                state.advisory_reliability,
            )
            exposure_event = record_event(
                state,
                "exposure",
                "turn2_advisory",
                "Automated facility diagnostic advisory exposed in Turn 2.",
            )
            state.exposure_event_index = exposure_event.index
            turn2_event = record_event(
                state,
                "env_turn2",
                "user",
                state.turn2_message,
            )
            if turn2_event.index != exposure_event.index + 1:
                raise RuntimeError("Turn-2 event ordering changed")
            await interaction.turn(state.turn2_message)


# Stable aliases used by local tooling.
TransportConfig = TransportTaskConfigRoot
