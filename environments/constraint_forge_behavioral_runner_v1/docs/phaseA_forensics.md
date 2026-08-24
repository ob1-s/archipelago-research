# Phase A — V0 Forensic Diagnosis: why formations favor probes (and what actually carries coordination)

Scope: sealed V0 evidence only (`cohort_artifacts/…luna-{low,medium}-v0/dyad-*.json`), plus read-only
code comprehension of `constraint_forge_formation_v0`. No new model inference. All claims carry
trace-level provenance (`dyad-NN / job-MM`).

## A.1 Mechanical parity of ordinary and probe jobs

From source (file:line):

- Single generator for all jobs — N=6 items/targets, target_factor uniform, decoy masks of 18 edges
  sharing only the 6-edge target matching (`generator.py:248-296`, constants `generator.py:12-15`).
  Kinds are assigned purely by schedule position; probes are difficulty-matched *pairs*
  (`schedule.py:190-243`) with identical latent factor layout inside a pair.
- Budgets identical everywhere: writes_remaining=3, mutations_remaining=8 per station per job
  (`models.py:125-126`), 16 rounds max (`models.py:185-186`).
- Success predicate identical: both finished + both layers full bijections + X layer == Y layer +
  all pairs in target matching (`world.py:138-146`).
- Rack visibility path is job-kind-independent: full view at each job's first observation, hash-only
  afterward, hidden under HIDE_RACK (`world.py:655-663`, `rack.py:168-177`).
- Probes additionally: read-only (memory phases skipped, `session.py:623-625`; retention rejected
  `session.py:756`), optional HIDE_RACK per pair condition.

**Conclusion: no mechanical difficulty difference exists between ordinary jobs and visible probes.**

## A.2 Empirical success signature (sealed traces)

Per-job metrics across all executed dyads (mean per job; successful vs failed):

| metric | successful | failed |
|---|---|---|
| turf-war rounds (same item, clashing targets) | **0.5–1.0** | 1.4–1.9 |
| agreeing rounds | up to 2.0 | 0.2–0.5 |
| LAYER_SETs (work volume incl. repairs) | 12.8–13.5 | ~11 |
| rounds consumed | 9–14 | ~8–11.7 |

Success = conflict suppression plus extra repair work within budget. Two failure modes exist:
(A) turf wars (direct item collisions) and (B) silent divergence/passivity (turf≈0 but still failing;
e.g., MEDIUM-05 jobs 9,10,14,15,16).

## A.3 The probe advantage is experiential, not mechanical

1. **Position**: probe block is last (jobs 18–23); actors arrive with maximal shared history.
   The coordination channel that accumulates is the **per-station conversation thread** — the harness
   ships the full message thread every turn (the very reason V0 needed file-based transport after the
   E2BIG abort). By job 18 a station's thread contains ~18 jobs of observed layer diffs.
2. **Rack access is NOT the driver** — it is if anything inverted. Classifying all 66 probe
   observations by actual availability (`RACK_VIEWED.detail.available`):
   - MEDIUM successes: 5/14 on all-hidden probes vs 1/14 on both-visible (2/14 partial)
   - LOW: its single probe solve was both-visible; 0/8 all-hidden.
   MEDIUM formed repeatedly with the rack hidden the entire job (e.g., dyad-00/job-19,
   dyad-01/job-23, dyad-02/job-23, dyad-05/job-21).
3. Therefore the operative cross-job memory candidate is the **in-context thread**, with films of
   unproven incremental value. This reframes the V1 memory question: films may be redundant carrier
   OR a small booster; V0 cannot distinguish.

## A.4 Fault-block interaction

No state carryover exists between jobs except racks (`world.py:917-925`). Yet MEDIUM-05's formation
burst (jobs 5→7→8, i.e., fault→fault→ordinary) immediately followed fault onset, with turf suppressed
during solves — faults plausibly forced adaptation. n=1 dyad; treated as hypothesis, not finding.

## A.5 Rack capacity artifact

Retention stops contributing after ~job 12 in most dyads: rack capacity is 6 films/station
(`rack.py:77`); later retains fail silently ("rack_full_after_eviction_subphase", `rack.py:237`).
Late-sequence "no retention" in traces reflects saturation, not choice.

## A.6 MEDIUM-05 case study (illustrative, not tuned upon)

Timeline (dyad-05): failures with heavy turf (jobs 1,3,11,13: turf 5–6) → formation cluster
5/7/8 with turf=1 → relapse into passive divergence (turf 0, still failing) → late probe formations
(18, 21). Demonstrates within-sequence development AND its fragility; both failure modes co-exist.

## A.7 Diagnosis statement

The ordinary/probe formation gap is explained by **accumulated in-context coordination experience**
(position), not by task mechanics — probes are mechanically identical and their rack conditions do
not help (hidden probes form most). Success mechanism is conflict-repair under budget; the binding
constraint on competence is unresolved turf conflict early in sequences, before shared conventions
crystallize in-thread. Implications for V1: give repair more round headroom, measure memory causality
by manipulating film content (not view permissions), and power the effort comparison properly.
