"""Four simultaneous real subprocess-MCP schema registrations."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

MODULE = "cross_rollout_postcommitment_evidence_threshold_transport_v1.servers.facility"
PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _launch_server(tmp_path: Path, index: int) -> subprocess.Popen[str]:
    port_file = tmp_path / f"mcp-{index}.port"
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
    return subprocess.Popen(
        [sys.executable, "-u", "-m", MODULE],
        cwd=PACKAGE_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_port(process: subprocess.Popen[str], port_file: Path) -> int:
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline and process.poll() is None:
        if port_file.exists():
            candidate = int(port_file.read_text())
            try:
                with socket.create_connection(("127.0.0.1", candidate), timeout=0.2):
                    return candidate
            except OSError:
                pass
        time.sleep(0.05)
    stderr = process.stderr.read() if process.stderr is not None else ""
    raise AssertionError(
        f"MCP server did not bind; returncode={process.returncode}\n{stderr}"
    )


async def _list_tools(url: str):
    async with (
        streamable_http_client(url) as (read_stream, write_stream, _),
        ClientSession(
            read_stream,
            write_stream,
            read_timeout_seconds=timedelta(seconds=30),
        ) as session,
    ):
        await session.initialize()
        return await session.list_tools()


async def _list_all_tools(ports: list[int]):
    return await asyncio.gather(
        *[_list_tools(f"http://127.0.0.1:{port}/mcp") for port in ports]
    )


def test_four_simultaneous_subprocess_mcp_servers_are_isolated(tmp_path: Path) -> None:
    processes = [_launch_server(tmp_path, index) for index in range(4)]
    try:
        ports = [
            _wait_port(process, tmp_path / f"mcp-{index}.port")
            for index, process in enumerate(processes)
        ]
        assert len(set(ports)) == 4
        results = asyncio.run(_list_all_tools(ports))
        for listed in results:
            names = {tool.name for tool in listed.tools}
            assert len(names) == 2
            select = next(
                tool for tool in listed.tools if tool.name.endswith("select_policy")
            )
            assert select.inputSchema["properties"]["policy"] == {
                "title": "Policy",
                "type": "string",
            }
            serialized = json.dumps(select.inputSchema)
            assert "enum" not in serialized and "oneOf" not in serialized
            assert all(label not in serialized for label in ("K", "M"))
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5.0)
            if process.stderr is not None:
                process.stderr.close()
