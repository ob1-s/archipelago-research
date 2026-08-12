# Cross-model policy-transmission generalization

## Outcome

No new model passed the preregistered competence gate, so there are **no new
50-rollout-per-condition confirmatory runs** and no valid cross-model
susceptibility trend estimate. This is a gate-limited result, not evidence that
the Qwen3.5 policy effect failed to generalize.

The archived 4B anchor remains:

| model | baseline A/B | Culture-A A/B | Culture-B A/B | success |
|---|---:|---:|---:|---:|
| Qwen3.5-4B (archived scaled) | 25/25 | 42/8 | 4/46 | 50/50 in all |

Its archived one-sided Fisher tests were `p=0.0002780` for Culture-A increasing
A and `p=0.00000255` for Culture-B increasing B.

## Competence gates

| model | condition | A | B | no policy | success | reads | tool-failure traces | gate |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Qwen3.5-0.8B | baseline | 5 | 3 | 2 | 7/10 | 0/10 | 5/10 | fail |
| Qwen3.5-0.8B | Culture-A | 2 | 4 | 4 | 5/10 | 1/10 | 4/10 | fail |
| Qwen3.5-0.8B | Culture-B | 5 | 1 | 4 | 5/10 | 1/10 | 5/10 | fail |
| Qwen3.5-9B | baseline | 7 | 3 | 0 | 10/10 | 0/10 | 0/10 | fail overall |
| Qwen3.5-9B | Culture-A | 9 | 1 | 0 | 10/10 | 10/10 | 3/10 | fail overall |
| Qwen3.5-9B | Culture-B | 0 | 10 | 0 | 10/10 | 9/10 | 0/10 | fail overall |

The fixed gate required at least 8/10 success, at least 8/10 non-null policy
choices, at most 2/10 tool-failure traces in every condition, and valid trace
structure. Qwen3.5-0.8B failed the task-success, policy, and failure-rate
requirements. Qwen3.5-9B met the success and policy requirements, but its
Culture-A condition had 3/10 recorded tool failures, exceeding the preregistered
cap. Those failures were recoverable route-order mistakes and all ten rollouts
succeeded, but the cap was applied literally; it was not relaxed after seeing
the outcome.

## What the gate traces show

The 9B gate already shows the expected directional pattern descriptively: 9/10
A in Culture-A and 10/10 B in Culture-B, versus 7/3 A/B in baseline. Artifact
read rates were 10/10 and 9/10 respectively, with aligned choices among readers
of 9/10 A and 9/9 B. These are only 10-rollout gate observations and are not
reported as confirmatory effect estimates or p-values.

The 0.8B traces show incomplete tool sequences, invalid area calls, and early
stopping; this is why it was not scaled. The environment and typed tool schema
were left unchanged.

Presentation mappings remained valid in every archived gate trace. The exact
artifact wording, prompt, task logic, sampling, harness, runtime, metrics, and
counterbalancing were unchanged. The 4B anchor was not rerun.

## Archive

- [preregistration](preregistration.md)
- [freeze manifest](freeze-manifest.txt)
- [provider model snapshot](model-availability.txt)
- [gate summary](GATE.md)
- [gate aggregate JSON](gate-results.json)
- [full aggregate JSON](aggregate-results.json)
- [0.8B gate traces and configs](qwen-0.8b/gate)
- [9B gate traces and configs](qwen-9b/gate)

No post-commitment policy-switch environment was built.
