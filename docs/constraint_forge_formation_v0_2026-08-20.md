# Constraint Forge V0: Predecessor Formation Prototype

Date: 2026-08-20  
World version: `constraint-forge/world-v0`  
Protocol version: `constraint-forge/exploration-v0`  
Status: **implementation specification; predecessor-only exploratory assay**  
Scientific status: **not H1, not a turnover experiment, not confirmatory evidence**

## 1. Purpose

V0 asks only whether Constraint Forge is worth promoting to a frozen formation
assay. It must answer three empirical questions:

1. Do independent predecessor dyads naturally form at least two stable,
   structurally meaningful coordination routines?
2. Do predecessors voluntarily retain role-local sensorimotor films for their
   own later jobs, and is the selected rack functionally useful relative to an
   empty view?
3. Can the observed procedural differences be represented by a small set of
   deterministic, intervention-grounded fields rather than by stylistic
   biometrics or an LLM judge?

V0 contains no successors, no active-population turnover, no carrier
transplantation, no donor matching, and no H1 claim. A positive V0 authorizes
development of `formation-assay-v0`; it does not authorize H1 execution.

## 2. Non-negotiable boundaries

### 2.1 Frozen H1 apparatus

Implementation is additive. It must create a new native `verifiers.v1`
environment package and must not modify, copy-edit, or silently specialize the
frozen H1 runtime or model-free apparatus, including:

- `environments/h1_live_runtime_adapter_v1/`
- `environments/h1_model_free_apparatus_v1/`
- `docs/h1_live_runtime_adapter_2026-08-15/`
- `docs/h1_model_free_apparatus_2026-08-15/`

Constraint Forge must consume qualified public boundaries as they exist. An
incompatibility is a blocker; it is not authorization to alter those packages.
The implementation handoff must show a zero diff for every frozen path.

The existing runtime establishes only its documented mechanical boundary. V0
must not reinterpret a runtime qualification metric as behavioral evidence.

### 2.2 No silent rescue

The following are frozen for one V0 attempt once model inference begins:

- world generator and visible instructions;
- action and observation APIs;
- round, write, and mutation budgets;
- rack capacity and film format;
- job and intervention schedule;
- cohort size and eligibility rules;
- deterministic reference policies and preflight gates;
- exploratory progression and kill rules.

If a preflight or formation gate fails, execution stops and produces a failure
report. The implementation must not, without an explicitly authorized new
world version:

- prompt a dyad to try another strategy;
- seed different lineages with different hints;
- add bandwidth, rounds, memory, demonstrations, or feedback;
- loosen a gate or redefine competence;
- discard unattractive behavioral runs;
- add replacement dyads or reroll seeds;
- select only the prettiest lineages;
- change physics and rerun under the V0 name.

Infrastructure recovery may use the already-qualified retry semantics only
when it preserves the exact, already-active actor lifecycle and provider
session identity for both X and Y. Retrying transport within that same session
is permitted. Any recovery that would terminate, reinstantiate, replace,
relabel, or open a fresh session for either predecessor immediately aborts the
dyad and the V0 cohort attempt as an infrastructure failure. Its partial data
remain audit-only: they are not behavioral data, no formation gate is
evaluated, no replacement actor or dyad is inserted, and no later attempt may
splice in its events or rack state. Behavioral failure is never an
infrastructure retry.

### 2.3 Endogenous behavior

The environment rewards task completion only. It never rewards routine
diversity, retention, lineage distinctiveness, a particular communication
pattern, or agreement with a researcher-defined routine.

Model-facing role and action language uses only neutral terms: `station X`,
`station Y`, `item`, `target`, `register`, `symbol`, `write`, `set`, `unset`,
`finish`, `wait`, `retain`, `evict`, and `keep unchanged`. It must not use
`leader`, `sender`, `receiver`, `encoder`, `checker`, `arm`, `latch`,
`challenge`, `ACK`, `NACK`, `rollback`, `batch`, `protocol`, `teach`,
`successor`, or `inheritance`.

## 3. Unit of observation and phase boundary

One independent lineage is one independently initialized X/Y predecessor dyad
plus its two role-local rack histories. Jobs, actions, films, and probe
responses nested within a dyad are not independent samples. This scientific
unit does not prescribe runtime trace granularity; the frozen execution layer's
existing trace/session mapping remains unchanged.

There are two separate data regimes:

1. **Exploration V0:** trajectories may be inspected to discover procedural
   structure. No H1 scoring follows from this cohort.
