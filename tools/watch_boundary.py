#!/usr/bin/env python3
"""Read-only progress monitor for the provenance-boundary qualification.

The monitor deliberately does not open ``traces.jsonl``.  It reads only:

* the atomically replaced assignment-ledger envelope (eligible count and claims
  length, never individual assignment fields);
* evaluator log-line prefixes for rollout-start/rollout-done counters and
  timestamps;
* the supervisor's operational status JSON; and
* Linux ``/proc/<pid>/stat`` process metadata.

It never takes the assignment lock, writes a file, signals a process, invokes
the evaluator, or retains/prints trace content.  Recent eligible/hour and ETA
are based on in-memory samples collected after this monitor starts.  No sample
file is created.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

DEFAULT_LEDGER = Path(
    "/tmp/cross-rollout-postcommitment-provenance-boundary-v1-assignments-2026-08-14-repaired.json"
)
DEFAULT_LOG = Path(
    "/tmp/archipelago-cross-rollout-postcommitment-provenance-boundary-v1-luna-2026-08-14-repaired/eval.log"
)
DEFAULT_STATUS = Path(
    "/tmp/archipelago-run-supervisor-current-luna-2026-08-14/status.json"
)
TARGET_ELIGIBLE = 432
BLOCK_SIZE = 36

LogKind = Literal["start", "done"]
LOG_EVENT = re.compile(
    r"^(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\s+"
    r".*\brollout (?P<kind>start|done):"
)


@dataclass(frozen=True)
class LogEvent:
    seconds: float
    kind: LogKind


@dataclass(frozen=True)
class LogSummary:
    starts: int = 0
    done: int = 0
    first_start: float | None = None
    last_event: float | None = None
    done_times: tuple[float, ...] = ()


@dataclass(frozen=True)
class LedgerSnapshot:
    eligible: int | None
    claims: int | None
    mtime: float | None
    error: str | None = None


@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int | None
    alive: bool | None
    state: str | None
    start_ticks: str | None
    pid_reused: bool = False


@dataclass(frozen=True)
class Sample:
    monotonic: float
    eligible: int


@dataclass
class MonitorState:
    samples: list[Sample] = field(default_factory=list)


def read_json(path: Path) -> dict[str, Any] | None:
    """Read one operational JSON file without any write or lock operation."""

    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def read_ledger(path: Path, target: int) -> LedgerSnapshot:
    """Read only the ledger counter envelope; do not inspect assignment fields."""

    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None
    payload = read_json(path)
    if payload is None:
        return LedgerSnapshot(None, None, mtime, "ledger unavailable or invalid")
    eligible = payload.get("next_eligible_index")
    claims = payload.get("claims")
    if (
        isinstance(eligible, bool)
        or not isinstance(eligible, int)
        or not 0 <= eligible <= target
        or not isinstance(claims, list)
    ):
        return LedgerSnapshot(None, None, mtime, "ledger counter envelope invalid")
    if len(claims) != eligible:
        return LedgerSnapshot(
            eligible,
            len(claims),
            mtime,
            "ledger counter and claims length disagree",
        )
    return LedgerSnapshot(eligible, len(claims), mtime)


def read_log(path: Path) -> LogSummary:
    """Count only known operational log prefixes, discarding the rest of each line."""

    starts = 0
    done = 0
    first_start: float | None = None
    last_event: float | None = None
    done_times: list[float] = []
    previous_seconds: float | None = None
    day_offset = 0.0
    try:
        handle = path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return LogSummary()
    with handle:
        for line in handle:
            match = LOG_EVENT.match(line)
            if match is None:
                continue
            seconds = (
                int(match.group("hour")) * 3600
                + int(match.group("minute")) * 60
                + int(match.group("second"))
            )
            if previous_seconds is not None and seconds < previous_seconds:
                day_offset += 24 * 3600
            event_seconds = seconds + day_offset
            previous_seconds = seconds
            kind: LogKind = "start" if match.group("kind") == "start" else "done"
            event = LogEvent(event_seconds, kind)
            if event.kind == "start":
                starts += 1
                if first_start is None:
                    first_start = event.seconds
            else:
                done += 1
                done_times.append(event.seconds)
            if last_event is None or event.seconds > last_event:
                last_event = event.seconds
    return LogSummary(
        starts=starts,
        done=done,
        first_start=first_start,
        last_event=last_event,
        done_times=tuple(done_times),
    )


def process_snapshot(
    pid: int | None, expected_start_ticks: str | None = None
) -> ProcessSnapshot:
    """Read Linux process metadata without signalling or otherwise touching a PID."""

    if pid is None or pid <= 0:
        return ProcessSnapshot(pid, None, None, None)
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return ProcessSnapshot(pid, False, None, None)
    marker = raw.rfind(") ")
    if marker < 0:
        return ProcessSnapshot(pid, True, "?", None)
    fields = raw[marker + 2 :].split()
    state = fields[0] if fields else "?"
    start_ticks = fields[19] if len(fields) > 19 else None
    return ProcessSnapshot(
        pid,
        state != "Z",
        state,
        start_ticks,
        expected_start_ticks is not None
        and start_ticks is not None
        and start_ticks != expected_start_ticks,
    )


def status_payload(path: Path) -> dict[str, Any]:
    return read_json(path) or {}


def int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def iso_age(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - timestamp).total_seconds())


def last_progress_age(
    status: dict[str, Any], ledger: LedgerSnapshot, log_path: Path
) -> float | None:
    """Prefer the supervisor's metadata-only activity age, with safe stat fallback."""

    watcher_age = iso_age(status.get("last_activity_at"))
    if watcher_age is not None:
        return watcher_age
    mtimes = [
        mtime for mtime in (ledger.mtime, file_mtime(log_path)) if mtime is not None
    ]
    if not mtimes:
        return None
    return max(0.0, time.time() - max(mtimes))


