"""Bake demo bundles: source -> ViewerEpisode -> replay document -> demo JSON.

Usage:
    python3 -m archipelago_viewer.bake [--out viewer/demo] [--limit N]

Reads only; writes only under the bundle output directory.  Each demo is a
single deterministic JSON file (``<id>.replay.json``) containing the episode
and the full replay document, plus an ``index.json`` listing the demos.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters import load_episodes
from .reduce import replay_json, reduce
from .schema import ViewerEpisode

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "demo"

DEMO_SOURCES: list[dict[str, str]] = [
    {
        "slug": "verifiers-policy-baseline",
        "title": "verifiers · policy baseline rollouts (community)",
        "path": "results/cross-rollout-policy-v1-luna-qualification-2026-08-12/baseline/traces.jsonl",
        "group_mode": "community",
        "limit": "12",
    },
    {
        "slug": "verifiers-policy-culture-b",
        "title": "verifiers · culture-B artifact inheritance (community)",
        "path": "results/cross-rollout-policy-v1-culture-b-2026-08-12/culture-b/traces.jsonl",
        "group_mode": "community",
        "limit": "12",
    },
    {
        "slug": "verifiers-postcommitment-single",
        "title": "verifiers · postcommitment phase1→phase2 (single rollout)",
        "path": "results/cross-rollout-postcommitment-v1-luna-qualification-2026-08-12/batch-1-60/traces.jsonl",
        "group_mode": "one",
        "limit": "1",
    },
    {
        "slug": "h1-runtime-turnover",
        "title": "H1 live-runtime mechanical turnover (signed record)",
        "path": "docs/h1_live_runtime_adapter_2026-08-15/RUNTIME_BOUNDARY_STATE.json",
        "group_mode": "n/a",
        "limit": "",
    },
    {
        "slug": "pre-framework-corpus",
        "title": "pre-framework conversation corpus (tree lineage)",
        "path": "docs/pre_framework_snapshot_2026-08-15/VISIBLE_HISTORICAL_CORPUS.jsonl",
        "group_mode": "n/a",
        "limit": "220",
    },
]


def bake_one(
    spec: dict[str, str],
    repo_root: Path,
    out_dir: Path,
    skip_missing: bool = True,
) -> dict[str, object] | None:
    source_path = repo_root / spec["path"]
    if not source_path.is_file():
        if skip_missing:
            return None
        raise FileNotFoundError(source_path)
    limit = int(spec["limit"]) if spec.get("limit") else None
    group_mode = spec.get("group_mode", "community")
    if group_mode == "n/a":
        group_mode = "community"
    episodes = load_episodes(str(source_path), limit=limit, group_mode=group_mode)
    if not episodes:
        return None
    episode = episodes[0]
    if isinstance(episode, list):
        episode = episode[0]
    if not isinstance(episode, ViewerEpisode):
        raise TypeError(f"unexpected episode type {type(episode)}")
    document = reduce(episode)
    out_path = out_dir / f"{spec['slug']}.replay.json"
    out_path.write_text(replay_json(episode, document), encoding="utf-8")
    return {
        "slug": spec["slug"],
        "title": episode.title,
        "id": episode.id,
        "source": episode.source,
        "source_kind": episode.source_kind,
        "environment": episode.environment,
        "model": episode.model,
        "events": len(episode.events),
        "agents": len(episode.agents),
        "artifacts": len(episode.artifacts),
        "carriers": len(episode.carriers),
        "bytes": out_path.stat().st_size,
        "file": out_path.name,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parent.parent.parent)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    index: list[dict[str, object]] = []
    for spec in DEMO_SOURCES:
        entry = bake_one(spec, args.repo_root, args.out)
        if entry is None:
            print(f"skip: {spec['slug']} (source missing)", file=sys.stderr)
            continue
        index.append(entry)
        print(f"baked: {entry['slug']} -> {entry['file']} ({entry['events']} events)")
    (args.out / "index.json").write_text(
        json.dumps({"demos": index}, sort_keys=True, indent=2), encoding="utf-8"
    )
    print(f"index written: {args.out / 'index.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())