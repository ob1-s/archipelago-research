# Constraint Forge R1 — substrate design (development round)

Name: Constraint Forge R1 ("register-coded"). Package:
`environments/constraint_forge_behavioral_runner_r1`. Shared physics package
`constraint_forge_formation_v0` is imported UNMODIFIED (no fork); all changes
live in the runner layer. Historical rounds remain immutable.

## Diagnosis recap (drives the design)

The measured channel (public registers carrying conventional symbols) is
payoff-free, so satisficing agents ignore it; LOW additionally never grinds
into accidental discovery. Fix the incentive structure, not the prose.

## Change set (exactly three additions)

1. **Private void symbol (new asymmetric information).** Each job derives
   `void = int(stable_hash({"void", job_seed})[:8]) % 4`, uniformly over
   {0,1,2,3}. It is injected into X's private request text only
   ("station-note"), mirroring how private panels already work. Y never sees
   it. Generator/masks/instances untouched.

2. **Register-coded success conjunct.** A job counts successful iff the
   world's original predicate holds AND the final directional register-0
   banks satisfy: X.reg0.symbol is not None, Y.reg0.symbol is not None,
   both equal, and != void. Mid-job writes of the void symbol remain LEGAL
   (no legality change anywhere); the conjunct simply fails if a final value
   is void or missing. Computed post-hoc as a pure function of the sealed
   event log + seed-derived void, so `replay_job` hash/reward assertions
   stay valid; the original world success is retained alongside as a
   diagnostic field (`world_success`).

3. **Prompt amendment (runner-layer text only).** Two neutral mechanical
   sentences appended to the common instructions: (a) the pair succeeds only
   if both stations' outgoing register 0 holds the same symbol at finish;
   (b) one symbol per job is void for register 0 and is stated in your
   private station note / cannot be known by the other station. No protocol,
   strategy, or teaching language.

Everything else — masks, n=6 matching difficulty, budgets, round cap 16,
fault kinds, film rack, memory phases, WIPE_RACK snapshot/restore,
film_intact/wiped matched probe pairs, parity rotation, context reset,
self-use retention framing, neutral no-teaching stance — is carried over
verbatim from V1.

## Why each piece is necessary

- Conjunct (2) makes the studied channel score-bearing: every success now
  implies >=2 delivered legal writes, so participation stops being a tail
  event and LOW-vs-MEDIUM comparisons become meaningful (diagnosis F1/F2).
- Private void (1) makes blind convergence insufficient: a fixed default
  symbol fails whenever it hits the hidden void (p=1/4 per job
  independently), and Y cannot even condition its choice without reading
  X's public behavior — creating genuine inter-agent dependence without
  prescribing how to communicate (regime items 1,2,4).
- Prompt text (3) is required by determinism/honesty: the new physics must
  be stated mechanically, like panel text; nothing more.

## Rejected alternatives (recorded)

- Panel-coded per-item legends: larger generator-facing change, same
  mechanism; deferred.
- Calibrating base difficulty (n=6 -> 5): touches shared generator math and
  matched-pair keys; unnecessary until qualification measures the new band.
- Tolerant JSON repair (~8% Y malformed-set quirk): alters legality
  semantics; frozen out; carried as threat.
- Rejecting void writes at action level: would require forking world
  validation and breaks replay determinism guarantees for zero benefit.

## Model-free screens (scripted, run before any model call)

S1 solvability: for N>=200 seeded instances, P∩Q has a unique perfect
matching and the centralized policy realizes it (constructive solver).
S2 non-centralization: neither mask alone determines the answer (each admits
>=2 perfect matchings) and no observation serialization contains the other
station's private pairs or X's void symbol.
S3 non-triviality of the conjunct: fixed-default strategies (both always
symbol k) succeed on the conjunct with probability exactly 3/4 per job;
Y-side blind brute-force (test-write symbols until rejection) is capped by
the 3-write budget at success probability <= 1/2; coordinated reading
approaches 1. Quantified in-script by enumeration.
S4 determinism: plan build + conjunct evaluation are pure functions; same
seed => same void, same plan hash, same adjudicated success twice.
S5 probe compatibility: read_only_probe gates memory phases only; round
actions (write/set/finish) remain legal in probes, so visible probes can
express register conventions; WIPE_RACK snapshot/restore path untouched.