2. **Future formation validation:** all probes, response fields, enum values,
   precedence/factorization rules, thresholds, normalization, and donor
   eligibility must be frozen as a versioned `formation-assay-v0` before a
   fresh predecessor cohort is sampled.

If validation data cause any substantive assay change, those data become
development data. The changed assay receives a new version and requires
another fresh cohort.

## 4. World physics

### 4.1 One job

Each job contains six neutral items and six neutral targets. Both stations must
privately construct the same one-to-one assignment.

- Station X privately observes binary compatibility mask `P`.
- Station Y privately observes binary compatibility mask `Q`.
- A pair `(item, target)` is globally valid exactly when it occurs in both
  masks.
- `P ∩ Q` contains exactly one perfect matching.
- Each private mask alone admits multiple perfect matchings.

Success requires both stations' final layers to encode the unique matching in
`P ∩ Q`. Neither station receives the other mask.

### 4.2 Deterministic seeded generator

For `n = 6`, generate one randomized one-factorization of the complete
bipartite graph:

1. From the job seed, sample independent permutations `rho` over item IDs and
   `sigma` over target IDs.
2. Define six edge-disjoint perfect matchings
   `M_f = {(rho(i), sigma((i + f) mod 6)) : i in 0..5}`.
3. Sample one target factor `f*` uniformly.
4. Uniformly partition four of the five remaining factors into two X decoys
   and two Y decoys; the fifth is unused.
5. Set `P` to the union of the target factor and X's two decoys.
6. Set `Q` to the union of the target factor and Y's two decoys.
7. Randomize presentation order. Do not expose factor identifiers or generator
   internals to either station.

This construction gives each station an 18-edge, degree-three private graph.
The X and Y masks share exactly the six target edges.

Every generated job must pass model-free validation:

- `P ∩ Q` is exactly one perfect matching;
- both `P` and `Q` contain at least three perfect matchings;
- visible item and target identifiers are unique and complete;
- the seed reproduces the complete immutable job record;
- no job is duplicated within or across V0 dyads.

Before live inference, a generator-aware solo screen must test whether either
private view reveals a high-probability answer through generator bias. Merely
counting local matchings is insufficient. Section 9 defines the gate.

### 4.3 Public and private state

At job start, each station receives its full role-local rack unless the job is
a rack-occlusion probe. At the start of every round, each station receives:

- its own immutable private mask;
- both stations' current public assignment layers;
- both directional register values and their delivery counters;
- remaining rounds, writes, and layer mutations for both stations;
- whether either station has locked its layer with `finish`;
- the unchanged rack content hash, but not repeated film bytes.

It never receives:

- the other station's private mask or rack;
- the other station's hidden model text or working context;
- an interpretation of register symbols;
- a recommended division of labor;
- earlier conversation outside the films it retained.

Model-facing observations use typed JSON with zero-based item/target IDs,
sorted private pairs, six-entry layers (`null` means unset), and the fixed
display order below. Scientific hashes use the project's canonical JSON
serializer independently of display formatting.

```json
{
  "station":"X",
  "round":1,
  "private_pairs":[[0,1],[0,3]],
  "layers":{"X":[null,null,null,null,null,null],"Y":[null,null,null,null,null,null]},
  "registers":{"X":[{"symbol":null,"counter":0},{"symbol":null,"counter":0}],"Y":[{"symbol":null,"counter":0},{"symbol":null,"counter":0}]},
  "remaining":{"X":{"writes":3,"mutations":8},"Y":{"writes":3,"mutations":8},"rounds":16},
  "finished":{"X":false,"Y":false},
  "rack":{"films":[]}
}
```

The example abbreviates `private_pairs`; real observations contain all 18.
After round one, `rack` contains only `{"content_hash":"..."}`. A model-visible
observation never contains job seeds, intervention labels, lineage IDs, hidden
trigger status, or the correct assignment.

### 4.4 Frozen model-facing instruction

Except for inserting the station label, the common instruction is identical
for X and Y:

```text
You operate station {X|Y}. Each job has six items and six targets. Your
private panel lists the item-target pairs accepted by this station. The other
station has a different private panel that you cannot see.

The pair succeeds only if both stations finish with the same complete
one-to-one assignment and every selected pair is accepted by both private
panels. The two private panels jointly admit exactly one successful
assignment. Your panel alone admits more than one.

At job start you receive your station's retained film rack. At each round you
receive your private panel, both public assignment layers, the public
registers, and remaining budgets. Choose exactly one available action. Your
ordinary response text is not shown to the other station and is not retained
between jobs.

A retained film is a six-round window from your own observations and actions.
It remains available to this station on later jobs. The rack holds at most six
films. Retaining or evicting films does not change the current job result.
```

