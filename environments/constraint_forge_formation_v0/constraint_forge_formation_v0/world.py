"""Model-free Constraint Forge world state, round resolution, and job runner."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr

from .actions import (
    FinishAction,
    SetAction,
    UnsetAction,
    WaitAction,
    WorldAction,
    WriteAction,
    action_payload,
    parse_world_action,
)
from .canonical import stable_hash
from .events import EventKind, EventLog
from .generator import ITEM_IDS, TARGET_IDS, generate_job
from .interventions import InterventionKind, InterventionSchedule
from .models import (
    DeliveryStatus,
    EffectStatus,
    InterventionState,
    Layer,
    PendingWrite,
    RegisterState,
    Seed,
    Station,
    StateTransition,
    StrictModel,
    TriggerStatus,
    VisibilitySuppression,
    WorldState,
)
from .rack import (
    FilmFrame,
    RackMutation,
    RackState,
    RackView,
    apply_memory_phases,
    empty_rack,
    full_rack_view,
    hashed_rack_view,
    hidden_rack_view,
)


class Observation(StrictModel):
    """Exactly the role-local model-facing public state for one round."""

    station: Station
    round: StrictInt = Field(ge=1, le=16)
    private_pairs: tuple[tuple[StrictInt, StrictInt], ...]
    layers: dict[str, Layer]
    registers: dict[str, tuple[RegisterState, RegisterState]]
    remaining: dict[str, dict[str, StrictInt]]
    finished: dict[str, StrictBool]
    rack: RackView
    visible_effects: tuple[StrictStr, ...] = ()


class ActionOutcome(StrictModel):
    station: Station
    action_id: StrictStr
    action_payload: dict
    legal: StrictBool
    rejection_reason: StrictStr | None = None
    pre_state_hash: StrictStr
    post_state_hash: StrictStr
    delivery_status: DeliveryStatus = DeliveryStatus.NOT_APPLICABLE
    visible_from_round: StrictInt | None = None


class RoundResolution(StrictModel):
    round: StrictInt
    pre_state_hash: StrictStr
    post_state_hash: StrictStr
    x: ActionOutcome
    y: ActionOutcome
    effects: tuple[dict, ...] = ()


class JobResult(StrictModel):
    schema_version: Literal["constraint-forge/job-result/v0"] = (
        "constraint-forge/job-result/v0"
    )
    run_id: StrictStr
    lineage_id: StrictStr
    job_id: StrictStr
    job_seed: Seed
    initial_rack_x: RackState
    initial_rack_y: RackState
    intervention_schedule: InterventionSchedule | None = None
    final_rack_x: RackState
    final_rack_y: RackState
    final_state: WorldState
    event_log: EventLog
    success: StrictBool
    rounds_resolved: StrictInt
    failure_reason: StrictStr | None = None
    frames_x: tuple[FilmFrame, ...] = ()
    frames_y: tuple[FilmFrame, ...] = ()
    memory_mutations_x: tuple[RackMutation, ...] = ()
    memory_mutations_y: tuple[RackMutation, ...] = ()

    @property
    def reward(self) -> float:
        return float(self.success)

    @property
    def final_state_hash(self) -> str:
        return world_state_hash(self.final_state)


Policy = Callable[[Observation], WorldAction]
MemoryPolicy = Callable[[Station, RackView, tuple[FilmFrame, ...]], tuple[str | None, int | None]]


def world_state_hash(state: WorldState) -> str:
    """Hash only authoritative state, never the event log or hidden reasoning."""

    return stable_hash(state.model_dump(mode="json"))


def _layer_pairs(layer: Layer) -> tuple[tuple[int, int], ...]:
    return tuple((item, target) for item, target in enumerate(layer) if target is not None)


def _layer_is_bijection(layer: Layer) -> bool:
    targets = [target for target in layer if target is not None]
    return len(targets) == 6 and len(set(targets)) == 6


def _success(state: WorldState) -> bool:
    if not state.x.finished or not state.y.finished:
        return False
    if not _layer_is_bijection(state.x.layer) or not _layer_is_bijection(state.y.layer):
        return False
    if state.x.layer != state.y.layer:
        return False
    accepted = frozenset(state.target_matching)
    return frozenset(_layer_pairs(state.x.layer)).issubset(accepted)


def initial_state(
    job,
    *,
    run_id: str,
    lineage_id: str,
    job_id: str,
    intervention: InterventionSchedule | None = None,
) -> WorldState:
    """Create a fresh job state with symmetric X/Y capabilities."""

    intervention_state = None
    if intervention is not None:
        trigger = (
            TriggerStatus.TRIGGERED
            if intervention.kind is InterventionKind.HIDE_RACK
            else TriggerStatus.ARMED
        )
        effect = (
            EffectStatus.APPLIED
            if intervention.kind is InterventionKind.HIDE_RACK
            else EffectStatus.PENDING
        )
        intervention_state = InterventionState(
            intervention_id=intervention.intervention_id,
            kind=intervention.kind.value,
            target_stations=intervention.target_stations,
            trigger_status=trigger,
            effect_status=effect,
            trigger_round=1 if intervention.kind is InterventionKind.HIDE_RACK else None,
            effect_round=1 if intervention.kind is InterventionKind.HIDE_RACK else None,
            detail=("rack view hidden from job start" if intervention.kind is InterventionKind.HIDE_RACK else ""),
        )
    return WorldState(
        run_id=run_id,
        lineage_id=lineage_id,
        job_id=job_id,
        job_seed=job.job_seed,
        target_matching=job.target_matching,
        x={"station": Station.X, "private_pairs": job.x_mask},
        y={"station": Station.Y, "private_pairs": job.y_mask},
        intervention=intervention_state,
    )


def _register_bank(state: WorldState, station: Station) -> tuple[RegisterState, RegisterState]:
    return state.registers_x if station is Station.X else state.registers_y


def _set_register_bank(
    state: WorldState, station: Station, bank: tuple[RegisterState, RegisterState]
) -> None:
    if station is Station.X:
        state.registers_x = bank
    else:
        state.registers_y = bank


def _set_station(state: WorldState, station: Station, station_state) -> None:
    if station is Station.X:
        state.x = station_state
    else:
        state.y = station_state


def _station_state(state: WorldState, station: Station):
    return state.x if station is Station.X else state.y


def _partner_view(state: WorldState, owner: Station) -> Layer:
    # X's layer is visible to Y through visible_layer_to_y; Y's to X through _to_x.
    if owner is Station.X:
        return state.visible_layer_to_y
    return state.visible_layer_to_x


def _set_partner_view(state: WorldState, owner: Station, layer: Layer) -> None:
    if owner is Station.X:
        state.visible_layer_to_y = layer
    else:
        state.visible_layer_to_x = layer


def _sync_partner_view(state: WorldState, owner: Station) -> None:
    _set_partner_view(state, owner, _station_state(state, owner).layer)


def _intervention_targets(state: WorldState, station: Station, kind: InterventionKind) -> bool:
    if not (
        state.intervention
        and state.intervention.kind == kind.value
        and station in state.intervention.target_stations
        and state.intervention.trigger_status is TriggerStatus.ARMED
    ):
        return False
    # The two register interventions are explicitly armed only for the first
    # legal target-station write selected at or after round three.
    if kind in {InterventionKind.DROP_WRITE, InterventionKind.DELAY_WRITE}:
        return state.round >= 3
    return True


def _trigger(
    state: WorldState,
    *,
    kind: InterventionKind,
    station: Station,
    round_number: int,
    effect: EffectStatus,
    detail: str,
) -> None:
    if state.intervention is None:
        return
    if state.intervention.kind != kind.value or station not in state.intervention.target_stations:
        return
    state.intervention = state.intervention.model_copy(
        update={
            "trigger_status": TriggerStatus.TRIGGERED,
            "effect_status": effect,
            "trigger_round": round_number,
            "effect_round": round_number,
            "detail": detail,
        }
    )


def begin_round(state: WorldState) -> tuple[WorldState, tuple[dict, ...]]:
    """Deliver due delayed effects and release one-round layer visibility."""

    if state.terminal:
        return state, ()
    updated = state.model_copy(deep=True)
    effects: list[dict] = []
    due = sorted(
        (item for item in updated.pending_writes if item.delivery_round == updated.round),
        key=lambda item: item.selected_round,
    )
    remaining = tuple(item for item in updated.pending_writes if item.delivery_round != updated.round)
    for item in due:
        effect_pre_hash = world_state_hash(updated)
        bank = list(_register_bank(updated, item.station))
        previous = bank[item.register]
        bank[item.register] = RegisterState(symbol=item.symbol, counter=previous.counter + 1)
        _set_register_bank(updated, item.station, tuple(bank))  # type: ignore[arg-type]
        effect_post_hash = world_state_hash(updated)
        effects.append(
            {
                "kind": EventKind.WRITE_DELIVERED.value,
                "station": item.station.value,
                "action_id": item.action_id,
                "visible_from_round": updated.round,
                "delivery_status": DeliveryStatus.DELIVERED.value,
                "detail": {"register": item.register, "symbol": item.symbol},
                "pre_state_hash": effect_pre_hash,
                "post_state_hash": effect_post_hash,
            }
        )
    updated.pending_writes = remaining

    suppression = updated.visibility_suppression
    if suppression is not None and updated.round >= suppression.release_round:
        effect_pre_hash = world_state_hash(updated)
        owner = suppression.owner
        _sync_partner_view(updated, owner)
        updated.visibility_suppression = None
        effect_post_hash = world_state_hash(updated)
        effects.append(
            {
                "kind": EventKind.LAYER_VISIBILITY_EXPIRED.value,
                "station": owner.value,
                "visible_from_round": updated.round,
                "detail": {"item": suppression.item},
                "pre_state_hash": effect_pre_hash,
                "post_state_hash": effect_post_hash,
            }
        )
    updated.visible_effects_x = tuple(
        effect.get("kind", "") for effect in effects if effect.get("station") in {None, "X"}
    )
    updated.visible_effects_y = tuple(
        effect.get("kind", "") for effect in effects if effect.get("station") in {None, "Y"}
    )
    return updated, tuple(effects)


def _illegal(
    state: WorldState,
    station: Station,
    action: WorldAction,
    action_id: str,
    reason: str,
    pre_hash: str,
) -> ActionOutcome:
    current = _station_state(state, station)
    current.illegal_action_count += 1
    return ActionOutcome(
        station=station,
        action_id=action_id,
        action_payload=action_payload(action),
        legal=False,
        rejection_reason=reason,
        pre_state_hash=pre_hash,
        post_state_hash=world_state_hash(state),
    )


def _apply_action(
    state: WorldState,
    station: Station,
    action: WorldAction,
    action_id: str,
    *,
    pre_hash_override: str | None = None,
) -> tuple[ActionOutcome, tuple[dict, ...]]:
    pre_hash = pre_hash_override or world_state_hash(state)
    current = _station_state(state, station)
    if current.finished:
        return _illegal(state, station, action, action_id, "station_already_finished", pre_hash), ()

    effects: list[dict] = []
    delivery = DeliveryStatus.NOT_APPLICABLE
    visible_from: int | None = None
    if isinstance(action, WriteAction):
        if current.writes_remaining <= 0:
            return _illegal(state, station, action, action_id, "write_budget_exhausted", pre_hash), ()
        current.writes_remaining -= 1
        current.legal_action_count += 1
        if _intervention_targets(state, station, InterventionKind.DROP_WRITE):
            _trigger(
                state,
                kind=InterventionKind.DROP_WRITE,
                station=station,
                round_number=state.round,
                effect=EffectStatus.APPLIED,
                detail="selected legal write was suppressed",
            )
            delivery = DeliveryStatus.DROPPED
            effects.append({"kind": EventKind.WRITE_DROPPED.value, "station": station.value, "action_id": action_id})
        elif _intervention_targets(state, station, InterventionKind.DELAY_WRITE):
            delivery_round = state.round + 3
            pending = PendingWrite(
                station=station,
                register=action.register,
                symbol=action.symbol,
                selected_round=state.round,
                delivery_round=delivery_round,
                action_id=action_id,
            )
            state.pending_writes = (*state.pending_writes, pending)
            _trigger(
                state,
                kind=InterventionKind.DELAY_WRITE,
                station=station,
                round_number=state.round,
                effect=EffectStatus.PENDING,
                detail="write queued for exactly two full hidden rounds",
            )
            delivery = DeliveryStatus.DELAYED
            visible_from = delivery_round
            effects.append(
                {
                    "kind": EventKind.WRITE_DELAYED.value,
                    "station": station.value,
                    "action_id": action_id,
                    "visible_from_round": delivery_round,
                }
            )
        else:
            bank = list(_register_bank(state, station))
            previous = bank[action.register]
            bank[action.register] = RegisterState(
                symbol=action.symbol, counter=previous.counter + 1
            )
            _set_register_bank(state, station, tuple(bank))  # type: ignore[arg-type]
            delivery = DeliveryStatus.DELIVERED
            visible_from = state.round + 1
            effects.append(
                {
                    "kind": EventKind.WRITE_DELIVERED.value,
                    "station": station.value,
                    "action_id": action_id,
                    "visible_from_round": visible_from,
                }
            )
        return ActionOutcome(
            station=station,
            action_id=action_id,
            action_payload=action_payload(action),
            legal=True,
            pre_state_hash=pre_hash,
            post_state_hash=world_state_hash(state),
            delivery_status=delivery,
            visible_from_round=visible_from,
        ), tuple(effects)

    if isinstance(action, SetAction):
        if current.layer[action.item] is not None:
            return _illegal(state, station, action, action_id, "item_already_set", pre_hash), ()
        if action.target in {target for target in current.layer if target is not None}:
            return _illegal(state, station, action, action_id, "target_already_used", pre_hash), ()
        if current.mutations_remaining <= 0:
            return _illegal(state, station, action, action_id, "mutation_budget_exhausted", pre_hash), ()
        delayed_visibility = _intervention_targets(
            state, station, InterventionKind.DELAY_LAYER_VISIBILITY
        ) and sum(target is not None for target in current.layer) >= 2
        current_layer = list(current.layer)
        current_layer[action.item] = action.target
        current.layer = tuple(current_layer)  # type: ignore[assignment]
        current.mutations_remaining -= 1
        current.legal_action_count += 1
        if delayed_visibility:
            _trigger(
                state,
                kind=InterventionKind.DELAY_LAYER_VISIBILITY,
                station=station,
                round_number=state.round,
                effect=EffectStatus.APPLIED,
                detail="partner layer visibility suppressed for one observation",
            )
            state.visibility_suppression = VisibilitySuppression(
                owner=station,
                item=action.item,
                selected_round=state.round,
                release_round=state.round + 2,
                hidden_target=_partner_view(state, station)[action.item]
                if _partner_view(state, station)[action.item] is not None
                else -1,
            )
            effects.append(
                {
                    "kind": EventKind.LAYER_VISIBILITY_DELAYED.value,
                    "station": station.value,
                    "action_id": action_id,
                    "visible_from_round": state.round + 2,
                    "item": action.item,
                }
            )
        else:
            _sync_partner_view(state, station)
        effects.append(
            {
                "kind": EventKind.LAYER_SET.value,
                "station": station.value,
                "action_id": action_id,
                "item": action.item,
                "target": action.target,
            }
        )
        if _intervention_targets(state, station, InterventionKind.CLEAR_LAYER_ENTRY) and sum(
            target is not None for target in current.layer
        ) >= 4:
            clear_item = min(item for item, target in enumerate(current.layer) if target is not None)
            cleared_layer = list(current.layer)
            cleared_layer[clear_item] = None
            current.layer = tuple(cleared_layer)  # type: ignore[assignment]
            _sync_partner_view(state, station)
            _trigger(
                state,
                kind=InterventionKind.CLEAR_LAYER_ENTRY,
                station=station,
                round_number=state.round,
                effect=EffectStatus.APPLIED,
                detail=f"environment cleared item {clear_item}",
            )
            effects.append(
                {
                    "kind": EventKind.LAYER_UNSET.value,
                    "station": "environment",
                    "target_station": station.value,
                    "item": clear_item,
                    "environment_clear": True,
                }
            )
        return ActionOutcome(
            station=station,
            action_id=action_id,
            action_payload=action_payload(action),
            legal=True,
            pre_state_hash=pre_hash,
            post_state_hash=world_state_hash(state),
        ), tuple(effects)

    if isinstance(action, UnsetAction):
        if current.layer[action.item] is None:
            return _illegal(state, station, action, action_id, "item_is_unset", pre_hash), ()
        if current.mutations_remaining <= 0:
            return _illegal(state, station, action, action_id, "mutation_budget_exhausted", pre_hash), ()
        updated_layer = list(current.layer)
        updated_layer[action.item] = None
        current.layer = tuple(updated_layer)  # type: ignore[assignment]
        current.mutations_remaining -= 1
        current.legal_action_count += 1
        _sync_partner_view(state, station)
        effects.append(
            {"kind": EventKind.LAYER_UNSET.value, "station": station.value, "action_id": action_id, "item": action.item}
        )
        return ActionOutcome(
            station=station,
            action_id=action_id,
            action_payload=action_payload(action),
            legal=True,
            pre_state_hash=pre_hash,
            post_state_hash=world_state_hash(state),
        ), tuple(effects)

    if isinstance(action, FinishAction):
        current.finished = True
        current.finish_round = state.round
        current.legal_action_count += 1
        effects.append({"kind": EventKind.FINISH_LOCKED.value, "station": station.value, "action_id": action_id})
        return ActionOutcome(
            station=station,
            action_id=action_id,
            action_payload=action_payload(action),
            legal=True,
            pre_state_hash=pre_hash,
            post_state_hash=world_state_hash(state),
        ), tuple(effects)

    if isinstance(action, WaitAction):
        current.legal_action_count += 1
        return ActionOutcome(
            station=station,
            action_id=action_id,
            action_payload=action_payload(action),
            legal=True,
            pre_state_hash=pre_hash,
            post_state_hash=world_state_hash(state),
        ), ()

    raise TypeError(f"unsupported world action: {type(action)!r}")


def resolve_round(
    state: WorldState,
    x_action: WorldAction,
    y_action: WorldAction,
    *,
    x_action_id: str | None = None,
    y_action_id: str | None = None,
) -> tuple[WorldState, RoundResolution]:
    """Resolve two decisions selected from one identical pre-round state."""

    if state.terminal:
        raise RuntimeError("cannot resolve a round after job termination")
    current_round = state.round
    pre_hash = world_state_hash(state)
    updated = state.model_copy(deep=True)
    x_result, x_effects = _apply_action(
        updated,
        Station.X,
        x_action,
        x_action_id or f"X:r{current_round}",
        pre_hash_override=pre_hash,
    )
    y_result, y_effects = _apply_action(
        updated,
        Station.Y,
        y_action,
        y_action_id or f"Y:r{current_round}",
        pre_hash_override=pre_hash,
    )
    effects = (*x_effects, *y_effects)
    if updated.x.finished and updated.y.finished:
        updated.terminal = True
        updated.rounds_remaining = 0
        updated.success = _success(updated)
    elif current_round >= 16:
        updated.terminal = True
        updated.rounds_remaining = 0
        updated.success = _success(updated)
    else:
        updated.round = current_round + 1
        updated.rounds_remaining = 16 - current_round
    post_hash = world_state_hash(updated)
    x_result = x_result.model_copy(update={"post_state_hash": post_hash})
    y_result = y_result.model_copy(update={"post_state_hash": post_hash})
    resolution = RoundResolution(
        round=current_round,
        pre_state_hash=pre_hash,
        post_state_hash=post_hash,
        x=x_result,
        y=y_result,
        effects=tuple((*effects,)),
    )
    return updated, resolution


def _rack_hidden(schedule: InterventionSchedule | None, station: Station) -> bool:
    return bool(
        schedule
        and schedule.kind is InterventionKind.HIDE_RACK
        and station in schedule.target_stations
    )


def observation(
    state: WorldState,
    station: Station,
    rack: RackState,
    *,
    schedule: InterventionSchedule | None,
    first_observation: bool,
) -> Observation:
    current = _station_state(state, station)
    other = Station.Y if station is Station.X else Station.X
    other_layer = (
        state.visible_layer_to_x if station is Station.X else state.visible_layer_to_y
    )
    other_state = _station_state(state, other)
    if _rack_hidden(schedule, station):
        rack_view = hidden_rack_view()
    elif first_observation:
        rack_view = full_rack_view(rack)
    else:
        rack_view = hashed_rack_view(rack)
    effects = state.visible_effects_x if station is Station.X else state.visible_effects_y
    return Observation(
        station=station,
        round=state.round,
        private_pairs=current.private_pairs,
        layers={
            station.value: current.layer,
            other.value: other_layer,
        },
        registers={
            Station.X.value: state.registers_x,
            Station.Y.value: state.registers_y,
        },
        remaining={
            station.value: {
                "writes": current.writes_remaining,
                "mutations": current.mutations_remaining,
            },
            other.value: {
                "writes": other_state.writes_remaining,
                "mutations": other_state.mutations_remaining,
            },
            "rounds": {"value": state.rounds_remaining},
        },
        finished={Station.X.value: state.x.finished, Station.Y.value: state.y.finished},
        rack=rack_view,
        visible_effects=effects,
    )


def _frame(
    state: WorldState,
    station: Station,
    observation_before: Observation,
    outcome: ActionOutcome,
) -> FilmFrame:
    # Frame fields are exactly local observations plus the typed local action/result.
    if station is Station.X:
        layer_x = state.x.layer
        layer_y = state.visible_layer_to_x
    else:
        layer_x = state.visible_layer_to_y
        layer_y = state.y.layer
    current = _station_state(state, station)
    return FilmFrame(
        round=observation_before.round,
        station=station,
        private_pairs=observation_before.private_pairs,
        layer_x=layer_x,
        layer_y=layer_y,
        registers_x=state.registers_x,
        registers_y=state.registers_y,
        remaining_rounds=state.rounds_remaining,
        writes_remaining=current.writes_remaining,
        mutations_remaining=current.mutations_remaining,
        finished_x=state.x.finished,
        finished_y=state.y.finished,
        action_payload=outcome.action_payload,
        action_legal=outcome.legal,
        rejection_reason=outcome.rejection_reason,
        visible_effects=(
            state.visible_effects_x if station is Station.X else state.visible_effects_y
        ),
    )


def _emit_action_events(log: EventLog, state: WorldState, outcome: ActionOutcome) -> EventLog:
    kind = EventKind.ACTION_SUBMITTED if outcome.legal else EventKind.ACTION_REJECTED
    current = _station_state(state, outcome.station)
    action_name = (
        outcome.action_payload.get("action")
        if isinstance(outcome.action_payload, dict)
        else None
    )
    write_before = current.writes_remaining
    write_after = write_before - 1 if outcome.legal and action_name == "write" else write_before
    mutation_before = current.mutations_remaining
    mutation_after = (
        mutation_before - 1
        if outcome.legal and action_name in {"set", "unset"}
        else mutation_before
    )
    return log.append(
        round=state.round,
        phase="job",
        source=outcome.station,
        event_kind=kind,
        action_id=outcome.action_id,
        action_payload=outcome.action_payload,
        legal=outcome.legal,
        rejection_reason=outcome.rejection_reason,
        pre_state_hash=outcome.pre_state_hash,
        post_state_hash=outcome.post_state_hash,
        write_budget_before=write_before,
        write_budget_after=write_after,
        mutation_budget_before=mutation_before,
        mutation_budget_after=mutation_after,
        delivery_status=outcome.delivery_status,
        visible_from_round=outcome.visible_from_round,
    )


def _emit_effect_events(log: EventLog, state: WorldState, resolution: RoundResolution) -> EventLog:
    updated = log
    for effect in resolution.effects:
        kind_value = effect.get("kind")
        try:
            kind = EventKind(kind_value)
        except ValueError:
            continue
        source: Station | Literal["environment"] = (
            effect.get("station")
            if effect.get("station") in {"X", "Y"}
            else "environment"
        )
        if isinstance(source, str) and source in {"X", "Y"}:
            source = Station(source)
        updated = updated.append(
            round=resolution.round,
            phase="job",
            source=source,
            event_kind=kind,
            action_id=effect.get("action_id"),
            action_payload=effect.get("detail"),
            legal=True,
            pre_state_hash=resolution.pre_state_hash,
            post_state_hash=resolution.post_state_hash,
            delivery_status=(
                DeliveryStatus(effect["delivery_status"])
                if effect.get("delivery_status")
                else None
            ),
            visible_from_round=effect.get("visible_from_round"),
            detail={key: value for key, value in effect.items() if key not in {"kind", "station", "action_id", "detail", "delivery_status", "visible_from_round"}},
        )
    return updated


def _finalize_intervention(state: WorldState, log: EventLog) -> tuple[WorldState, EventLog]:
    updated = state.model_copy(deep=True)
    updated_log = log
    if updated.pending_writes:
        for pending in sorted(updated.pending_writes, key=lambda item: item.selected_round):
            updated_log = updated_log.append(
                round=updated.round,
                phase="job",
                source="environment",
                event_kind=EventKind.WRITE_CANCELLED,
                action_id=pending.action_id,
                legal=True,
                pre_state_hash=world_state_hash(updated),
                post_state_hash=world_state_hash(updated),
                delivery_status=DeliveryStatus.CANCELLED_AT_JOB_END,
                visible_from_round=pending.delivery_round,
                detail={"selected_round": pending.selected_round},
            )
        updated.pending_writes = ()
        if updated.intervention and updated.intervention.kind == InterventionKind.DELAY_WRITE.value:
            updated.intervention = updated.intervention.model_copy(
                update={"effect_status": EffectStatus.CANCELLED_AT_JOB_END}
            )
    if updated.visibility_suppression is not None:
        suppression = updated.visibility_suppression
        updated_log = updated_log.append(
            round=updated.round,
            phase="job",
            source="environment",
            event_kind=EventKind.LAYER_VISIBILITY_EXPIRED,
            legal=True,
            pre_state_hash=world_state_hash(updated),
            post_state_hash=world_state_hash(updated),
            effect_status=EffectStatus.VISIBILITY_EXPIRED_AT_JOB_END,
            visible_from_round=suppression.release_round,
            detail={"item": suppression.item},
        )
        updated.visibility_suppression = None
        if updated.intervention and updated.intervention.kind == InterventionKind.DELAY_LAYER_VISIBILITY.value:
            updated.intervention = updated.intervention.model_copy(
                update={"effect_status": EffectStatus.VISIBILITY_EXPIRED_AT_JOB_END}
            )
    if updated.intervention and updated.intervention.trigger_status is TriggerStatus.ARMED:
        updated.intervention = updated.intervention.model_copy(
            update={"trigger_status": TriggerStatus.NOT_TRIGGERED, "effect_status": EffectStatus.NOT_APPLICABLE}
        )
        updated_log = updated_log.append(
            round=updated.round,
            phase="job",
            source="environment",
            event_kind=EventKind.INTERVENTION_NOT_TRIGGERED,
            legal=True,
            pre_state_hash=world_state_hash(updated),
            post_state_hash=world_state_hash(updated),
            intervention_id=updated.intervention.intervention_id,
            trigger_status=TriggerStatus.NOT_TRIGGERED,
            effect_status=EffectStatus.NOT_APPLICABLE,
        )
    return updated, updated_log


def _memory_view(schedule: InterventionSchedule | None, station: Station, rack: RackState) -> RackView:
    return hidden_rack_view() if _rack_hidden(schedule, station) else full_rack_view(rack)


def run_job(
    job,
    *,
    run_id: str,
    lineage_id: str,
    job_id: str,
    policy_x: Policy,
    policy_y: Policy,
    rack_x: RackState | None = None,
    rack_y: RackState | None = None,
    intervention: InterventionSchedule | None = None,
    memory_policy_x: MemoryPolicy | None = None,
    memory_policy_y: MemoryPolicy | None = None,
    read_only_probe: bool = False,
) -> JobResult:
    """Run one deterministic model-free job using only role-local policies."""

    from .generator import validate_job

    job = validate_job(job)
    read_only_probe = read_only_probe or bool(
        intervention is not None and intervention.read_only_probe
    )
    initial_rack_x = rack_x or empty_rack()
    initial_rack_y = rack_y or empty_rack()
    state = initial_state(
        job,
        run_id=run_id,
        lineage_id=lineage_id,
        job_id=job_id,
        intervention=intervention,
    )
    log = EventLog(
        run_id=run_id,
        lineage_id=lineage_id,
        job_id=job_id,
        job_seed=job.job_seed,
    )
    state_hash = world_state_hash(state)
    log = log.append(
        round=0,
        phase="job",
        source="environment",
        event_kind=EventKind.JOB_START,
        pre_state_hash=state_hash,
        post_state_hash=state_hash,
        intervention_id=state.intervention.intervention_id if state.intervention else None,
        trigger_status=state.intervention.trigger_status if state.intervention else None,
        effect_status=state.intervention.effect_status if state.intervention else None,
    )
    log = log.append(
        round=0,
        phase="job",
        source="environment",
        event_kind=EventKind.CONTEXT_RESET,
        pre_state_hash=state_hash,
        post_state_hash=state_hash,
        detail={"same_actor_lifecycle_required": True},
    )
    if intervention is not None:
        log = log.append(
            round=0,
            phase="job",
            source="environment",
            event_kind=EventKind.INTERVENTION_ARMED,
            pre_state_hash=state_hash,
            post_state_hash=state_hash,
            intervention_id=intervention.intervention_id,
            trigger_status=state.intervention.trigger_status if state.intervention else None,
            effect_status=state.intervention.effect_status if state.intervention else None,
        )
        if intervention.kind is InterventionKind.HIDE_RACK:
            log = log.append(
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
    frames_x: list[FilmFrame] = []
    frames_y: list[FilmFrame] = []
    rounds = 0
    while not state.terminal:
        state, begin_effects = begin_round(state)
        for effect in begin_effects:
            log = log.append(
                round=state.round,
                phase="job",
                source=Station(effect["station"]) if effect.get("station") in {"X", "Y"} else "environment",
                event_kind=EventKind(effect["kind"]),
                pre_state_hash=effect.get("pre_state_hash", world_state_hash(state)),
                post_state_hash=effect.get("post_state_hash", world_state_hash(state)),
                action_id=effect.get("action_id"),
                visible_from_round=effect.get("visible_from_round"),
                delivery_status=(
                    DeliveryStatus(effect["delivery_status"])
                    if effect.get("delivery_status")
                    else None
                ),
                detail=effect.get("detail", {}),
            )
        first_observation = state.round == 1
        obs_x = observation(
            state,
            Station.X,
            rack_x or empty_rack(),
            schedule=intervention,
            first_observation=first_observation,
        )
        obs_y = observation(
            state,
            Station.Y,
            rack_y or empty_rack(),
            schedule=intervention,
            first_observation=first_observation,
        )
        observation_hash = world_state_hash(state)
        for station, obs, rack in (
            (Station.X, obs_x, rack_x or empty_rack()),
            (Station.Y, obs_y, rack_y or empty_rack()),
        ):
            log = log.append(
                round=state.round,
                phase="job",
                source=station,
                event_kind=EventKind.OBSERVATION,
                pre_state_hash=observation_hash,
                post_state_hash=observation_hash,
                rack_hash_before=rack.content_hash,
                rack_hash_after=rack.content_hash,
                detail={"observation_hash": stable_hash(obs.model_dump(mode="json"))},
            )
            log = log.append(
                round=state.round,
                phase="job",
                source=station,
                event_kind=EventKind.RACK_VIEWED,
                pre_state_hash=observation_hash,
                post_state_hash=observation_hash,
                rack_hash_before=rack.content_hash,
                rack_hash_after=rack.content_hash,
                detail={"available": obs.rack.available, "hashed_only": obs.rack.hashed_only},
            )
        # Both observations are materialized before either policy is called.
        action_x = policy_x(obs_x)
        action_y = policy_y(obs_y)
        intervention_before = state.intervention
        resolution_state, resolution = resolve_round(
            state,
            action_x,
            action_y,
            x_action_id=f"X:r{state.round}",
            y_action_id=f"Y:r{state.round}",
        )
        log = _emit_action_events(log, state, resolution.x)
        log = _emit_action_events(log, state, resolution.y)
        log = _emit_effect_events(log, state, resolution)
        if (
            intervention_before is not None
            and intervention_before.trigger_status is TriggerStatus.ARMED
            and resolution_state.intervention is not None
            and resolution_state.intervention.trigger_status is TriggerStatus.TRIGGERED
        ):
            triggered = resolution_state.intervention
            log = log.append(
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
            log = log.append(
                round=resolution.round,
                phase="job",
                source=Station.X,
                event_kind=EventKind.FINISH_LOCKED,
                action_id=resolution.x.action_id,
                pre_state_hash=resolution.pre_state_hash,
                post_state_hash=resolution.post_state_hash,
            )
        if resolution.y.action_payload.get("action") == "finish" and resolution.y.legal:
            log = log.append(
                round=resolution.round,
                phase="job",
                source=Station.Y,
                event_kind=EventKind.FINISH_LOCKED,
                action_id=resolution.y.action_id,
                pre_state_hash=resolution.pre_state_hash,
                post_state_hash=resolution.post_state_hash,
            )
        frames_x.append(_frame(resolution_state, Station.X, obs_x, resolution.x))
        frames_y.append(_frame(resolution_state, Station.Y, obs_y, resolution.y))
        state = resolution_state
        rounds += 1

    state, log = _finalize_intervention(state, log)
    log = log.append(
        round=state.round,
        phase="job",
        source="environment",
        event_kind=EventKind.JOB_END,
        pre_state_hash=world_state_hash(state),
        post_state_hash=world_state_hash(state),
        detail={"success": state.success, "rounds_resolved": rounds},
    )

    mutations_x: tuple[RackMutation, ...] = ()
    mutations_y: tuple[RackMutation, ...] = ()
    final_rack_x = rack_x or empty_rack()
    final_rack_y = rack_y or empty_rack()
    if not read_only_probe:
        log = log.append(
            round=state.round,
            phase="job",
            source="environment",
            event_kind=EventKind.MEMORY_PHASE_START,
            pre_state_hash=world_state_hash(state),
            post_state_hash=world_state_hash(state),
        )
        # A no-op policy is the explicit keep_unchanged path.  The two stations
        # choose independently from their own post-job rack.
        choices = []
        for station, rack, memory_policy, frames in (
            (Station.X, final_rack_x, memory_policy_x, tuple(frames_x)),
            (Station.Y, final_rack_y, memory_policy_y, tuple(frames_y)),
        ):
            view = _memory_view(intervention, station, rack)
            choices.append(
                (
                    station,
                    rack,
                    memory_policy(station, view, frames)
                    if memory_policy is not None
                    else (None, None),
                    frames,
                )
            )
        log = log.append(
            round=state.round,
            phase="eviction",
            source="environment",
            event_kind=EventKind.MEMORY_EVICTION_PHASE,
            pre_state_hash=world_state_hash(state),
            post_state_hash=world_state_hash(state),
        )
        for station, rack, (evict_handle, _), frames in choices:
            if evict_handle is None:
                final_rack, mutations = apply_memory_phases(
                    rack,
                    station,
                    frames,
                    evict_handle=None,
                    retain_start_round=None,
                    source_job_id=job_id,
                    handle_seed=f"{lineage_id}:{job_id}:{station.value}",
                )
                eviction = mutations[0]
            else:
                final_rack, eviction = apply_memory_phases(
                    rack,
                    station,
                    frames,
                    evict_handle=evict_handle,
                    retain_start_round=None,
                    source_job_id=job_id,
                    handle_seed=f"{lineage_id}:{job_id}:{station.value}",
                )
            if station is Station.X:
                final_rack_x = final_rack
                mutations_x = (eviction,)
            else:
                final_rack_y = final_rack
                mutations_y = (eviction,)
            log = log.append(
                round=state.round,
                phase="eviction",
                source=station,
                event_kind=EventKind.EVICT_ATTEMPTED,
                action_payload=(
                    {"action": "keep_unchanged"}
                    if evict_handle is None
                    else {"action": "evict", "fragment_handle": evict_handle}
                ),
                pre_state_hash=world_state_hash(state),
                post_state_hash=world_state_hash(state),
                legal=eviction.legal,
                rejection_reason=eviction.rejection_reason,
                rack_hash_before=eviction.rack_hash_before,
                rack_hash_after=eviction.rack_hash_after,
                fragment_hash=eviction.fragment_hash,
            )
            if eviction.legal and eviction.fragment_hash is not None:
                log = log.append(
                    round=state.round,
                    phase="eviction",
                    source=station,
                    event_kind=EventKind.EVICTED,
                    pre_state_hash=world_state_hash(state),
                    post_state_hash=world_state_hash(state),
                    rack_hash_before=eviction.rack_hash_before,
                    rack_hash_after=eviction.rack_hash_after,
                    fragment_hash=eviction.fragment_hash,
                )
        log = log.append(
            round=state.round,
            phase="retention",
            source="environment",
            event_kind=EventKind.MEMORY_RETENTION_PHASE,
            pre_state_hash=world_state_hash(state),
            post_state_hash=world_state_hash(state),
        )
        for station, _, (_, retain_start), frames in choices:
            rack = final_rack_x if station is Station.X else final_rack_y
            if retain_start is None:
                final_rack, mutations = apply_memory_phases(
                    rack,
                    station,
                    frames,
                    evict_handle=None,
                    retain_start_round=None,
                    source_job_id=job_id,
                    handle_seed=f"{lineage_id}:{job_id}:{station.value}",
                )
                retention = mutations[1]
            else:
                final_rack, mutations = apply_memory_phases(
                    rack,
                    station,
                    frames,
                    evict_handle=None,
                    retain_start_round=retain_start,
                    source_job_id=job_id,
                    handle_seed=f"{lineage_id}:{job_id}:{station.value}",
                )
                retention = mutations[1]
            if station is Station.X:
                final_rack_x = final_rack
                mutations_x = (*mutations_x, retention)
            else:
                final_rack_y = final_rack
                mutations_y = (*mutations_y, retention)
            log = log.append(
                round=state.round,
                phase="retention",
                source=station,
                event_kind=EventKind.RETAIN_ATTEMPTED,
                action_payload=(
                    {"action": "keep_unchanged"}
                    if retain_start is None
                    else {"action": "retain", "start_round": retain_start}
                ),
                pre_state_hash=world_state_hash(state),
                post_state_hash=world_state_hash(state),
                legal=retention.legal,
                rejection_reason=retention.rejection_reason,
                rack_hash_before=retention.rack_hash_before,
                rack_hash_after=retention.rack_hash_after,
                fragment_hash=retention.fragment_hash,
                local_window_bounds=retention.local_window_bounds,
                detail=(
                    {"source_job_id": job_id}
                    if retention.legal or retain_start is not None
                    else {}
                ),
            )
            if retention.legal:
                log = log.append(
                    round=state.round,
                    phase="retention",
                    source=station,
                    event_kind=EventKind.RETAINED,
                    pre_state_hash=world_state_hash(state),
                    post_state_hash=world_state_hash(state),
                    rack_hash_before=retention.rack_hash_before,
                    rack_hash_after=retention.rack_hash_after,
                    fragment_hash=retention.fragment_hash,
                    local_window_bounds=retention.local_window_bounds,
                    detail={"source_job_id": job_id},
                )

    failure_reason = None
    if not state.success:
        if not state.x.finished or not state.y.finished:
            failure_reason = "both_stations_did_not_finish"
        elif state.x.layer != state.y.layer:
            failure_reason = "terminal_layers_differ"
        elif not _layer_is_bijection(state.x.layer) or not _layer_is_bijection(state.y.layer):
            failure_reason = "terminal_layer_not_bijective"
        else:
            failure_reason = "terminal_assignment_contains_invalid_edge"
    return JobResult(
        run_id=run_id,
        lineage_id=lineage_id,
        job_id=job_id,
        job_seed=job.job_seed,
        initial_rack_x=initial_rack_x,
        initial_rack_y=initial_rack_y,
        intervention_schedule=intervention,
        final_rack_x=final_rack_x,
        final_rack_y=final_rack_y,
        final_state=state,
        event_log=log,
        success=state.success,
        rounds_resolved=rounds,
        failure_reason=failure_reason,
        frames_x=tuple(frames_x),
        frames_y=tuple(frames_y),
        memory_mutations_x=mutations_x,
        memory_mutations_y=mutations_y,
    )


def replay_job(result: JobResult) -> JobResult:
    """Replay only the typed actions recorded in an event log and compare later."""

    world_events = [
        event
        for event in result.event_log.events
        if event.event_kind in {EventKind.ACTION_SUBMITTED, EventKind.ACTION_REJECTED}
    ]
    by_round: dict[int, dict[Station, WorldAction]] = {}
    for event in world_events:
        if not isinstance(event.source, Station) or event.action_payload is None:
            raise ValueError("action event is missing its typed station payload")
        by_round.setdefault(event.round, {})[event.source] = parse_world_action(
            __import__("json").dumps(event.action_payload, separators=(",", ":"))
        )
    if not by_round:
        raise ValueError("event log contains no world actions to replay")

    def scripted(station: Station) -> Policy:
        def policy(obs: Observation) -> WorldAction:
            try:
                return by_round[obs.round][station]
            except KeyError as exc:
                raise ValueError(f"missing recorded {station.value} action at round {obs.round}") from exc

        return policy

    eviction: dict[Station, str | None] = {Station.X: None, Station.Y: None}
    retention: dict[Station, int | None] = {Station.X: None, Station.Y: None}
    for event in result.event_log.events:
        if event.event_kind is EventKind.EVICT_ATTEMPTED and isinstance(event.source, Station):
            if event.action_payload and event.action_payload.get("action") == "evict":
                eviction[event.source] = event.action_payload["fragment_handle"]
        if event.event_kind is EventKind.RETAIN_ATTEMPTED and isinstance(event.source, Station):
            if event.action_payload and event.action_payload.get("action") == "retain":
                retention[event.source] = event.action_payload["start_round"]

    def memory(station: Station, view: RackView, frames: tuple[FilmFrame, ...]) -> tuple[str | None, int | None]:
        del view, frames
        return eviction[station], retention[station]

    replayed = run_job(
        generate_job(result.job_seed),
        run_id=result.run_id,
        lineage_id=result.lineage_id,
        job_id=result.job_id,
        policy_x=scripted(Station.X),
        policy_y=scripted(Station.Y),
        rack_x=result.initial_rack_x,
        rack_y=result.initial_rack_y,
        intervention=result.intervention_schedule,
        memory_policy_x=memory,
        memory_policy_y=memory,
        read_only_probe=not any(
            event.event_kind is EventKind.MEMORY_PHASE_START
            for event in result.event_log.events
        ),
    )
    if replayed.final_state_hash != result.final_state_hash:
        raise AssertionError("replay final state hash differs from original")
    if replayed.success != result.success:
        raise AssertionError("replay reward differs from original")
    return replayed
