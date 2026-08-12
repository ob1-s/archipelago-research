# Qwen3.5-9B policy-transmission replication

Fresh confirmatory run of frozen `cross_rollout_policy_v1`, 50 fresh rollouts per condition, with no pooling of the archived 9B gate. Environment code: `5e4ba04f7b5f18a06d150a8a38f4e0eeb8a53e26`.

## Primary result

| Condition | Policy A | Policy B | Valid n | Task success |
|---|---:|---:|---:|---:|
| baseline | 21/50 (42%) | 29/50 (58%) | 50 | 50/50 |
| Culture-A | 47/50 (94%) | 3/50 (6%) | 50 | 50/50 |
| Culture-B | 10/50 (20%) | 40/50 (80%) | 50 | 50/50 |

Primary preregistered tests, one-sided Fisher exact:

- Culture-A vs baseline, endpoint A: absolute difference `+0.52`, risk ratio `2.2381`, odds ratio `21.6349`, `p = 9.64e-09`.
- Culture-B vs baseline, endpoint B: absolute difference `+0.22`, risk ratio `1.3793`, odds ratio `2.8966`, `p = 0.01487`.

Both directional hypotheses are supported in this 9B sample. This is evidence of convention-aligned policy selection under this task and setup; it does not establish a general causal theory of culture or a monotonic model-scaling law.

## Exposure and policy timing

| Condition | Artifact available | Artifact read | Aligned among readers | Aligned among non-readers | Selection before read | Selection after read | Policy changed after read |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 0/50 | 0/50 | n/a | n/a | 50 | 0 | 0 |
| Culture-A | 50/50 | 45/50 | 44/45 (97.8%) | 3/5 (60.0%) | 5 | 45 | 0 |
| Culture-B | 50/50 | 37/50 | 36/37 (97.3%) | 4/13 (30.8%) | 13 | 37 | 0 |

The artifact was a researcher-seeded policy-only note, exactly as preregistered. The traces show strong alignment among readers. In this sample, no rollout changed its policy after reading or after a recoverable failure; exposure was generally followed by selection of the noted convention rather than a later switch.

## Validity and recoverable failures

All 150 traces were valid under the revised criterion. There were zero provider/runtime/harness errors, zero missing A/B policies, zero mapping inconsistencies, zero genuinely ambiguous trajectories, and zero task failures. The 21 recoverable mistakes were retained:

| Condition | Recoverable failures | Type | Before/without artifact read | After artifact read | Policy changed after failure |
|---|---:|---|---:|---:|---:|
| baseline | 7 | `release_resource` before route selection | 7 | 0 | 0 |
| Culture-A | 4 | `release_resource` before route selection | 1 | 3 | 0 |
| Culture-B | 10 | `release_resource` before route selection | 4 | 6 | 0 |

These failures are sequencing behavior, not exclusions. They did not make the policy trajectory ambiguous and every rollout still obtained the resource.

## Counterbalancing and exploratory sequencing

Both presentation orders occurred in every condition, and all 150 route-to-policy mappings were consistent. The random order totals were baseline 18 A-first / 32 B-first, Culture-A 23 / 27, and Culture-B 27 / 23; the imbalance is recorded rather than repaired after the run.

| Condition | A-first: A/B | B-first: A/B |
|---|---|---|
| baseline | 18/0 (n=18) | 3/29 (n=32) |
| Culture-A | 23/0 (n=23) | 24/3 (n=27) |
| Culture-B | 9/18 (n=27) | 1/22 (n=23) |

Baseline behavior tracks presentation order strongly. Culture-A shifts choices toward A even when B is presented first; Culture-B shifts choices toward B even when A is presented first. This is a descriptive sequencing observation, not a separate preregistered endpoint. Mean observation counts were baseline 2.92, Culture-A 2.84, and Culture-B 2.74. First-action counts were:

| Condition | Notes read first | Atrium observe first | Release first |
|---|---:|---:|---:|
| baseline | 29 | 21 | 0 |
| Culture-A | 29 | 20 | 1 |
| Culture-B | 29 | 20 | 1 |

## Comparison with archived 4B anchor

The archived Qwen3.5-4B scaled anchor reported baseline A/B `25/25`, Culture-A `42/8`, and Culture-B `4/46`. The fresh 9B replication reports `21/29`, `47/3`, and `10/40`, respectively. Descriptively, both models show bidirectional convention alignment. The 9B A-direction shift is larger (`+0.52` vs `+0.34`), while its B-direction shift is smaller (`+0.22` vs `+0.42`). The runs were not preregistered as a cross-model trend test, so these differences are exploratory and should not be treated as evidence that susceptibility increases or decreases monotonically with capability.

The earlier 10-rollout 9B gate remains archived separately at commit `395118015b3263440315126f72ecec5843fe4bb1` and was not pooled into this sample.

## Archive

- Preregistration: `preregistration.md`
- Frozen run configs: `baseline/run.toml`, `culture-a/run.toml`, `culture-b/run.toml`
- Resolved configs: `baseline/config.toml`, `culture-a/config.toml`, `culture-b/config.toml`
- Raw traces: `baseline/traces.jsonl`, `culture-a/traces.jsonl`, `culture-b/traces.jsonl`
- Evaluator logs: `baseline/eval.log`, `culture-a/eval.log`, `culture-b/eval.log`
- Aggregate machine-readable results: `aggregate-results.json`
- Validity table: `invalid-flagged.md`
- Frozen hashes: `freeze-manifest.txt`

All three raw trace files contain exactly 50 JSONL records.
