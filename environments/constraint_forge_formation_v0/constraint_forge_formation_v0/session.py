"""Authoritative round-by-round Constraint Forge job session.

The model-free runner in :mod:`world` remains the reference batch API.  This
module exposes the same world transitions one decision barrier at a time for a
behavioral referee.  It deliberately contains orchestration only: parsing,
physics, interventions, racks, and event construction are delegated to the V0
modules that already own those rules.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr

from .actions import (
    ActionParseError,
    KeepUnchangedAction,
    WaitAction,
    action_payload,
    parse_memory_action,
    parse_world_action,
)
from .canonical import stable_hash
from .events import EventKind, EventLog
from .generator import validate_job
from .interventions import InterventionKind, InterventionSchedule
from .models import (
    DeliveryStatus,
    EffectStatus,
    Station,
    StrictModel,
    TriggerStatus,
)
from .rack import (
    FilmFrame,
    RackMutation,
    RackState,
    RackView,
    apply_memory_phases,
    empty_rack,
)
from .world import (
    JobResult,
    Observation,
    RoundResolution,
    _emit_action_events,
    _emit_effect_events,
    _finalize_intervention,
    _frame,
    _memory_view,
    begin_round,
    initial_state,
    observation,
    resolve_round,
    world_state_hash,
)


class ParseClassification(StrEnum):
    """How a raw behavioral response was turned into a typed decision."""

    VALID = "valid"
    MALFORMED_NOOP = "malformed_noop"
    WRONG_PHASE_NOOP = "wrong_phase_noop"


class SessionPhase(StrEnum):
    ROUND = "round"
    EVICTION = "eviction"
    RETENTION = "retention"
    COMPLETE = "complete"


class SessionPhaseError(RuntimeError):
    """Raised when a caller violates the session's explicit phase barrier."""


class RoundOffer(StrictModel):
    schema_version: Literal["constraint-forge/round-offer/v0"] = (
        "constraint-forge/round-offer/v0"
    )
    token: StrictStr
    round: StrictInt = Field(ge=1, le=16)
    pre_state_hash: StrictStr
    event_sequence_before: StrictInt = Field(ge=0)
    observation_x: Observation
    observation_y: Observation


class RoundSubmitResult(StrictModel):
    schema_version: Literal["constraint-forge/round-result/v0"] = (
        "constraint-forge/round-result/v0"
    )
    token: StrictStr
    round: StrictInt = Field(ge=1, le=16)
    pre_state_hash: StrictStr
    post_state_hash: StrictStr
    parse_x: ParseClassification
    parse_y: ParseClassification
    event_sequence_start: StrictInt = Field(ge=0)
    event_sequence_end: StrictInt = Field(ge=0)
    resolution: RoundResolution
    terminal: StrictBool


class MemoryOffer(StrictModel):
    schema_version: Literal["constraint-forge/memory-offer/v0"] = (
        "constraint-forge/memory-offer/v0"
    )
    token: StrictStr
    phase: Literal["eviction", "retention"]
    state_hash: StrictStr
    event_sequence_before: StrictInt = Field(ge=0)
    rack_view_x: RackView
    rack_view_y: RackView
    frames_x: tuple[FilmFrame, ...]
    frames_y: tuple[FilmFrame, ...]


class MemorySubmitResult(StrictModel):
    schema_version: Literal["constraint-forge/memory-result/v0"] = (
        "constraint-forge/memory-result/v0"
    )
    token: StrictStr
    phase: Literal["eviction", "retention"]
    parse_x: ParseClassification
    parse_y: ParseClassification
    event_sequence_start: StrictInt = Field(ge=0)
    event_sequence_end: StrictInt = Field(ge=0)
    mutation_x: RackMutation
    mutation_y: RackMutation
    rack_hash_x: StrictStr
    rack_hash_y: StrictStr


def _world_action(raw: str) -> tuple[object, ParseClassification]:
    """Parse one model response; malformed text is one deterministic no-op.

    A no-op is represented by the existing typed ``wait`` action.  It consumes
    the behavioral opportunity and enters the ordinary event stream exactly
    once; the separate classification preserves the fact that the response was
    malformed for the runner audit without teaching the physics a second action
    language.
    """

    try:
        return parse_world_action(raw), ParseClassification.VALID
    except ActionParseError:
        return WaitAction(action="wait"), ParseClassification.MALFORMED_NOOP


