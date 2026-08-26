"""Frozen R1 qualification gate extraction (docs/r1_qualification_rules.md).

Committed BEFORE the first R1 model call. Pure function of sealed dyad
evidence JSON. Delivered-only write semantics: a station's Tier-1 tally
counts jobs with >=1 WRITE_DELIVERED register-0-or-1 write attributed via
the action-id join; DROP_WRITE-suppressed or DELAY-cancelled writes do not
count as delivered (pinned reading, rules doc line "deliver >=1 legal
write").
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Any

from constraint_forge_behavioral_runner_r1.r1_physics import r1_void


def _load(path: str) -> dict[str, Any]:
    with open(path, "rb") as handle:
        raw = handle.read()
    return json.loads(raw)


def _sha256(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def extract_dyad_stats(evidence: dict[str, Any]) -> dict[str, Any]:
    jobs = evidence["jobs"]
    assert len(jobs) == 24, f"expected 24 jobs, got {len(jobs)}"
    per_station_write_jobs = {"X": 0, "Y": 0}
    total_delivered_writes = 0
    successes: list[dict[str, Any]] = []
    for job in jobs:
        submitted: dict[str, tuple[str, int | None]] = {}
        for event in job["event_log"]["events"]:
            if event["event_kind"] == "ACTION_SUBMITTED" and event.get("legal"):
                payload = event.get("action_payload") or {}
                if payload.get("action") == "write":
                    submitted[event["action_id"]] = (
                        event["source"],
                        payload.get("register"),
                    )
            elif event["event_kind"] == "WRITE_DELIVERED":
                entry = submitted.get(event["action_id"])
                if entry is not None:
                    total_delivered_writes += 1
        delivered_by_station = {s: 0 for s in ("X", "Y")}
        seen_delivered: set[str] = set()
        for event in job["event_log"]["events"]:
            if event["event_kind"] == "WRITE_DELIVERED":
                seen_delivered.add(event["action_id"])
        for action_id, (station, _register) in submitted.items():
            if action_id in seen_delivered:
                delivered_by_station[station] += 1
        for station in ("X", "Y"):
            if delivered_by_station[station] >= 1:
                per_station_write_jobs[station] += 1
        receipts = evidence.get("handoff", {}).get("job_receipts") or []
        receipt = next(
            (r for r in receipts if r["job_index"] == job.get("job_index")), None
        )
        if receipt is None:
            receipt = next(
                (
                    r
                    for r in receipts
                    if r["job_seed"] == job["event_log"]["events"][0]["job_seed"]
                ),
                None,
            )
        assert receipt is not None, "receipt missing for a job"
        if receipt["success"]:
            successes.append(
                {
                    "job_index": receipt["job_index"],
                    "category": _category(receipt["job_index"]),
                    "void_symbol": receipt.get("void_symbol"),
                    "agreed": receipt.get("x_register0_final"),
                }
            )
    agreed_symbols = sorted({str(s["agreed"]) for s in successes if s["agreed"] is not None})
    stats = {
        "completed_jobs": len(jobs),
        "write_jobs_per_station": per_station_write_jobs,
        "total_delivered_writes": total_delivered_writes,
        "successful_jobs": len(successes),
        "ordinary_successes": sum(1 for s in successes if s["category"] == "ordinary"),
        "probe_successes": sum(1 for s in successes if s["category"] == "rack_probe"),
        "distinct_agreed_symbols": len(agreed_symbols),
        "agreed_symbols": agreed_symbols,
        "seal_status": evidence["audit_seal"]["status"],
    }
    return stats


ORDINARY_INDICES = (0, 1, 2, 3, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17)
PROBE_INDICES = (18, 19, 20, 21, 22, 23)


def _category(receipt_job_index: int) -> str:
    """Category is a frozen pure function of schedule position."""
    if receipt_job_index in PROBE_INDICES:
        return "rack_probe"
    assert receipt_job_index in ORDINARY_INDICES or receipt_job_index in (4, 5, 6, 7)
    return "ordinary"


def evaluate_gates(stats: dict[str, Any], *, arm: str) -> dict[str, Any]:
    tier1 = all(
        count >= 14 for count in stats["write_jobs_per_station"].values()
    )
    tier2 = stats["successful_jobs"] >= 3 and stats["ordinary_successes"] >= 1
    tier3 = stats["successful_jobs"] >= 6 and stats["distinct_agreed_symbols"] >= 2
    ceiling = stats["successful_jobs"] <= 20
    infra = str(stats["seal_status"]).lower() == "completed"
    gates = {
        "tier1_participation": tier1,
        "tier2_competence": tier2,
        "tier3_measurability": tier3,
        "ceiling_below_trivial": ceiling,
        "infrastructure_validity": infra,
    }
    required = ("tier1_participation", "tier2_competence", "tier3_measurability")
    verdict = "PASS" if all(gates[g] for g in required + ("ceiling_below_trivial", "infrastructure_validity")) else "FAIL"
    return {"arm": arm, "gates": gates, "verdict": verdict}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_path")
    parser.add_argument("--arm", choices=("medium", "low"), required=True)
    args = parser.parse_args()
    evidence = _load(args.evidence_path)
    summary_path = args.evidence_path.replace("dyad-luna-", "summary-luna-").replace(
        ".json", ".json"
    )
    try:
        summary = _load(summary_path)
        digest = _sha256(args.evidence_path)
        assert digest == summary["evidence_sha256"], "evidence sha256 mismatch"
        assert summary["plan_hash"] == evidence.get("plan_hash"), "plan hash mismatch"
        assert summary["reasoning_effort"] == args.arm
    except FileNotFoundError:
        print(json.dumps({"warning": "summary file missing; sha check skipped"}))
    stats = extract_dyad_stats(evidence)
    result = evaluate_gates(stats, arm=args.arm)
    print(json.dumps({"stats": stats, "adjudication": result}, indent=2))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
