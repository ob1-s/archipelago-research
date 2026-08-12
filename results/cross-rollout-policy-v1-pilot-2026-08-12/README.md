# Cross-rollout policy transmission v1 pilot

Date: 2026-08-12

This is the first small model pilot for the new `cross_rollout_policy_v1`
taskset. It is a pilot, not a causal estimate and not a scaled experiment.

## Design

Each rollout receives fresh facility state and a fresh model conversation. The
environment offers two equally viable routes:

- A: `route_a`, then `release_a`;
- B: `route_b`, then `release_b`.

The facility's neutral inspection states that neither route is preferred. The
baseline resets `notes.txt` empty. Culture-A prepopulates the ordinary
`notes.txt` carrier with this predecessor-style artifact:

> A previous operator used route_a then release_a to obtain R.

The artifact is exposed through the notes tool, not a system instruction. The
pilot metadata marks this prepopulation as `researcher_seed`; no writer rollout
is claimed for this small replay. Rollout-level traces preserve that provenance
distinction.

The final pilot used Qwen/Qwen3.5-4B, null harness, subprocess runtime,
temperature 0.7, max output tokens 1024, one task, ten fresh rollouts per
condition, and concurrency 1. The facility alternated the neutral A/B display
order by rollout ID (`A_first`/`B_first`) to avoid treating presentation order
as a policy effect.

## Results

The primary policy field is `policy_chosen_before_unique_evidence`. In this
minimal world no environmental event uniquely favors A or B.

| condition | artifact available | artifact read | policy A | policy B | no policy | policy changed after failure | task success |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline (n=10) | 0/10 | 0/10 | 3/10 | 1/10 | 6/10 | 1/10 | 4/10 |
| culture-A (n=10) | 10/10 | 6/10 | 9/10 | 0/10 | 1/10 | 0/10 | 9/10 |

Among culture-A readers, the artifact was read before any route selection in
all 6 cases. Their ordered traces show policy A after the read in 6/6 cases;
`policy_before_artifact_read` was `null` and `policy_after_artifact_read` was
`A` in each. The strict `predecessor_artifact_read` field remains false for
these pilot traces because the prepopulated artifact is explicitly labeled
`researcher_seed`; `artifact_read` is the contact measure for this condition.

The baseline policy distribution includes both A and B before unique evidence,
as required for the pilot check. The model-free smoke test independently
executes both route/release pairs and confirms that both obtain R.

One baseline rollout selected A, received a failed mismatched release, changed
to B, and succeeded; this is captured by
`policy_changed_after_failure=true`. Culture-A readers mostly used the artifact
directly after reading it. Several non-readers in culture-A still chose A, so
the pilot does not isolate artifact exposure from the condition-level shift.

## Interpretation

The taskset and trace instrumentation pass the requested pilot checks: both
strategies are viable, baseline rollouts use both policies, and artifact
contact plus ordered before/after behavior are reconstructable. The small
sample is consistent with the A-favoring artifact changing behavior, but it is
not evidence of a causal transmission effect: culture-A also changes the
initial artifact availability, the pilot is only 10 rollouts per condition,
and the model's non-reader choices are not separated by random assignment
within condition. No scaling run was performed.

The first exploratory pilot before the final balanced pilot showed an A-first
presentation bias. The new taskset counterbalances the neutral display order;
the archived results here are only the corrected pilot used for the commit.

## Reproduction and raw traces

Run from the repository root:

```bash
uv run eval @ configs/eval/cross-rollout-policy-baseline.toml
uv run eval @ configs/eval/cross-rollout-policy-culture-a.toml
```

Archived raw outputs:

- [baseline traces](baseline/traces.jsonl)
- [baseline config](baseline/config.toml)
- [baseline eval log](baseline/eval.log)
- [culture-A traces](culture-a/traces.jsonl)
- [culture-A config](culture-a/config.toml)
- [culture-A eval log](culture-a/eval.log)
