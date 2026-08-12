# GPT-5.6 Luna exploratory qualification report

## Scope

This is a 30-rollout exploratory qualification of the frozen
`cross_rollout_policy_v1` taskset. It is not a confirmatory replication, was
not pooled with Qwen results, and does not support model-scaling or causal
claims.

Runtime condition:

```text
GPT-5.6-Luna via ChatGPT OAuth / OpenAI-compatible chat proxy
```

Proxy version and source commit, resolved configs, evaluator logs, traces, and
protocol audit are archived beside this report.

## Aggregate results

| Condition | Valid | Success | Final A | Final B | Artifact available | Artifact read | Read before policy | Recoverable failures |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 10/10 | 10/10 | 6 | 4 | 0/10 | 0/10 | n/a | 0 |
| Culture-A | 10/10 | 10/10 | 10 | 0 | 10/10 | 10/10 | 10/10 | 0 |
| Culture-B | 10/10 | 10/10 | 1 | 9 | 10/10 | 9/10 | 9/10 | 0 |

There were no ambiguous policy selections, no task failures, and no
infrastructure errors in the intended 30-rollout sample.

The first detached-proxy attempt produced 10 zero-turn provider errors. It is
archived separately and excluded from the table above.

## Artifact contact and policy timing

- Baseline had no available predecessor artifact.
- Culture-A: all 10 rollouts read the policy-only A artifact; none selected a
  policy before reading it, and all 10 selected A afterward.
- Culture-B: 9 rollouts read the policy-only B artifact; none of those 9 had a
  policy action before the read. Eight readers selected B and one reader
  selected A. The single nonreader selected B without reading the artifact.
- No rollout changed policy after artifact reading.
- No rollout changed policy after a failure; there were no failures.
- No assistant trace explicitly argued that it discounted or rejected the
  predecessor convention. The one discordant case was the Culture-B reader
  that read the B artifact and subsequently selected A.

Reader-aligned descriptive rates:

```text
Culture-A readers: 10/10 chose A
Culture-B readers:  8/9 chose B
Culture-B nonreaders: 1/1 chose B
```

These reader/nonreader subsets are descriptive only and were not treated as
causal estimates.

## Presentation-order checks

| Condition | A-first (A/B) | B-first (A/B) |
|---|---|---|
| Baseline | 6/0 | 0/4 |
| Culture-A | 2/0 | 8/0 |
| Culture-B | 1/2 | 0/7 |

Both presentation orders occurred in every condition. The small qualification
has uneven order counts, and Luna's baseline followed presentation order
exactly (6/6 A-first A; 4/4 B-first B). This makes the baseline highly
deterministic and is an important interpretability caveat, not evidence of a
model law.

## Tool/protocol behavior

All 208 intended-sample model calls were recorded as `/chat/completions`.
There were 178 standard tool-call turns and 30 final stop turns. All 178 tool
results used `role="tool"`; all tool-call IDs and tool-result IDs were present,
unique, and matched. Tool-call assistant messages had `content: null`, with
ordinary function names and JSON arguments. The trace contained reasoning-token
usage metadata but no separate reasoning message/content field.

Luna's tool behavior was clean in this sample: no malformed calls, no tool
failures, no ambiguous mappings, and the same multi-turn environment loop used
by the prior Qwen runs. Final assistant prose varied slightly (`via policy A/B`,
`through policy A/B`, or a generic success sentence), but scoring came from the
environment state and all 30 tasks succeeded.

The runtime is not sampling-equivalent to Qwen: Verifiers sent
`temperature=0.7`, but the proxy warned that temperature is unsupported for
this reasoning model and ignored it. No emulation or task-specific adjustment
was attempted.

## Exploratory interpretation

Luna was fully competent on this frozen taskset: 30/30 intended rollouts
succeeded without tool or runtime errors. Its neutral baseline was highly
deterministic and presentation-order-following. In the two seeded culture
conditions, choices were directionally aligned with the available convention:
10/10 A under Culture-A and 9/10 B under Culture-B, with 19/20 artifacts read.

This is consistent with the same qualitative directional pattern seen in the
Qwen archives, but the sample is small, the effective sampling differs, and
the ChatGPT OAuth proxy is a distinct runtime. The result should therefore be
read as a successful Luna qualification and a qualitative compatibility signal,
not as an apples-to-apples Qwen replication or a causal estimate.

It does not support claims about model-size scaling, capability laws, the
Archipelago governance thesis, or post-commitment cultural override.
