"""Create the canonical primary analysis input from frozen trace extraction."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cross_rollout_postcommitment_evidence_threshold_transport_v1.analysis import (
    iter_trace_objects,
    parse_trace,
)

RAW = Path(
    "/tmp/archipelago-cross-rollout-postcommitment-evidence-threshold-transport-v1-luna-2026-08-14/traces.jsonl"
)
OUT = Path(__file__).with_name("analysis_input.json")
FROZEN_COMMIT = "9c47e0c279c01b77bdd21f63c27e7eca8346439f"


def main() -> None:
    rows = []
    line_count = 0
    source_hash = hashlib.sha256()
    with RAW.open("rb") as stream:
        for raw_line in stream:
            line_count += 1
            source_hash.update(raw_line)

    for source_trace_index, (trace, outer_id) in enumerate(iter_trace_objects(RAW)):
        row = parse_trace(trace, outer_id)
        if not row.primary_eligible:
            continue
        info = trace["info"]["evidence_threshold_transport_assay"]
        rows.append(
            {
                "trace_id": row.trace_id,
                "source_trace_index": source_trace_index,
                "attempt_index": row.attempt_index,
                "assignment_key": info["assignment_key"],
                "quota_cell_key": info["quota_cell_key"],
                "strength": row.strength,
                "q": row.q,
                "phase1_order": row.phase1_order,
                "phase2_order": row.phase2_order,
                "phase1_policy": info.get("phase1_policy"),
                "phase2_policy": info.get("phase2_policy"),
                "evidence_class": info.get("evidence_class"),
                "primary_eligible": row.primary_eligible,
                "evidence_eligible": row.evidence_eligible,
                "primary_choice_observed": row.primary_choice_observed,
                "switch": row.primary_itt_switch,
                "retain": not row.primary_itt_switch,
                "phase2_missing": row.phase2_missing,
                "phase2_incomplete": row.phase2_incomplete,
                "natural_yield": row.natural_yield,
                "r2_activated": row.r2_activated,
                "turn2_sent_count": row.turn2_sent_count,
                "interstage_call_count": row.interstage_call_count,
                "user_message_count": row.user_message_count,
                "duration_seconds": row.duration_seconds,
                "model_requests": row.model_requests,
                "tool_calls": row.tool_calls,
                "errors": list(row.errors),
            }
        )

    rows.sort(key=lambda item: (item["attempt_index"], item["trace_id"]))
    if len(rows) != 504:
        raise RuntimeError(f"expected 504 primary rows, found {len(rows)}")
    if len({row["attempt_index"] for row in rows}) != len(rows):
        raise RuntimeError("duplicate primary attempt index")
    payload = {
        "schema_version": "evidence_threshold_transport_v1.analysis_input.v1",
        "frozen_commit": FROZEN_COMMIT,
        "source": {
            "path": str(RAW),
            "sha256": source_hash.hexdigest(),
            "byte_count": RAW.stat().st_size,
            "line_count": line_count,
        },
        "extraction": {
            "parser": "cross_rollout_postcommitment_evidence_threshold_transport_v1.analysis.parse_trace",
            "primary_filter": "TraceRow.primary_eligible is true",
            "canonical_order": "attempt_index, trace_id",
            "missingness": "preserve frozen phase2_missing and phase2_incomplete flags",
        },
        "primary_count": len(rows),
        "rows": rows,
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
