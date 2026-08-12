# Luna exploratory post-commitment qualification report

## Result

The qualification was stopped after 38 completed rollouts. Luna was clean and
competent in Phase 1, but the requested null harness did not reliably produce
the required Phase-2 policy action after the frozen environment revealed R2.
This is a systematic harness/environment-interface incompatibility for this
runtime, not a measured cultural effect. The planned 20 eligible B-success
rollouts per arm were not reached.

## Primary-cohort observations

| Condition | Eligible Phase-1 B successes | B→A selected | B→B selected | Missing Phase-2 policy | R2 success |
|---|---:|---:|---:|---:|---:|
| Neutral | 3 | 1 | 0 | 2 | 1 |
| Culture-A | 2 | 1 | 0 | 1 | 0 |

The two observed Phase-2 A selections are not a valid treatment comparison:
one completed R2 in Neutral, while the Culture-A selection did not complete R2.
No absolute difference, risk ratio, odds ratio, confidence interval, or Fisher
test is reported because the missing Phase-2 actions are not interpretable as
staying with B, and the target cohort was not collected.

## Phase-1 and order diagnostics

All 38 rollouts successfully completed Phase 1, with no provider/runtime error,
selection ambiguity, or Phase-1 tool failure.

| Phase-1 presentation | Rollouts | Chose A | Chose B |
|---|---:|---:|---:|
| A-first | 30 | 30 | 0 |
| B-first | 8 | 3 | 5 |
| Total | 38 | 33 | 5 |

All five Phase-1 B choices were successful and became eligible for deferred
treatment assignment. The low B yield is consistent with the strong
presentation-order dependence already seen in this environment, but it was not
the stopping reason.

Across all 38 traces, 34 received reward 1 and 4 received reward 0. The four
failures were concentrated among the five B-success candidates because the
second action was absent or R2 was not completed.

## First-pass trace audit

- R2 was not visibly anticipated before the environment revealed it.
- No treatment leakage was observed before the successful Phase-1 B commitment.
- The direct A/B tool interface was used; no left/right mapping confusion was
  observed.
- The old “try the other policy next” pathology cannot be meaningfully assessed
  from the incomplete Phase-2 sample. The failures instead look like premature
  finalization after R1.
- Tool protocol behavior was structurally clean: 134 `/chat/completions`
  requests, 96 assistant tool-call nodes, 96 matching tool results, and no
  provider/runtime errors.
- The null harness’s normal completion path did not issue a continuation after
  the environment’s R2 reveal. The frozen custom post-commitment harness has a
  continuation nudge for this case, but using it would violate the requested
  null-harness condition, so it was not substituted.

## Candidate trace summaries

- Neutral `432896840d84474181fcaa9a58d593eb`: chose B and succeeded on R1; no
  Phase-2 policy action.
- Neutral `f87ad9ae1d0c483fb52ca9f5050d885a`: chose B and succeeded on R1,
  selected A for R2, and completed R2. Visible final content summarized that
  R1 used B and R2 used A.
- Culture-A `6023b46775de4ecd8066449ed6bf779a`: chose B and succeeded on R1,
  selected A for R2, but did not complete R2.
- Neutral `7a49b55c3ec641288a012fd60b406864`: chose B and succeeded on R1; no
  Phase-2 policy action.
- Culture-A `c78d6e2fd6784c289844649963c0f7c0`: chose B and succeeded on R1; no
  Phase-2 policy action.

No visible assistant content provided a reliable stated rationale about the
predecessor convention, switching, or staying. Reasoning-token metadata was
not used to reconstruct hidden reasoning.

## Protocol and comparability notes

The evaluator used `/chat/completions`, with `role="tool"`, matching tool-call
IDs, and ordinary `finish_reason` values (`tool_calls` or `stop`). Usage
included `reasoning_tokens`; 2,113 were observed in total. Reasoning effort was
left unspecified/default/null. The proxy ignored the requested `temperature=0.7`
because it reported temperature unsupported for Luna. These differences make
this exploratory condition non-equivalent to the earlier Qwen runtime.

The proxy was bound to localhost and was stopped after the run. OAuth material
was not copied into this archive or committed.

## Comparison with partial Qwen result

The archived partial Qwen3.5-9B run had Neutral `25/46 = 54.35%` B→A and
Culture-A `26/43 = 60.47%` B→A, a descriptive difference of `+6.1` percentage
points (one-sided Fisher approximately `p=.356`). Luna did not produce enough
interpretable Phase-2 transitions to compare effect sizes. The samples are not
pooled and no cross-model inference is made.

## Recommendation

Treat this archive as a qualification failure for the requested null-harness
configuration, while retaining it as evidence that Luna can operate Phase 1
and the tool protocol. Do not launch another treatment run from this result.
Before any future run, explicitly decide whether the post-commitment
continuation nudge is part of the harness condition; changing to the frozen
custom harness would be a new runtime condition and should be preregistered
separately.

