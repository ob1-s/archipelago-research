#!/usr/bin/env python3
"""Read-only operational monitor for the evidence-threshold transport run.

This utility never opens ``traces.jsonl``. It reads only the atomically replaced
quota-counter JSON, known evaluator log prefixes, file timestamps, and Linux
``/proc/<pid>/stat`` metadata. It never acquires the quota lock, writes a file,
signals a process, invokes a model, or mutates execution state.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

TARGET = 504
SCHEDULE_CAP = 5040
ROUND_SIZE = 84
ROUND_COUNT = SCHEDULE_CAP // ROUND_SIZE
LOG_EVENT = re.compile(
    r"^(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\s+"
    r".*\brollout (?P<kind>start|done):"
)

DEFAULT_LEDGER = Path(
    "/tmp/archipelago-cross-rollout-postcommitment-evidence-threshold-transport-v1-quota-2026-08-14.json"
)
DEFAULT_LOG = Path(
    "/tmp/archipelago-cross-rollout-postcommitment-evidence-threshold-transport-v1-luna-2026-08-14/eval.log"
)


@dataclass(frozen=True)
class LedgerSnapshot:
    eligible: int | None
    mtime: float | None
    error: str | None = None


@dataclass(frozen=True)
class LogSummary:
    starts: int = 0
    done: int = 0
    first_start: float | None = None
    last_event: float | None = None
    done_times: tuple[float, ...] = ()


@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int | None
    alive: bool | None
    state: str | None


@dataclass(frozen=True)
class Sample:
    monotonic: float
    eligible: int


@dataclass
class MonitorState:
    samples: list[Sample] = field(default_factory=list)


def read_ledger(path: Path) -> LedgerSnapshot:
    """Read only the aggregate accepted counter; never acquire its lock."""

    try:
        mtime = path.stat().st_mtime
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return LedgerSnapshot(None, locals().get("mtime"), "ledger unavailable")
    if not isinstance(payload, dict):
        return LedgerSnapshot(None, mtime, "ledger is not an object")
    counts = payload.get("accepted_by_cell")
    accepted = payload.get("accepted_attempts")
    if not isinstance(counts, dict) or not isinstance(accepted, list):
        return LedgerSnapshot(None, mtime, "ledger counter envelope invalid")
    total = 0
    try:
        total = sum(int(value) for value in counts.values())
    except (TypeError, ValueError):
        return LedgerSnapshot(None, mtime, "ledger counter values invalid")
    if total != len(accepted) or not 0 <= total <= TARGET:
        return LedgerSnapshot(None, mtime, "ledger aggregate counters disagree")
    return LedgerSnapshot(total, mtime)


def read_log(path: Path) -> LogSummary:
    """Count only rollout start/done prefixes and discard the rest of each line."""

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
            if match.group("kind") == "start":
                starts += 1
                if first_start is None:
                    first_start = event_seconds
            else:
                done += 1
                done_times.append(event_seconds)
            last_event = event_seconds if last_event is None else max(last_event, event_seconds)
    return LogSummary(starts, done, first_start, last_event, tuple(done_times))


def process_snapshot(pid: int | None) -> ProcessSnapshot:
    if pid is None or pid <= 0:
        return ProcessSnapshot(pid, None, None)
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return ProcessSnapshot(pid, False, None)
    marker = raw.rfind(") ")
    fields = raw[marker + 2 :].split() if marker >= 0 else []
    return ProcessSnapshot(pid, bool(fields) and fields[0] != "Z", fields[0] if fields else "?")


def file_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def rate(count: int, span: float | None) -> float | None:
    if span is None or span <= 0 or count < 0:
        return None
    return count * 3600.0 / span


def format_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}/h"


def format_age(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "n/a"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def bar(value: int, target: int, width: int = 30) -> str:
    fraction = min(1.0, max(0.0, value / target)) if target else 0.0
    filled = round(width * fraction)
    return "[" + "#" * filled + "." * (width - filled) + "]"


def render(
    *,
    ledger: LedgerSnapshot,
    log: LogSummary,
    state: MonitorState,
    evaluator: ProcessSnapshot,
    watcher: ProcessSnapshot,
    target: int,
    ledger_path: Path,
    log_path: Path,
    recent_window: float,
) -> str:
    now = time.monotonic()
    eligible = ledger.eligible
    if eligible is None:
        eligible_text = "n/a"
        percentage = "n/a"
        eta = None
    else:
        eligible_text = str(eligible)
        percentage = f"{eligible / target * 100:.1f}%"
        recent = [sample for sample in state.samples if now - sample.monotonic <= recent_window]
        recent_rate = (
            rate(recent[-1].eligible - recent[0].eligible, recent[-1].monotonic - recent[0].monotonic)
            if len(recent) >= 2
            else None
        )
        remaining = max(0, target - eligible)
        eta = remaining / recent_rate * 3600 if remaining and recent_rate else 0.0 if not remaining else None

    if log.starts:
        schedule_index = min(log.starts - 1, SCHEDULE_CAP - 1)
        round_index, within = divmod(schedule_index, ROUND_SIZE)
        block = f"{round_index + 1}/{ROUND_COUNT} ({within + 1}/{ROUND_SIZE} scheduled attempts)"
    else:
        block = "n/a"

    elapsed = (
        log.last_event - log.first_start
        if log.first_start is not None and log.last_event is not None
        else None
    )
    recent_attempt_rate = None
    if log.last_event is not None and log.first_start is not None and log.done_times:
        recent_start = max(log.first_start, log.last_event - recent_window)
        recent_done = sum(event >= recent_start for event in log.done_times)
        recent_attempt_rate = rate(recent_done, log.last_event - recent_start)
    whole_attempt_rate = rate(log.done, elapsed)
    whole_eligible_rate = rate(eligible, elapsed) if eligible is not None else None
    progress_mtime = max(
        value for value in (ledger.mtime, file_mtime(log_path)) if value is not None
    ) if any(value is not None for value in (ledger.mtime, file_mtime(log_path))) else None
    progress_age = time.time() - progress_mtime if progress_mtime is not None else None

    def process_text(snapshot: ProcessSnapshot) -> str:
        if snapshot.pid is None:
            return "unknown PID"
        if snapshot.alive:
            return f"PID {snapshot.pid}: running (state {snapshot.state or '?'})"
        if snapshot.alive is False:
            return f"PID {snapshot.pid}: not running"
        return f"PID {snapshot.pid}: unknown"

    lines = [
        "cross_rollout_postcommitment_evidence_threshold_transport_v1 — READ-ONLY MONITOR",
        f"Eligible assignments: {eligible_text} / {target} ({percentage}) {bar(eligible or 0, target)}",
        f"Phase-1 attempts observed: {log.starts}",
        f"Current accepted-primary rate: {eligible / log.starts * 100:.1f}%" if eligible is not None and log.starts else "Current accepted-primary rate: n/a",
        f"Current schedule macro-block: {block}",
        f"Attempts/hour (completed): recent {format_rate(recent_attempt_rate)}; whole run {format_rate(whole_attempt_rate)}",
        f"Eligible/hour (whole run): {format_rate(whole_eligible_rate)}",
        f"ETA at sampled eligible rate: {format_duration(eta)} estimate" if eta is not None else "ETA at sampled eligible rate: n/a (waiting for monitor samples)",
        f"Evaluator: {process_text(evaluator)}",
        f"Watcher: {process_text(watcher)}",
        f"Time since last operational file progress: {format_age(progress_age)}",
        f"Sources: {ledger_path} counters, {log_path} prefixes, /proc.",
        "Trace contents are not read; no lock is acquired; no files are written.",
    ]
    if ledger.error:
        lines.insert(2, f"WARNING: {ledger.error}")
    return "\n".join(lines)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    result.add_argument("--log", type=Path, default=DEFAULT_LOG)
    result.add_argument("--evaluator-pid", type=int)
    result.add_argument("--watcher-pid", type=int, default=os.getpid())
    result.add_argument("--target", type=int, default=TARGET)
    result.add_argument("--refresh-seconds", type=float, default=7.0)
    result.add_argument("--recent-window-minutes", type=float, default=30.0)
    result.add_argument("--once", action="store_true")
    result.add_argument("--no-clear", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.target <= 0 or args.refresh_seconds <= 0:
        raise SystemExit("--target and --refresh-seconds must be positive")
    state = MonitorState()
    while True:
        ledger = read_ledger(args.ledger)
        log = read_log(args.log)
        if ledger.eligible is not None:
            state.samples.append(Sample(time.monotonic(), ledger.eligible))
            cutoff = time.monotonic() - max(args.recent_window_minutes * 60, 60.0) * 2
            state.samples[:] = [sample for sample in state.samples if sample.monotonic >= cutoff]
        output = render(
            ledger=ledger,
            log=log,
            state=state,
            evaluator=process_snapshot(args.evaluator_pid),
            watcher=process_snapshot(args.watcher_pid),
            target=args.target,
            ledger_path=args.ledger,
            log_path=args.log,
            recent_window=max(args.recent_window_minutes * 60, 60.0),
        )
        if not args.no_clear and sys.stdout.isatty():
            sys.stdout.write("\x1b[2J\x1b[H")
        print(output, flush=True)
        if args.once:
            return 0
        time.sleep(args.refresh_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
