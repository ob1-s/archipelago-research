"""Real subprocess-MCP registration and serialized schema tests."""

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

import pytest
from cross_rollout_phase1_label_attractor_diagnostic_v1.constants import (
    RELEASE_DESCRIPTION,
    SELECT_DESCRIPTION,
    expected_schema_enum,
)
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MODULE = "cross_rollout_phase1_label_attractor_diagnostic_v1.servers.facility"


@pytest.mark.parametrize("variant", ["AB_A", "AB_B", "KM_K", "KM_M"])
def test_real_mcp_registers_the_expected_schema(
    tmp_path: Path, variant: str
) -> None:
    port_file = tmp_path / f"mcp-{variant}.port"
    env = os.environ.copy()
    env.update(
        {
            "MCP_HOST": "127.0.0.1",
            "MCP_PORT": "0",
            "MCP_PORT_FILE": str(port_file),
            "VF_CONFIG": json.dumps(
                {"variant": variant, "colocated": False, "runtime": {"type": "subprocess"}}
            ),
            "PYTHONUNBUFFERED": "1",
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-u", "-m", MODULE],
        cwd=PACKAGE_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    port: int | None = None
    deadline = time.monotonic() + 10.0
    try:
        while time.monotonic() < deadline and process.poll() is None:
            if port_file.exists():
                candidate = int(port_file.read_text())
                try:
                    with socket.create_connection(("127.0.0.1", candidate), timeout=0.2):
                        port = candidate
                        break
                except OSError:
                    pass
            time.sleep(0.05)
        if port is None:
            _, stderr = process.communicate(timeout=2.0)
            raise AssertionError(
                f"MCP server {variant} did not bind; returncode={process.returncode}\n{stderr}"
            )
        listed = asyncio.run(_list_tools(f"http://127.0.0.1:{port}/mcp"))
        tools = {tool.name: tool for tool in listed.tools}
        select = next(tool for name, tool in tools.items() if name.endswith("select_policy"))
        release = next(tool for name, tool in tools.items() if name.endswith("release_resource"))
        assert select.description == SELECT_DESCRIPTION
        assert release.description == RELEASE_DESCRIPTION
        assert select.inputSchema["properties"]["policy"]["enum"] == expected_schema_enum(variant)
        assert set(tools) == {
            select.name,
            release.name,
        }
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3.0)
        if process.stderr is not None:
            process.stderr.close()


async def _list_tools(url: str):
    async with streamable_http_client(url) as (
        read_stream,
        write_stream,
        _,
    ), ClientSession(
        read_stream,
        write_stream,
        read_timeout_seconds=timedelta(seconds=30),
    ) as session:
        await session.initialize()
        return await session.list_tools()