The implementation may make purely mechanical formatting changes required by
the selected harness, but the text and semantics above must be hash-pinned in
the V0 run manifest. A substantive wording change creates a new protocol
version.

Only valid typed action objects affect the other station or world state.
Free-form response text, hidden reasoning, and provider metadata are never
copied into messages, films, racks, or task feedback.

The action descriptions are also frozen:

```text
write   Place one uninterpreted symbol in one outgoing public register.
set     Set one item-target pair on your station's public assignment layer.
unset   Clear one item from your station's public assignment layer.
finish  Irreversibly lock your current assignment layer for this job.
wait    Make no world-state change this round.
retain  Save one six-round window from this completed job in your station's rack.
evict   Remove one retained film from your station's rack.
keep_unchanged  Make no rack change in the current memory subphase.
```

The frozen provider boundary exposes no model tools. Each decision therefore
uses one strict canonical JSON object in ordinary output text, for example:

```json
{"action":"write","register":0,"symbol":2}
{"action":"set","item":4,"target":1}
{"action":"finish"}
```

The parser forbids additional keys, surrounding prose, Markdown fences,
multiple actions, and unknown enum values. A syntactically invalid response is
an illegal action for that round. Environment-side parsing is deterministic
and is not an LLM judge.

The discriminated action union is exact:

```text
{"action":"write", "register": int, "symbol": int}
{"action":"set", "item": int, "target": int}
{"action":"unset", "item": int}
{"action":"finish"}
{"action":"wait"}

post-job memory phase only:
{"action":"retain", "start_round": int}
{"action":"evict", "fragment_handle": str}
{"action":"keep_unchanged"}
```

### 4.5 Symmetric primitive actions

Both stations have the same model-facing actions:

```text
write(register, symbol)   register in {0,1}; symbol in {0,1,2,3}
set(item, target)         set one entry on the station's own layer
unset(item)               clear one entry on the station's own layer
finish()                  lock the station's current layer
wait()                    make no state change this round
```

There are no semantic aliases or high-level protocol actions.

Per job, each station has:

- at most three `write` actions;
- at most eight layer mutations total (`set` plus `unset`), of which six are
  needed for an unrevised complete layer;
- one action per round;
- sixteen rounds;
- one irreversible `finish`.

Action legality is exact:

- `write` is legal while a write remains. It consumes one write even when the
  environment later drops or delays delivery.
- `set` is legal only for in-range IDs when that item is currently unset and
  that target is unused on the station's layer. A legal set consumes one layer
  mutation.
- `unset` is legal only when that item is currently set. A legal unset consumes
  one layer mutation.
- `finish` and `wait` consume no write or mutation budget.
- no world action is legal after that station has finished.

An illegal action is rejected, consumes the round, and is logged. It does not
consume or expand a write/mutation budget. A station that calls `finish` with
an incomplete or non-bijective layer locks that invalid layer and cannot repair
it. Environment-originated clearing does not debit the actor's mutation
budget; any actor repair does.

### 4.6 Round resolution

Round selection is symmetric even if underlying model calls are serialized:

1. X and Y receive the same pre-round public state.
2. Each independently selects one action without seeing the other's current
   selection.
3. The environment resolves both actions deterministically.
4. Effects become visible in the next round unless an intervention says
   otherwise.

Canonical X-before-Y event serialization is permitted only for logging; it
must not change observations or outcomes. Directional writes do not collide.

A register stores the most recently delivered symbol from each sender on that
register plus a monotonic delivery counter. A new delivered write overwrites
the visible value. Silence, action timing, layer changes, and order are public
and therefore count as possible communication in the centralization screen.

### 4.7 Completion and reward

A job ends when both stations finish or round 16 resolves.

Task success is one iff:

- both stations finished;
- both layers are complete bijections;
- the two layers are identical;
- every selected edge is in both private masks.

Stations receive only the binary job outcome after completion. They do not
receive the target matching, a list of wrong edges, a protocol diagnosis, or a
routine score.

The only behavioral reward is mean job success. Within a successful job there
is no reward difference for speed, message count, role allocation, rack use,
or stylistic simplicity. Budgets are hard physics, not reward terms.

