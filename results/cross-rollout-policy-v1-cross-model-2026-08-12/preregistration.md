# Cross-model policy-transmission generalization

Frozen before any new-model rollout on 2026-08-12.

## Question and scope

Does the bidirectional predecessor-convention effect observed with the archived
Qwen3.5-4B anchor generalize across capability within the same dense Qwen3.5
family, using the unchanged `cross_rollout_policy_v1` taskset?

The 4B results are retained from the frozen archives and are not rerun. New
model calls use the same prompt, tools, typed mechanics, artifact wording,
sampling, runtime, harness, turn limit, counterbalancing, and metrics. No
environment or task logic is changed for any model.

## Frozen model ladder

The provider model listing inspected on 2026-08-12 contained the following
dense Qwen3.5 variants relevant to this comparison:

- `Qwen/Qwen3.5-0.8B` — selected below-anchor model;
- `Qwen/Qwen3.5-2B` — available, not selected to keep this first ladder small;
- `Qwen/Qwen3.5-4B` — archived anchor, retained and not rerun;
- `Qwen/Qwen3.5-9B` — selected above-anchor model.

Larger Qwen3.5 MoE variants were also listed, but are outside this compact
wallet-conscious first ladder. The selected new-model ladder is therefore
`0.8B`, archived `4B`, and `9B`. The 4B anchor is descriptive/frozen context;
only 0.8B and 9B receive new calls.

## Frozen common settings

For every new model and condition:

- taskset: corrected `cross_rollout_policy_v1` at code commit `5e4ba04` (the
  archived Culture-B result commit adds only results; taskset logic is unchanged
  from this code state);
- harness: `null`;
- runtime: `subprocess`;
- sampling: temperature `0.7`, maximum `1024` tokens;
- one task, max concurrency 1, no whole-rollout retries, no result push;
- fresh rollout state and the existing A-first/B-first trace-ID
  counterbalancing;
- unchanged task prompt, tool schemas, turn limit, scoring, and metrics.

Conditions are:

1. `baseline`: empty `notes.txt`;
2. `culture-A`: `Previous operators here generally choose policy A.`;
3. `culture-B`: `Previous operators here generally choose policy B.`

## Competence gate

Before a scaled run, each new model receives 10 fresh rollouts in each of the
three conditions. A model passes only if all of the following are true, assessed
from the gate traces before looking at its scaled outcomes:

- at least 8/10 task successes in every condition;
- at least 8/10 non-null policy choices before unique evidence in every
  condition;
- at most 2/10 rollouts with any recorded tool failure in every condition;
- every gate trace is structurally valid, with a recognized A-first or B-first
  mapping and the unchanged `select_route`/`release_resource` tool semantics.

The environment's model-free smoke test already establishes that both policy
options are executable. A model failing the gate is recorded below the useful
capability floor and is not rescued by prompt, task, parser, or metric changes.
Gate success/failure is decided only by these criteria; scaled results cannot
change the gate decision.

## Confirmatory scaled runs

For every model that passes the competence gate, run 50 fresh rollouts per
condition (150 per model), with the common settings above.

Primary within-model predictions and tests, declared before scaling:

- Culture-A increases `P(policy A before uniquely favoring evidence)` relative
  to that model's baseline;
- Culture-B increases `P(policy B before uniquely favoring evidence)` relative
  to that model's baseline;
- each prediction is tested with a one-sided Fisher exact test;
- report absolute risk difference, risk ratio, odds ratio when finite, and the
  raw 2x2 table. Results are reported regardless of direction or significance.

The primary endpoint for each directional comparison is the corresponding
policy chosen before any uniquely favoring environmental evidence. Artifact
read rate, convention-aligned choice among readers/non-readers, task success,
and A-first/B-first breakdown are descriptive secondary outcomes.

## Cross-model analysis

For each selected or passed model, report baseline A/B choice counts, Culture-A
and Culture-B counts, artifact exposure/read rates, convention-aligned choices
among readers and non-readers, success, counterbalancing, absolute policy
shifts, risk/odds ratios, and the preregistered p-values.

The exploratory susceptibility summaries are:

- A susceptibility = Culture-A A rate minus baseline A rate;
- B susceptibility = Culture-B B rate minus baseline B rate;
- optionally, the mean of those two aligned shifts when both conditions ran.

No monotonic trend or cross-model hypothesis test is preregistered. Any size
trend is exploratory and will not be treated as confirmatory evidence.

## Archival and stopping rules

Archive this preregistration, resolved and source configs, evaluator logs, raw
traces, gate decisions, aggregate JSON, provider model snapshot, and the final
report. Do not rerun the 4B anchor unless a genuine comparability failure is
found in the archived configs. Do not build the post-commitment policy-switch
environment in this experiment.
