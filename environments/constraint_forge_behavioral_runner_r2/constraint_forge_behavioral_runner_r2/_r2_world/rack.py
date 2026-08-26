"""Role-local immutable six-film racks and exact memory-phase semantics."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator

from ._config import max_rounds
from .canonical import canonical_bytes, sha256_bytes, stable_hash
from .models import (
    Layer,
    MutableStrictModel,
    Pair,
    RegisterState,
    Station,
    StrictModel,
)


class FilmFrame(StrictModel):
    """One local sensorimotor frame; it contains no rack or prior-film field."""

    schema_version: Literal["constraint-forge/film-frame/v0"] = (
        "constraint-forge/film-frame/v0"
    )
    round: Annotated[StrictInt, Field(ge=1)]
    station: Station
    private_pairs: tuple[Pair, ...]
    layer_x: Layer
    layer_y: Layer
    registers_x: tuple[RegisterState, RegisterState]
    registers_y: tuple[RegisterState, RegisterState]
    remaining_rounds: Annotated[StrictInt, Field(ge=0)]
    writes_remaining: Annotated[StrictInt, Field(ge=0)]
    mutations_remaining: Annotated[StrictInt, Field(ge=0)]
    finished_x: StrictBool
    finished_y: StrictBool
    action_payload: dict
    action_legal: StrictBool
    rejection_reason: StrictStr | None = None

    @field_validator("round")
    @classmethod
    def _frame_round_within_job(cls, value: int) -> int:
        if value > max_rounds():
            raise ValueError(f"round exceeds configured max_rounds {max_rounds()}")
        return value

    @field_validator("remaining_rounds")
    @classmethod
    def _remaining_within_job(cls, value: int) -> int:
        if value > max_rounds():
            raise ValueError(
                f"remaining_rounds exceeds configured max_rounds {max_rounds()}"
            )
        return value
    visible_effects: tuple[StrictStr, ...] = ()


class Film(StrictModel):
    schema_version: Literal["constraint-forge/film/v0"] = "constraint-forge/film/v0"
    handle: StrictStr = Field(min_length=1)
    content_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    frames: tuple[FilmFrame, ...]

    @property
    def content_payload(self) -> list[dict]:
        return [frame.model_dump(mode="json") for frame in self.frames]

    @property
    def content_bytes(self) -> bytes:
        return canonical_bytes(self.content_payload)

    @model_validator(mode="after")
    def validate_immutable_content(self) -> "Film":
        if len(self.frames) != 6:
            raise ValueError("a film must contain exactly six frames")
        rounds = [frame.round for frame in self.frames]
        if rounds != list(range(rounds[0], rounds[0] + 6)):
            raise ValueError("film frames must be six contiguous rounds")
        if self.content_hash != sha256_bytes(self.content_bytes):
            raise ValueError("film content hash does not match immutable frame bytes")
        return self


class FilmSummary(StrictModel):
    handle: StrictStr
    content_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class RackState(StrictModel):
    schema_version: Literal["constraint-forge/rack/v0"] = "constraint-forge/rack/v0"
    capacity: Literal[6] = 6
    films: tuple[Film, ...] = ()

    @model_validator(mode="after")
    def validate_order_and_capacity(self) -> "RackState":
        if len(self.films) > self.capacity:
            raise ValueError("rack capacity is six films")
        handles = [film.handle for film in self.films]
        if len(handles) != len(set(handles)):
            raise ValueError("rack film handles must be unique")
        expected = tuple(sorted(self.films, key=lambda film: (film.content_hash, film.handle)))
        if self.films != expected:
            raise ValueError("rack films must be canonically ordered by content hash")
        return self

    @property
    def serialization_payload(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "capacity": self.capacity,
            "films": [
                {
                    "handle": film.handle,
                    "content_hash": film.content_hash,
                    "frames": film.content_payload,
                }
                for film in self.films
            ],
        }

    @property
    def serialization_bytes(self) -> bytes:
        return canonical_bytes(self.serialization_payload)

    @property
    def content_hash(self) -> str:
        return sha256_bytes(self.serialization_bytes)

    def summaries(self) -> tuple[FilmSummary, ...]:
        return tuple(
            FilmSummary(handle=film.handle, content_hash=film.content_hash)
            for film in self.films
        )


class RackView(StrictModel):
    """Model-visible rack view, including the exact hidden-rack sentinel."""

    available: StrictBool
    rack_unavailable: Literal["rack_unavailable"] | None = None
    full_films: tuple[Film, ...] = ()
    content_hash: StrictStr | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    hashed_only: StrictBool = False

    @model_validator(mode="after")
    def validate_view(self) -> "RackView":
        if not self.available:
            if self.rack_unavailable != "rack_unavailable":
                raise ValueError("hidden rack must use the rack_unavailable sentinel")
            if self.full_films or self.content_hash or self.hashed_only:
                raise ValueError("hidden rack view must omit all rack contents")
        elif self.rack_unavailable is not None:
            raise ValueError("available rack cannot carry the hidden sentinel")
        if self.hashed_only and self.full_films:
            raise ValueError("hashed-only rack view cannot contain film bytes")
        if self.hashed_only and self.content_hash is None:
            raise ValueError("hashed-only rack view must expose the rack content hash")
        if not self.hashed_only and self.content_hash is not None:
            raise ValueError("full rack view must not replace films with a hash")
        return self


class RackMutation(StrictModel):
    station: Station
    operation: Literal["retain", "evict", "keep_unchanged"]
    legal: StrictBool
    rejection_reason: StrictStr | None = None
    rack_hash_before: StrictStr
    rack_hash_after: StrictStr
    fragment_handle: StrictStr | None = None
    fragment_hash: StrictStr | None = None
    local_window_bounds: tuple[StrictInt, StrictInt] | None = None
    # Scientific provenance belongs to the audit record, never to Film, Rack,
    # RackView, or any carrier/model-visible representation.
    source_job_id: StrictStr | None = None


def empty_rack() -> RackState:
    return RackState()


def full_rack_view(rack: RackState) -> RackView:
    return RackView(available=True, full_films=rack.films, hashed_only=False)


def hashed_rack_view(rack: RackState) -> RackView:
    return RackView(available=True, content_hash=rack.content_hash, hashed_only=True)


def hidden_rack_view() -> RackView:
    return RackView(available=False, rack_unavailable="rack_unavailable")


def evict_film(rack: RackState, station: Station, handle: str) -> tuple[RackState, RackMutation]:
    before = rack.content_hash
    film = next((film for film in rack.films if film.handle == handle), None)
    if film is None:
        return rack, RackMutation(
            station=station,
            operation="evict",
            legal=False,
            rejection_reason="unknown_fragment_handle",
            rack_hash_before=before,
            rack_hash_after=before,
        )
    updated = RackState(films=tuple(item for item in rack.films if item.handle != handle))
    return updated, RackMutation(
        station=station,
        operation="evict",
        legal=True,
        rack_hash_before=before,
        rack_hash_after=updated.content_hash,
        fragment_handle=film.handle,
        fragment_hash=film.content_hash,
    )


def _film_handle(handle_seed: str, content_hash: str) -> str:
    # The result is opaque to the station and deterministic for replay.
    payload = {"seed": handle_seed, "content_hash": content_hash}
    return f"fragment-{stable_hash(payload)[:32]}"


def retain_film(
    rack: RackState,
    station: Station,
    frames: tuple[FilmFrame, ...],
    *,
    start_round: int,
    source_job_id: str,
    handle_seed: str,
) -> tuple[RackState, RackMutation]:
    before = rack.content_hash
    if len(frames) != 6 or [frame.round for frame in frames] != list(
        range(start_round, start_round + 6)
    ):
        return rack, RackMutation(
            station=station,
            operation="retain",
            legal=False,
            rejection_reason="window_not_six_extant_contiguous_rounds",
            rack_hash_before=before,
            rack_hash_after=before,
            local_window_bounds=(start_round, start_round + 5),
        )
    if len(rack.films) >= rack.capacity:
        return rack, RackMutation(
            station=station,
            operation="retain",
            legal=False,
            rejection_reason="rack_full_after_eviction_subphase",
            rack_hash_before=before,
            rack_hash_after=before,
            local_window_bounds=(start_round, start_round + 5),
        )
    content_hash = sha256_bytes(canonical_bytes([frame.model_dump(mode="json") for frame in frames]))
    film = Film(
        handle=_film_handle(handle_seed, content_hash),
        content_hash=content_hash,
        frames=frames,
    )
    if any(existing.handle == film.handle for existing in rack.films):
        return rack, RackMutation(
            station=station,
            operation="retain",
            legal=False,
            rejection_reason="opaque_fragment_handle_collision",
            rack_hash_before=before,
            rack_hash_after=before,
            fragment_handle=film.handle,
            fragment_hash=film.content_hash,
            local_window_bounds=(start_round, start_round + 5),
            source_job_id=source_job_id,
        )
    updated = RackState(
        films=tuple(
            sorted(
                (*rack.films, film),
                key=lambda item: (item.content_hash, item.handle),
            )
        )
    )
    return updated, RackMutation(
        station=station,
        operation="retain",
        legal=True,
        rack_hash_before=before,
        rack_hash_after=updated.content_hash,
        fragment_handle=film.handle,
        fragment_hash=film.content_hash,
        local_window_bounds=(start_round, start_round + 5),
        source_job_id=source_job_id,
    )


def keep_unchanged(rack: RackState, station: Station, operation: str) -> RackMutation:
    if operation not in {"evict", "retain", "keep_unchanged"}:
        raise ValueError("invalid memory subphase operation")
    digest = rack.content_hash
    return RackMutation(
        station=station,
        operation="keep_unchanged",
        legal=True,
        rack_hash_before=digest,
        rack_hash_after=digest,
    )


def apply_memory_phases(
    rack: RackState,
    station: Station,
    frames: tuple[FilmFrame, ...],
    *,
    evict_handle: str | None,
    retain_start_round: int | None,
    source_job_id: str,
    handle_seed: str,
) -> tuple[RackState, tuple[RackMutation, RackMutation]]:
    """Apply eviction, then retention, with no implicit harness choice."""

    if evict_handle is None:
        after_evict, eviction = rack, keep_unchanged(rack, station, "evict")
    else:
        after_evict, eviction = evict_film(rack, station, evict_handle)
    if retain_start_round is None:
        after_retain, retention = after_evict, keep_unchanged(after_evict, station, "retain")
    else:
        selected = tuple(
            frame for frame in frames if retain_start_round <= frame.round < retain_start_round + 6
        )
        after_retain, retention = retain_film(
            after_evict,
            station,
            selected,
            start_round=retain_start_round,
            source_job_id=source_job_id,
            handle_seed=handle_seed,
        )
    return after_retain, (eviction, retention)
