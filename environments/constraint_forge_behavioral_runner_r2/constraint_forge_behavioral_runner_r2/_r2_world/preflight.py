"""Deterministic model-free gates for Constraint Forge V0.

This module is deliberately an offline reference runner.  It never imports a
provider, harness, actor lifecycle, or live inference path.  The default CLI
sizes mirror the frozen specification: 10,000 generator/solo jobs, 1,000
ordinary coordination jobs, and a balanced 1,000-job four-fault suite.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from statistics import median
from typing import Callable, Iterable

from .events import EventKind
from .generator import (
    generate_jobs,
    generator_conditioned_map,
    validate_job,
)
from .interventions import InterventionKind, InterventionSchedule
from .models import JobRecord, Station
from .policies import (
    MaskCodebook,
    centralized_ambiguous_edges,
    centralized_candidate_first,
    centralized_compressed_constraints,
    centralized_full_state_dump,
    centralized_proposal_correction,
    codebook_from_jobs,
    distributed_mask_exchange,
    distributed_mutual_consensus,
)
from .world import JobResult, Policy, run_job


PolicyFactory = Callable[[], tuple[Policy, Policy]]


def binomial_upper_95(successes: int, trials: int) -> float:
    """One-sided 95% Clopper--Pearson upper confidence bound."""

    if trials <= 0 or not 0 <= successes <= trials:
        raise ValueError("invalid binomial sample")
    if successes == trials:
        return 1.0

    tail = 0.05

    def lower_tail(probability: float) -> float:
        if probability <= 0:
            return 1.0
        if probability >= 1:
            return 0.0
        log_probability = math.log(probability)
        log_complement = math.log1p(-probability)
        terms = [
            math.lgamma(trials + 1)
            - math.lgamma(index + 1)
            - math.lgamma(trials - index + 1)
            + index * log_probability
            + (trials - index) * log_complement
            for index in range(successes + 1)
        ]
        maximum = max(terms)
        return math.exp(maximum) * sum(math.exp(term - maximum) for term in terms)

    low = successes / trials
    high = 1.0
    for _ in range(80):
        mid = (low + high) / 2
        if lower_tail(mid) > tail:
            low = mid
        else:
            high = mid
    return high


def _solo_accuracy(jobs: Iterable[JobRecord], station: Station) -> dict:
    jobs = tuple(jobs)
    successes = sum(
        frozenset(generator_conditioned_map(job.x_mask if station is Station.X else job.y_mask))
        == frozenset(job.target_matching)
        for job in jobs
    )
    return {
        "station": station.value,
        "successes": successes,
        "trials": len(jobs),
        "accuracy": successes / len(jobs),
        "upper_bound_95": binomial_upper_95(successes, len(jobs)),
        "accuracy_threshold": 0.40,
        "upper_bound_threshold": 0.42,
        "passed": successes / len(jobs) <= 0.40
        and binomial_upper_95(successes, len(jobs)) <= 0.42,
    }


def _role_symmetry(jobs: Iterable[JobRecord]) -> dict:
    jobs = tuple(jobs)
    x = Counter((job.target_factor, tuple(sorted(job.x_decoy_factors))) for job in jobs)
    y = Counter((job.target_factor, tuple(sorted(job.y_decoy_factors))) for job in jobs)
    keys = set(x) | set(y)
    max_count_difference = max((abs(x[key] - y[key]) for key in keys), default=0)
    total_variation = 0.5 * sum(abs(x[key] - y[key]) for key in keys) / len(jobs)
    # The finite sample has binomial noise; the construction is role-symmetric
    # because the two decoy pairs are sampled from a uniform random partition.
    return {
        "x_marginal_cells": len(x),
        "y_marginal_cells": len(y),
        "max_factor_cell_count_difference": max_count_difference,
        "total_variation_distance": total_variation,
        "empirical_tolerance": 0.05,
        "passed": total_variation <= 0.05,
        "construction_role_swap_invariant": True,
    }


def generator_and_solo_gate(jobs: Iterable[JobRecord]) -> dict:
    jobs = tuple(jobs)
    payload_hashes = {job.payload_hash for job in jobs}
    invariant_failures: list[str] = []
    for job in jobs:
        try:
            validate_job(job)
        except Exception as exc:  # pragma: no cover - included in report only
            invariant_failures.append(f"{job.job_seed}: {exc}")
    solo_x = _solo_accuracy(jobs, Station.X)
    solo_y = _solo_accuracy(jobs, Station.Y)
    symmetry = _role_symmetry(jobs)
    return {
        "trials": len(jobs),
        "generator_invariant_failures": invariant_failures,
        "generator_invariants_passed": not invariant_failures,
        "unique_payloads": len(payload_hashes),
        "duplicate_payloads": len(payload_hashes) != len(jobs),
        "solo_x": solo_x,
        "solo_y": solo_y,
        "role_swap": symmetry,
        "passed": not invariant_failures
        and len(payload_hashes) == len(jobs)
        and solo_x["passed"]
        and solo_y["passed"]
        and symmetry["passed"],
    }


def _final_surviving_sets(result: JobResult) -> dict[Station, tuple[int, ...]]:
    """Identify final surviving actor sets for the frozen overhead metric."""

    actions = result.event_log.events
    final_layers = {Station.X: result.final_state.x.layer, Station.Y: result.final_state.y.layer}
    surviving: dict[Station, list[int]] = {Station.X: [], Station.Y: []}
    for station in (Station.X, Station.Y):
        for item, target in enumerate(final_layers[station]):
            if target is None:
                continue
            candidates = [
                event
                for event in actions
                if event.event_kind is EventKind.ACTION_SUBMITTED
                and event.source is station
                and event.legal
                and event.action_payload
                and event.action_payload.get("action") == "set"
                and event.action_payload.get("item") == item
                and event.action_payload.get("target") == target
            ]
            if not candidates:
                continue
            candidate = candidates[-1]
            removed_after = any(
                event.event_sequence > candidate.event_sequence
                and event.event_kind is EventKind.LAYER_UNSET
                and (
                    event.source is station
                    or (
                        event.detail.get("environment_clear") is True
                        and event.detail.get("target_station") == station.value
                    )
                )
                and event.detail.get("item") == item
                for event in actions
            )
            if not removed_after:
                surviving[station].append(candidate.event_sequence)
    return {station: tuple(items) for station, items in surviving.items()}


def _job_metrics(result: JobResult) -> dict:
    action_events = tuple(
        event
        for event in result.event_log.events
        if event.event_kind in {EventKind.ACTION_SUBMITTED, EventKind.ACTION_REJECTED}
    )
    surviving = _final_surviving_sets(result)
    surviving_ids = set(surviving[Station.X] + surviving[Station.Y])
    finish_events = tuple(
        event
        for event in action_events
        if event.legal
        and event.action_payload
        and event.action_payload.get("action") == "finish"
    )
    writes = sum(
        bool(event.action_payload and event.action_payload.get("action") == "write")
        for event in action_events
    )
    nonfinal_mutations = sum(
        bool(
            event.action_payload
            and event.action_payload.get("action") in {"set", "unset"}
            and event.event_sequence not in surviving_ids
        )
        for event in action_events
    )
    qualifying = len(surviving[Station.X]) == 6 and len(surviving[Station.Y]) == 6 and len(finish_events) == 2
    overhead = len(action_events) - len(surviving_ids) - len(finish_events) if qualifying else None
    return {
        "success": bool(result.success),
        "rounds": result.rounds_resolved,
        "writes": writes,
        "nonfinal_layer_mutations": nonfinal_mutations,
        "action_events": len(action_events),
        "final_surviving_sets_x": len(surviving[Station.X]),
        "final_surviving_sets_y": len(surviving[Station.Y]),
        "legal_finishes": len(finish_events),
        "qualifying_final_actions": qualifying,
        "coordination_overhead": overhead,
    }


def _summarize(results: Iterable[JobResult]) -> dict:
    results = tuple(results)
    metrics = tuple(_job_metrics(result) for result in results)
    successful = tuple(item for item in metrics if item["success"])

    def med(key: str, rows: Iterable[dict]) -> float | None:
        values = [row[key] for row in rows if row[key] is not None]
        return float(median(values)) if values else None

    return {
        "trials": len(metrics),
        "successes": sum(item["success"] for item in metrics),
        "success_rate": sum(item["success"] for item in metrics) / len(metrics),
        "median_rounds_all": med("rounds", metrics),
        "median_rounds_successful": med("rounds", successful),
        "median_writes_all": med("writes", metrics),
        "median_nonfinal_layer_mutations_all": med("nonfinal_layer_mutations", metrics),
        "median_coordination_overhead_successful": med("coordination_overhead", successful),
        "qualifying_successes": sum(
            item["qualifying_final_actions"] for item in metrics if item["success"]
        ),
        "all_successes_have_exact_final_action_accounting": all(
            item["qualifying_final_actions"] for item in metrics if item["success"]
        ),
    }


def _run_factory(
    jobs: Iterable[JobRecord],
    factory: PolicyFactory,
    *,
    run_prefix: str,
    intervention_factory: Callable[[int], InterventionSchedule | None] | None = None,
) -> tuple[JobResult, ...]:
    results: list[JobResult] = []
    for index, job in enumerate(jobs):
        policy_x, policy_y = factory()
        intervention = intervention_factory(index) if intervention_factory else None
        results.append(
            run_job(
                job,
                run_id=f"{run_prefix}:{index}",
                lineage_id="constraint-forge-preflight",
                job_id=f"{run_prefix}:{index}",
                policy_x=policy_x,
                policy_y=policy_y,
                intervention=intervention,
                read_only_probe=True,
            )
        )
    return tuple(results)


def _central_factories(codebook: MaskCodebook) -> dict[str, PolicyFactory]:
    return {
        "full_state_dump_X": lambda: centralized_full_state_dump(codebook, sender=Station.X),
        "full_state_dump_Y": lambda: centralized_full_state_dump(codebook, sender=Station.Y),
        "candidate_first_X": lambda: centralized_candidate_first(proposer=Station.X),
        "candidate_first_Y": lambda: centralized_candidate_first(proposer=Station.Y),
        "ambiguous_edges_X": lambda: centralized_ambiguous_edges(codebook, proposer=Station.X),
        "ambiguous_edges_Y": lambda: centralized_ambiguous_edges(codebook, proposer=Station.Y),
        "compressed_constraints_X": lambda: centralized_compressed_constraints(codebook, sender=Station.X),
        "compressed_constraints_Y": lambda: centralized_compressed_constraints(codebook, sender=Station.Y),
        "proposal_correction_X": lambda: centralized_proposal_correction(codebook, proposer=Station.X),
        "proposal_correction_Y": lambda: centralized_proposal_correction(codebook, proposer=Station.Y),
    }


def _witness_factories(codebook: MaskCodebook) -> dict[str, PolicyFactory]:
    return {
        "distributed_mask_exchange": lambda: distributed_mask_exchange(codebook),
        "distributed_mutual_consensus": lambda: distributed_mutual_consensus(codebook),
    }


def _balanced_fault(index: int) -> InterventionSchedule:
    kinds = (
        InterventionKind.DROP_WRITE,
        InterventionKind.DELAY_WRITE,
        InterventionKind.DELAY_LAYER_VISIBILITY,
        InterventionKind.CLEAR_LAYER_ENTRY,
    )
    kind = kinds[index % len(kinds)]
    target = Station.X if (index // len(kinds)) % 2 == 0 else Station.Y
    return InterventionSchedule.write_effect(
        kind,
        target=target,
        intervention_id=f"preflight-{kind.value.lower()}-{index}",
    )


def _centralization_gate(central: dict[str, dict], witnesses: dict[str, dict]) -> dict:
    cheap = [
        name
        for name, row in central.items()
        if row["success_rate"] >= 0.90
        and row["median_coordination_overhead_successful"] is not None
        and row["median_coordination_overhead_successful"] <= 2
    ]
    dominance: list[dict] = []
    for central_name, central_row in central.items():
        for witness_name, witness_row in witnesses.items():
            comparable = all(
                central_row[key] is not None and witness_row[key] is not None
                for key in (
                    "success_rate",
                    "median_rounds_all",
                    "median_writes_all",
                    "median_nonfinal_layer_mutations_all",
                )
            )
            if not comparable:
                continue
            weak = (
                central_row["success_rate"] >= witness_row["success_rate"]
                and central_row["median_rounds_all"] <= witness_row["median_rounds_all"]
                and central_row["median_writes_all"] <= witness_row["median_writes_all"]
                and central_row["median_nonfinal_layer_mutations_all"]
                <= witness_row["median_nonfinal_layer_mutations_all"]
            )
            strict = any(
                (
                    central_row["success_rate"] > witness_row["success_rate"],
                    central_row["median_rounds_all"] < witness_row["median_rounds_all"],
                    central_row["median_writes_all"] < witness_row["median_writes_all"],
                    central_row["median_nonfinal_layer_mutations_all"]
                    < witness_row["median_nonfinal_layer_mutations_all"],
                )
            )
            if weak and strict:
                dominance.append({"central": central_name, "witness": witness_name})
    return {
        "cheap_centralized_adversaries": cheap,
        "dominance_pairs": dominance,
        "successful_job_accounting_passed": all(
            row["all_successes_have_exact_final_action_accounting"]
            for row in central.values()
        ),
        "passed": not cheap
        and not dominance
        and all(
            row["all_successes_have_exact_final_action_accounting"]
            for row in central.values()
        ),
        "thresholds": {"success_rate": 0.90, "median_overhead": 2},
    }


def run_preflight(
    *,
    generator_trials: int = 10_000,
    coordination_trials: int = 1_000,
    fault_trials: int = 1_000,
) -> dict:
    if generator_trials < 1 or coordination_trials < 1 or fault_trials < 8:
        raise ValueError("preflight trial counts are too small")
    generator_jobs = generate_jobs(
        f"constraint-forge/preflight/generator/{index}" for index in range(generator_trials)
    )
    ordinary_jobs = generate_jobs(
        f"constraint-forge/preflight/ordinary/{index}" for index in range(coordination_trials)
    )
    generator_report = generator_and_solo_gate(generator_jobs)

    fault_jobs = generate_jobs(
        f"constraint-forge/preflight/fault/{index}" for index in range(fault_trials)
    )
    # The reference codebook is shared and precomputed, but it must cover the
    # finite model-free evaluation corpus, including its fault jobs.  It is
    # never a job-seed or target oracle exposed through an observation.
    codebook = codebook_from_jobs((*ordinary_jobs, *fault_jobs))

    witnesses = {
        name: _summarize(
            _run_factory(ordinary_jobs, factory, run_prefix=f"witness-{name}")
        )
        for name, factory in _witness_factories(codebook).items()
    }
    fault_reports = {
        name: _summarize(
            _run_factory(
                fault_jobs,
                factory,
                run_prefix=f"fault-{name}",
                intervention_factory=_balanced_fault,
            )
        )
        for name, factory in _witness_factories(codebook).items()
    }
    central = {
        name: _summarize(
            _run_factory(ordinary_jobs, factory, run_prefix=f"central-{name}")
        )
        for name, factory in _central_factories(codebook).items()
    }
    central_gate = _centralization_gate(central, witnesses)
    feasibility_gate = {
        "ordinary_threshold": 0.80,
        "fault_threshold": 0.60,
        "witnesses": {
            name: {
                "ordinary_success_rate": witnesses[name]["success_rate"],
                "fault_success_rate": fault_reports[name]["success_rate"],
                "ordinary_passed": witnesses[name]["success_rate"] >= 0.80,
            }
            for name in witnesses
        },
        "at_least_one_fault_witness_passed": any(
            row["success_rate"] >= 0.60 for row in fault_reports.values()
        ),
    }
    feasibility_gate["passed"] = all(
        row["ordinary_passed"] for row in feasibility_gate["witnesses"].values()
    ) and feasibility_gate["at_least_one_fault_witness_passed"] and all(
        row["all_successes_have_exact_final_action_accounting"]
        for row in (*witnesses.values(), *fault_reports.values())
    )
    feasibility_gate["successful_job_accounting_passed"] = all(
        row["all_successes_have_exact_final_action_accounting"]
        for row in (*witnesses.values(), *fault_reports.values())
    )
    return {
        "schema_version": "constraint-forge/preflight/v0",
        "live_model_calls": 0,
        "generator_and_solo": generator_report,
        "shared_codebook_masks": len(codebook.masks),
        "centralization": {"adversaries": central, "gate": central_gate},
        "feasibility": {
            "fault_suite_trials": fault_trials,
            "balanced_faults": {
                "each_kind_count": fault_trials // 4,
                "each_kind_target_station_count": fault_trials // 8,
                "remainder": fault_trials % 8,
            },
            "ordinary_witnesses": witnesses,
            "fault_witnesses": fault_reports,
            "gate": feasibility_gate,
        },
        "passed": generator_report["passed"]
        and central_gate["passed"]
        and feasibility_gate["passed"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generator-trials", type=int, default=10_000)
    parser.add_argument("--coordination-trials", type=int, default=1_000)
    parser.add_argument("--fault-trials", type=int, default=1_000)
    args = parser.parse_args()
    print(
        json.dumps(
            run_preflight(
                generator_trials=args.generator_trials,
                coordination_trials=args.coordination_trials,
                fault_trials=args.fault_trials,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
