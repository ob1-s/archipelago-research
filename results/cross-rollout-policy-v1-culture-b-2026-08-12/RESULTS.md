# Culture-B directional-reversal results

This is the preregistered 50-rollout Culture-B run on corrected
`cross_rollout_policy_v1`. The run used Qwen/Qwen3.5-4B, the null harness,
subprocess runtime, temperature 0.7, maximum 1024 tokens, one rollout at a
time, and no retries. The task logic, typed interface, prompt, sampling, and
counterbalancing were frozen before model calls.

## Primary result

| condition | policy A before unique evidence | policy B before unique evidence | n |
|---|---:|---:|---:|
| frozen baseline | 25/50 (50.0%) | 25/50 (50.0%) | 50 |
| culture-B | 4/50 (8.0%) | 46/50 (92.0%) | 50 |

The preregistered endpoint was `policy B before uniquely favoring evidence`.
Culture-B increased the B rate by **0.42** relative to baseline (risk ratio
**1.84**, odds ratio **11.5**). The one-sided Fisher exact test for the frozen
directional alternative, Culture-B B rate greater than baseline B rate, gives

```text
p = 0.000002548703737423585
```

The result is consistent with a directional policy-choice shift toward the
artifact's favored policy. It is not evidence that the artifact improved raw
task capability: both conditions succeeded 50/50.

## Artifact exposure and ordered behavior

| condition | artifact available | artifact read | B among readers | B among non-readers | task success |
|---|---:|---:|---:|---:|---:|
| frozen baseline | 0/50 | 0/50 | — | 25/50 | 50/50 |
| frozen culture-A | 50/50 | 39/50 | 1/39 | 8/11 | 50/50 |
| culture-B | 50/50 | 43/50 | 43/43 | 3/7 | 50/50 |

Among Culture-B readers, every rollout read the exact frozen text
`Previous operators here generally choose policy B.` and then selected B.
Seven rollouts did not read the artifact; three selected B and four selected A.
All 50 Culture-B rollouts had no policy selected before the artifact-read
boundary, so the paired `policy_changed_after_artifact_read` field is 0/50 by
definition: the readers made their first recorded policy choice after reading,
rather than switching from an already selected policy. No rollout changed
policy after a failure. Two rollouts attempted `release_resource` too early;
both subsequently selected B and succeeded.

Artifact contact was ordered and reconstructable: 20 first read at event index
0, 23 first read at index 3 after the three area observations, and 7 never read.
There were no successor-facing writes in this run. Trace metadata labels the
prepopulated artifact `researcher_seed`; this run tests exposure to a
predecessor-style policy artifact, not spontaneous artifact production by a
previous rollout.

## Counterbalancing sanity check

The option-to-policy mapping was unchanged and consistent in every trace.
`A_first` means left selects A; `B_first` means left selects B.

| condition | mapping | n | A | B |
|---|---|---:|---:|---:|
| frozen baseline | A-first | 23 | 23 | 0 |
| frozen baseline | B-first | 27 | 2 | 25 |
| frozen culture-A | A-first | 25 | 25 | 0 |
| frozen culture-A | B-first | 25 | 17 | 8 |
| culture-B | A-first | 30 | 4 | 26 |
| culture-B | B-first | 20 | 0 | 20 |

The Culture-B shift is visible in both mappings: it selected B in 26/30
A-first rollouts and 20/20 B-first rollouts. The realized Culture-B mapping
split was 30/20 rather than exactly 25/25 because presentation order is assigned
from the fresh rollout trace IDs; the mapping itself remained symmetric.

## Direct A/B symmetry

| condition | artifact available | artifact read | A | B | success |
|---|---:|---:|---:|---:|---:|
| baseline | 0/50 | 0/50 | 25/50 | 25/50 | 50/50 |
| culture-A | 50/50 | 39/50 | 42/50 | 8/50 | 50/50 |
| culture-B | 50/50 | 43/50 | 4/50 | 46/50 | 50/50 |

The archived Culture-A directional comparison was 42/50 A versus 25/50 A in
baseline (one-sided Fisher p = 0.0002780165). The new preregistered Culture-B
comparison is 46/50 B versus 25/50 B (p = 0.0000025487). This three-condition
table is a symmetry summary; the confirmatory test for this kickoff was
Culture-B versus baseline with B as the endpoint.

## Archive

- [aggregate results](aggregate-results.json)
- [preregistration](preregistration.md)
- [freeze manifest](freeze-manifest.txt)
- [Culture-B raw traces](culture-b/traces.jsonl)
- [Culture-B resolved config](culture-b/config.toml)
- [Culture-B source run config](culture-b/run.toml)
- [evaluator log](culture-b/eval.log)

The taskset extension was committed separately as `5e4ba04`; the preregistration
and source run config were frozen in `916f27b` before the 50 model calls.