## 5. Self-serving film rack

### 5.1 Context reset

Working conversation context is reset between jobs. At the next job, the same
station receives only the neutral world instructions, its new private job
view, current public state, and its own retained rack. No successor or teaching
language is used.

One X predecessor lifecycle and one Y predecessor lifecycle remain the active
dyad for all 24 jobs. A context reset clears the model-visible job transcript;
it does not terminate, replace, or relabel either predecessor actor/process.
If the frozen execution layer can reset context only by replacing an actor,
that is an incompatibility blocker for V0 rather than permission to redefine
the predecessor population.

The model-facing explanation is limited to:

> A retained film remains available to this station on later jobs. The rack
> holds at most six films.

### 5.2 Film content

After observing the job outcome, a station may retain at most one six-round
contiguous window from its own current-job sensorimotor stream. Each local
frame contains only task-local fields:

- the station's private mask, public layers, registers, budgets, locks, and
  intervention effects visible at that round;
- the station's submitted typed action and legality result;
- environment effects visible to that station after resolution.

Film frames explicitly exclude the current rack, all prior films, common
instructions, free-form model text, provider metadata, and hidden reasoning.
A retained film therefore cannot recursively package earlier racks or expand
the carrier capacity by nesting prior films.

There is no free-text field, agent-written title, semantic tag, researcher
summary, protocol label, or automatically selected success marker. If the
outcome is visible inside the chosen window, it survives because the agent
selected that window.

Films are immutable after retention. Absolute job IDs, wall-clock timestamps,
and original slot positions are not model-visible on later jobs. Each film has
an environment-generated opaque handle for eviction and a content hash. Rack
display order is canonical by content hash rather than agent-controlled.

### 5.3 Memory operations

The post-job memory phase exposes only:

```text
retain(start_round)
evict(fragment_handle)
keep_unchanged()
```

Every completed non-read-only job has exactly two ordered memory subphases:

1. **Eviction subphase.** Each station independently submits either one
   `evict(fragment_handle)` or `keep_unchanged()`. `retain` is invalid here.
   Both stations decide from their own post-job rack without seeing the other
   station's choice; all valid evictions then resolve.
2. **Retention subphase.** Each station sees its own resulting rack and
   independently submits either one `retain(start_round)` or
   `keep_unchanged()`. `evict` is invalid here. Both valid retentions then
   resolve.

`keep_unchanged()` means no operation in the current subphase. A retention is
valid only when `start_round` through `start_round + 5` are six extant,
contiguous rounds of the just-completed job and the post-eviction rack has a
free slot. Thus a full rack can be replaced only by a valid eviction in the
first subphase followed by a valid retention in the second; there is no
implicit eviction, overwrite, or harness-chosen fallback. After retention,
rack order is recanonicalized by content hash. Read-only rack probes expose no
memory subphase and cannot alter either rack.

The station may therefore make at most one eviction and one retention decision
per eligible job. The harness never chooses an episode, window, eviction,
balance, or summary on the station's behalf.

Memory decisions do not affect job reward. Every attempted and completed
operation is logged. Evicted bytes cease to be model-visible but their hashes
remain in the scientific audit log.

### 5.4 Role locality and future compatibility

X never reads Y's rack and Y never reads X's rack. V0 keeps racks only as
predecessor task state; it performs no turnover.

The final rack serialization must nevertheless be canonical and byte-stable so
that a later, separately authorized H1 package can write each role's exact rack
as its own `DECLARED_LINEAGE_CARRIER` through the existing frozen carrier API.
No controller selection, transformation, or merged transcript is permitted.
This compatibility requirement does not authorize H1 integration in V0.

## 6. Intervention hooks

V0 implements a closed, typed set of low-level intervention effects. The
intervention record specifies a trigger predicate, target station/event, and
effect. The environment logs whether the trigger fired.

```text
DROP_WRITE              suppress one selected write delivery
DELAY_WRITE             delay one selected write by exactly two rounds
DELAY_LAYER_VISIBILITY  hide one selected set/unset effect from the partner
                        for exactly one round
CLEAR_LAYER_ENTRY       clear one selected, currently set local entry
HIDE_RACK               omit one station's rack for the complete job
```

