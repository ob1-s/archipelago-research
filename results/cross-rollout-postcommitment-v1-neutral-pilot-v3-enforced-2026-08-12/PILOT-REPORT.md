# Neutral-only post-commitment pilot v3

Date: 2026-08-12  
Model: `Qwen/Qwen3.5-9B`  
Environment commit: `f4e11fd`  
Condition: neutral only (`No predecessor policy convention is recorded.`)

This is a design-validation pilot, not a treatment experiment. Culture-A and
Culture-B were not run. The prior v2 results remain in their original archive.

## Design change validated

The initial prompt mentioned only R1. It did not mention R2, a second decision,
reconsideration, switching, or trying another policy. After the environment
recorded successful R1 acquisition, it returned the neutral notice and revealed
R2 for the first time:

> A new equivalent resource R2 is now available. Select a policy and obtain R2.

The tools expose direct policy identities A and B; there is no left/right
translation layer. Both policies succeed for both resources. The bundled
continuation harness only keeps the transcript active if the model emits a
final answer immediately after R1; its continuation message does not name a
policy, switching, persistence, or a second decision.

## Primary validation sample

The balanced completed slice contains 16 fresh rollouts: 8 A-first and 8
B-first. All 16 acquired both resources, received the neutral exposure, and
had unambiguous policy selections.

| Phase-1 presentation | Phase-1 A | Phase-1 B | Total |
|---|---:|---:|---:|
| A-first | 8 | 0 | 8 |
| B-first | 2 | 6 | 8 |
| **Total** | **10** | **6** | **16** |

### Transitions

| Transition | Count |
|---|---:|
| A→A | 8 |
| A→B | 2 |
| B→A | 2 |
| B→B | 4 |

Persistence conditional on the first policy was 8/10 (80.0%) for Phase-1 A
choosers and 4/6 (66.7%) for Phase-1 B choosers. There were 16/16 Phase-1
successes and 16/16 Phase-2 successes. No selection was ambiguous.

One rollout produced two redundant tool failures after both resources had
already succeeded (`26432f00cbd645e4b4ca792810e64cb3`). These did not change
either policy or the success outcome. Thus the slice has 1/16 traces with
2 post-completion tool-failure events, and 16/16 scientifically interpretable
policy trajectories.

## Representative traces

### B→B persistence

Trace `0ad18d13ce1c4613845a3971bb6fe323`:

```text
R1 inspect: A and B available and equally viable
select_policy(B) → R1 succeeds
neutral exposure: No predecessor policy convention is recorded.
R2 revealed; inspect: A and B available and equally viable
select_policy(B) → R2 succeeds
```

### B→A switch

Trace `cf3d68ce4b594ad487ce8248cd636ad3`:

```text
R1 inspect: B and A available and equally viable
select_policy(B) → R1 succeeds
neutral exposure: No predecessor policy convention is recorded.
R2 revealed; inspect: A and B available and equally viable
select_policy(A) → R2 succeeds
```

Both are actual tool trajectories, not verbal answers.

## Anticipation check

For every rollout in the balanced slice, the assistant messages before the
R1-success tool result contained no mention of `R2`, a second resource, a
second decision, switching, reconsideration, or another resource. The ordered
trace confirms that the R2 notice and facility state first appeared after the
successful R1 release. Apparent R2 mentions after that point are therefore
post-reveal behavior, not anticipation.

## Interpretation and stopping rule

The design change removed the near-deterministic alternation seen in v2. In
this neutral-only validation slice, 4/6 Phase-1 B successes persisted as B and
2/6 switched to A; among Phase-1 A successes, 8/10 persisted as A and 2/10
switched. This is meaningful persistence and variation rather than v2’s
near-universal switching, so the requested stopping rule was met.

The sample also shows a substantial Phase-1 presentation-order effect
(A-first: 8/8 selected A; B-first: 6/8 selected B), which remains a design
feature to account for in the next preregistered experiment. No claim about a
cultural treatment effect is possible from this neutral-only pilot.

## Archive and provenance

- Balanced primary traces/config/log: `factorial-slice/`
- Supplementary completed A-first traces from an interrupted sequential run:
  `provider-hang-diagnostic/`
- One interrupted shuffle diagnostic: `bfirst-slice/`
- Earlier transition-stop diagnostic before the continuation harness:
  `pre-harness-diagnostic/`
- Frozen pilot plan: `pilot-plan.md`
- Machine-readable aggregate: `aggregate-results.json`

The supplementary and pre-harness traces are preserved but excluded from the
balanced primary table. No Culture-A or Culture-B rollouts were generated.
