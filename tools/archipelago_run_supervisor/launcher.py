"""Detached evaluator launcher with explicit child exit-code tracking."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

try:
    from .supervisor import atomic_write_json, process_snapshot, utc_now
except ImportError:  # Direct script execution is used by detached subprocesses.
    from supervisor import atomic_write_json, process_snapshot, utc_now


def run_child(command: list[str], exit_path: Path, child_metadata_path: Path) -> int:
    child = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        start_new_session=False,
    )
    snapshot = process_snapshot(child.pid)
    atomic_write_json(
        child_metadata_path,
        {
            "schema_version": 1,
            "scope": "operational_only",
            "pid": child.pid,
            "start_ticks": snapshot.get("start_ticks"),
            "started_at": utc_now(),
        },
    )
    exit_code = child.wait()
    atomic_write_json(
        exit_path,
        {
            "schema_version": 1,
            "scope": "operational_only",
            "pid": child.pid,
            "exit_code": exit_code,
            "finished_at": utc_now(),
        },
    )
    return exit_code


def launch(
    command: list[str],
    *,
    run_dir: Path,
    status_path: Path,
    activity_paths: list[Path],
    stall_seconds: float,
    poll_seconds: float,
    run_id: str,
    cwd: Path | None,
) -> dict[str, object]:
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "evaluator.log"
    exit_path = run_dir / "exit.json"
    child_metadata_path = run_dir / "child.json"
    wrapper_command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "run-child",
        "--exit-path",
        str(exit_path),
        "--child-metadata-path",
        str(child_metadata_path),
        "--",
        *command,
    ]
    with log_path.open("ab") as log_handle:
        wrapper = subprocess.Popen(
            wrapper_command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    wrapper_snapshot = process_snapshot(wrapper.pid)
    activity = [*activity_paths, log_path]
    launch_payload = {
        "schema_version": 1,
        "scope": "operational_only",
        "run_id": run_id,
        "wrapper_pid": wrapper.pid,
        "wrapper_start_ticks": wrapper_snapshot.get("start_ticks"),
        "exit_path": str(exit_path),
        "child_metadata_path": str(child_metadata_path),
        "status_path": str(status_path),
        "activity_paths": [str(path) for path in activity],
        "started_at": utc_now(),
        "behavioral_content_inspected": False,
    }
    atomic_write_json(run_dir / "launch.json", launch_payload)

    supervisor_command = [
        sys.executable,
        str(Path(__file__).with_name("supervisor.py")),
        "watch",
        "--pid",
        str(wrapper.pid),
        "--status-path",
        str(status_path),
        "--exit-path",
        str(exit_path),
        "--poll-seconds",
        str(poll_seconds),
        "--stall-seconds",
        str(stall_seconds),
        "--run-id",
        run_id,
    ]
    if wrapper_snapshot.get("start_ticks") is not None:
        supervisor_command.extend(
            ["--expected-start-ticks", str(wrapper_snapshot["start_ticks"])]
        )
    for activity_path in activity:
        supervisor_command.extend(["--activity-path", str(activity_path)])
    supervisor_log = (run_dir / "supervisor.log").open("ab")
    try:
        supervisor = subprocess.Popen(
            supervisor_command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=supervisor_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    finally:
        supervisor_log.close()
    launch_payload["supervisor_pid"] = supervisor.pid
    atomic_write_json(run_dir / "launch.json", launch_payload)
    return launch_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    child = subparsers.add_parser("run-child")
    child.add_argument("--exit-path", type=Path, required=True)
    child.add_argument("--child-metadata-path", type=Path, required=True)
    child.add_argument("command_args", nargs=argparse.REMAINDER)
    launch_parser = subparsers.add_parser("launch")
    launch_parser.add_argument("--run-dir", type=Path, required=True)
    launch_parser.add_argument("--status-path", type=Path, required=True)
    launch_parser.add_argument("--activity-path", type=Path, action="append", default=[])
    launch_parser.add_argument("--stall-seconds", type=float, default=3600.0)
    launch_parser.add_argument("--poll-seconds", type=float, default=5.0)
    launch_parser.add_argument("--run-id", required=True)
    launch_parser.add_argument("--cwd", type=Path)
    launch_parser.add_argument("command_args", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run-child":
        command = list(args.command_args)
        if command and command[0] == "--":
            command = command[1:]
        if not command:
            raise SystemExit("run-child requires a command after --")
        return run_child(command, args.exit_path, args.child_metadata_path)
    if args.command == "launch":
        command = list(args.command_args)
        if command and command[0] == "--":
            command = command[1:]
        if not command:
            raise SystemExit("launch requires a command after --")
        payload = launch(
            command,
            run_dir=args.run_dir,
            status_path=args.status_path,
            activity_paths=args.activity_path,
            stall_seconds=args.stall_seconds,
            poll_seconds=args.poll_seconds,
            run_id=args.run_id,
            cwd=args.cwd,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
