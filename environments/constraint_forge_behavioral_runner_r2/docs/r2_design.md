# Constraint Forge R2 — difficulty-calibration development round

Status: development-only, separately named. Greenlight: Reviewer 2, 2026-08-26.
Carries forward verbatim from R1: interaction substrate, register-coded
success conjunct, X-private void symbol, film rack/memory phases, WIPE_RACK
snapshot/restore, film_intact/wiped matched probe pairs, parity rotation,
context reset, neutral prompts, hardened infra. Nothing about films, probes,
conjunct logic, or the leader/follower channel changes unless calibration
exposes a direct dependency.

## Motivation (isolated by R1)

Participation is fixed (39 delivered writes/dyad; Y tracks X's symbols incl.
non-default) while base matching competence is ~zero (world_success 0/24;
V1 qual 1/24). The isolated variable for R2 is TASK DIFFICULTY of the
private-mask matching problem — nothing else.

## Difficulty ladder (predefined, ordered, minimal-lever first)

Physics constants currently pin zero slack: mutation budget 6 == exact number
of sets a perfect assignment needs (any collision costs unset+set = 2/6 of
budget), round cap 16.

- L1 "slack": mutation budget 6 -> 12/station/job, write budget 3 -> 4,
  round cap 16 -> 24. Instance distribution, n=6, masks, generator untouched.
  Rationale: cheapest lever; removes unrecoverable-mistake fragility without
  changing the information problem.
- L2 "smaller instance": n=6 -> 4 (K_{4,4} one-factorization), mutation 8,
  write 3, rounds 20. Requires generator partition adaptation (decoy counts)
  and domain-text regeneration.
- L3 "denser masks": n=6, raise per-item admissible-pair density so each
  private mask admits strictly more perfect matchings than V0's construction
  (details fixed at implementation time from generator internals, before any
  L3 call).

## Calibration protocol (predeclared before any R2 model call)

- Calibration seed prefix `constraint-forge/r2-calibration-v0`, never reused.
- One MEDIUM-effort dyad per rung on the STANDARD 24-job plan structure
  (full machinery, comparable numbers; cost accepted deliberately over a
  reduced-plan smoke design for machinery-reuse reasons — recorded tradeoff).
- Success metric per rung: fraction of the 24 jobs satisfying the R2 success
  predicate (world success AND register conjunct), extracted by the same
  committed gatecheck extraction logic.
- SELECTION RULE: walk rungs in order L1 -> L2 -> L3. Select the FIRST rung
  whose observed success fraction lands in [2/24, 12/24] (= 0.083 .. 0.50).
  Band chosen so the floor sits above "one lucky job" (V1 baseline) with
  headroom below ceiling.
- OVERSHOOT RULE: if a rung observes >=13/24 successes (>0.50), stop the
  ladder immediately and select NOTHING; report that even that rung
  trivializes. (Do not walk back down post hoc.)
- EXHAUSTION RULE: if all rungs finish below the band floor (<2/24), STOP and
  report: MEDIUM cannot enter a measurable band on the reasonable ladder
  without trivializing. Do not invent softer worlds beyond the ladder.

## Freeze + qualification (after selection)

The selected rung's knobs are frozen into the R2 substrate spec; fresh
qualification seed prefix `constraint-forge/r2-qualification-v0`; ONE full
MEDIUM dyad then evaluation against the R1 frozen tiers VERBATIM
(participation >=14/24/station, competence >=3 successes incl ordinary,
measurability >=6 successes & >=2 agreed symbols, ceiling <=20/24, infra
validity). Only on MEDIUM pass runs the single LOW one-shot dyad. Same
gate-extraction script. Same infra-validity semantics; one clean
pre-declared relaunch per arm remains the cap.

## Model-free screens

S1-S5 re-run per selected rung before its qualification call (uniqueness of
P∩Q solution, unilateral ambiguity, blind-strategy caps recomputed under new
budgets, void privacy screen S2B, probe-action legality).

## Infra-leniency note

Operator directive #1 (park-on-quota checkpointing) is deferred again this
round: calibration/qualification launches will be timed early in a quota
window instead. Recorded as known gap; sized-in-window policy per directive
#4.
