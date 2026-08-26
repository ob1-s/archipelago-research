# R2 qualification outcome (2026-08-26, predeclared adjudication)

## Execution

MEDIUM dyad, frozen L1 knobs (mutation 12 / write 4 / rounds 24), fresh
seeds `constraint-forge/r2-qualification-v0`: sealed `completed` 24/24,
810 calls, zero infra retries. LOW dyad NOT RUN (frozen rule: MEDIUM
failure ends the round; LOW's one-shot remains banked for the next named
round).

## Gates

| gate | result | verdict |
|---|---|---|
| Tier 1 participation | X 23/24, Y 21/24, 45 delivered writes | PASS |
| Tier 2 competence | 5/24 successes incl 4 ordinary | PASS |
| Tier 3 measurability | 5 successes (<6) AND 1 distinct agreed symbol (<2) | FAIL |
| Ceiling | trivially satisfied | PASS |
| Infra | clean seal | PASS |

ROUND VERDICT: NO-GO for an R2-based scientific cohort. No re-rolls.

## Reading (evidence-backed)

1. Difficulty calibration worked mechanically: success moved from 0/24
   (R1) into the calibration band and qualified at 5/24 under fresh seeds -
   the L1 slack lever does what it claims without touching task structure.
2. The binding constraint moved again: participation (V1) -> base
   competence (R1) -> CONVENTION DIVERSITY (R2). The register channel is
   used and successful, but pairs collapse onto the Schelling-default
   symbol 0 in every job. Films therefore persist no convention that could
   not be regenerated from scratch, so a future intact-vs-wiped film
   contrast has nothing to detect. Tier 3's >=2-distinct-symbols clause
   was designed for exactly this degeneracy and fired correctly.
3. Predeclaration inconsistency to own: the calibration band floor (2/24)
   sits below what Tiers 2+3 jointly demand at qualification (>=6
   successes with diversity). A rung can pass calibration and still fail
   qualification - as happened. Rules were followed as written; the
   mismatch goes into next-round design as a required fix (align band
   floor with the qualification tiers' joint requirement).

## Next-round shape (proposal, not committed)

R3 candidates, in order of parsimony: (a) make X's lead symbol costly to
fixate at 0 - e.g., per-job private salience structure so the non-void
lead varies; (b) void drawn from a distribution that disfavors 0; (c)
two-register conjunct (register 0 AND register 1 must agree), doubling
convention surface. Any R3 re-runs model-free screens and keeps operator
infra directives. Budget note: this window consumed ~16M prompt tokens
across calibration + qualification; LOW remains unspent.
