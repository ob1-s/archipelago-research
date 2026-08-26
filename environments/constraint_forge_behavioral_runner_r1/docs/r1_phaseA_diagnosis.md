# Constraint Forge R1 — Phase A: participation-failure diagnosis

Round: substrate-development (separately named; V1 closed NO-GO at `77db805`).
Inputs: sealed evidence only (dyad-luna-low.json, dyad-luna-medium.json, V0
cohort artifacts, V0/V1 code). Two independent forensic passes; adjudicated
by the round lead. Nothing was modified.

## Finding 1 — the register channel is score-irrelevant (primary cause)

Success (world spec §4.7) is defined purely over assignment layers: both
finish, identical complete bijections, edges inside both private masks.
`write` places an "uninterpreted symbol" in a public register and appears in
no success conjunct. The affordance is otherwise impeccable — first-listed
schema, restated every turn, visible `remaining.writes` budget — yet:

- V1 LOW: 0 write attempts in 362 submissions (not even malformed ones);
  write budget display constant 3->3 across all 1083 events; registers
  `"symbol":null` in 100% of observations.
- V1 MEDIUM: 3 writes / 24 jobs; the only discovery path was accidental —
  X ground on a failing set for 13 consecutive rejected rounds, then wrote.
- Environment faults aimed AT the channel (DROP_WRITE, DELAY_WRITE, jobs
  4-5) fired as no-ops because there was nothing to disrupt.

A satisficing policy reads the objective exactly as scored: layers pay,
registers do not. Engagement with the mechanism the science measures was
never incentivized for EITHER effort level.

## Finding 2 — LOW's planning horizon forecloses accidental discovery (amplifier)

reasoning_tokens=0 throughout; replies are bare one-shot JSON; FINISH_LOCKED
at the round-7 floor in 12/23 X agent-jobs (vs 5/23 MEDIUM); stuck-loops of
>=3 identical failing attempts in 10 episodes (worst: 12x rejected echo),
~40 rounds burned. MEDIUM found write only through prolonged failure
grinding; LOW locks ~2 rounds earlier and never grinds into the channel.
This is a model-side threshold, not a spec defect — the substrate must not
depend on grinding luck for channel discovery.

## Finding 3 — excluded causes

- Affordance clarity: excluded. Spec complete and repeated; same framing
  produced writes at medium effort.
- V1 prompt/harness regression: excluded. protocol.py is byte-identical
  V0->V1; remaining diffs are id strings and probe-block redesign (jobs
  18-23 film content only).
- Instance-stream shift: contributing but inseparable from n=1. Seed-prefix
  change guarantees fresh instances; V0 completed LOW dyads carried 1-4
  writes each (~lambda 2.5 => P(zero-write dyad) ~8%), so the V1-LOW dry
  draw was likely-ish — but only BECAUSE the channel is ultra-rare when
  unscored. Fixing the incentive removes the fragility class.

## Residual observations carried forward

- ~8% of Y submissions died to a JSON-quoting corruption (`"target":1"}`);
  same signature at MEDIUM (62x). Model quirk; recorded as inference threat,
  not repaired (legality semantics stay frozen).
- Post-finish dead rounds burn turns on wait/rejected echoes; harmless to
  physics, noted for budget realism.
- Adjudication note: one forensic pass placed the V1-MEDIUM formation at
  job 14 vs the sealed record's job 16; the sealed record stands; methods
  difference flagged, no reinterpretation of V1.

## Design consequence

Raise participation by making the register channel causally necessary for
success under PRIVATE asymmetric constraint — not by exhortation, protocol
prescription, or gate lowering. See r1_design.md.
