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
ProbeCondition = Literal["both_visible", "x_hidden", "y_hidden", "both_hidden"]
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
            if self.rack_condition == "rack_visible" and self.intervention is not None:
                raise ValueError("visible probes cannot carry a rack intervention")
            hidden = self.rack_condition != "both_visible"
            if hidden != (self.intervention is not None):
                raise ValueError("hidden probe rack condition and intervention disagree")
            if self.intervention is not None and self.intervention.kind is not InterventionKind.HIDE_RACK:
                raise ValueError("probe interventions must be HIDE_RACK")
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
        probe_conditions = tuple(
            job.rack_condition for job in self.jobs if job.category == "rack_probe"
        )
        if (
            probe_conditions.count("both_visible") != 2
            or probe_conditions.count("both_hidden") != 2
        ):
            raise ValueError("rack probes require two intact and two both-hidden slots")
        if probe_conditions.count("x_hidden") != 1 or probe_conditions.count("y_hidden") != 1:
            raise ValueError("rack probes require one X-hidden and one Y-hidden slot")
        expected_pairs = {
            "probe-pair-0": {"both_visible", "both_hidden"},
            "probe-pair-1": {"both_visible", "both_hidden"},
            "probe-pair-2": {"x_hidden", "y_hidden"},
        }
        for pair_id, expected_conditions in expected_pairs.items():
            pair = [job for job in self.jobs if job.probe_pair_id == pair_id]
            if {job.rack_condition for job in pair} != expected_conditions:
                raise ValueError(f"probe pair {pair_id} has the wrong conditions")
            if len({job.matched_difficulty_key for job in pair}) != 1:
                raise ValueError(f"probe pair {pair_id} is not difficulty matched")
        return self

    @property
    def serialization_payload(self) -> dict:
        return _plan_payload(self.sequence_id, self.jobs) | {"plan_hash": self.plan_hash}


def _probe_order(sequence_index: int) -> tuple[tuple[str, ProbeCondition], ...]:
    base = (
        ("probe-pair-0", "both_visible"),
        ("probe-pair-0", "both_hidden"),
        ("probe-pair-1", "both_visible"),
        ("probe-pair-1", "both_hidden"),
        ("probe-pair-2", "x_hidden"),
        ("probe-pair-2", "y_hidden"),
    )
    shift = sequence_index % len(base)
    rotated = base[shift:] + base[:shift]
    return rotated if sequence_index % 2 == 0 else tuple(reversed(rotated))


def _probe_intervention(
    sequence_index: int, job_index: int, pair_id: str, condition: ProbeCondition
) -> InterventionSchedule | None:
    targets = {
        "both_visible": (),
        "x_hidden": (Station.X,),
        "y_hidden": (Station.Y,),
        "both_hidden": (Station.X, Station.Y),
    }[condition]
    if not targets:
        return None
    return InterventionSchedule.hide_rack(
        targets,
        intervention_id=f"{pair_id}:{condition}:s{sequence_index}:j{job_index}",
    )


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
        "probe-pair-0": ("both_visible", "both_hidden"),
        "probe-pair-1": ("both_visible", "both_hidden"),
        "probe-pair-2": ("x_hidden", "y_hidden"),
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
                "intervention": _probe_intervention(
                    sequence_index, index, pair_id, condition
                ),
                "read_only_probe": True,
                "rack_condition": condition,
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
