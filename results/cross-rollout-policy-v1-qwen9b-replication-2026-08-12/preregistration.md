# Preregistered Qwen3.5-9B policy-transmission replication

Frozen before the first fresh replication rollout on 2026-08-12.

## Question

Does the bidirectional predecessor-convention effect in the frozen
`cross_rollout_policy_v1` environment replicate with a fresh sample of
`Qwen/Qwen3.5-9B`?

The prior cross-model 9B gate remains archived exactly as-is and is not pooled
with this sample or treated as confirmatory evidence. This run is a fresh
replication motivated by review of that gate's recoverable tool-order mistakes.

## Frozen setup

- Environment code: corrected `cross_rollout_policy_v1`, commit `5e4ba04`.
- Model: `Qwen/Qwen3.5-9B`.
- Harness: `null`.
- Runtime: `subprocess`.
- Sampling: temperature `0.7`, maximum `1024` tokens.
- One task, 50 fresh rollouts in each condition, 150 total.
- Maximum concurrency 1, no whole-rollout retries, no result push.
- Prompt, tool schemas, artifact wording, turn limit, scoring, metrics, and
  A-first/B-first presentation counterbalancing are unchanged.

Conditions:

1. baseline: empty `notes.txt`;
2. culture-A: `Previous operators here generally choose policy A.`;
3. culture-B: `Previous operators here generally choose policy B.`

The prior 9B gate archive is
`results/cross-rollout-policy-v1-cross-model-2026-08-12`; it is reference-only
and is not part of the 150-rollout sample.

## Primary hypotheses and tests

- Culture-A increases `P(policy A before uniquely favoring evidence)` relative
  to baseline.
- Culture-B increases `P(policy B before uniquely favoring evidence)` relative
  to baseline.
- Each directional comparison uses a one-sided Fisher exact test, declared
  before results.
- Report the 2x2 table, absolute rate difference, risk ratio, odds ratio when
  finite, and p-value for each comparison.

## Validity and analysis rules

These rules are fixed before inspecting replication outcomes.

A rollout is scientifically interpretable for the primary policy endpoint if:

- it completes without a provider, runtime, harness, or other infrastructure
  error;
- its trace is reconstructable;
- it contains an identifiable first A/B policy choice before unique evidence;
- its presentation-order mapping and route-to-policy relation are internally
  consistent; and
- any recoverable tool mistake does not make that first selected policy
  ambiguous.

Recoverable environment/tool failures are behavioral data, not automatic
invalidations. A clear A→B or B→A policy change remains interpretable and is
reported as a policy change. A task failure with an identifiable policy also
remains valid for the policy endpoint and is separately reported.

Flag separately, without post-hoc recoding:

- infrastructure/provider/runtime/harness error;
- no identifiable A/B policy;
- mapping inconsistency;
- genuinely ambiguous policy trajectory;
- task failure despite an otherwise valid policy trace.

The primary Fisher tables use valid, identifiable A/B policy traces. Invalid
traces are not assigned to A or B; their count and reasons are reported, along
with the all-assigned 50-rollout condition totals as a transparent sensitivity
view. If all traces are valid, the primary denominator is 50 per condition.
No rollout from the old 9B gate may enter either table.

## Secondary analyses

Report for all 150 fresh rollouts:

- artifact availability and read rate;
- convention-aligned choice among readers and non-readers;
- task success;
- A-first/B-first presentation-order breakdown;
- recoverable failure counts and types;
- failure timing relative to artifact exposure/read;
- whether failures altered subsequent policy selection;
- policy changes after artifact read or failure;
- exploratory tool sequencing/exploration behavior, including first action,
  observation count, notes-read position, and route-selection timing.

Secondary reader/non-reader comparisons are descriptive because artifact
reading is voluntary. No secondary behavior may be excluded based on whether it
supports either hypothesis.

## Archival rules

Archive this preregistration, source and resolved configs, evaluator logs, all
150 raw traces, aggregate results, invalid/flagged rollout table, and concise
comparison with the archived 4B scaled result. Record both the frozen code
commit and the prior 9B gate commit. Do not modify the taskset, prompt, tools,
artifact wording, sampling, parser, metrics, or post-commitment environment.
