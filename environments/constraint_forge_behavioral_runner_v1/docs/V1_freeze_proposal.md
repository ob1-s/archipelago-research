# Constraint Forge V1 — Freeze Proposal & GO/NO-GO Report

**Status: AWAITING FINAL GO. No scientific call has been made.**
Code commit `4daf5fa`; 63/63 tests green; MEDIUM qualification complete
(sealed, hash-verified); LOW qualification INCOMPLETE (launch failure — see §9).

## 1. Scientific questions (priority order)
Q1 (gating): does V1 support sustained predecessor competence?
Q2 (primary confirmatory): causal contribution of film-state availability at
job start to coordination expression, on difficulty-matched probe pairs.
Q3 (secondary descriptive): LOW/MEDIUM direction replication (sign test).

## 2. Changes from V0 + justification
Physics bit-identical (round budget stays 16; shared historical package
untouched). Probes: HIDE_RACK removed → within-pair film_intact/film_wiped
contrast via snapshot-and-restore wipe; intact-first pair rotates by
`sequence_index % 3` (adversarial finding 2). New hardened execution package;
V0 preserved untouched. Justifications in `docs/v1_design.md` §B.2/B.9.

## 3. Competence gate (one-shot)
Formation tier: ≥1 formation in ≥60% completed dyads/arm.
Late-competence tier: arm final-eight mean ≥ T = max(0.15, 1.5 × pooled
qualification final-eight mean). MEDIUM qual f8 = 0.0 ⇒ **T = 0.15 now**;
if LOW completes before launch, T updates once from pooled value, then frozen.

## 4. Memory intervention & estimand
WIPE_RACK empties both racks before wiped members (receipt records prior films:
5–6 observed; wiped hashes), snapshot restored after the job — no leakage into
later intact probes (verified in qualification evidence). Estimand: within-dyad
paired success difference intact-vs-wiped (exact permutation);
condition×position interaction pre-registered; simulated power <0.6 ⇒ reported
exploratory. Scope note: tests EXPRESSION; developmental role of films is V2.

## 5. Effort factor role
Secondary/descriptive only. 12+12 matched dyads; sign test on paired indices.

## 6. Cohort size / power / attrition
12 dyads/arm; expected ≤10% infra attrition under hardened layer (V0: ~30%);
matched analyses require both arms completed at that index (pre-registered).

## 7. Job schedule & randomization
Identical block structure to V0 (ordinary 0–3, faults 4–7, ordinary 8–17,
probes 18–23); seeds `constraint-forge/v1-behavioral-sequence-v0:<i>...`;
probe pair conditions per §B.2/#3 with %3 rotation; plans hash-frozen pre-launch.

## 8. Stop/abort/retry rules
Infra retry ≤2 @ [4,8]s on bare 429/5xx only (attempt-journaled); arm stop =
≥3 aborted AND none completed (code == frozen text; regression-tested);
invariant halts global; infra-abort ≠ behavioral failure.

## 9. Qualification results (excluded from science)
MEDIUM: 24/24 jobs, seal completed, 622 calls, 1.77 h; formation at job 14
(ordinary post-fault — substrate alive, not ceiling); final-eight 0.0;
wipe receipts fired on 19/21/23 with prior films 5/6 ✓; no HIDE_RACK anywhere ✓.
LOW: NOT COMPLETED — detached launch failed silently during monitoring gap;
interface was proven in V0 but must be re-qualified before scientific launch
(gate item, decision point #8 of B.9 also requires visible-probe formation
check across qualification dyads).

## 10. Implementation/test status
63/63 tests pass incl. 8 new incident-class regressions (stop-rule text parity,
@ROW protocol, reconcile, preflight fail-fast, schedule contrast/rotation,
wipe-flag scoping, no-HIDE_RACK invariant). Committed & pushed through `4daf5fa`.

## 11. Freeze artifacts (at GO)
Freeze-only run emits manifest + freeze record at HEAD; expected plan hashes
deterministic from seeds above; declared budget ceiling ≤17k calls,
≤75M prompt + ≤8M completion tokens, ≤30h wall at ≤2 concurrent dyads.

## 12. Adversarial review (independent subagent, adjudicated)
8 threats raised; dispositions in `docs/v1_design.md` §B.9. Strongest remaining
risks: (a) wipe detectability/demand effects — mitigated by honest estimand
framing; (b) expression-vs-development scope limit on Q2 — documented, V2
candidate mid-sequence wipes; (c) LOW qualification gap — hard gate before launch;
(d) power for Q2 likely modest — exploratory fallback pre-declared.
