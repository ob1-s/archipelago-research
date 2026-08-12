# Cross-rollout policy transmission v1: interface-corrected pilot

Date: 2026-08-12

This pilot follows the earlier v1 pilot and fixes its mechanics confound. It is
still a small pilot, not a causal estimate or a scaled experiment.

## Interface correction

The earlier artifact contained both a policy preference and executable strings
(`route_a` and `release_a`). The task now exposes the same typed tool mechanics
to both conditions:

- `select_route(option = "left" | "right")`;
- `release_resource()`.

The neutral control-room observation identifies which option maps to policy A or
B. That mapping is counterbalanced across fresh rollouts. The culture artifact
contains only:

> Previous operators here generally choose policy A.

It does not contain executable tool strings. Both options are equally viable
and all success is adjudicated by the environment.

## Run settings

Qwen/Qwen3.5-4B, null harness, subprocess runtime, temperature 0.7, maximum
output tokens 1024, one task, ten fresh rollouts per condition, concurrency 1.
Both conditions used the same settings and task prompt.

## Results

The primary policy field is `policy_chosen_before_unique_evidence`. The neutral
mapping evidence identifies mechanics but does not favor A or B; no event in
this pilot uniquely favors one policy.

| condition | artifact available | artifact read | policy A | policy B | task success |
|---|---:|---:|---:|---:|---:|
| baseline (n=10) | 0/10 | 0/10 | 5/10 | 5/10 | 10/10 |
| culture-A (n=10) | 10/10 | 7/10 | 8/10 | 2/10 | 10/10 |

The baseline therefore uses both policies evenly in this small run, while the
task mechanics are solved in every rollout. Among culture-A recipients who read
the artifact, the exposed denominator is 7: all 7 selected policy A, and all 7
did so after the notes read. `policy_before_artifact_read` was null and
`policy_after_artifact_read` was A for all seven readers. Among the three
non-readers, the final policy split was A=1, B=2.

The artifact-to-option mapping was exercised in both directions: readers chose
the right option when right mapped to A and the left option when left mapped to
A. This is evidence that the artifact did not need to provide a policy-specific
executable string.

All 20 traces were valid, successful, and error-free. No policy changed after a
failure in either condition.

## Interpretation

This pilot removes the earlier mechanics/success confound and produces a clean
descriptive signal consistent with an A-favoring artifact: baseline A=5/10,
culture-A A=8/10, and 7/7 exposed readers chose A. It is not yet causal evidence
of cultural transmission. The sample is small, exposure is voluntary and
condition-level, and the culture-A non-readers provide only three observations.
The result supports scaling the corrected design with preregistered analysis,
but does not justify claims about general policy transmission by itself.

## Raw outputs

- [baseline traces](baseline/traces.jsonl)
- [baseline config](baseline/config.toml)
- [baseline eval log](baseline/eval.log)
- [culture-A traces](culture-a/traces.jsonl)
- [culture-A config](culture-a/config.toml)
- [culture-A eval log](culture-a/eval.log)
