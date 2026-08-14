from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.archipelago_run_supervisor.stop_hook import handle_stop
from tools.archipelago_run_supervisor.supervisor import (
    WatchSpec,
    atomic_write_json,
    process_snapshot,
    watch,
)

ROOT = Path(__file__).resolve().parents[3]
LAUNCHER = ROOT / "tools/archipelago_run_supervisor/launcher.py"


class SupervisorTests(unittest.TestCase):
    def test_atomic_status_and_outcome_blind_activity_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            status_path = run_dir / "status.json"
            activity_path = run_dir / "operational.log"
            activity_path.write_text("behavioral-looking content must not be opened", encoding="utf-8")
            atomic_write_json(status_path, {"state": "waiting"})
            self.assertEqual(json.loads(status_path.read_text()), {"state": "waiting"})
            snapshot = process_snapshot(os.getpid())
            self.assertTrue(snapshot["alive"])
            self.assertIsInstance(snapshot["start_ticks"], str)

    def test_stop_hook_blocks_once_then_disarms(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            status_path = run_dir / "status.json"
            hook_state_path = run_dir / "hook-state.json"
            atomic_write_json(status_path, {"state": "succeeded", "exit_code": 0})
            first = handle_stop(
                {"stop_hook_active": False},
                status_path=status_path,
                hook_state_path=hook_state_path,
            )
            self.assertEqual(first["decision"], "block")
            second = handle_stop(
                {"stop_hook_active": True},
                status_path=status_path,
                hook_state_path=hook_state_path,
            )
            self.assertEqual(second, {})
            self.assertFalse(json.loads(hook_state_path.read_text())["armed"])

    def test_wrapper_records_exit_and_watcher_detects_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            exit_path = run_dir / "exit.json"
            child_metadata_path = run_dir / "child.json"
            status_path = run_dir / "status.json"
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
                "raise SystemExit(0)",
            ]
            with log_path.open("wb") as log_handle:
                process = subprocess.Popen(command, stdout=log_handle, stderr=subprocess.STDOUT)
            result = watch(
                WatchSpec(
                    pid=process.pid,
                    status_path=status_path,
                    exit_path=exit_path,
                    activity_paths=(log_path,),
                    poll_seconds=0.01,
                    stall_seconds=2,
                    run_id="unit-test",
                )
            )
            process.wait(timeout=2)
            self.assertEqual(result["state"], "succeeded")
            self.assertEqual(result["exit_code"], 0)
            self.assertFalse(result["behavioral_content_inspected"])


if __name__ == "__main__":
    unittest.main()
