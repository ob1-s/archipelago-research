# Competence-gate results

The fixed gate used 10 fresh rollouts per condition, with the preregistered
thresholds of at least 8/10 successes, at least 8/10 non-null policy choices,
at most 2/10 tool-failure traces, and structurally valid traces.

## Gate summary

| model | condition | success | non-null policy | tool-failure traces | errors | decision |
|---|---|---:|---:|---:|---:|---|
| Qwen3.5-0.8B | baseline | 7/10 | 8/10 | 5/10 | 0 | fail |
| Qwen3.5-0.8B | culture-A | 5/10 | 6/10 | 4/10 | 0 | fail |
| Qwen3.5-0.8B | culture-B | 5/10 | 6/10 | 5/10 | 0 | fail |
| Qwen3.5-9B | baseline | 10/10 | 10/10 | 0/10 | 0 | pass |
| Qwen3.5-9B | culture-A | 10/10 | 10/10 | 3/10 | 0 | fail |
| Qwen3.5-9B | culture-B | 10/10 | 10/10 | 0/10 | 0 | fail (model fails another condition) |

Qwen3.5-0.8B is recorded below the useful capability floor and is not scaled.
It frequently stopped after incomplete or invalid tool sequences, and its
failures were not repaired by the unchanged environment.

Qwen3.5-9B is not eligible for scaling under the frozen rule. Its three
Culture-A tool-failure traces were recoverable `release_resource`-before-route-
order mistakes, and all three still obtained the resource, but the preregistered
cap was two failures per condition. The rule is applied literally rather than
relaxed after observing the gate.

Because no new model passed all three gate conditions, there are no new
confirmatory 50-rollout-per-condition runs and no valid cross-model trend
estimate in this archive.

The 9B gate traces show valid A-first/B-first mappings and the exact frozen
artifact strings. No prompt, task, mechanics, parser, sampling, or metric
changes were made.

## Archived gate artifacts

- [structured gate results](gate-results.json)
- [0.8B gate traces](qwen-0.8b/gate)
- [9B gate traces](qwen-9b/gate)
