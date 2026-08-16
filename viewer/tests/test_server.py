"""Server and bundle tests: API basics and one-command launch sanity."""

from __future__ import annotations

import json
import os
import threading
import urllib.request
from pathlib import Path

import pytest

from archipelago_viewer.server import ViewerHandler, main as server_main

BUNDLE = Path(__file__).resolve().parent.parent / "demo" / "index.json"


@pytest.fixture(scope="module")
def demo_server() -> str:
    if not BUNDLE.is_file():
        pytest.skip("demo bundles not baked")
    from http.server import ThreadingHTTPServer  # re-import to bind fixture

    sources = [Path(__file__).resolve().parent.parent.parent / "results"]
    ViewerHandler.sources = [s.resolve() for s in sources if s.exists()]
    server = ThreadingHTTPServer(("127.0.0.1", 0), ViewerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.read()


def test_index_served(demo_server: str) -> None:
    assert b"Archipelago" in _get(f"{demo_server}/")


def test_demos_api(demo_server: str) -> None:
    data = json.loads(_get(f"{demo_server}/api/demos"))
    assert data["demos"], "baked demos expected"
    names = {entry["slug"] for entry in data["demos"]}
    assert "h1-runtime-turnover" in names


def test_demo_bundle_served(demo_server: str) -> None:
    data = json.loads(_get(f"{demo_server}/api/demo/h1-runtime-turnover"))
    assert data["schema_version"].startswith("archipelago-viewer-bundle")
    assert data["replay"]["sequences"]
    assert data["episode"]["schema_version"] == "archipelago-viewer-episode/v1"


def test_asset_served(demo_server: str) -> None:
    content = _get(f"{demo_server}/assets/lab/floor_plain.png")
    assert content.startswith(b"\x89PNG\r\n\x1a\n")


def test_asset_traversal_rejected(demo_server: str) -> None:
    import urllib.error

    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(f"{demo_server}/assets/../web/index.html")
    assert exc.value.code == 404


def test_source_api_includes_scene_projection(demo_server: str) -> None:
    sources_data = json.loads(_get(f"{demo_server}/api/sources"))
    if not sources_data["sources"]:
        pytest.skip("no sources available for source api test")
    first_rel = sources_data["sources"][0]["rel"]
    encoded_rel = urllib.parse.quote(first_rel)
    bundle = json.loads(_get(f"{demo_server}/api/source?path={encoded_rel}"))
    assert "scene" in bundle
    assert bundle["schema_version"] == "archipelago-viewer-bundle/v2"


def test_source_api_rejects_traversal(demo_server: str) -> None:
    import urllib.error

    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(f"{demo_server}/api/source?path=..%2F..%2Fetc%2Fpasswd")
    assert exc.value.code == 404


def test_unknown_route_404(demo_server: str) -> None:
    import urllib.error

    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(f"{demo_server}/api/nope")
    assert exc.value.code == 404