Interventions never alter private masks, fabricate messages, inject protocol
labels, or provide task answers. Later assay development may schedule these
same typed effects differently; adding a new effect changes the world version.
`HIDE_RACK` replaces the complete rack view, including its count, hashes, and
handles, with the neutral `rack_unavailable` sentinel. It does not delete or
mutate the underlying rack, and the partner is not directly told that it fired.

Exploration V0 uses these exact trigger templates:

- `DROP_WRITE`: drop the first legal write by the seeded target station at or
  after round three.
- `DELAY_WRITE`: delay by two rounds the first legal write by the seeded target
  station at or after round three.
- `DELAY_LAYER_VISIBILITY`: after the seeded target station has two entries,
  hide its next legal `set` from the partner for one round.
- `CLEAR_LAYER_ENTRY`: immediately after the seeded target station reaches
  four entries, clear the lowest visible item ID currently on its layer.
- `HIDE_RACK`: apply from job start to the seeded target set `{X}`, `{Y}`, or
  `{X,Y}` as fixed by the probe schedule.

Target stations are exactly balanced over X and Y across the twelve-dyad
schedule. A trigger that never fires has no substitute effect; it is recorded
as `INTERVENTION_NOT_TRIGGERED`.

### 6.1 Exact delayed-effect timing

Let an action be selected in round `r`. Ordinary resolved effects first appear
in observations at the start of round `r + 1`.

- A `DELAY_WRITE` write is queued for delivery at the start of round `r + 3`.
  It is absent from observations in rounds `r + 1` and `r + 2`. At delivery it
  increments the delivery counter and overwrites that directional register.
- If multiple writes to the same directional register are due at one round
  boundary, they resolve in ascending original-selection round, so the most
  recently selected due write is the visible value. Every delivered write
  still increments the counter.
- A `DELAY_LAYER_VISIBILITY` action changes the authoritative layer during
  resolution of round `r`, as usual. Its owner sees the resulting layer in
  round `r + 1`; the partner receives the pre-effect value for that entry in
  round `r + 1` and the then-current authoritative value from round `r + 2`
  onward. This is a one-observation suppression, not a queued second mutation.

Job termination is evaluated immediately after a round resolves. If it ends
before a queued write's delivery boundary, that write is cancelled, never
changes the register or counter, and is logged with
`CANCELLED_AT_JOB_END`. If a layer-visibility suppression has no later
observation in which to expire, the authoritative layer still governs task
scoring, while the unused release is logged as
`VISIBILITY_EXPIRED_AT_JOB_END`. No delayed effect crosses a job boundary or
appears in a post-job film frame that was never observed during the job.

## 7. Canonical event log

The typed event log, not model prose, is the scientific record. Every event
contains at least:

```text
schema_version
run_id, lineage_id, job_id, job_seed
event_sequence, round
phase
source                  X | Y | environment
event_kind
action_id and typed arguments, when applicable
legal and rejection_reason
pre_state_hash, post_state_hash
parent_event_ids
write_budget_before/after
mutation_budget_before/after
intervention_id, trigger_status, effect_status
delivery_status and visible_from_round
rack_hash_before/after
fragment_hash and local_window_bounds, when applicable
```

Required event kinds include:

```text
JOB_START, CONTEXT_RESET, OBSERVATION
ACTION_SUBMITTED, ACTION_REJECTED
WRITE_DELIVERED, WRITE_DROPPED, WRITE_DELAYED, WRITE_CANCELLED
LAYER_SET, LAYER_UNSET, LAYER_VISIBILITY_DELAYED
LAYER_VISIBILITY_EXPIRED
FINISH_LOCKED, JOB_END
MEMORY_PHASE_START, MEMORY_EVICTION_PHASE, MEMORY_RETENTION_PHASE
RETAIN_ATTEMPTED, RETAINED
EVICT_ATTEMPTED, EVICTED, RACK_VIEWED
INTERVENTION_ARMED, INTERVENTION_TRIGGERED, INTERVENTION_NOT_TRIGGERED
```

All pre/post hashes derive from canonical JSON. Generator records, action
events, local film bytes, and rack states must round-trip exactly. The event
log must be sufficient for a deterministic top-down renderer and for complete
offline recomputation of every reward and metric.

Raw chain-of-thought or hidden reasoning is neither required nor used by any
scientific scorer. Ordinary provider traces remain governed by the frozen
runtime boundary.

## 8. Native verifiers V1 contract

Implementation begins with a new package created through:

```text
prime env init constraint-forge-formation-v0
```