def file_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def rate_per_hour(delta: int, span_seconds: float | None) -> float | None:
    if span_seconds is None or span_seconds <= 0 or delta < 0:
        return None
    return delta * 3600.0 / span_seconds


def whole_run_rate(count: int, log: LogSummary) -> float | None:
    if log.first_start is None or log.last_event is None:
        return None
    return rate_per_hour(count, log.last_event - log.first_start)


def recent_done_rate(log: LogSummary, window_seconds: float) -> float | None:
    if not log.done_times or log.last_event is None or log.first_start is None:
        return None
    window_start = max(log.first_start, log.last_event - window_seconds)
    count = sum(event >= window_start for event in log.done_times)
    return rate_per_hour(count, log.last_event - window_start)


def sampled_rate(
    samples: list[Sample], now: float, window_seconds: float, minimum_span: float
) -> float | None:
    if len(samples) < 2:
        return None
    recent = [sample for sample in samples if now - sample.monotonic <= window_seconds]
    if len(recent) < 2:
        return None
    first, last = recent[0], recent[-1]
    span = last.monotonic - first.monotonic
    if span < minimum_span:
        return None
    return rate_per_hour(last.eligible - first.eligible, span)


def format_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}/h"


def format_age(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f}m"
    return f"{minutes / 60:.1f}h"


def format_duration(seconds: float | None) -> str:
    if seconds is None or seconds <= 0:
        return "n/a"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def process_text(snapshot: ProcessSnapshot) -> str:
    if snapshot.pid is None:
        return "unknown PID"
    if snapshot.pid_reused:
        return f"PID {snapshot.pid}: PID_REUSED"
    if snapshot.alive:
        return f"PID {snapshot.pid}: running (state {snapshot.state or '?'})"
    if snapshot.alive is False:
        return f"PID {snapshot.pid}: not running"
    return f"PID {snapshot.pid}: unknown"


def progress_bar(value: int, target: int, width: int = 30) -> str:
    """Return a compact progress bar without exposing any experiment fields."""

    if target <= 0:
        return "[" + "?" * width + "]"
    fraction = min(1.0, max(0.0, value / target))
    filled = int(round(width * fraction))
    return "[" + "#" * filled + "." * (width - filled) + "]"


