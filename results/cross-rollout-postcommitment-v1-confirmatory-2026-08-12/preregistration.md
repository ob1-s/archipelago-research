# Preregistration: deferred-assignment post-commitment policy transmission

Status: frozen before confirmatory data generation  
Base pilot commit: `f4e11fd`  
Confirmatory environment: `cross-rollout-postcommitment-confirmatory-v1`  
Model: `Qwen/Qwen3.5-9B`

## Scientific question

Among fresh rollouts that independently select policy B and observe unambiguous
success obtaining R1, does unavoidable exposure to a predecessor convention
favoring policy A increase switching to A on a second equivalent decision,
relative to a neutral predecessor notice?

This is a behavioral policy-switch test. Selecting B in Phase 1 is not treated
as evidence of a deep or stable preference; it is the eligibility state defined
for the primary analysis.

## Conditions and deferred assignment

Every rollout begins with fresh state and an initial prompt mentioning only R1.
The initial prompt, tool schemas, and Phase-1 facility inspection do not contain
the treatment, the neutral notice, R2, or any instruction to switch or persist.

After and only after a rollout selects B and `release_resource()` returns
successful R1 feedback, the environment allocates it 1:1 using the frozen rule:

```text
sha256(assignment_seed + ":" + fresh_trace_id)[0] % 2
0 → neutral
1 → culture-A
```

The assignment seed is `postcommitment-confirmatory-v1`. Assignment is recorded
as occurring at the Phase-1-B success event and is not visible before that
event. The two exposure texts are:

```text
No predecessor policy convention is recorded.
Previous operators here generally choose policy A.
```

After exposure, R2 is revealed for the first time with the same neutral
instruction in both arms:

```text
A new equivalent resource R2 is now available. Select a policy and obtain R2.
```

Culture-B is not included. Phase-1-A successes remain in the raw archive but
receive no R2 exposure and are marked ineligible for the primary cohort.

## Sample size and stopping rule

Target: at least 50 valid Phase-1-B rollouts in each exposure arm. The frozen
run configuration requests 160 fresh rollouts for each of the two balanced
Phase-1 presentation-order tasks (320 total maximum in the initial batch).

If the target is not reached, additional batches use the identical frozen
configuration and are archived separately. Stop data generation at the first
completed batch for which both arms have at least 50 valid primary rollouts.
The primary analysis includes every valid primary rollout completed through the
stopping batch; the realized N is reported rather than truncating to exactly 50.

## Primary endpoint and analysis

The primary endpoint is the observed Phase-2 policy among valid Phase-1-B
rollouts:

- switch: `B→A`;
- persistence: `B→B`.

A primary-valid rollout must have no provider/runtime/harness/interception error,
successful Phase-1 B acquisition, delivered assigned exposure, an identifiable
Phase-2 A/B policy selection, and no policy-selection ambiguity. Phase-2 task
success is not required for the policy endpoint and is reported separately.

Primary comparison: Culture-A versus neutral.  
Directional hypothesis: Culture-A increases `P(B→A)`.  
Primary test: one-sided Fisher exact test, declared before data generation.

The 2×2 table is:

```text
                    B→A switch     B→B persistence
neutral                 ...               ...
culture-A               ...               ...
```

Report the switch-rate difference (Culture-A minus neutral), risk ratio, odds
ratio, and one-sided Fisher p-value. If a ratio is undefined because of a zero
cell, report that fact and the exact table rather than applying a post-hoc
correction.

## Secondary/descriptive outcomes

Report without changing the primary endpoint:

- Phase-1 A/B choice by A-first/B-first presentation order;
- eligible-B count and arm allocation balance;
- Phase-2 B→A/B→B counts;
- Phase-2 policy choice among readers is not applicable because exposure is
  mandatory; report exposure delivery instead;
- Phase-2 task success;
- recoverable tool failures and their timing;
- ambiguity, infrastructure errors, and incomplete traces;
- exact exposure text and ordered assignment/exposure/action events;
- whether any policy changed after a tool failure.

No Culture-B, model ladder, prompt, wording, mechanics, difficulty, sampling,
or post-commitment ablation is included in this run. Secondary analyses are
descriptive and are not used to redefine validity after observing outcomes.

## Frozen runtime

- harness: `cross-rollout-postcommitment-confirmatory-v1`;
- runtime: subprocess;
- sampling: temperature `0.7`, max tokens `1024`;
- direct typed tools: `select_policy(A|B)`, `release_resource()`,
  `inspect_facility()`;
- Phase-1 order: balanced A-first/B-first tasks;
- no left/right mapping layer.

The preregistration, resolved configs, all traces, aggregate analysis, and
commit hashes will be archived together. No task or analysis changes are
permitted after confirmatory data generation begins.
