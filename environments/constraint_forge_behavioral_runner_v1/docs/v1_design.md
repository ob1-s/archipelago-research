# Constraint Forge V1 — Behavioral Runner Design (pre-freeze draft)

Status: DESIGN — nothing here is frozen until Phase E. Predecessor: sealed V0
(`environments/constraint_forge_behavioral_runner_v0`, report at
`qual_artifacts/V0_analysis_report.md`; forensics at `docs/phaseA_forensics.md`).

## B.1 Scientific questions (priority order)

- **Q1 (substrate, gating)**: Can the V1 task support sustained predecessor
  competence — non-trivial formation frequency and non-zero late-sequence job
  success — under adequately powered, attrition-resistant execution?
- **Q2 (memory causality, primary confirmatory)**: Does accumulated film state
  make a causal contribution to coordination-routine expression on matched
  diagnostic probes, holding task physics and in-context history fixed?
  Estimand: paired difference in success probability between film-intact and
  film-wiped difficulty-matched probe pairs within dyads.
  V0 forensics motivates this sharply: formations occurred most on all-hidden
  probes, suggesting in-context threads carry coordination; if films matter,
  wiping must hurt; if they do not, the null is itself decisive for design.
- **Q3 (effort replication, secondary descriptive)**: Is the LOW/MEDIUM
  direction (MEDIUM ≥ LOW) reproducible when powered? Analyzed by sign test on
  matched dyad indices; not a gate.

## B.2 Changes from V0 (each justified)

| # | change | justification |
|---|---|---|
| 1 | Round budget per job 16 → 20 | V0 solves consumed 9–14 rounds *with* repairs; failures exhausted ~8–12 with live conflicts (phaseA A.2). Gives observed repair behavior headroom without touching success definition. Physics otherwise identical to V0 for comparability. |
| 2 | Probes: HIDE_RACK removed; all probes both-visible; new **WIPE_RACK** factor instead | V0 shows view-permission is not the operative variable (hidden probes formed most). Wiping changes *film content availability* while holding observation permissions and task physics fixed — the actual causal contrast for Q2. |
| 3 | Probe schedule = 3 difficulty-matched pairs; conditions [intact, wiped, wiped] on even dyads, [wiped, intact, wiped] on odd | Within-dyad paired estimand with mild position counterbalancing. Difficulty matching inherited from v0 schedule machinery. |
| 4 | Job kinds/blocks identical to V0 (ordinary 0–3, faults 4–7, ordinary 8–17, probes 18–23); 24 jobs | Preserves comparability and the lifecycle that produced the phenomenon. |
| 5 | Competence gates recalibrated from QUALIFICATION data only (excluded from science), then frozen prospectively | Old 70% gate demanded near-ceiling competence V0 never approached; see B.3. |
| 6 | Execution layer rewritten (Phase C) with stop-rule text parity, reconciliation, preflight health checks, stable row protocol | All V0 incident classes; no historical code touched. |

Not changed: generator, masks, decoys, success predicate, rack capacity/semantics,
fault types, message transport (file-based), audit/seal machinery concepts.

## B.3 Competence criterion (to be frozen after qualification)

Two-tier, both evaluated per completed dyad:

- **Formation-frequency tier** (phenomenon persistence): ≥1 formation event in
  ≥60% of completed dyads per arm.
- **Late-competence tier**: arm-level mean of final-eight (jobs 16–23) success
  proportion ≥ threshold T, where T = max(0.20, 2 × qualification-arm mean of
  final-eight on ordinary-block analogues) — set from throwaway qualification
  runs before freeze, never revisited after scientific launch.
  Rationale: V0's absolute ceiling was 0.25 final-eight; requiring 0.70 again
  would measure nothing but the gate. T demands a genuine multiplicative lift
  over whatever V1's own substrate baseline proves to be, while staying
  reachable if curriculum effects are real.

Gate pass rule (primary): MEDIUM arm passes Q1 iff both tiers hold AND ≥8 of 12
dyads complete. LOW arm reported descriptively under the same thresholds.

## B.4 Memory-intervention validity

- WIPE_RACK executes immediately before a probe job: RackState replaced with
  empty films + fresh content hash; audit event `RACK_WIPED` records prior
  film count and content hash. Observation permissions unchanged (both actors
  keep normal round-1 full view of an EMPTY rack vs full view of accumulated
  films in intact probes).
- What stays constant across wiped/intact members of a matched pair: latent
  factor layout (difficulty matching), position block, conversation thread,
  actor lifecycles, round budget. Only rack contents differ → any success
  difference is attributable to film-state availability at job start.
- Distinguishability guard: if in-context threads alone drive everything, the
  paired difference is ≈ 0 — which is the informative null that resolves the
  V0 ambiguity (films vs thread as carrier).

## B.5 Effort factor & cohort shape

- Two arms (LOW / MEDIUM), 12 dyads each, matched plan indices across arms
  (same seeds/plans as mechanism allows).
- Primary analyses run on MEDIUM (Q1 gate, Q2 estimand pooled across arms with
  arm as covariate); effort enters as secondary sign-test on paired indices.
- Interleaved pair execution retained but capped at 2 in-flight dyads total;
  sequential fallback mode if infra degrades.

## B.6 Power / attrition

- V0 attrition: 7 of 24 executed dyads aborted under unhardened infra; V1 adds
  preflight + supervision targeting <10% abort. 12/arm with expected ≤2
  abortions/arm leaves ≥10 analyzable dyads/arm.
- Sign test: with 9+ usable matched pairs, 8/9 direction-consistent gives
  p≈0.039 two-sided — adequate for a *replication-direction* claim, explicitly
  not an effect-size claim.
- Paired probe estimand: 12 dyads × 6 probes = 72 observations per arm split
  24 intact / 48 wiped (counterbalanced); McNemar-style within-dyad pairing on
  difficulty-matched structures; exact permutation p reported.

## B.7 Stop/abort/retry rules (frozen text to be implemented literally)

- Infra retry: identical same-session re-launch ≤2×, backoff [4,8]s, only on
  explicit 429/500/502/503/504 delivering no response; attempt-level journaling.
- Arm stop rule (text == implementation): stop scheduling an arm once ≥3 of its
  executed dyads have infrastructure-aborted **and none of its dyads has
  completed**.
- Global halt on any scientific-invariant violation.
- Infrastructure abort ≠ behavioral failure: separate evidence classes exactly
  as V0, with `abort_class` machine-readable.

## B.8 Budget ceiling (declared before freeze; refined at Phase E)

≤ 24 dyads × ~700 calls × ≤450 tok avg completion ≈ ≤17k calls, ≤75M prompt +
≤8M completion tokens; wall-clock ≤ 30 h at ≤2 concurrent dyads.