It uses `import verifiers.v1 as vf` exclusively and exports one native
`vf.Taskset` subclass. It must not import or mix legacy verifiers environment,
rubric, parser, multi-turn, or tool-environment types.

- Each `TaskData` record contains the immutable lineage/job/round identifiers,
  seeds, applicable intervention schedule, and V0 version hashes required by
  the frozen runner's existing trace granularity.
- Strict typed `vf.State` objects own only the behavioral world state assigned
  to the environment: board, budgets, rack views, and event counters.
- A strict environment-side parser validates the canonical JSON action union
  in Sections 4 and 5. No MCP or provider tool surface is added.
- `Task.validate()` runs generator and schedule invariants without a model.
- `Task.finalize()` places the canonical event log, rack inventories, and
  deterministic summaries in `trace.info`.
- `@vf.reward` reports task success only.
- `@vf.metric` reports observability metrics; metrics never reward routine
  identity or diversity.
- No LLM judge is permitted.

The new package owns behavioral world mechanics, typed actions, validation,
and scoring only. It does not own actor lifecycle, provider transport,
cross-process isolation, retry policy, or multi-agent orchestration. In
particular, do not retrofit the qualification-only
`h1_live_runtime_adapter_v1` Taskset or its outcome-blind Orchestrator into a
behavioral runner.

The already-frozen execution layer must call the new behavioral contract. If
that layer cannot supply two symmetric station decisions, stateless job
requests, or the required task-state continuity, stop and report the
incompatibility rather than adding a harness, lifecycle path, or orchestration
mechanism inside Constraint Forge.

The implementation must verify this compatibility before scaffolding beyond
the model-free generator/state core. The qualification-only live adapter does
not itself supply an adaptive behavioral runner; it must not be repurposed to
fill that role.

## 9. Deterministic preflight and centralization screen

No live predecessor inference may begin until all preflight gates pass.

### 9.1 Generator and solo gates

Run at least 10,000 fixed-seed model-free jobs.

Required:

- 100% generator invariant validity;
- no duplicate job payloads;
- X-only and Y-only generator-aware reference solvers each have exact-answer
  accuracy at most 0.40;
- a 95% binomial upper confidence bound for each measured solo reference is at
  most 0.42;
- swapping visible X/Y labels leaves the job distribution unchanged.

The solo references receive their private mask, full knowledge of the
generator, and the same output budget, but no partner behavior or messages.
At minimum, enumerate all perfect matchings of the local mask and implement the
strongest generator-conditioned MAP rule available from the finite generator.

### 9.2 Scripted centralization adversaries

Implement through the exact public V0 action API:

1. `full_state_dump_X` and its Y mirror: serialize as much of one private mask
   as the complete observable transcript permits, then let the receiver solve
   and direct completion.
2. `candidate_first_X` and mirror: publish one locally valid full matching;
   the partner accepts compatible edges and signals corrections; the proposer
   centrally finalizes.
3. `ambiguous_edges_X` and mirror: transmit only locally ambiguous rows/edges,
   then let the receiver solve.
4. `compressed_constraints_X` and mirror: use the best hand-designed compact
   summary of row masks/domains that fits V0 physics.
5. `proposal_correction_X` and mirror: proposer publishes partial work,
   partner reports conflicts, proposer owns final revision.

Reference actors may use full knowledge of the generator and a shared
precomputed codebook, but each receives only its assigned private observation
and the public transcript during a job. This makes the screen adversarial
rather than a test of whether a particular hand-written agent noticed the
generator structure.

Silence, message timing, action choice, assignment order, and permitted
revisions all count as communication. A nominal register-bit calculation is
not an adequate screen.

### 9.3 Feasibility witnesses

Implement at least two structurally different, symmetric joint reference
policies that do not assign all inference and final control to one station.
Their only purpose is to demonstrate that the physics admits successful
distributed coordination. They are never exposed to models and never become
routine labels.

Across 1,000 fixed-seed ordinary jobs, both witnesses must achieve at least
0.80 success. Across a fixed balanced suite of the four non-rack fault effects,
at least one must achieve 0.60 success.

### 9.4 Centralization kill gate

