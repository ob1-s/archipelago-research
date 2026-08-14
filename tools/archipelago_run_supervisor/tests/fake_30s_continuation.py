"""30-second operational proof: wait, then request one same-thread continuation."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from tools.archipelago_run_supervisor.stop_hook import handle_stop
from tools.archipelago_run_supervisor.supervisor import WatchSpec, watch

ROOT = Path(__file__).resolve().parents[3]
LAUNCHER = ROOT / "tools/archipelago_run_supervisor/launcher.py"


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        run_dir = Path(temporary)
        exit_path = run_dir / "exit.json"
        child_metadata_path = run_dir / "child.json"
        status_path = run_dir / "status.json"
        hook_state_path = run_dir / "hook-state.json"
        log_path = run_dir / "evaluator.log"
        command = [
            sys.executable,
            str(LAUNCHER),
            "run-child",
            "--exit-path",
            str(exit_path),
            "--child-metadata-path",
            str(child_metadata_path),
            "--",
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
        ]
        started = time.monotonic()
        with log_path.open("wb") as log_handle:
            process = subprocess.Popen(command, stdout=log_handle, stderr=subprocess.STDOUT)
        result = watch(
            WatchSpec(
                pid=process.pid,
                status_path=status_path,
                exit_path=exit_path,
                activity_paths=(log_path,),
                poll_seconds=0.25,
                stall_seconds=45,
                run_id="fake-30s",
            )
        )
        process.wait(timeout=2)
        elapsed = time.monotonic() - started
        if elapsed < 29 or result["state"] != "succeeded" or result["exit_code"] != 0:
            raise AssertionError({"elapsed": elapsed, "result": result})

        first = handle_stop(
            {"stop_hook_active": False},
            status_path=status_path,
            hook_state_path=hook_state_path,
        )
        second = handle_stop(
            {"stop_hook_active": True},
            status_path=status_path,
            hook_state_path=hook_state_path,
        )
        if first.get("decision") != "block" or second != {}:
            raise AssertionError({"first": first, "second": second})
        print(json.dumps({"elapsed_seconds": round(elapsed, 2), "first": first, "second": second}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
