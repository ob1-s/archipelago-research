# Supported semantics

This file documents which source facts the viewer can surface, and how they
map to event kinds, town rendering, and panels. It is a *capability map*,
not a promise about any particular trace: absent fields simply produce no
event (nothing is invented).

## Event kinds

| Kind                   | Meaning                                   | Group      |
| ---------------------- | ----------------------------------------- | ---------- |
| `user_message`         | human/system user message node            | message    |
| `assistant_message`    | assistant message node (incl. tool calls) | message    |
| `tool_call` / `tool_result` | tool invocation and its result        | tool       |
| `system_message`       | system node                               | message    |
| `provider_request`     | model call (model, endpoint, usage, time) | provider   |
| `artifact_write`       | artifact write recorded by the harness    | artifact   |
| `artifact_read`        | artifact read recorded by the harness     | artifact   |
| `carrier_activate`     | carrier came online                        | carrier    |
| `carrier_finalize`     | carrier transferred / finalized           | carrier    |
| `carrier_read`         | signed read through a carrier             | carrier    |
| `spawn` / `teardown`   | lifecycle events (H1 runtime journal)     | lifecycle  |
| `authorization_revoked`| gate/token revocation (H1)                | lifecycle  |
| `phase`                | phase boundary (exposure/transition)      | info       |
| `reward` / `metric`    | reward & metric records                   | outcome    |
| `stop`                 | trace end (stop condition, ok, errors)    | outcome    |
| `info`                 | verbatim structured state (phase machine, policy transmission, ...) | info |

Unknown kinds fall into the `info` group and remain fully inspectable.

## Source formats

### verifiers v1 `traces.jsonl`

One Episode per line, each with an ordered `traces[]` list sharing clock
base. Semantics surfaced:

- message nodes (`role`, `content`, `reasoning_content`, `tool_calls`);
- model calls (`calls`: model, endpoint, finish reason, usage, time) — as
  `provider_request`;   assay arrays in `trace.info` whose records have a
  node `index` are interleaved into the node timeline (read/write records
  become artifact events, others become `info`);
- `reward`/`metrics` at trace end; `stop` with stop condition;
- phase exposure / transition recorded by the harness
  (`exposure_event_index`, `transition`) — `phase` events positioned at the
  exact node time;
- postcommitment phase machine (`info.postcommitment_policy`) — verbatim
  `info` event (assignment stage, phase1/2 policy and success, transition);
- artifact inheritance (`info.policy_transmission`) — verbatim `info`
  event; when the harness recorded `first_artifact_read_index`, a
  positioned `artifact_read` event is emitted at that node time;
- episode-level facts → `meta` (condition, run id, rewards, timing, ok).

Community mode: all rollout traces in a file become one town, one agent per
rollout. One mode: each trace is a standalone episode (`limit` applies).

### H1 live runtime record (`RUNTIME_BOUNDARY_STATE.json`)

The signed runtime boundary state becomes a whole episode:

- journal rows in `lifecycle_events` → `spawn` / `teardown` /
  `authorization_revoked` in journal order;
- teardown evidence is matched by `runtime_process_id` where referenced;
- `carrier_records` → carrier artifacts plus `carrier_finalize` and signed
  `carrier_read` events (writer/reader from signed claims);
- canary / network probe / provider request actions (or retry attempts)
  → provider events with verbatim payloads;
- `gate_results`, `status`, `authorized_to_run_h1`, `live_model_calls`,
  `record_hash`, boundary assessment → `meta`;
- the boundary `controller` agent visits the town as an actor.

### Pre-framework corpus (`VISIBLE_HISTORICAL_CORPUS.jsonl`)

- every row → one user/assistant message event;
- timestamps from real `create_time`, offset to episode start;
- the full turn tree (`parent`, `children`, `role`, `content_type`,
  `metadata`) is kept verbatim in the event payload so lineage is
  inspectable event-per-event;
- `t` monotonic per episode (offsets), letting the town walk the
  conversation.

## Town rendering

- **Plaza** — fixed center; the "start" of every iteration.
- **Facilities** — one labeled building per artifact kind (workshop,
  library, hub, ...); files/notes land here.
- **Artifacts** — per-kind glyphs (scroll, chest, box, letter, seed,
  files, gear); created from writes, retained while "live".
- **Carriers** — dashed animated lines between agents with arrowheads,
  provider carriers in a distinct color; active only while they exist.
- **Agents** — one body per agent on the plaza ring; generation rings
  drawn from lineage; busy glyph while a tool call is current; effects for
  spawn/teardown/artifact transitions.
- **Timeline scrubber** — dots per event (densely sampled), click to seek.

## Determinism & integrity

- Same source bytes + same `VIEWER_REPRO_TIME` → byte-identical bundles.
- Layouts are seeded by episode id, never by wall clock.
- `validate()` rejects dangling agent references and out-of-order seq.
- Screenshots in `docs/screenshots/` are generated headless against the
  live app and are simple PNGs of real renders, not mockups.