Coordination overhead is defined on each successful ordinary job only. For
each station and each item, its **final-surviving set** is the unique last legal
`set` action that installed the item-target pair present in that station's
successfully locked terminal layer and whose installed entry was never later
removed by either an actor action or an environment effect before that lock.
A successful job must have exactly six such actions per station. The overhead
count is the number of all other submitted world actions by X or Y before job
termination, including writes, waits, unsets, illegal actions, and any
nonfinal sets. It excludes only those twelve final-surviving sets and the two
legal `finish` actions that produced the successful locks. Environment events
and post-job memory actions are not submitted world actions and are excluded.
Failure to identify exactly twelve qualifying sets and two qualifying finishes
on a nominally successful job is an implementation-invariant failure. The
reported median is over the centralized policy's successful ordinary jobs.

V0 fails preflight if either condition holds:

- any scripted centralized adversary achieves at least 0.90 ordinary-job
  success with median coordination overhead of at most two events, where
  coordination overhead is defined immediately above; or
- one centralized adversary weakly dominates every distributed feasibility
  witness in success, median rounds, total writes, and nonfinal layer
  mutations, with a strict advantage on at least one measure.

This suite does not prove that centralization is impossible. If an unprompted
model discovers a new cheap centralized solution or nearly all dyads converge
on one centralized procedure, formation fails empirically.

Preflight failure ends V0 before model inference. Changing `n`, budgets,
generator structure, or visibility creates a new world version.

## 10. Exploratory predecessor cohort

### 10.1 Fixed cohort

V0 runs exactly twelve independent predecessor dyads. Seeds, job payloads, and
schedule positions are generated and frozen before the first model call. A
failed behavioral dyad is not replaced.

Before execution, the run manifest must also pin the exact provider endpoint,
model snapshot, reasoning/sampling configuration, system/action-schema prompt hashes,
runtime configuration, and twelve independent actor assignments required by
the frozen H1 readiness dossier. This spec does not choose those deployment
values and does not waive the dossier's pre-execution canary obligation.

Each dyad receives 24 jobs:

- 14 ordinary rack-visible jobs;
- four rack-visible jobs carrying one each of `DROP_WRITE`, `DELAY_WRITE`,
  `DELAY_LAYER_VISIBILITY`, and `CLEAR_LAYER_ENTRY`;
- six late, matched-difficulty, read-only rack probes: two with both racks
  visible, one with only X's rack hidden, one with only Y's rack hidden, and
  two with both racks hidden.

The six read-only rack probes do not permit retention or eviction and restore
the exact pre-probe rack afterward. Their order is counterbalanced and hidden
from the stations. Intervention jobs are placed by the frozen schedule after
at least four ordinary jobs and are not described as diagnostic trials.

The rack probes form three latent matched pairs with independently permuted
visible IDs: two pairs compare both-visible against both-hidden, and one pair
compares X-hidden against Y-hidden. Pair members share generator-level latent
difficulty but never have identical visible task payloads. Pair order is
counterbalanced across dyads.

Every job begins with fresh working context. Apart from the immutable common
instructions and task physics, rack state is the only lineage-specific
model-visible information carried between jobs.

### 10.2 Deterministic V0 outputs

V0 computes only:

- job success and failure reason;
- legal/illegal action counts;
- writes, rounds, sets, unsets, and finish state;
- intervention trigger and effect status;
- retain/evict attempts and successes;
- rack occupancy, content hashes, and replacement history;
- success under ordinary, fault, rack-visible probe, and hidden-rack probe
  jobs;
- lineage-level summaries with the dyad as the inferential unit.

V0 does not assign a routine family, train a classifier, compute donor
distance, or score prose descriptions of behavior.

### 10.3 Exploratory inspection

After all twelve dyads finish, humans and/or LLMs may inspect anonymized event
tables and deterministic replays to discover candidate procedural structure.
Inspectors may propose factorized fields such as first response, repair scope,
proposal disposition, information-flow locus, or recovery action. These are
development hypotheses only.

For every proposed field, the exploration report must identify:

- the intervention or task event that anchors it;
- exact event-log inputs needed to compute it;
- a closed enum with `OTHER` or independently scored boolean fields;
- how compound responses are represented without subjective precedence;
- invariance to symbol and object relabeling;
- whether X/Y exchange is a true automorphism under V0 physics;
- examples that falsify or leave the field unclassified.

Timing, verbosity, raw action totals, prose style, and message-symbol identity
may be secondary diagnostics but cannot be primary routine fields.

## 11. Progression and kill criteria

V0 progresses to writing `formation-assay-v0` only if all of the following are
true:

1. **Competence:** at least eight of twelve dyads achieve at least 0.70 success
   over their final eight non-occluded jobs.
