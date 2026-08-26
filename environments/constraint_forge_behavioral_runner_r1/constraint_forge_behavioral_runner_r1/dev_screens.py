"""Model-free R1 screens S1-S5 (docs/r1_design.md). No model calls."""

from __future__ import annotations

import itertools
import json

from constraint_forge_formation_v0.canonical import stable_hash
from constraint_forge_formation_v0.generator import generate_job
from constraint_forge_formation_v0.models import JobRecord, Pair

from .r1_physics import r1_void


def _observation_fixture():
    from constraint_forge_formation_v0.models import RegisterState, Station
    from constraint_forge_formation_v0.rack import empty_rack, full_rack_view
    from constraint_forge_formation_v0.world import Observation

    return Observation(
        station=Station.X,
        round=1,
        private_pairs=((0, 1),),
        layers={"X": tuple([None] * 6), "Y": tuple([None] * 6)},
        registers={
            "X": (RegisterState(), RegisterState()),
            "Y": (RegisterState(), RegisterState()),
        },
        remaining={},
        finished={"X": False, "Y": False},
        rack=full_rack_view(empty_rack()),
    )


def screen_s2b_note_privacy() -> dict:
    from .requests import round_request
    from .r1_physics import station_note

    marker = "void symbol for register 0 is"
    x_req = round_request(
        role="X", job_index=0, job_id="j", context_epoch=0,
        pre_state_hash="h", observation=_observation_fixture(),
        station_note=station_note(3),
    )
    y_req = round_request(
        role="Y", job_index=0, job_id="j", context_epoch=0,
        pre_state_hash="h", observation=_observation_fixture(),
    )
    x_text = json.dumps(x_req.visible_payload)
    y_text = json.dumps(y_req.visible_payload)
    assert x_req.visible_payload["instructions"].count(marker) == 1
    assert marker not in y_text
    try:
        round_request(
            role="Y", job_index=0, job_id="j", context_epoch=0,
            pre_state_hash="h", observation=_observation_fixture(),
            station_note=station_note(3),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("station note accepted for Y")
    return {"x_note_visible_once": True, "y_note_absent": True, "y_constructor_rejects": True}


def perfect_matchings(pairs: set[Pair]) -> list[tuple[Pair, ...]]:
    matchings: list[tuple[Pair, ...]] = []
    items = sorted({p[0] for p in pairs})

    def walk(used: frozenset[int], chosen: tuple[Pair, ...]) -> None:
        if len(chosen) == len(items):
            matchings.append(chosen)
            return
        item = min(set(items) - used)
        for it, tg in sorted(pairs):
            if it == item and tg not in {t for _, t in chosen}:
                walk(used | {item}, (*chosen, (it, tg)))

    walk(frozenset(), ())
    return matchings


def screen_s1_s2(instances: int = 240) -> dict:
    unique = 0
    x_alone_multi = 0
    y_alone_multi = 0
    voids: list[int] = []
    for i in range(instances):
        job = generate_job(f"constraint-forge/r1-screen-v0:seq:{i}:job:{i % 24}")
        inter = job.intersection
        assert len(perfect_matchings(inter)) == 1, "P∩Q not uniquely solvable"
        assert frozenset(job.target_matching) == inter
        unique += 1
        if len(perfect_matchings(set(job.x_mask))) >= 2:
            x_alone_multi += 1
        if len(perfect_matchings(set(job.y_mask))) >= 2:
            y_alone_multi += 1
        voids.append(r1_void(job.job_seed))
    counts = [voids.count(v) for v in range(4)]
    assert min(counts) / instances > 0.18, f"void distribution skewed: {counts}"
    return {
        "instances": instances,
        "unique_intersection_solvable": unique,
        "x_mask_alone_ambiguous": x_alone_multi,
        "y_mask_alone_ambiguous": y_alone_multi,
        "void_symbol_counts": counts,
    }


def screen_s3(trials: int = 20000) -> dict:
    import random

    rng = random.Random(0)
    fixed_default_hits = 0
    brute_force_hits = 0
    for _ in range(trials):
        void = rng.randrange(4)
        if 0 != void:
            fixed_default_hits += 1
        order = [0, 1, 2, 3]
        rng.shuffle(order)
        budget = 3
        found_void_at = None
        for pos, sym in enumerate(order):
            if sym == void:
                found_void_at = pos
                break
        if found_void_at is not None and found_void_at <= budget - 2:
            brute_force_hits += 1
        elif found_void_at is None:
            brute_force_hits += 1
    return {
        "trials": trials,
        "fixed_default_conjunct_success": round(fixed_default_hits / trials, 4),
        "blind_brute_force_cap": round(brute_force_hits / trials, 4),
        "expected_blind_brute_force": 0.5,
    }


def screen_s4() -> dict:
    plan_a = [r1_void(generate_job(f"p:s:0:job:{j}").job_seed) for j in range(24)]
    plan_b = [r1_void(generate_job(f"p:s:0:job:{j}").job_seed) for j in range(24)]
    assert plan_a == plan_b
    return {"deterministic_void_vector": plan_a}


def screen_s5() -> dict:
    from constraint_forge_formation_v0 import world as world_mod
    import inspect

    src = inspect.getsource(world_mod.run_job)
    assert "read_only_probe" in src
    apply_src = inspect.getsource(world_mod._apply_action)
    assert "read_only" not in apply_src.replace("read_only_probe", ""), (
        "round-action legality must not depend on probe flag"
    )
    return {
        "probe_memory_phases_skipped_only": True,
        "round_actions_legal_in_probes": True,
        "note": "write/set/finish legality independent of read_only_probe; WIPE_RACK path untouched",
    }


if __name__ == "__main__":
    out = {
        "S1_S2": screen_s1_s2(),
        "S3": screen_s3(),
        "S4": screen_s4(),
        "S2B": screen_s2b_note_privacy(),
        "S5": screen_s5(),
    }
    print(json.dumps(out, indent=2))
