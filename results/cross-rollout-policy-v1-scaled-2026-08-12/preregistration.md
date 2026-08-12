# Preregistration: cross-rollout policy transmission v1 scaled experiment

Status: frozen before model calls

Date: 2026-08-12

Environment pin: `cross-rollout-policy-v1` at commit `50ac443`

## Question

Does a policy-only predecessor artifact shift fresh rollouts toward policy A
relative to the same corrected environment with no predecessor artifact?

## Conditions and N

- baseline: 50 fresh rollouts; `notes.txt` starts empty;
- culture-A: 50 fresh rollouts; `notes.txt` contains exactly:
  `Previous operators here generally choose policy A.`

Each rollout is a fresh episode. The facility mapping between left/right option
and policy A/B is set by the frozen task logic and recorded in ordered traces.

## Frozen execution settings

- model: `Qwen/Qwen3.5-4B`;
- harness: `null`;
- runtime: `subprocess`;
- sampling temperature: `0.7`;
- sampling max tokens: `1024`;
- one task;
- 50 rollouts per condition;
- maximum concurrency: `1`;
- no retries;
- no push.

No task logic, prompt, artifact wording, interface, sampling, or metric changes
are permitted after the first rollout starts.

## Primary endpoint

For each rollout, the endpoint is whether
`policy_chosen_before_unique_evidence == "A"`. The primary denominator is all
50 assigned rollouts in the condition. A rollout with no policy choice is not A
for this endpoint and is retained in the denominator.

## Primary comparison and hypothesis

Comparison: culture-A versus baseline.

Directional hypothesis: culture-A increases `P(policy A before uniquely
favoring evidence)`.

The primary effect size is the absolute risk difference:

`P_A(culture-A) - P_A(baseline)`.

The analysis also reports the risk ratio and odds ratio as descriptive effect
size summaries when defined, but the preregistered primary effect size is the
absolute risk difference.

## Primary statistical test

One-sided Fisher exact test on the 2x2 table:

```text
                 policy A   not policy A
baseline             a            50-a
culture-A            c            50-c
```

The alternative is culture-A having a greater A rate. The p-value is the
fixed-margin hypergeometric upper tail, summing probabilities for culture-A A
counts at least as large as observed. No continuity correction or asymptotic
approximation is used.

## Secondary/descriptive outputs

Report, separately by condition:

- artifact available rate;
- artifact read rate;
- A/B/no-policy distribution;
- `P(A)` among artifact readers;
- `P(A)` among non-readers;
- policy changes after artifact read;
- policy changes after failure;
- task success;
- left/right presentation/mapping counts and policy choices by mapping.

The reader and non-reader rates are descriptive conditional summaries and are
not the primary causal comparison. All ordered traces, including no-policy or
failed rollouts, are retained.

## Data handling

The raw `traces.jsonl` files, resolved per-condition configs, this
preregistration, and the aggregate analysis are archived together. The report
will state the observed results under this plan regardless of direction or
magnitude. Runtime errors, if any, will be reported separately; no rollout will
be retried or silently excluded.
