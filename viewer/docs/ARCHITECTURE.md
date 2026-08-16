# Architecture

The viewer is a pure pipeline with no shared mutable state:

```
source file ──> Adapter (probe-selected) ──> ViewerEpisode (schema)
                                               │
                                        reduce()  (deterministic)
                                               │
                                        replay bundle (JSON)
                                               │
                              server (stdlib HTTP) ──> web app (canvas)
```

## Layers

### 1. Schema (`schema.py`)

`ViewerEpisode` is the generic interchange format:

- `episode.id` — stable, content-derived (hash of source path + source id).
- `agents` — one `ViewerAgent` per participating agent; carries lineage
  (`parent_id`, `generation`), role, and verbatim attributes.
- `artifacts` — typed records (kind, title, payload); created only from
  real write events.
- `carriers` — carrier records (kind, `artifact_ids`, from/to agent ids).
- `events` — a flat, `seq`-ordered event stream. Each event has a `kind`,
  a timestamp `t`, `title`, `detail`, optional `agent_id`, and a `payload`
  that is *always verbatim source material* (never synthesized).
- `meta` — episode-level facts verbatim from the source (condition, run id,
  rewards, timing, gate status, ...).

`VIEWER_SCHEMA_VERSION = "archipelago-viewer-episode/v1"` stamps every
episode. `validate()` checks ordering and referential integrity and is
covered by tests.

Event kinds are grouped by `EVENT_KINDS` into: message, tool, lifecycle,
provider, artifact, carrier, outcome, info. The UI maps each group to a
color; the schema is open for new kinds (unknown kinds map to "info").

### 2. Adapters (`adapters/`)

One adapter per source format, selected by *probe* (`can_load`), never by
extension alone:

- `verifiers_jsonl.py` (`VerifiersTracesAdapter`) — verifiers v1
  `traces.jsonl` files: message nodes → user/assistant/tool events; model
  calls → `provider_request`; assay arrays keyed by node index →
  interleaved info/artifact events; reward/metrics/stop at trace end.
  `group_mode="community"` groups many rollout traces into one town (one
  agent per trace); `"one"` keeps each trace as its own episode.
  Phase-machine state (`postcommitment_policy`) and artifact-inheritance
  metadata (`policy_transmission`) are reported as verbatim `info` events;
  a harness-recorded `first_artifact_read_index` becomes a positioned
  `artifact_read` event at that exact node timestamp.
- `runtime_state.py` (`RuntimeBoundaryAdapter`) — the H1 live-runtime
  signed record (`RUNTIME_BOUNDARY_STATE.json`): lifecycle journal rows →
  spawn/teardown/authorization_revoked events in journal order; carrier
  records → carrier artifacts + finalize/read events; canary/network/probe
  provider actions → events; gates/status/record_hash → meta. A
  `controller` agent (assistant role) is derived from the boundary state.
- `corpus.py` (`PreFrameworkCorpusAdapter`) — pre-framework turn trees
  (`VISIBLE_HISTORICAL_CORPUS.jsonl`): each row → one user/assistant
  message event with the verbatim tree in the payload (`parent`, `children`,
  etc.); timestamps are the real `create_time` offsets.

Adapter invariants (enforced by tests):

- events are emitted in strictly increasing `seq`;
- payloads are verbatim slices of the source;
- no event or fact is synthesized when a field is absent
  (`test_missing_artifacts_never_invented`);
- parsing is deterministic for identical bytes and `VIEWER_REPRO_TIME`.

### 3. Reducer (`reduce.py`)

Pure function `reduce(episode) -> replay`:

- positions are purely presentational: a plaza at the center, facilities
  around a ring (`agent_ring_radius`), agents on the ring, artifacts at
  facility lots by kind, carriers between agents;
- deterministic fixed seeds (`NamedHash`), so the same episode always
  reduces to the same layout;
- per-event `sequences` snapshots (event count + 1), including initial,
  with alive/dead, generation, artifact created/live, carrier
  active/from/to;
- lineage: `generation` from `parent_id` chains; `turnover_seq` is set
  only when a spawn follows a teardown of the same lineage
  (`spawn_after_teardown`);
- the bundle (`replay_json`) is self-contained JSON:
  `{schema_version, episode, replay}`.

### 4. Server (`server.py`)

Stdlib `ThreadingHTTPServer`:

- `GET /` — the web app;
- `GET /api/demos` — index of baked bundles;
- `GET /api/demo/<slug>` — full bundle;
- `GET /api/sources` — discoverable trace files under repo roots;
- `GET /api/source?path=&limit=&group=` — adapt a file on the fly
  (path traversal rejected via realpath containment).

Read-only by construction: no mutation endpoints exist.

### 5. Web app (`web/`)

No build step, no frameworks. `app.js` renders the current snapshot
deterministically onto one canvas: grass, plaza, facilities with signs,
artifact icons (one per kind), agents as colored bodies with generation
rings and busy glyphs, animated dashed carrier transfers with arrowheads,
spawn/teardown/artifact effects, selection + hover hit-testing. Panels:
demo/source picker, transport bar (play/pause, step, scrubber with event
markers, speed), agent list with alive/dead and lineage, filterable event
log, inspector showing verbatim payloads. Deep links: `#demo=<slug>[&seq=N]`.
Keyboard: space (play/pause), arrows + shift for fine stepping, Home/End.

All randomness is derived from `hashStr()` seeds — re-rendering the same
bundle at the same `seq` reproduces the same frame, which matters for
screenshots and for comparing runs.

## Reproducibility

- `VIEWER_REPRO_TIME` pins `generated_at` in adapters and bake.
- Determinism is asserted on the *full bundle JSON string* (not just
  positions) in `test_reduce_is_deterministic` and
  `test_policy_baseline_adapter_is_deterministic`.

## Non-goals

- No scientific claims: a replay is a visualization aid, never evidence.
  The raw trace files remain the canonical source of truth.
- No editing, no write-back, no server-side state beyond serving files.