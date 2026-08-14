"""Machine-readable model-visible and frozen-contract audit."""

from __future__ import annotations

import argparse
import difflib
import inspect
import json
import re
from pathlib import Path
from typing import Any

from . import assignment, randomness
from .constants import (
    ADVISORY_RELIABILITY_LEVELS,
    AUTOMATED_SOURCE_SENTENCE,
    PHASE1_ORDERS,
    PREDECESSOR_SOURCE_SENTENCE,
    RELEASE_DESCRIPTION,
    SELECT_DESCRIPTION,
    SOURCE_CONDITIONS,
    phase1_prompt,
    phase2_prompt,
)
from .schedule import MAX_ATTEMPTS, TARGET_PRIMARY_ELIGIBLE, build_schedule
from .servers.facility import BoundaryToolset
from .taskset import CrossRolloutPostcommitmentProvenanceBoundaryV1Env


def _diff_segments(left: str, right: str) -> list[dict[str, Any]]:
    matcher = difflib.SequenceMatcher(a=left, b=right, autojunk=False)
    segments = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            segments.append({"operation": tag, "left": left[i1:i2], "right": right[j1:j2]})
    return segments


def _schema_surface() -> dict[str, Any]:
    parameter = inspect.signature(BoundaryToolset.select_policy).parameters["policy"]
    return {
        "annotation": repr(parameter.annotation),
        "select_description": SELECT_DESCRIPTION,
        "release_description": RELEASE_DESCRIPTION,
        "serialized_schema": {
            "properties": {"policy": {"title": "Policy", "type": "string"}},
            "required": ["policy"],
            "title": "select_policyArguments",
            "type": "object",
        },
        "label_free": parameter.annotation is str
        and not any(label in SELECT_DESCRIPTION + RELEASE_DESCRIPTION for label in ("K", "M")),
    }


def build_surface_audit() -> dict[str, Any]:
    phase1 = {}
    for order in PHASE1_ORDERS:
        prompt = phase1_prompt(order)
        prefix = prompt.split("For R1, choose one policy with", 1)[0]
        phase1[order] = {
            "prompt": prompt,
            "prefix_has_uppercase_policy_labels": any(label in prefix for label in ("K", "M")),
            "source_or_q_before_choice": any(
                marker in prefix.lower()
                for marker in (" source ", "advisory", "%", "previous operators")
            ),
            "ordered_pair_occurrences": prompt.count(
                'select_policy(policy="K" or "M")'
            ) + prompt.count('select_policy(policy="M" or "K")'),
        }

    source_diffs = []
    q_diffs = []
    for order in PHASE1_ORDERS:
        for q in ADVISORY_RELIABILITY_LEVELS:
            predecessor = phase2_prompt(order, q, "PredecessorSource")
            automated = phase2_prompt(order, q, "AutomatedSource")
            source_normalized = predecessor.replace(PREDECESSOR_SOURCE_SENTENCE, "{SOURCE}")
            source_normalized_other = automated.replace(AUTOMATED_SOURCE_SENTENCE, "{SOURCE}")
            source_diffs.append({
                "order": order,
                "q": q,
                "normalized_equal": source_normalized == source_normalized_other,
                "segments": _diff_segments(predecessor, automated),
            })
        for source in SOURCE_CONDITIONS:
            messages = [phase2_prompt(order, q, source) for q in ADVISORY_RELIABILITY_LEVELS]
            normalized = [re.sub(r"\d+\.\d+%", "{Q}", message) for message in messages]
            q_diffs.append({
                "order": order,
                "source": source,
                "normalized_equal": len(set(normalized)) == 1,
                "rendered_percentages": re.findall(r"\d+\.\d+%", " ".join(messages)),
            })

    source_root = Path(__file__).resolve().parent
    texts = "\n".join(
        (source_root / name).read_text(encoding="utf-8")
        for name in ("constants.py", "taskset.py", "servers/facility.py")
    )
    banned = ("5/5", "2/8", "NoAdvisory", "Continue the active facility operation")
    schedule = build_schedule()
    plan = assignment.build_assignment_plan("audit-seed")
    by_cell: dict[tuple[float, str], list[Any]] = {}
    for row in plan:
        by_cell.setdefault((row.advisory_reliability, row.source_condition), []).append(row)
    schema = _schema_surface()
    checks = {
        "phase1_order_only_in_explicit_syntax": all(
            not row["prefix_has_uppercase_policy_labels"] and not row["source_or_q_before_choice"]
            and row["ordered_pair_occurrences"] == 1
            for row in phase1.values()
        ),
        "source_diff_only_source_sentence": all(
            row["normalized_equal"] and row["segments"] for row in source_diffs
        ),
        "q_diff_only_numeric_reliability": all(row["normalized_equal"] for row in q_diffs),
        "all_q_strings_present": sorted(set(q_diffs[0]["rendered_percentages"])) == [
            "78.00%", "78.50%", "79.00%", "79.25%", "79.50%", "79.75%", "80.00%", "80.50%", "81.00%"
        ],
        "advisory_points_to_not_p": all(
            "policy you did not use on R1 is the batch-matching policy" in phase2_prompt(order, q, source)
            for order in PHASE1_ORDERS
            for q in ADVISORY_RELIABILITY_LEVELS
            for source in SOURCE_CONDITIONS
        ),
        "schema_label_neutral": bool(schema["label_free"]),
        "phase2_order_balanced_by_q_source": all(
            len([row for row in plan if row.advisory_reliability == q and row.source_condition == source and row.phase2_order == order]) == 12
            for q in ADVISORY_RELIABILITY_LEVELS
            for source in SOURCE_CONDITIONS
            for order in PHASE1_ORDERS
        ),
        "assignment_cell_counts": all(len(rows) == 24 for rows in by_cell.values()),
        "target_and_cap_frozen": len(plan) == TARGET_PRIMARY_ELIGIBLE == 432 and MAX_ATTEMPTS == 1400,
        "schedule_balanced": (
            len(schedule) == 1400
            and sum(row.phase1_order == "K_first" for row in schedule) == 700
            and sum(row.phase1_order == "M_first" for row in schedule) == 700
        ),
        "no_old_or_custom_surface_terms": not any(term in texts for term in banned),
        "native_interaction_and_null_harness_source_present": (
            "interaction.turn" in inspect.getsource(CrossRolloutPostcommitmentProvenanceBoundaryV1Env)
            and "NullHarnessConfig" in Path(__file__).with_name("taskset.py").read_text(encoding="utf-8")
        ),
        "random_namespaces_are_distinct": len(randomness.ROLLOUT_NAMESPACES) == len(set(randomness.ROLLOUT_NAMESPACES)),
    }
    return {
        "checks": checks,
        "all_pass": all(checks.values()),
        "phase1": phase1,
        "source_diffs": source_diffs,
        "q_diffs": q_diffs,
        "mcp_schema": schema,
        "assignment_counts": {
            f"{q:.4f}/{source}": len(rows)
            for (q, source), rows in sorted(by_cell.items(), key=lambda item: str(item[0]))
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = build_surface_audit()
    encoded = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    if not result["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
