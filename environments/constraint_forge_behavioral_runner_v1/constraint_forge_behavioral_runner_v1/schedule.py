"""The immutable 24-job exploratory schedule from the V0 specification."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator

from constraint_forge_formation_v0.canonical import stable_hash
from constraint_forge_formation_v0.generator import generate_job
from constraint_forge_formation_v0.interventions import (
    InterventionKind,
    InterventionSchedule,
)
from constraint_forge_formation_v0.models import JobRecord, Seed, Station, StrictModel


JOB_COUNT = 24
ORDINARY_INDICES = (0, 1, 2, 3, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17)
FAULT_INDICES = (4, 5, 6, 7)
PROBE_INDICES = (18, 19, 20, 21, 22, 23)
FAULT_KINDS = (
    InterventionKind.DROP_WRITE,
    InterventionKind.DELAY_WRITE,
    InterventionKind.DELAY_LAYER_VISIBILITY,
    InterventionKind.CLEAR_LAYER_ENTRY,
)
ProbeCondition = Literal["film_intact", "film_wiped"]
JobCategory = Literal["ordinary", "fault", "rack_probe"]


class FormationJobCondition(StrictModel):
    """One schedule slot, including all hidden condition metadata."""

    schema_version: Literal["constraint-forge/formation-job-condition/v0"] = (
        "constraint-forge/formation-job-condition/v0"
    )
    job_index: StrictInt = Field(ge=0, lt=JOB_COUNT)
    job_seed: Seed
    expected_job_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    category: JobCategory
    intervention: InterventionSchedule | None = None
    read_only_probe: StrictBool = False
    rack_condition: ProbeCondition | Literal["rack_visible"] = "rack_visible"
    wipe_rack: StrictBool = False
    probe_pair_id: StrictStr | None = None
    matched_difficulty_key: StrictStr | None = Field(
        default=None, pattern=r"^[0-9a-f]{16}$"
    )

    @model_validator(mode="after")
    def validate_condition(self) -> "FormationJobCondition":
        if self.category == "ordinary":
            if self.intervention is not None or self.read_only_probe:
                raise ValueError("ordinary slots cannot carry an intervention or probe")
            if (
                self.rack_condition != "rack_visible"
                or self.probe_pair_id is not None
                or self.matched_difficulty_key is not None
            ):
                raise ValueError("ordinary slots cannot carry probe metadata")
        elif self.category == "fault":
            if self.intervention is None or self.intervention.kind is InterventionKind.HIDE_RACK:
                raise ValueError("fault slots require one non-rack intervention")
            if self.read_only_probe or self.rack_condition != "rack_visible":
                raise ValueError("fault slots must be rack-visible and writable")
            if self.probe_pair_id is not None or self.matched_difficulty_key is not None:
                raise ValueError("fault slots cannot carry probe metadata")
        else:
            if not self.read_only_probe or self.probe_pair_id is None:
                raise ValueError("rack probes require a pair id and read-only mode")
            if self.matched_difficulty_key is None:
                raise ValueError("rack probes require a matched-difficulty key")
            if self.rack_condition not in ("film_intact", "film_wiped"):
                raise ValueError("v1 probes must declare film_intact or film_wiped")
            if self.intervention is not None:
                raise ValueError("v1 probes never carry HIDE_RACK interventions")
            if self.wipe_rack != (self.rack_condition == "film_wiped"):
                raise ValueError("wipe_rack flag must match rack_condition")
        return self


def _plan_payload(sequence_id: str, jobs: tuple[FormationJobCondition, ...]) -> dict:
    return {
        "schema_version": "constraint-forge/formation-run-plan/v0",
        "sequence_id": sequence_id,
        "jobs": [job.model_dump(mode="json") for job in jobs],
    }


class FormationRunPlan(StrictModel):
    """A hash-pinned schedule; no runner default may replace it."""

    schema_version: Literal["constraint-forge/formation-run-plan/v0"] = (
        "constraint-forge/formation-run-plan/v0"
    )
    sequence_id: StrictStr
    jobs: tuple[FormationJobCondition, ...] = Field(
        min_length=JOB_COUNT, max_length=JOB_COUNT
    )
    plan_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_plan(self) -> "FormationRunPlan":
        if tuple(job.job_index for job in self.jobs) != tuple(range(JOB_COUNT)):
            raise ValueError("run plan indices must be contiguous and ordered")
        if self.plan_hash != stable_hash(_plan_payload(self.sequence_id, self.jobs)):
            raise ValueError("run plan hash does not match its immutable conditions")
        if (
            tuple(job.job_index for job in self.jobs if job.category == "ordinary")
            != ORDINARY_INDICES
        ):
            raise ValueError("ordinary schedule positions are not frozen")
        if (
            tuple(job.job_index for job in self.jobs if job.category == "fault")
            != FAULT_INDICES
        ):
            raise ValueError("fault schedule positions are not frozen")
        if (
            tuple(job.job_index for job in self.jobs if job.category == "rack_probe")
            != PROBE_INDICES
        ):
            raise ValueError("rack-probe schedule positions are not frozen")
        fault_kinds = tuple(
            job.intervention.kind
            for job in self.jobs
            if job.category == "fault" and job.intervention is not None
        )
        if len(fault_kinds) != 4 or set(fault_kinds) != set(FAULT_KINDS):
            raise ValueError("fault schedule must contain each non-rack effect once")
        probes = [job for job in self.jobs if job.category == "rack_probe"]
        conditions = tuple(job.rack_condition for job in probes)
        if conditions.count("film_intact") != 3 or conditions.count("film_wiped") != 3:
            raise ValueError("v1 probe block requires three film_intact and three film_wiped slots")
        for pair_id in ("probe-pair-0", "probe-pair-1", "probe-pair-2"):
            pair = [job for job in probes if job.probe_pair_id == pair_id]
            if {job.rack_condition for job in pair} != {"film_intact", "film_wiped"}:
                raise ValueError(f"probe pair {pair_id} must contrast film_intact vs film_wiped")
            if len({job.matched_difficulty_key for job in pair}) != 1:
                raise ValueError(f"probe pair {pair_id} is not difficulty matched")
        return self

    @property
    def serialization_payload(self) -> dict:
        return _plan_payload(self.sequence_id, self.jobs) | {"plan_hash": self.plan_hash}


def _probe_order(sequence_index: int) -> tuple[tuple[str, ProbeCondition], ...]:
    """Within-pair contrast: matched members differ only in film availability.

    Even sequences run intact-first inside every pair; odd sequences run
    wiped-first, counterbalancing intra-block position against condition.
    """

    first = "film_intact" if sequence_index % 2 == 0 else "film_wiped"
    second = "film_wiped" if first == "film_intact" else "film_intact"
    return (
        ("probe-pair-0", first),
        ("probe-pair-0", second),
        ("probe-pair-1", first),
        ("probe-pair-1", second),
        ("probe-pair-2", first),
        ("probe-pair-2", second),
    )


def _probe_intervention(
    sequence_index: int, job_index: int, pair_id: str, condition: ProbeCondition
) -> InterventionSchedule | None:
    """V1 probes never hide the rack; the manipulated factor is film content."""

    return None


def _matched_difficulty_key(job: JobRecord) -> str:
    """Key a probe pair to latent factor layout, not visible task bytes.

    The permutations ``rho`` and ``sigma`` independently relabel the visible
    graph.  Keeping the hidden factor roles equal therefore gives pair members
    an isomorphic generator-level difficulty while retaining independent masks,
    presentations, and job payloads.
    """

    return stable_hash(
        {
            "target_factor": job.target_factor,
            "x_decoy_factors": list(job.x_decoy_factors),
            "y_decoy_factors": list(job.y_decoy_factors),
        }
    )[:16]


def _matched_probe_pair(
    *,
    sequence_index: int,
    seed_prefix: str,
    pair_id: str,
    conditions: tuple[ProbeCondition, ProbeCondition],
    used_hashes: set[str],
) -> tuple[tuple[str, JobRecord], tuple[str, JobRecord], str]:
    """Choose two deterministic, independently seeded jobs with one key."""

    left_condition, right_condition = conditions
    left_by_key: dict[str, tuple[str, JobRecord]] = {}
    for attempt in range(4096):
        left_seed = (
            f"{seed_prefix}:{sequence_index}:probe:{pair_id}:"
            f"{left_condition}:candidate:{attempt}"
        )
        left_job = generate_job(left_seed)
        if left_job.payload_hash in used_hashes:
            continue
        left_by_key.setdefault(_matched_difficulty_key(left_job), (left_seed, left_job))

        right_seed = (
            f"{seed_prefix}:{sequence_index}:probe:{pair_id}:"
            f"{right_condition}:candidate:{attempt}"
        )
        right_job = generate_job(right_seed)
        right_key = _matched_difficulty_key(right_job)
        left = left_by_key.get(right_key)
        if (
            left is not None
            and right_job.payload_hash not in used_hashes
            and right_job.payload_hash != left[1].payload_hash
        ):
            return left, (right_seed, right_job), right_key
    raise RuntimeError(f"could not deterministically match probe pair {pair_id}")


def build_run_plan(
    *, sequence_id: str, sequence_index: int, seed_prefix: str
) -> FormationRunPlan:
    """Build the fixed 14 + 4 + 6 schedule before any behavioral call."""

    seed_by_index: dict[int, str] = {}
    hash_by_index: dict[int, str] = {}
    metadata_by_index: dict[int, dict[str, object]] = {}
    used_hashes: set[str] = set()
    fault_target = Station.X if sequence_index % 2 == 0 else Station.Y
    probe_slots = dict(zip(PROBE_INDICES, _probe_order(sequence_index)))
    for job_index in (*ORDINARY_INDICES, *FAULT_INDICES):
        if job_index in FAULT_INDICES:
            kind = FAULT_KINDS[(job_index - FAULT_INDICES[0] + sequence_index) % len(FAULT_KINDS)]
            intervention = InterventionSchedule.write_effect(
                kind,
                target=fault_target,
                intervention_id=f"fault:{kind.value}:s{sequence_index}:j{job_index}",
            )
            category: JobCategory = "fault"
            read_only = False
            rack_condition: ProbeCondition | Literal["rack_visible"] = "rack_visible"
            pair_id = None
        else:
            intervention = None
            category = "ordinary"
            read_only = False
            rack_condition = "rack_visible"
            pair_id = None
        seed = f"{seed_prefix}:{sequence_index}:job:{job_index}"
        job = generate_job(seed)
        used_hashes.add(job.payload_hash)
        seed_by_index[job_index] = seed
        hash_by_index[job_index] = job.payload_hash
        metadata_by_index[job_index] = {
            "category": category,
            "intervention": intervention,
            "read_only_probe": read_only,
            "rack_condition": rack_condition,
            "probe_pair_id": pair_id,
            "matched_difficulty_key": None,
        }

    pair_conditions = {
        "probe-pair-0": ("film_intact", "film_wiped"),
        "probe-pair-1": ("film_intact", "film_wiped"),
        "probe-pair-2": ("film_intact", "film_wiped"),
    }
    for pair_id, conditions in pair_conditions.items():
        left, right, difficulty_key = _matched_probe_pair(
            sequence_index=sequence_index,
            seed_prefix=seed_prefix,
            pair_id=pair_id,
            conditions=conditions,
            used_hashes=used_hashes,
        )
        used_hashes.update((left[1].payload_hash, right[1].payload_hash))
        for condition, (seed, job) in zip(conditions, (left, right)):
            index = next(
                index
                for index, slot in probe_slots.items()
                if slot == (pair_id, condition)
            )
            metadata_by_index[index] = {
                "category": "rack_probe",
                "intervention": None,
                "read_only_probe": True,
                "rack_condition": condition,
                "wipe_rack": condition == "film_wiped",
                "probe_pair_id": pair_id,
                "matched_difficulty_key": difficulty_key,
            }
            seed_by_index[index] = seed
            hash_by_index[index] = job.payload_hash

    jobs = tuple(
        FormationJobCondition(
            job_index=job_index,
            job_seed=seed_by_index[job_index],
            expected_job_hash=hash_by_index[job_index],
            **metadata_by_index[job_index],
        )
        for job_index in range(JOB_COUNT)
    )
    return FormationRunPlan(
        sequence_id=sequence_id,
        jobs=jobs,
        plan_hash=stable_hash(_plan_payload(sequence_id, jobs)),
    )


__all__ = [
    "FAULT_INDICES",
    "FAULT_KINDS",
    "FormationJobCondition",
    "FormationRunPlan",
    "JOB_COUNT",
    "ORDINARY_INDICES",
    "PROBE_INDICES",
    "build_run_plan",
]
