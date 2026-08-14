"""Outcome-blind synchronous Codex Stop hook.

The hook only reads the supervisor's operational status file and its own
one-shot state file.  It never opens evaluator traces or model transcripts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from .supervisor import TERMINAL_STATES, atomic_write_json, read_json

CONTINUATION_REASON = (
    "The unattended evaluator has terminated or entered a terminal operational "
    "state. Inspect its final operational status, then perform the preregistered "
    "post-stop audit and analysis. Do not inspect behavioral outcomes until the "
    "stopping criterion is verified."
)


def _load_hook_state(path: Path) -> dict[str, Any]:
    return read_json(path) or {"armed": True, "fired": False}


def _disarm(path: Path, *, fired: bool, reason: str) -> None:
    atomic_write_json(
        path,
        {
            "schema_version": 1,
            "scope": "operational_only",
            "armed": False,
            "fired": fired,
            "reason": reason,
        },
    )


def _block_once(path: Path) -> None:
    atomic_write_json(
        path,
        {
            "schema_version": 1,
            "scope": "operational_only",
            "armed": True,
            "fired": True,
            "reason": "continuation_requested",
        },
    )


def handle_stop(
    payload: dict[str, Any],
    *,
    status_path: Path,
    hook_state_path: Path,
    wait_timeout: float = 0.0,
    poll_seconds: float = 2.0,
) -> dict[str, Any]:
    state = _load_hook_state(hook_state_path)
    if payload.get("stop_hook_active"):
        _disarm(hook_state_path, fired=bool(state.get("fired")), reason="active_continuation_seen")
        return {}
    if not state.get("armed", True) or state.get("fired", False):
        return {}

    deadline = time.monotonic() + max(0.0, wait_timeout)
    while True:
        status = read_json(status_path)
        if status and status.get("state") in TERMINAL_STATES:
            _block_once(hook_state_path)
            return {"decision": "block", "reason": CONTINUATION_REASON}
        if time.monotonic() >= deadline:
            return {}
        time.sleep(min(poll_seconds, max(0.0, deadline - time.monotonic())))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status-path", type=Path, default=Path(os.environ["ARCHIPELAGO_SUPERVISOR_STATUS"]))
    parser.add_argument(
        "--hook-state-path",
        type=Path,
        default=Path(os.environ["ARCHIPELAGO_SUPERVISOR_HOOK_STATE"]),
    )
    parser.add_argument("--wait-timeout", type=float, default=float(os.environ.get("ARCHIPELAGO_SUPERVISOR_HOOK_WAIT", "0")))
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    print(
        json.dumps(
            handle_stop(
                payload,
                status_path=args.status_path,
                hook_state_path=args.hook_state_path,
                wait_timeout=args.wait_timeout,
                poll_seconds=args.poll_seconds,
            ),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
