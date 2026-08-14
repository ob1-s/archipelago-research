"""Regression coverage for the real subprocess MCP registration path."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MODULE = "cross_rollout_postcommitment_evidence_relative_v1.servers.facility"


def test_real_mcp_subprocess_registers_tool_schema(tmp_path: Path) -> None:
    port_file = tmp_path / "mcp.port"
    env = os.environ.copy()
    env.update(
        {
            "MCP_HOST": "127.0.0.1",
            "MCP_PORT": "0",
            "MCP_PORT_FILE": str(port_file),
            "VF_CONFIG": json.dumps(
                {"colocated": False, "runtime": {"type": "subprocess"}}
            ),
            "PYTHONUNBUFFERED": "1",
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-u", "-m", MODULE],
        cwd=PACKAGE_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    connected = False
    deadline = time.monotonic() + 10.0
    try:
        while time.monotonic() < deadline and process.poll() is None:
            if port_file.exists():
                port = int(port_file.read_text())
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        connected = True
                        break
                except OSError:
                    pass
            time.sleep(0.05)

        if not connected:
            stdout, stderr = process.communicate(timeout=2.0)
            raise AssertionError(
                "real MCP server did not reach a listening state after schema "
                f"registration; returncode={process.returncode}\n"
                f"stdout:\n{stdout}\nstderr:\n{stderr}"
            )
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3.0)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