def _memory_action(raw: str, *, phase: Literal["eviction", "retention"]):
    try:
        action = parse_memory_action(raw)
    except ActionParseError:
        return KeepUnchangedAction(action="keep_unchanged"), ParseClassification.MALFORMED_NOOP
    if phase == "eviction" and action.action == "retain":
        return KeepUnchangedAction(action="keep_unchanged"), ParseClassification.WRONG_PHASE_NOOP
    if phase == "retention" and action.action == "evict":
        return KeepUnchangedAction(action="keep_unchanged"), ParseClassification.WRONG_PHASE_NOOP
    return action, ParseClassification.VALID


class ConstraintForgeJobSession:
    """One authoritative, deterministic job with explicit decision barriers."""

    def __init__(
        self,
        *,
        job,
        run_id: str,
        lineage_id: str,
        job_id: str,
        rack_x: RackState,
        rack_y: RackState,
        intervention: InterventionSchedule | None,
        read_only_probe: bool,
    ) -> None:
        self.job = job
        self.run_id = run_id
        self.lineage_id = lineage_id
        self.job_id = job_id
        self.intervention = intervention
        self.read_only_probe = read_only_probe or bool(
            intervention is not None and intervention.read_only_probe
        )
        self.initial_rack_x = rack_x
        self.initial_rack_y = rack_y
        self.rack_x = rack_x
        self.rack_y = rack_y
        self.state = initial_state(
            job,
            run_id=run_id,
            lineage_id=lineage_id,
            job_id=job_id,
            intervention=intervention,
        )
        self.log = EventLog(
            run_id=run_id,
            lineage_id=lineage_id,
            job_id=job_id,
            job_seed=job.job_seed,
        )
        self.frames_x: list[FilmFrame] = []
        self.frames_y: list[FilmFrame] = []
        self.mutations_x: list[RackMutation] = []
        self.mutations_y: list[RackMutation] = []
        self.rounds_resolved = 0
        self.phase = SessionPhase.ROUND
        self._pending_round: RoundOffer | None = None
        self._pending_memory: MemoryOffer | None = None
        self._job_end_written = False
        self._closed = False

        state_hash = world_state_hash(self.state)
        self.log = self.log.append(
            round=0,
            phase="job",
            source="environment",
            event_kind=EventKind.JOB_START,
            pre_state_hash=state_hash,
            post_state_hash=state_hash,
            intervention_id=self.state.intervention.intervention_id
            if self.state.intervention
            else None,
            trigger_status=self.state.intervention.trigger_status
            if self.state.intervention
            else None,
            effect_status=self.state.intervention.effect_status
            if self.state.intervention
            else None,
        )
        self.log = self.log.append(
            round=0,
            phase="job",
            source="environment",
            event_kind=EventKind.CONTEXT_RESET,
            pre_state_hash=state_hash,
            post_state_hash=state_hash,
            detail={"same_actor_lifecycle_required": True},
        )
        if intervention is not None:
            self.log = self.log.append(
                round=0,
                phase="job",
                source="environment",
                event_kind=EventKind.INTERVENTION_ARMED,
                pre_state_hash=state_hash,
                post_state_hash=state_hash,
                intervention_id=intervention.intervention_id,
                trigger_status=self.state.intervention.trigger_status
                if self.state.intervention
                else None,
                effect_status=self.state.intervention.effect_status
                if self.state.intervention
                else None,
            )
            if intervention.kind is InterventionKind.HIDE_RACK:
                self.log = self.log.append(
                    round=1,
                    phase="job",
                    source="environment",
                    event_kind=EventKind.INTERVENTION_TRIGGERED,
                    pre_state_hash=state_hash,
                    post_state_hash=state_hash,
                    intervention_id=intervention.intervention_id,
                    trigger_status=TriggerStatus.TRIGGERED,
                    effect_status=EffectStatus.APPLIED,
                )

    @classmethod
    def open(
        cls,
        job,
        *,
        run_id: str,
        lineage_id: str,
        job_id: str,
        rack_x: RackState | None = None,
        rack_y: RackState | None = None,
        intervention: InterventionSchedule | None = None,
        read_only_probe: bool = False,
    ) -> "ConstraintForgeJobSession":
        return cls(
            job=validate_job(job),
            run_id=run_id,
            lineage_id=lineage_id,
            job_id=job_id,
            rack_x=rack_x if rack_x is not None else empty_rack(),
            rack_y=rack_y if rack_y is not None else empty_rack(),
            intervention=intervention,
            read_only_probe=read_only_probe,
        )

    @property
    def event_log(self) -> EventLog:
        return self.log

    @property
    def state_hash(self) -> str:
        return world_state_hash(self.state)

    @property
    def terminal(self) -> bool:
        return self.state.terminal

    @property
    def complete(self) -> bool:
        return self.phase is SessionPhase.COMPLETE

    def _require_open(self) -> None:
        if self._closed:
            raise SessionPhaseError("job session is closed")

    def _token(self, phase: str, ordinal: int, pre_state_hash: str) -> str:
        return stable_hash(
            {
                "run_id": self.run_id,
                "lineage_id": self.lineage_id,
                "job_id": self.job_id,
                "phase": phase,
                "ordinal": ordinal,
                "pre_state_hash": pre_state_hash,
                "event_sequence": len(self.log.events),
            }
        )

    def _append_begin_effects(self, effects: tuple[dict, ...]) -> None:
        for effect in effects:
            self.log = self.log.append(
                round=self.state.round,
                phase="job",
                source=(
                    Station(effect["station"])
                    if effect.get("station") in {"X", "Y"}
                    else "environment"
                ),
                event_kind=EventKind(effect["kind"]),
                pre_state_hash=effect.get("pre_state_hash", world_state_hash(self.state)),
                post_state_hash=effect.get("post_state_hash", world_state_hash(self.state)),
                action_id=effect.get("action_id"),
                visible_from_round=effect.get("visible_from_round"),
                delivery_status=(
                    DeliveryStatus(effect["delivery_status"])
                    if effect.get("delivery_status")
                    else None
                ),
                detail=effect.get("detail", {}),
            )

    def _append_observation_events(self, state_hash: str, observations) -> None:
        for station, obs, rack in (
            (Station.X, observations[0], self.rack_x),
            (Station.Y, observations[1], self.rack_y),
        ):
            self.log = self.log.append(
                round=self.state.round,
                phase="job",
                source=station,
                event_kind=EventKind.OBSERVATION,
                pre_state_hash=state_hash,
                post_state_hash=state_hash,
                rack_hash_before=rack.content_hash,
                rack_hash_after=rack.content_hash,
                detail={"observation_hash": stable_hash(obs.model_dump(mode="json"))},
            )
            self.log = self.log.append(
                round=self.state.round,
                phase="job",
                source=station,
                event_kind=EventKind.RACK_VIEWED,
                pre_state_hash=state_hash,
                post_state_hash=state_hash,
                rack_hash_before=rack.content_hash,
                rack_hash_after=rack.content_hash,
                detail={"available": obs.rack.available, "hashed_only": obs.rack.hashed_only},
            )

    def begin_round(self) -> RoundOffer:
        self._require_open()
        if self.phase is not SessionPhase.ROUND or self.state.terminal:
            raise SessionPhaseError("round offer is not available")
        if self._pending_round is not None:
            raise SessionPhaseError("a round offer is already outstanding")

        self.state, effects = begin_round(self.state)
        self._append_begin_effects(effects)
        # ``begin_round`` delivers scheduled effects before either station can
        # act.  The state after that delivery is the actual shared prestate for
        # this decision barrier and for both audit bindings.
        pre_state_hash = self.state_hash
        first_observation = self.state.round == 1
        obs_x = observation(
            self.state,
            Station.X,
            self.rack_x,
            schedule=self.intervention,
            first_observation=first_observation,
        )
        obs_y = observation(
            self.state,
            Station.Y,
            self.rack_y,
            schedule=self.intervention,
            first_observation=first_observation,
        )
        observation_hash = world_state_hash(self.state)
        self._append_observation_events(observation_hash, (obs_x, obs_y))
        offer = RoundOffer(
            token=self._token("round", self.rounds_resolved, pre_state_hash),
            round=self.state.round,
            pre_state_hash=pre_state_hash,
            event_sequence_before=len(self.log.events),
            observation_x=obs_x,
            observation_y=obs_y,
        )
        self._pending_round = offer
        return offer

    def submit_round(self, *, token: str, raw_x: str, raw_y: str) -> RoundSubmitResult:
        self._require_open()
        offer = self._pending_round
        if offer is None or token != offer.token:
            raise SessionPhaseError("unknown or stale round token")
        if self.state.terminal:
            raise SessionPhaseError("cannot submit a round after termination")

        action_x, parse_x = _world_action(raw_x)
        action_y, parse_y = _world_action(raw_y)
        event_start = len(self.log.events)
        intervention_before = self.state.intervention
        resolution_state, resolution = resolve_round(
            self.state,
            action_x,  # type: ignore[arg-type]
            action_y,  # type: ignore[arg-type]
            x_action_id=f"X:r{self.state.round}",
            y_action_id=f"Y:r{self.state.round}",
        )
        self.log = _emit_action_events(self.log, self.state, resolution.x)
        self.log = _emit_action_events(self.log, self.state, resolution.y)
        self.log = _emit_effect_events(self.log, self.state, resolution)
        if (
            intervention_before is not None
            and intervention_before.trigger_status is TriggerStatus.ARMED
            and resolution_state.intervention is not None
            and resolution_state.intervention.trigger_status is TriggerStatus.TRIGGERED
        ):
            triggered = resolution_state.intervention
            self.log = self.log.append(
                round=resolution.round,
                phase="job",
                source="environment",
                event_kind=EventKind.INTERVENTION_TRIGGERED,
                pre_state_hash=resolution.pre_state_hash,
                post_state_hash=resolution.post_state_hash,
                intervention_id=triggered.intervention_id,
                trigger_status=triggered.trigger_status,
                effect_status=triggered.effect_status,
                detail={"kind": triggered.kind, "detail": triggered.detail},
            )
        if resolution.x.action_payload.get("action") == "finish" and resolution.x.legal:
            self.log = self.log.append(
                round=resolution.round,
                phase="job",
                source=Station.X,
                event_kind=EventKind.FINISH_LOCKED,
                action_id=resolution.x.action_id,
                pre_state_hash=resolution.pre_state_hash,
                post_state_hash=resolution.post_state_hash,
            )
        if resolution.y.action_payload.get("action") == "finish" and resolution.y.legal:
            self.log = self.log.append(
                round=resolution.round,
                phase="job",
                source=Station.Y,
                event_kind=EventKind.FINISH_LOCKED,
                action_id=resolution.y.action_id,
                pre_state_hash=resolution.pre_state_hash,
                post_state_hash=resolution.post_state_hash,
            )
        self.frames_x.append(_frame(resolution_state, Station.X, offer.observation_x, resolution.x))
        self.frames_y.append(_frame(resolution_state, Station.Y, offer.observation_y, resolution.y))
        self.state = resolution_state
        self.rounds_resolved += 1
        self._pending_round = None
        if self.state.terminal:
            self._write_job_end()
        return RoundSubmitResult(
            token=offer.token,
            round=resolution.round,
            pre_state_hash=resolution.pre_state_hash,
            post_state_hash=resolution.post_state_hash,
            parse_x=parse_x,
            parse_y=parse_y,
            event_sequence_start=event_start,
            event_sequence_end=len(self.log.events),
            resolution=resolution,
            terminal=self.state.terminal,
        )

    def _write_job_end(self) -> None:
        if self._job_end_written:
            return
        self.state, self.log = _finalize_intervention(self.state, self.log)
        self.log = self.log.append(
            round=self.state.round,
            phase="job",
            source="environment",
            event_kind=EventKind.JOB_END,
            pre_state_hash=world_state_hash(self.state),
            post_state_hash=world_state_hash(self.state),
            detail={"success": self.state.success, "rounds_resolved": self.rounds_resolved},
        )
        self._job_end_written = True

    def _memory_offer(self, phase: Literal["eviction", "retention"]) -> MemoryOffer:
        return MemoryOffer(
            token=self._token(phase, self.rounds_resolved, self.state_hash),
            phase=phase,
            state_hash=self.state_hash,
            event_sequence_before=len(self.log.events),
            rack_view_x=_memory_view(self.intervention, Station.X, self.rack_x),
            rack_view_y=_memory_view(self.intervention, Station.Y, self.rack_y),
            frames_x=tuple(self.frames_x),
            frames_y=tuple(self.frames_y),
        )

    def begin_eviction(self) -> MemoryOffer | None:
        self._require_open()
        if not self.state.terminal or not self._job_end_written:
            raise SessionPhaseError("eviction is available only after job termination")
        if self.read_only_probe:
            self.phase = SessionPhase.COMPLETE
            return None
        if self.phase is not SessionPhase.ROUND or self._pending_memory is not None:
            raise SessionPhaseError("eviction offer is not available")
        state_hash = self.state_hash
        self.log = self.log.append(
            round=self.state.round,
            phase="job",
            source="environment",
            event_kind=EventKind.MEMORY_PHASE_START,
            pre_state_hash=state_hash,
            post_state_hash=state_hash,
        )
        self.log = self.log.append(
            round=self.state.round,
            phase="eviction",
            source="environment",
            event_kind=EventKind.MEMORY_EVICTION_PHASE,
            pre_state_hash=state_hash,
            post_state_hash=state_hash,
        )
        offer = self._memory_offer("eviction")
        self._pending_memory = offer
        self.phase = SessionPhase.EVICTION
        return offer

    def submit_eviction(self, *, token: str, raw_x: str, raw_y: str) -> MemorySubmitResult:
        self._require_open()
        offer = self._pending_memory
        if offer is None or offer.phase != "eviction" or token != offer.token:
            raise SessionPhaseError("unknown or stale eviction token")
        action_x, parse_x = _memory_action(raw_x, phase="eviction")
        action_y, parse_y = _memory_action(raw_y, phase="eviction")
        event_start = len(self.log.events)
        handle_x = action_x.fragment_handle if action_x.action == "evict" else None
        handle_y = action_y.fragment_handle if action_y.action == "evict" else None
        self.rack_x, mutations_x = apply_memory_phases(
            self.rack_x,
            Station.X,
            tuple(self.frames_x),
            evict_handle=handle_x,
            retain_start_round=None,
            source_job_id=self.job_id,
            handle_seed=f"{self.lineage_id}:{self.job_id}:X",
        )
        self.rack_y, mutations_y = apply_memory_phases(
            self.rack_y,
            Station.Y,
            tuple(self.frames_y),
            evict_handle=handle_y,
            retain_start_round=None,
            source_job_id=self.job_id,
            handle_seed=f"{self.lineage_id}:{self.job_id}:Y",
        )
        mutation_x, mutation_y = mutations_x[0], mutations_y[0]
        self.mutations_x.append(mutation_x)
        self.mutations_y.append(mutation_y)
        self._append_memory_event("eviction", Station.X, mutation_x, action_x)
        self._append_memory_event("eviction", Station.Y, mutation_y, action_y)
        self._pending_memory = None
        self.phase = SessionPhase.EVICTION
        return MemorySubmitResult(
            token=offer.token,
            phase="eviction",
            parse_x=parse_x,
            parse_y=parse_y,
            event_sequence_start=event_start,
            event_sequence_end=len(self.log.events),
            mutation_x=mutation_x,
            mutation_y=mutation_y,
            rack_hash_x=self.rack_x.content_hash,
            rack_hash_y=self.rack_y.content_hash,
        )

    def _append_memory_event(self, phase: Literal["eviction", "retention"], station: Station, mutation: RackMutation, action) -> None:
        attempted = EventKind.EVICT_ATTEMPTED if phase == "eviction" else EventKind.RETAIN_ATTEMPTED
        completed = EventKind.EVICTED if phase == "eviction" else EventKind.RETAINED
        self.log = self.log.append(
            round=self.state.round,
            phase=phase,
            source=station,
            event_kind=attempted,
            action_payload=action_payload(action),
            pre_state_hash=self.state_hash,
            post_state_hash=self.state_hash,
            legal=mutation.legal,
            rejection_reason=mutation.rejection_reason,
            rack_hash_before=mutation.rack_hash_before,
            rack_hash_after=mutation.rack_hash_after,
            fragment_hash=mutation.fragment_hash,
            local_window_bounds=mutation.local_window_bounds,
            detail=(
                {"source_job_id": self.job_id}
                if phase == "retention" and (mutation.legal or action.action == "retain")
                else {}
            ),
        )
        # Preserve V0's event semantics: retention emits RETAINED for the
        # explicit legal keep_unchanged path as well, while eviction emits
        # EVICTED only when a film was actually removed.
        if mutation.legal and (
            phase == "retention" or mutation.fragment_hash is not None
        ):
            self.log = self.log.append(
                round=self.state.round,
                phase=phase,
                source=station,
                event_kind=completed,
                pre_state_hash=self.state_hash,
                post_state_hash=self.state_hash,
                rack_hash_before=mutation.rack_hash_before,
                rack_hash_after=mutation.rack_hash_after,
                fragment_hash=mutation.fragment_hash,
                local_window_bounds=mutation.local_window_bounds,
                detail={"source_job_id": self.job_id} if phase == "retention" else {},
            )

    def begin_retention(self) -> MemoryOffer:
        self._require_open()
        if self.read_only_probe or self.phase is not SessionPhase.EVICTION:
            raise SessionPhaseError("retention requires a completed eviction phase")
        if self._pending_memory is not None:
            raise SessionPhaseError("an eviction offer is still outstanding")
        state_hash = self.state_hash
        self.log = self.log.append(
            round=self.state.round,
            phase="retention",
            source="environment",
            event_kind=EventKind.MEMORY_RETENTION_PHASE,
            pre_state_hash=state_hash,
            post_state_hash=state_hash,
        )
        offer = self._memory_offer("retention")
        self._pending_memory = offer
        self.phase = SessionPhase.RETENTION
        return offer

    def submit_retention(self, *, token: str, raw_x: str, raw_y: str) -> MemorySubmitResult:
        self._require_open()
        offer = self._pending_memory
        if offer is None or offer.phase != "retention" or token != offer.token:
            raise SessionPhaseError("unknown or stale retention token")
        action_x, parse_x = _memory_action(raw_x, phase="retention")
        action_y, parse_y = _memory_action(raw_y, phase="retention")
        event_start = len(self.log.events)
        start_x = action_x.start_round if action_x.action == "retain" else None
        start_y = action_y.start_round if action_y.action == "retain" else None
        self.rack_x, mutation_xs = apply_memory_phases(
            self.rack_x,
            Station.X,
            tuple(self.frames_x),
            evict_handle=None,
            retain_start_round=start_x,
            source_job_id=self.job_id,
            handle_seed=f"{self.lineage_id}:{self.job_id}:X",
        )
        self.rack_y, mutation_ys = apply_memory_phases(
            self.rack_y,
            Station.Y,
            tuple(self.frames_y),
            evict_handle=None,
            retain_start_round=start_y,
            source_job_id=self.job_id,
            handle_seed=f"{self.lineage_id}:{self.job_id}:Y",
        )
        mutation_x, mutation_y = mutation_xs[1], mutation_ys[1]
        self.mutations_x.append(mutation_x)
        self.mutations_y.append(mutation_y)
        self._append_memory_event("retention", Station.X, mutation_x, action_x)
        self._append_memory_event("retention", Station.Y, mutation_y, action_y)
        self._pending_memory = None
        self.phase = SessionPhase.COMPLETE
        return MemorySubmitResult(
            token=offer.token,
            phase="retention",
            parse_x=parse_x,
            parse_y=parse_y,
            event_sequence_start=event_start,
            event_sequence_end=len(self.log.events),
            mutation_x=mutation_x,
            mutation_y=mutation_y,
            rack_hash_x=self.rack_x.content_hash,
            rack_hash_y=self.rack_y.content_hash,
        )

    def result(self) -> JobResult:
        self._require_open()
        if not self.state.terminal or not self._job_end_written:
            raise SessionPhaseError("job has not terminated")
        if not self.read_only_probe and self.phase is not SessionPhase.COMPLETE:
            raise SessionPhaseError("memory phases have not completed")
        failure_reason = None
        if not self.state.success:
            if not self.state.x.finished or not self.state.y.finished:
                failure_reason = "both_stations_did_not_finish"
            elif self.state.x.layer != self.state.y.layer:
                failure_reason = "terminal_layers_differ"
            elif len(set(target for target in self.state.x.layer if target is not None)) != 6:
                failure_reason = "terminal_layer_not_bijective"
            else:
                failure_reason = "terminal_assignment_contains_invalid_edge"
        return JobResult(
            run_id=self.run_id,
            lineage_id=self.lineage_id,
            job_id=self.job_id,
            job_seed=self.job.job_seed,
            initial_rack_x=self.initial_rack_x,
            initial_rack_y=self.initial_rack_y,
            intervention_schedule=self.intervention,
            final_rack_x=self.rack_x,
            final_rack_y=self.rack_y,
            final_state=self.state,
            event_log=self.log,
            success=self.state.success,
            rounds_resolved=self.rounds_resolved,
            failure_reason=failure_reason,
            frames_x=tuple(self.frames_x),
            frames_y=tuple(self.frames_y),
            memory_mutations_x=tuple(self.mutations_x),
            memory_mutations_y=tuple(self.mutations_y),
        )

    def close(self) -> JobResult:
        result = self.result()
        self._closed = True
        return result


__all__ = [
    "ConstraintForgeJobSession",
    "MemoryOffer",
    "MemorySubmitResult",
    "ParseClassification",
    "RoundOffer",
    "RoundSubmitResult",
    "SessionPhase",
    "SessionPhaseError",
]
