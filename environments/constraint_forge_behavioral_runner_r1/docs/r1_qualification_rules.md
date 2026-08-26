# Constraint Forge R1 — frozen qualification decision rule

Frozen 2026-08-26 UTC, BEFORE any R1 model call of any kind. No parameter on
this page may change after the first qualification call. Qualification seeds,
evidence, and analyses are permanently excluded from scientific use.

## Qualification economy and order (predeclared)

- Seed prefix: `constraint-forge/r1-qualification-v0` (never reused anywhere else).
- Exactly ONE MEDIUM dyad (sequence index 0) runs FIRST.
- Exactly ONE LOW dyad (sequence index 0) runs ONLY IF the MEDIUM dyad passes
  Tiers 1–3, ceiling, and infrastructure validity below. If MEDIUM fails any
  gate, the round ends NO-GO without spending the LOW opportunity (a substrate
  that fails its own development gates requires redesign under a new name, not
  more sampling).
- No dyad is ever re-run, resumed into a second attempt after a sealed
  lifecycle, or re-seeded. An infra-killed attempt with zero observations is
  documented as an infra event; at most one clean relaunch per arm, declared
  as such in the record.

## Gates (evaluated on completed sealed lifecycles only)

### Tier 1 — participation floor (per station, per dyad)

Each station must deliver >=1 legal `write` action in >=14 of 24 jobs
(58%). Justification: under the R1 conjunct no job can succeed without both
stations writing, so a solving policy writes essentially always; 14/24
tolerates fault/probe oddities and learning transients while sitting an
order of magnitude above the V0/V1 unscored baseline (<=4 writes per dyad
TOTAL). Both stations must clear it individually in the same dyad.

### Tier 2 — competence floor (gate on the MEDIUM dyad)

>=3 of 24 jobs successful (>=12.5%) including >=1 ordinary-category success.
Justification: V0's absolute ceiling was ~0.25 late-block mean; requiring 3
scattered successes (not a lucky streak of probe easiness) shows the substrate
is solveable by the model population, not merely by construction. This is far
above renaming one lucky job as competence, and deliberately far below ceiling.

### Tier 3 — formation measurability (gate on the MEDIUM dyad)

Among successful jobs: >=6 successes AND >=2 distinct agreed register symbols.
Justification: six varied successes cannot arise from independent fixed-symbol
defaults colliding with a uniformly random private void (joint probability of
the observed pattern under the S3 null is <1%); >=2 distinct agreed values
shows behavior tracks the moving constraint instead of a degenerate constant.

### Ceiling check (gate on the MEDIUM dyad)

<=20 of 24 jobs successful (<=83%). Above this the substrate is trivially
solved and cannot measure coordination improvement.

### Infrastructure validity (both dyads)

Lifecycle sealed `completed`; abort_class null; evidence sha256 matches the
run summary; plan_hash derives from the frozen prefix; every infra retry
within the designed budget; no unresolved crash markers. Recovered retries do
not fail this gate; unresolved aborts do.

### LOW disposition (one-shot, immutable)

LOW receives exactly this one qualification opportunity on R1. Evaluation of
the LOW dyad: Tier 1 is the gate; Tiers 2–3 are recorded descriptively.

- If LOW passes Tier 1 while MEDIUM passes all gates: both arms proceed to the
  proposed scientific design.
- If LOW fails Tier 1 while MEDIUM passes all gates: record LOW as below the
  usable substrate threshold; REMOVE LOW from the primary formation/memory
  experiment; make MEDIUM the main scientific model condition; defer any
  reasoning-effort comparison to a separately designed later experiment. Do
  not redesign repeatedly around LOW. Do not revisit this rule after
  observing the outcome.

## Adjudication method (predeclared)

Writes, deliveries, register states, and categories are extracted mechanically
from the sealed event logs by script; extraction code is committed before the
first call alongside this document. Any behavioral judgment calls are
adjudicated by the round lead and reported with verbatim evidence excerpts.
