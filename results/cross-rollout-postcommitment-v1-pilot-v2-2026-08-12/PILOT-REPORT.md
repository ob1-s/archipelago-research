# Post-commitment cultural override pilot report

## Bottom line

The v2 taskset works mechanically and is fully traceable, but this pilot is not a
clean readiness signal for a confirmatory override test. It produced both direct
Phase-1 A and B actions, but the initial choice was almost entirely determined by
which policy was listed first: 16/16 A-first prompts produced A, while 14/16
B-first prompts produced B. Among the Phase-1 B-success cohort, the neutral control
already produced `B→A` in 2/2 cases, and there were no `B→B` cases in any condition.
Therefore no confirmatory scaling should begin from this pilot without deciding how
to handle the strong presentation-order baseline and the absence of persistence.

This is a pilot/design result, not a cultural-effect estimate.

## Validation counts

The pilot used 4 factorial presentation variants × 8 fresh Qwen/Qwen3.5-9B
rollouts, with the preregistered-style null harness, subprocess runtime, temperature
0.7, and 1024 maximum tokens.

| Check | Result |
|---|---:|
| Rollouts | 32/32 |
| Evaluator `ok` | 32/32 |
| Both resources obtained | 32/32 |
| Phase-1 A choices | 18 |
| Phase-1 B choices | 14 |
| Phase-1 B successes | 14 |
| Exact exposure after Phase-1 success | 32/32 |
| Phase-2 A choices | 16 |
| Phase-2 B choices | 16 |
| Policy-selection ambiguity | 0 |
| Tool failures | 0 |
| Infrastructure/runtime errors | 0 |

Assigned exposure conditions were neutral 13, Culture-A 8, and Culture-B 11. The
exact assigned notices are stored in every trace and were delivered in the
Phase-1-success tool response only.

## Transition table

| Assigned condition | Phase-1 B-success cohort | B→A | B→B |
|---|---:|---:|---:|
| neutral | 2 | 2 | 0 |
| Culture-A | 6 | 6 | 0 |
| Culture-B | 6 | 6 | 0 |

Across all rollouts, transitions were `A→A=2`, `A→B=16`, `B→A=14`, and `B→B=0`.
The primary cohort is too small for inference, and the neutral B→A ceiling means
the current pilot does not establish usable control variation for the proposed
directional test.

## Exposure and trace checks

Every rollout has the ordered structure:

```text
Phase-1 select_policy(A|B)
→ Policy {A|B} succeeded. Resource R1 obtained.
→ exact neutral/Culture-A/Culture-B notice
→ Phase-2 select_policy(A|B)
→ Policy {A|B} succeeded. Resource R2 obtained.
```

The notice is direct and unavoidable: it is part of the successful `release_resource`
response, not a voluntary notes read. The second selection is a real tool call and
has no mechanical carryover from the first. The four presentation combinations were
balanced at 8 rollouts each, and the trace records the two orders independently.

Representative clean direct-switch trace: `64dffa7e597743349cd35516819b967f`
(Culture-A, `B→A`), in `traces.jsonl`.

## Interpretation

The environment implementation satisfies the core mechanics: direct A/B tools,
equal success, clear Phase-1 success, post-success exposure, actual Phase-2 choice,
all transition classes in the schema, and complete ordered traces. The pilot also
reveals a major behavioral baseline: Qwen follows the first-listed policy in Phase 1
with near-deterministic consistency, and all observed Phase-1 B rollouts switched on
the second decision. That may reflect presentation/variety behavior rather than
cultural override.

The earlier fixed-A-wording pilot is retained at
`../cross-rollout-postcommitment-v1-pilot-2026-08-12/` and documented in its
`INITIAL-PILOT-REPORT.md`. It produced 30/30 A choices and motivated this factorial
counterbalance. The v2 result is an improvement in instrumentation and coverage,
but not yet a validated confirmatory design.

No large confirmatory run or statistical test was performed.

## Archive

- `run.toml`: resolved pilot request
- `pilot-plan.md`: pre-run validation plan
- `config.toml`: evaluator-resolved configuration
- `traces.jsonl`: all 32 raw traces
- `eval.log`: evaluator log
- `aggregate-results.json`: machine-readable aggregate
- `PILOT-REPORT.md`: this validation report
