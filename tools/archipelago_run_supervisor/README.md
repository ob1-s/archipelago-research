# Archipelago run supervisor

This is an operational-only supervisor for future long-running evaluators. It
is deliberately outside every scientific environment package and never reads
traces, transcripts, rewards, assignments, or model outputs. It observes only:

- detached process identity and `/proc` state;
- an atomic exit-code record written by the detached wrapper;
- `stat` metadata for explicitly supplied operational activity files;
- an atomic supervisor status file.

The `launcher.py launch` command starts an evaluator in a new session, records
wrapper/child PID and start-time identity, redirects stdout/stderr to an
operational log, and starts a separate watcher. The watcher reports
`succeeded`, `fatal_error`, or `stalled` without sending signals or modifying
the evaluator.

The `stop_hook.py` command is a future Codex synchronous `Stop` hook. When a
terminal status is present it emits one `decision: block` continuation request
with an outcome-blind audit instruction. It uses both its own one-shot state
and Codex's `stop_hook_active` input to disarm after the continuation, so it
cannot create a continuation loop. The example hook is not installed or
trusted by this change.

## Future launch

From the repository root, use an operational run directory outside the frozen
environment package:

```bash
python -m tools.archipelago_run_supervisor.launcher launch \
  --run-dir /tmp/archipelago-run-supervisor/example \
  --status-path /tmp/archipelago-run-supervisor/example/status.json \
  --activity-path /tmp/archipelago-run-supervisor/example/eval.log \
  --run-id example-2026-08-14 -- \
  prime eval run @ frozen.toml
```

Before use on a real run, review/trust the exact hook definition in Codex and
choose a synchronous timeout that is demonstrably longer than the remaining
evaluator wait. The current Codex release documents a 600-second default;
this design intentionally does not assume that a Stop hook can block for
hours.

## Current-run fallback

When a session began without the hook loaded and trusted, use only the
non-invasive watcher form against the existing evaluator PID. Do not use the
launcher for an already-running evaluator. A process that exits without the
wrapper's exit record is reported as `fatal_error` with reason
`target_exited_without_exit_code`, requiring manual operational review.
