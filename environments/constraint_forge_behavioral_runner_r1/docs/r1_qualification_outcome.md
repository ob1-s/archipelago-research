# R1 qualification outcome (2026-08-26, predeclared adjudication)

## Execution record

- Attempt 1 (MEDIUM): sealed `aborted` at 15/24 jobs — provider usage limit;
  infra event, one clean relaunch declared before relaunch (see
  qual_artifacts/INFRA_EVENT_medium_attempt1.md); excluded from evaluation.
- Attempt 2 (MEDIUM): sealed `completed`, 24/24 jobs, 683 live calls,
  1 recovered infra retry, ~60 min wall. Evidence + sha256-verified summary
  committed alongside this document.
- LOW dyad: NOT RUN. Frozen rule: MEDIUM gate failure ends the round without
  spending the LOW opportunity. LOW retains its unspent one-shot for the next
  named round on whatever substrate follows.

## Gate adjudication (frozen rules, r1_gatecheck.py)

| gate | result | verdict |
|---|---|---|
| Tier 1 participation (>=14/24 jobs per station) | X 20/24, Y 18/24, 39 delivered writes | PASS |
| Tier 2 competence (>=3 successes incl ordinary) | 0/24 successful | FAIL |
| Tier 3 measurability (>=6 successes, >=2 symbols) | 0 successes | FAIL |
| Ceiling (<=20/24) | trivially satisfied | PASS |
| Infrastructure validity | completed seal, retries within budget | PASS |

ROUND VERDICT: NO-GO for an R1-based scientific cohort.

## Diagnosis of the failure (evidence-backed)

The redesign achieved exactly what it targeted, and nothing else blocked:

1. PARTICIPATION FIXED. Prior generations delivered <=4 writes per dyad in
   total; R1-MEDIUM delivered 39, with both stations writing in 17/24 jobs.
2. REGISTER COORDINATION EMERGED. Every job where both stations' final
   register-0 values were non-null shows AGREEMENT (0 mismatches). Y tracks
   X's symbol, including non-default choices (3 jobs where X led with
   symbol 1 were echoed by Y). The leader/follower signal path works.
3. THE CONJUNCT NEVER BOUND: world_success = 0/24. The base n=6 private-mask
   matching task is above the model's medium-effort ceiling on this instance
   stream (V1 qualification: 1/24; V0 late-block ceiling ~0.25). R1 added no
   new failure mode; it inherited the old one.
4. Null-register jobs (7) are explained by fault/probe jobs and early-finish
   paths, not by refusal to engage.

## Consequence for the next named round (proposal sketch)

Substrate R2 = R1 + calibrated base difficulty (the lever explicitly
deferred in r1_design.md): shrink or restructure the matching problem until
medium-effort job success sits inside a measurable band (~15-50%), keeping
the register conjunct, private void, film machinery, and probe contrast
unchanged. Model-free screens S1-S5 must be re-run on the calibrated
generator. Operator directives for infra leniency already committed
(docs/r1_operator_directives_for_next_round.md): per-job checkpointing,
park-on-quota, partial-evidence descriptives, cheap smoke probes, phase
budgets sized to one quota window.
