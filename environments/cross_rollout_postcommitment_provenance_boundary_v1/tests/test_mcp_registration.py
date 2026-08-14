"""Real subprocess-MCP schema registration checks."""

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

from cross_rollout_postcommitment_provenance_boundary_v1.constants import (
    RELEASE_DESCRIPTION,
    SELECT_DESCRIPTION,
)

MODULE = "cross_rollout_postcommitment_provenance_boundary_v1.servers.facility"
PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_real_subprocess_mcp_schema_is_string_only_and_label_free(tmp_path: Path) -> None:
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
                f"MCP server did not bind; returncode={process.returncode}\n{stderr}"
            )
        listed = asyncio.run(_list_tools(f"http://127.0.0.1:{port}/mcp"))
        tools = {tool.name: tool for tool in listed.tools}
        select = next(tool for name, tool in tools.items() if name.endswith("select_policy"))
        release = next(tool for name, tool in tools.items() if name.endswith("release_resource"))
        assert set(tools) == {select.name, release.name}
        assert select.description == SELECT_DESCRIPTION
        assert release.description == RELEASE_DESCRIPTION
        schema = select.inputSchema
        assert schema["properties"]["policy"] == {"title": "Policy", "type": "string"}
        serialized = json.dumps(schema)
        assert "enum" not in serialized
        assert "oneOf" not in serialized
        assert not any(label in serialized for label in ("K", "M"))
        assert not any(label in select.description for label in ("K", "M"))
        assert not any(label in release.description for label in ("K", "M"))
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
