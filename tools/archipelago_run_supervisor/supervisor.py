"""Operational-only evaluator supervision.

This module deliberately never opens a trace/archive file.  It observes only
process identity, exit-code metadata, and filesystem metadata (size and mtime)
for explicitly supplied operational activity paths.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TERMINAL_STATES = frozenset({"succeeded", "fatal_error", "stalled"})


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON durably enough for another process to observe atomically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        except (AttributeError, OSError):
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        temporary_path.unlink(missing_ok=True)


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def process_snapshot(pid: int) -> dict[str, Any]:
    """Return Linux process state and start time without signalling the PID."""

    proc_stat = Path(f"/proc/{pid}/stat")
    try:
        raw = proc_stat.read_text(encoding="utf-8")
    except OSError:
        return {"alive": False, "state": None, "start_ticks": None}

    # The comm field may contain ')', so split after its final closing paren.
    marker = raw.rfind(") ")
    if marker < 0:
        return {"alive": True, "state": "?", "start_ticks": None}
    fields = raw[marker + 2 :].split()
    state = fields[0] if fields else "?"
    start_ticks = fields[19] if len(fields) > 19 else None
    return {"alive": state != "Z", "state": state, "start_ticks": start_ticks}


def filesystem_snapshot(paths: tuple[Path, ...]) -> dict[str, dict[str, int] | None]:
    """Read only stat metadata for operational activity paths."""

    result: dict[str, dict[str, int] | None] = {}
    for path in paths:
        try:
            stat_result = path.stat()
        except OSError:
            result[str(path)] = None
        else:
            result[str(path)] = {
                "mtime_ns": stat_result.st_mtime_ns,
                "size": stat_result.st_size,
            }
    return result


def read_exit_code(path: Path | None) -> int | None:
    if path is None:
        return None
    payload = read_json(path)
    if payload is None:
        return None
    value = payload.get("exit_code")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


@dataclass(frozen=True)
class WatchSpec:
    pid: int
    status_path: Path
    exit_path: Path | None = None
    activity_paths: tuple[Path, ...] = ()
    expected_start_ticks: str | None = None
    poll_seconds: float = 5.0
    stall_seconds: float = 3600.0
    wait_timeout: float | None = None
    run_id: str = "unnamed"


def _status_payload(
    spec: WatchSpec,
    *,
    state: str,
    reason: str,
    process: dict[str, Any],
    exit_code: int | None,
    started_at: str,
    last_activity_at: str,
    activity: dict[str, dict[str, int] | None],
    last_activity_monotonic: float,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": spec.run_id,
        "scope": "operational_only",
        "behavioral_content_inspected": False,
        "supervisor_pid": os.getpid(),
        "target_pid": spec.pid,
        "target_start_ticks": spec.expected_start_ticks,
        "state": state,
        "terminal": state in TERMINAL_STATES,
        "reason": reason,
        "exit_code": exit_code,
        "observed_at": utc_now(),
        "started_at": started_at,
        "last_activity_at": last_activity_at,
        "last_activity_age_seconds": max(0.0, time.monotonic() - last_activity_monotonic),
        "activity_paths": list(activity),
        "process": process,
        "stall_seconds": spec.stall_seconds,
    }


def watch(spec: WatchSpec) -> dict[str, Any]:
    """Wait for success, fatal termination, or an operational stall."""

    started_at = utc_now()
    initial_process = process_snapshot(spec.pid)
    expected_start_ticks = spec.expected_start_ticks or initial_process.get("start_ticks")
    effective_spec = WatchSpec(**{**spec.__dict__, "expected_start_ticks": expected_start_ticks})
    activity = filesystem_snapshot(effective_spec.activity_paths)
    last_activity = activity
    last_activity_at = utc_now()
    last_activity_monotonic = time.monotonic()
    wait_started = time.monotonic()

    while True:
        now = time.monotonic()
        process = process_snapshot(effective_spec.pid)
        exit_code = read_exit_code(effective_spec.exit_path)
        activity = filesystem_snapshot(effective_spec.activity_paths)
        if activity != last_activity:
            last_activity = activity
            last_activity_at = utc_now()
            last_activity_monotonic = now

        state = "waiting"
        reason = "target_running"
        if expected_start_ticks is not None and process.get("start_ticks") not in {
            expected_start_ticks,
            None,
        }:
            state = "fatal_error"
            reason = "target_pid_reused"
        elif exit_code is not None:
            state = "succeeded" if exit_code == 0 else "fatal_error"
            reason = "exit_code_zero" if exit_code == 0 else "nonzero_exit_code"
        elif not process.get("alive", False):
            state = "fatal_error"
            reason = "target_exited_without_exit_code"
        elif now - last_activity_monotonic >= effective_spec.stall_seconds:
            state = "stalled"
            reason = "no_operational_activity"
        elif (
            effective_spec.wait_timeout is not None
            and now - wait_started >= effective_spec.wait_timeout
        ):
            state = "stalled"
            reason = "supervisor_wait_timeout"

        payload = _status_payload(
            effective_spec,
            state=state,
            reason=reason,
            process=process,
            exit_code=exit_code,
            started_at=started_at,
            last_activity_at=last_activity_at,
            activity=activity,
            last_activity_monotonic=last_activity_monotonic,
        )
        atomic_write_json(effective_spec.status_path, payload)
        if state in TERMINAL_STATES:
            return payload
        time.sleep(effective_spec.poll_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    watch_parser = subparsers.add_parser("watch")
    watch_parser.add_argument("--pid", type=int, required=True)
    watch_parser.add_argument("--status-path", type=Path, required=True)
    watch_parser.add_argument("--exit-path", type=Path)
    watch_parser.add_argument("--activity-path", type=Path, action="append", default=[])
    watch_parser.add_argument("--expected-start-ticks")
    watch_parser.add_argument("--poll-seconds", type=float, default=5.0)
    watch_parser.add_argument("--stall-seconds", type=float, default=3600.0)
    watch_parser.add_argument("--wait-timeout", type=float)
    watch_parser.add_argument("--run-id", default="unnamed")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "watch":
        result = watch(
            WatchSpec(
                pid=args.pid,
                status_path=args.status_path,
                exit_path=args.exit_path,
                activity_paths=tuple(args.activity_path),
                expected_start_ticks=args.expected_start_ticks,
                poll_seconds=args.poll_seconds,
                stall_seconds=args.stall_seconds,
                wait_timeout=args.wait_timeout,
                run_id=args.run_id,
            )
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["state"] == "succeeded" else 1
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
