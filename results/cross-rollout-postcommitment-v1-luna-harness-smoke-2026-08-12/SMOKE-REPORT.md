# Smoke report

## Outcome

The original custom post-commitment harness worked with Luna in this smoke:

- 8/8 rollouts completed with reward 1.
- 3/3 eligible Phase-1-B successes completed the R2 decision and release.
- No provider/runtime errors, selection ambiguities, or tool failures.
- All 8 traces stopped as `agent_completed`.
- The custom continuation nudge was not needed in any of the 8 traces; Luna
  continued directly after the R1 tool result in every eligible B trace.

This validates the harness lifecycle mechanically. It does not estimate a
cultural effect: all three eligible B-success rollouts happened to receive
Culture-A under the frozen assignment rule, leaving no Neutral B-success smoke
observations.

## Rollout summary

| Phase-1 order | Rollouts | A | B | Phase-1 success |
|---|---:|---:|---:|---:|
| A-first | 4 | 4 | 0 | 4 |
| B-first | 4 | 1 | 3 | 4 |
| Total | 8 | 5 | 3 | 8 |

Eligible B-success traces:

| Condition | n | B→A | B→B | R2 success |
|---|---:|---:|---:|---:|
| Neutral | 0 | 0 | 0 | 0 |
| Culture-A | 3 | 3 | 0 | 3 |

The three Culture-A eligible traces were:

- `2de05f4ef26d44bdbbd918aa63166299`
- `9fb14b1d63a14114ad443b15434f7cfb`
- `9eae9a70e87548249b15fea88af70e1c`

All three followed the sequence `B/R1 success → Culture-A exposure → select A
for R2 → R2 success`. The five Phase-1-A traces correctly received no Phase-2
exposure and were retained as valid raw traces.

## Protocol audit

- Model calls: 34
- Endpoint: `/chat/completions` only
- Assistant tool calls: 26
- Tool results: 26
- Tool-call IDs matched tool-result IDs: yes
- Finish reasons: `tool_calls=26`, `stop=8`
- Observed reasoning tokens: 483
- No hidden reasoning was inspected or reconstructed.

The proxy emitted its known warning for each request that the requested
`temperature=0.7` is unsupported for Luna and ignored it. No credentials were
stored in the archive. The proxy was localhost-only and stopped after the run.

## Interpretation

The earlier null-harness failure was a harness-lifecycle mismatch, not a Luna
tool or competence failure. This smoke supports using the custom Qwen harness
for the future Luna post-commitment qualification so that the model/runtime
comparison changes the model condition without silently changing the
multi-stage apparatus.

No confirmatory or treatment conclusion should be drawn from this smoke.