def render(
    *,
    ledger: LedgerSnapshot,
    log: LogSummary,
    status: dict[str, Any],
    evaluator: ProcessSnapshot,
    watcher: ProcessSnapshot,
    state: MonitorState,
    target: int,
    log_path: Path,
    recent_window: float,
    minimum_rate_span: float,
) -> str:
    now = time.monotonic()
    eligible = ledger.eligible
    eligible_display = "n/a" if eligible is None else str(eligible)
    percentage = "n/a" if eligible is None else f"{eligible / target * 100:.1f}%"
    block_count = max(1, (target + BLOCK_SIZE - 1) // BLOCK_SIZE)
    if eligible is None:
        block_display = "n/a"
        eta = None
        recent_eligible_rate = None
        whole_eligible_rate = None
    else:
        if eligible >= target:
            block_display = f"complete ({block_count}/{block_count} blocks)"
        else:
            block_index, within = divmod(eligible, BLOCK_SIZE)
            block_display = (
                f"{block_index + 1}/{block_count} "
                f"({within}/{BLOCK_SIZE} eligible in current block)"
            )
        recent_eligible_rate = sampled_rate(
            state.samples, now, recent_window, minimum_rate_span
        )
        whole_eligible_rate = whole_run_rate(eligible, log)
        remaining = max(0, target - eligible)
        eta = (
            remaining / recent_eligible_rate * 3600
            if remaining and recent_eligible_rate and recent_eligible_rate > 0
            else 0.0
            if remaining == 0
            else None
        )

    starts = log.starts
    eligibility_rate = (
        f"{eligible / starts * 100:.1f}%"
        if eligible is not None and starts > 0
        else "n/a"
    )
    recent_attempt_rate = recent_done_rate(log, recent_window)
    whole_attempt_rate = whole_run_rate(log.done, log)
    progress_age = last_progress_age(status, ledger, log_path)
    if progress_age is None:
        progress_age = status.get("last_activity_age_seconds")
        if not isinstance(progress_age, (int, float)):
            progress_age = None

    bar = progress_bar(eligible or 0, target)
    status_state = status.get("state") or "unavailable"
    elapsed = (
        log.last_event - log.first_start
        if log.first_start is not None and log.last_event is not None
        else None
    )
    lines = [
        "cross_rollout_postcommitment_provenance_boundary_v1 — READ-ONLY MONITOR",
        f"Eligible assignments: {eligible_display} / {target} ({percentage}) {bar}",
        f"Phase-1 attempts observed (rollout starts): {starts if starts else 'n/a'}",
        f"Current eligibility rate: {eligibility_rate}",
        f"Current macro-block: {block_display}",
        (
            "Attempts/hour (completed; recent window): "
            f"{format_rate(recent_attempt_rate)}; whole-run: {format_rate(whole_attempt_rate)}"
        ),
        (
            "Eligible/hour: "
            f"recent monitor estimate {format_rate(recent_eligible_rate)}; "
            f"whole-run {format_rate(whole_eligible_rate)}"
        ),
        (
            "ETA at recent eligible/hour: "
            f"{format_duration(eta)} estimate"
            if eta is not None
            else "ETA at recent eligible/hour: n/a (waiting for a stable monitor window)"
        ),
        f"Evaluator: {process_text(evaluator)}",
        f"Watcher: {process_text(watcher)} (reported state: {status_state})",
        f"Time since last recorded operational progress: {format_age(progress_age)}",
        (
            f"Rate window: {recent_window / 60:.0f}m; minimum sampled eligible window: "
            f"{minimum_rate_span:.0f}s; observed log span: {format_duration(elapsed)}"
        ),
        "Sources: assignment counter envelope, evaluator log prefixes, supervisor status, /proc.",
        "Trace contents are not read; no assignment lock is acquired; no files are written.",
    ]
    if ledger.error:
        lines.insert(2, f"WARNING: {ledger.error}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--evaluator-pid", type=int)
    parser.add_argument("--watcher-pid", type=int)
    parser.add_argument("--target", type=int, default=TARGET_ELIGIBLE)
    parser.add_argument("--refresh-seconds", type=float, default=7.0)
    parser.add_argument("--recent-window-minutes", type=float, default=30.0)
    parser.add_argument("--minimum-rate-span-seconds", type=float, default=60.0)
    parser.add_argument("--once", action="store_true", help="render one snapshot and exit")
    parser.add_argument("--no-clear", action="store_true", help="do not clear the terminal")
    return parser


def one_snapshot(args: argparse.Namespace, state: MonitorState) -> str:
    ledger = read_ledger(args.ledger, args.target)
    log = read_log(args.log)
    status = status_payload(args.status)
    evaluator_pid = args.evaluator_pid or int_or_none(status.get("target_pid"))
    watcher_pid = args.watcher_pid or int_or_none(status.get("supervisor_pid"))
    expected_start = status.get("target_start_ticks")
    evaluator = process_snapshot(
        evaluator_pid, expected_start if isinstance(expected_start, str) else None
    )
    watcher = process_snapshot(watcher_pid)
    if ledger.eligible is not None:
        state.samples.append(Sample(time.monotonic(), ledger.eligible))
        cutoff = time.monotonic() - max(args.recent_window_minutes * 60, 60.0) * 2
        state.samples[:] = [sample for sample in state.samples if sample.monotonic >= cutoff]
    return render(
        ledger=ledger,
        log=log,
        status=status,
        evaluator=evaluator,
        watcher=watcher,
        state=state,
        target=args.target,
        log_path=args.log,
        recent_window=max(1.0, args.recent_window_minutes * 60),
        minimum_rate_span=max(0.0, args.minimum_rate_span_seconds),
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.target <= 0 or args.refresh_seconds <= 0:
        raise SystemExit("--target and --refresh-seconds must be positive")
    state = MonitorState()
    try:
        while True:
            output = one_snapshot(args, state)
            if not args.no_clear and sys.stdout.isatty():
                sys.stdout.write("\x1b[2J\x1b[H")
            print(output, flush=True)
            if args.once:
                return 0
            time.sleep(args.refresh_seconds)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
