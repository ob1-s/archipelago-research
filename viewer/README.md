# Archipelago trajectory viewer

A read-only, deterministic replay surface for Archipelago agent-rollout
traces. Traces are parsed into a generic episode schema, reduced into a
position-based "town" replay (AI-town-style), and served as a local web app.

The viewer never modifies data. Every event carries verbatim payloads from
the source; nothing is invented during parsing or rendering.

## Quick start

Requires Python 3.10+ (stdlib only) and any modern browser.

```bash
cd viewer

# 1. Bake the demo bundles (reads sources under ../results and ../docs)
python3 -m archipelago_viewer.bake --repo-root ..

# 2. Serve the web app (demo list + live source browser)
python3 -m archipelago_viewer.server        # http://127.0.0.1:8777
```

Open http://127.0.0.1:8777 — the five baked demos appear in the dropdown.

Reproducible builds: set `VIEWER_REPRO_TIME` (ISO timestamp) to pin the
`generated_at` fields so identical sources produce byte-identical bundles.

## Layout

```
viewer/
  archipelago_viewer/
    schema.py        # generic episode schema (ViewerEpisode/Event/Agent/...)
    util.py          # deterministic ids, hashing, now_utc(), text folding
    adapters/        # probe-based format adapters (verifiers, H1 runtime, corpus)
    reduce.py        # deterministic reducer: episode -> position replay
    bake.py          # CLI: build demo bundles from real sources
    server.py        # stdlib HTTP server: demos, sources, static web/
  web/               # single-page canvas app (no frameworks, no build)
  demo/              # baked bundles + index.json
  assets/            # CC0 sprite reference material (see ASSET_LICENSES.md)
  tests/             # pytest suite (sources optional; skipped when absent)
  docs/              # architecture + semantics + screenshots
```

## Browsing arbitrary sources

The `Sources` control in the top bar opens the live source browser backed by
`/api/sources` + `/api/source?path=...`. It lists trace files under the repo
`results/` and `outputs/` trees and adapts them on the fly; the path must
resolve inside the configured roots (traversal is rejected).

## Tests

```bash
cd viewer
VIEWER_REPRO_TIME=2026-08-16T00:00:00+00:00 python3 -m pytest tests/ -q
```

Adapter tests run against real traces when present in the parent repo, and
skip cleanly otherwise. All determinism tests compare full bundle JSON.

## License notes

`assets/` contains third-party CC0 art (Kenney Tiny Town) — see
`assets/ASSET_LICENSES.md`. Everything else in this directory is original
code. No AI Town or other proprietary assets are used.