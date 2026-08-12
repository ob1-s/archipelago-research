# Cross-rollout policy transmission v1: preregistered scaled experiment

Date: 2026-08-12
Environment: `cross-rollout-policy-v1` at commit `50ac443`
Model: Qwen/Qwen3.5-4B
N: 50 baseline + 50 culture-A

## Frozen analysis plan

The analysis plan was frozen before model calls in
[preregistration.md](preregistration.md). The primary endpoint was
`policy_chosen_before_unique_evidence == "A"`, with all 50 assigned rollouts
retained in each denominator. No-policy would count as not-A; no rollout was
excluded or retried.

## Main result

| condition | policy A | policy B | no policy | task success |
|---|---:|---:|---:|---:|
| baseline (n=50) | 25/50 (50.0%) | 25/50 (50.0%) | 0 | 50/50 |
| culture-A (n=50) | 42/50 (84.0%) | 8/50 (16.0%) | 0 | 50/50 |

Effect size, culture-A minus baseline:

- absolute risk difference: **+0.34** (+34 percentage points);
- risk ratio: **1.68**;
- odds ratio: **2.10**.

The preregistered one-sided Fisher exact test on

```text
                 policy A   not policy A
baseline             25           25
culture-A            42            8
```

gives **p = 0.0002780165** for the directional alternative that culture-A has a
higher policy-A rate.

## Secondary/descriptive results

| condition | artifact available | artifact read | A among readers | A among non-readers | changed after artifact read | changed after failure | success |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 0/50 | 0/50 | n/a | 25/50 | 0/50 | 0/50 | 50/50 |
| culture-A | 50/50 | 39/50 (78.0%) | 38/39 (97.4%) | 4/11 (36.4%) | 0/50 | 0/50 | 50/50 |

All 39 culture-A readers selected a policy after the artifact read; 38 chose A
and 1 chose B. `policy_before_artifact_read` was null for every rollout, so the
trace does not show an already-selected policy being changed after reading.
The descriptive reader/non-reader split is not the preregistered causal test:
exposure was voluntary and the reader denominator is only 39.

## Left/right counterbalancing checks

The frozen task mapping was consistent in every inspected trace. The observed
assignment and policy counts were:

| condition | mapping | rollouts | A | B |
|---|---|---:|---:|---:|
| baseline | A-first | 23 | 23 | 0 |
| baseline | B-first | 27 | 2 | 25 |
| culture-A | A-first | 25 | 25 | 0 |
| culture-A | B-first | 25 | 17 | 8 |

In A-first, left maps to A; in B-first, left maps to B and right maps to A.
The baseline mapping counts are 23/27 and culture-A counts are 25/25. The
baseline arm mostly chose the left option (23 A-first left choices and 25
B-first left choices), while culture-A selected the A-mapped option in 17 of 25
B-first rollouts. This is consistent with the policy-level shift and confirms
that the result is not simply an artifact of naming `left` as A.

## Runtime and provenance

All 100 rollouts were `ok`, completed successfully, and had no captured errors
or retries. There were two baseline and eight culture-A rollouts with an
environment failure event, but none changed policy after failure and all still
obtained the resource.

The culture-A note was the frozen policy-only text and was prepopulated at each
rollout boundary. Trace metadata labels it `researcher_seed`, so this experiment
tests the effect of exposure to a predecessor-style policy artifact; it does
not test spontaneous production of that artifact by an earlier rollout.

## Archive

- [preregistration](preregistration.md)
- [aggregate JSON](aggregate-results.json)
- [freeze manifest](freeze-manifest.txt)
- [baseline raw traces](baseline/traces.jsonl)
- [baseline resolved config](baseline/config.toml)
- [baseline source config](baseline/run.toml)
- [culture-A raw traces](culture-a/traces.jsonl)
- [culture-A resolved config](culture-a/config.toml)
- [culture-A source config](culture-a/run.toml)