2. **Natural rack adoption:** at least six dyads retain at least two films, and
   at least four competent dyads end with nonempty racks maintained across at
   least four subsequent jobs.
3. **Plausible functional rack use:** across competent rack users, the
   exploratory intact-versus-hidden probes show a directional loss in task
   success or an inspectable disruption of the candidate joint procedure when
   racks are hidden. This is a development gate, not an H1 estimand; exact
   rack-dependence scoring must be frozen later.
4. **Noncosmetic multistability:** inspection identifies at least two candidate
   routine families, each expressed by at least two competent dyads, that
   remain different after symbol/object relabeling and best valid X/Y exchange.
   They must differ on at least two procedural dimensions, including at least
   one information-use, conflict-resolution, handoff, or recovery dimension.
5. **Small deterministic assayability:** the candidate differences can be
   represented with no more than eight factorized, intervention-anchored
   fields with closed values plus `OTHER`. A high-dimensional embedding,
   learned behavioral classifier, or holistic judge is not acceptable.

V0 stops as a negative or inconclusive formation result if any gate fails.
In particular, stop if:

- competent dyads converge on one normalized routine;
- apparent diversity is only role reversal, symbol permutation, object order,
  speed, verbosity, or error rate;
- racks are unused or appear behaviorally inert;
- one station's generic central solver and the other's generic follower explain
  nearly all successful behavior;
- meaningful routines can be recognized only through holistic human/LLM
  judgment;
- fewer than eight dyads become competent under the frozen physics.

The failure report must preserve the world hash, prompts, seeds, raw typed
events, rack histories, reference results, and the exact failed gate. It may
recommend a separately named V1, but it may not execute that repair.

## 12. Requirements for a later frozen formation assay

If V0 passes, a separate `formation-assay-v0` specification must be written
and frozen before sampling a fresh predecessor cohort. It must contain:

- exact diagnostic task and intervention schedules;
- exact factorized response fields, enums, compound-response rules, and
  `OTHER` handling;
- exact stability and missingness thresholds;
- symbol, object, and role-automorphism normalization;
- a simple deterministic family-separation rule;
- selected-rack versus empty-rack scoring;
- selected-rack versus uniform-history analysis as a separate, stronger
  curation test rather than an H1 requirement;
- competence and donor-eligibility rules;
- a commitment to carry every mechanically eligible donor forward or to state
  explicitly that later inference is conditional on a frozen sampling rule;
- a rule that any assay change after validation requires another fresh cohort.

No successor work begins until the fresh formation-validation cohort passes
the frozen assay unchanged.

## 13. Implementation acceptance checklist

Before any model call, the implementation owner must provide evidence that:

- [ ] Only a new Constraint Forge package, configs, tests, and this spec's
      implementation records changed; all frozen H1 paths have zero diff.
- [ ] The frozen execution layer can run the behavioral contract without a new
      harness, lifecycle path, provider surface, or orchestration mechanism.
- [ ] The package uses native `verifiers.v1` only and exports one Taskset.
- [ ] Every task, intervention, and cohort seed is pinned and reproducible.
- [ ] Generator, solo, feasibility, and centralization preflight gates pass.
- [ ] X and Y receive symmetric capabilities and pre-round observations.
- [ ] No model-facing semantic routine labels or successor language exist.
- [ ] Context reset leaves the station's selected rack as the only
      lineage-specific state visible across jobs.
- [ ] Every permitted infrastructure retry preserves the exact X and Y actor
      lifecycle/session identities; any identity-breaking recovery aborts the
      V0 attempt without replacement or behavioral scoring.
- [ ] Retained films are exact agent-selected local windows with no harness
      selection or semantic enrichment.
- [ ] The environment can recompute all task rewards from the canonical event
      log without an LLM judge.
- [ ] The renderer consumes the same event log and is not a scoring path.
- [ ] Behavioral failures cannot trigger replacement, prompt mutation, or
      automatic parameter tuning.
- [ ] Cohort execution is explicitly authorized after review of the preflight
      report; implementation alone is not authorization for inference.

## 14. Authorized next action

This specification authorizes implementation and model-free testing of the new
Constraint Forge V0 package only. It does not authorize:

- edits to the frozen H1 runtime or apparatus;
- live predecessor inference before the preflight report passes review;
- expansion beyond the twelve-dyad exploratory cohort;
- successors, turnover, carrier transplantation, or an H1 claim;
- automatic redesign or rerun after a failed gate.
