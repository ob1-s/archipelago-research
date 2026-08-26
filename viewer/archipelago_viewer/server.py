"""Zero-dependency local viewer server (stdlib http.server only).

Serves the static web UI plus:
  GET /api/demos                -> demo index (baked bundles)
  GET /api/demo/<slug>          -> one baked bundle
  GET /api/sources              -> source files found under --sources roots
  GET /api/source?path=<rel>    -> adapt+reduce a source file on the fly

The server is read-only: it never writes to sources.  Baked demos are served
from the viewer/demo directory.  ``--sources`` roots restrict which files may
be adapted at runtime (path traversal is rejected).
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .adapters import AdapterError, load_episodes
from .reduce import replay_json, reduce
from .schema import ViewerEpisode

VIEWER_ROOT = Path(__file__).resolve().parent.parent / "web"
DEMO_ROOT = Path(__file__).resolve().parent.parent / "demo"

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
}


class ViewerHandler(BaseHTTPRequestHandler):
    sources: list[Path] = []
    server_version = "ArchipelagoViewer/0.1"

    # ------------------------------------------------------------- helpers

    def _send(self, status: int, content: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, status: int, data: object) -> None:
        self._send(
            status,
            json.dumps(data, sort_keys=True).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _resolve_source(self, rel: str) -> Path | None:
        candidate = Path(urllib.parse.unquote(rel))
        if candidate.is_absolute():
            return None
        for root in self.sources:
            target = (root / candidate).resolve()
            if target.is_file() and target.is_relative_to(root.resolve()):
                return target
        return None

    # ------------------------------------------------------------- routing

    def do_GET(self) -> None:  # noqa: N802 (stdlib hook name)
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            self._api(path[len("/api/") :])
            return
        if path in ("/", ""):
            path = "/index.html"
        file_path = (VIEWER_ROOT / path.lstrip("/")).resolve()
        if not file_path.is_relative_to(VIEWER_ROOT.resolve()) or not file_path.is_file():
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        content_type = CONTENT_TYPES.get(
            file_path.suffix.lower(), "application/octet-stream"
        )
        self._send(200, file_path.read_bytes(), content_type)

    def _api(self, route: str) -> None:
        try:
            if route == "demos":
                index_path = DEMO_ROOT / "index.json"
                if index_path.is_file():
                    self._send_json(200, json.loads(index_path.read_text()))
                else:
                    self._send_json(200, {"demos": []})
            elif route.startswith("demo/"):
                slug = route[len("demo/") :]
                bundle = DEMO_ROOT / f"{slug}.replay.json"
                if not bundle.is_file():
                    self._send_json(404, {"error": f"no demo {slug!r}"})
                    return
                self._send(200, bundle.read_bytes(), "application/json; charset=utf-8")
            elif route == "sources":
                found: list[dict[str, str]] = []
                for root in self.sources:
                    for file_path in sorted(root.rglob("*")):
                        if not file_path.is_file():
                            continue
                        if file_path.suffix.lower() not in (".json", ".jsonl", ".gz"):
                            continue
                        rel = file_path.relative_to(root.resolve())
                        try:
                            load_episodes(str(file_path), limit=1)
                            found.append(
                                {
                                    "root": str(root),
                                    "rel": str(rel),
                                    "size": file_path.stat().st_size,
                                }
                            )
                        except AdapterError:
                            continue
                self._send_json(200, {"sources": found})
            elif route.startswith("source?"):
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                rel = (query.get("path") or [""])[0]
                target = self._resolve_source(rel)
                if target is None:
                    self._send_json(404, {"error": f"source not allowed: {rel!r}"})
                    return
                limit_raw = (query.get("limit") or [""])[0]
                limit = int(limit_raw) if limit_raw.isdigit() else None
                group_mode = (query.get("group") or ["community"])[0]
                try:
                    episodes = load_episodes(
                        str(target), limit=limit, group_mode=group_mode
                    )
                    if not episodes:
                        self._send_json(404, {"error": "no episodes in source"})
                        return
                    episode = episodes[0]
                    if isinstance(episode, list):
                        episode = episode[0]
                    assert isinstance(episode, ViewerEpisode)
                    self._send_json(200, json.loads(replay_json(episode, reduce(episode))))
                except (AdapterError, AssertionError) as exc:
                    self._send_json(400, {"error": str(exc)})
            else:
                self._send_json(404, {"error": f"unknown api route {route!r}"})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # noqa: BLE001 - report, keep serving
            try:
                self._send_json(500, {"error": f"{type(exc).__name__}: {exc}"})
            except (BrokenPipeError, ConnectionResetError):
                pass

    def log_message(self, fmt: str, *args: object) -> None:  # noqa: A003
        # quiet by default; keep access noise out of demos
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument(
        "--sources",
        action="append",
        default=[],
        help="root directory whose trace files may be adapted at runtime",
    )
    args = parser.parse_args(argv)

    sources = []
    for raw in args.sources:
        path = Path(raw).expanduser().resolve()
        if path.is_dir():
            sources.append(path)
    if not sources:
        repo = Path(__file__).resolve().parent.parent.parent
        for candidate in ("results", "outputs"):
            if (repo / candidate).is_dir():
                sources.append((repo / candidate).resolve())

    ViewerHandler.sources = sources
    server = ThreadingHTTPServer((args.host, args.port), ViewerHandler)
    url = f"http://{args.host}:{args.port}"
    print(f"Archipelago trajectory viewer: {url}")
    print(f"  demos:    {DEMO_ROOT}")
    for root in sources:
        print(f"  sources:  {root} (runtime adapt only)")
    print("  ctrl-c to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())