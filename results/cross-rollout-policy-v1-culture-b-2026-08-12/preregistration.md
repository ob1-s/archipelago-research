# Culture-B directional-reversal experiment

Frozen before the first Culture-B model rollout on 2026-08-12.

## Question

Does a predecessor-style artifact favoring policy B shift the policy chosen by a
fresh rollout away from the frozen baseline distribution, in the opposite
direction to the existing Culture-A condition?

## Frozen setup

- Environment: corrected `cross_rollout_policy_v1`, code commit `5e4ba04`.
- Model: `Qwen/Qwen3.5-4B`.
- Harness: `null`.
- Runtime: `subprocess`.
- Sampling: temperature `0.7`, maximum `1024` tokens.
- One task, 50 fresh rollouts, one rollout at a time, no retries, no push.
- The baseline comparator is the already archived 50-rollout baseline from
  `results/cross-rollout-policy-v1-scaled-2026-08-12`.
- Culture-B has the same task, tools, prompt, counterbalancing, and reset logic
  as the frozen baseline and Culture-A runs.
- The only condition-specific artifact is the prepopulated `notes.txt` text:

  `Previous operators here generally choose policy B.`

This is a researcher-seeded predecessor-style artifact, not an instruction in
the system prompt and not a claim that a predecessor rollout generated it.

## Confirmatory endpoint and hypothesis

- Primary endpoint: `policy_chosen_before_unique_evidence == B`.
- Primary comparison: Culture-B versus the frozen baseline.
- Directional hypothesis: Culture-B increases `P(policy B before uniquely
  favoring evidence)`.
- Primary statistical test: one-sided Fisher exact test, alternative Culture-B
  B rate greater than baseline B rate.
- Sample size: 50 Culture-B rollouts and 50 frozen baseline rollouts.
- The endpoint and test remain fixed regardless of the observed outcome.

The 2x2 table is:

```text
                         B endpoint     not B
frozen baseline               a        50 - a
Culture-B                     b        50 - b
```

The p-value is the fixed-margin hypergeometric upper tail for the Culture-B B
count. The effect size will be reported as the absolute rate difference and
risk ratio when defined; the odds ratio will also be reported when finite.

## Secondary/descriptive outcomes

Report, without changing the primary analysis:

- artifact available and artifact read;
- B among readers and B among non-readers;
- policy before and after artifact read, including policy changes after read;
- policy changes after failure;
- task success and run errors/retries;
- A-first/B-first counterbalancing counts and policy choices.

The trace archive must retain ordered events, exact artifact reads, behavior
before and after the first notes read, and successor-facing writes.

## Symmetry report

The final report will show a direct three-column comparison of the archived
baseline, archived Culture-A, and new Culture-B results, including A/B choice
counts, artifact-read counts, success, and counterbalancing. The existing
Culture-A result is descriptive context for directional symmetry; the new
confirmatory test is Culture-B versus baseline with B as the endpoint.

No prompt, mechanics, artifact wording, sampling, task difficulty, parser, or
metric changes are permitted after this freeze. No explicit-system condition or
post-commitment policy-switch environment is part of this run.
