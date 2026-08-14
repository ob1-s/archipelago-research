# cross-rollout-postcommitment-native-v1

Native Verifiers v1 implementation of the post-commitment policy experiment. The
environment uses the built-in null harness and holds one rollout open across two
scripted user turns with `Agent.interaction()`.

## Frozen lifecycle

R1 alone exists in Phase 1. Successful A ends as ineligible; successful B triggers
deferred deterministic randomization and returns the success evidence together with
the assigned Neutral or Culture-A notice. The state then becomes `awaiting_r2`, in
which every facility tool returns the same no-resource observation and cannot set a
Phase-2 choice. Only `CrossRolloutPostcommitmentNativeEnv.run()` can activate R2,
and it does so only after the first null-harness segment yields naturally. It then
sends the same `TURN_2_MESSAGE` in both conditions.

No custom harness, continuation recovery message, artifact, or external dataset is
part of this package. Do not launch model evaluations until the model-free lifecycle
tests and experimental wording have been reviewed.

## Taskset configuration

| Field | Default | Meaning |
| --- | --- | --- |
| `assignment_mode` | `post_b_success_random` | Fixed deferred assignment mode. |
| `assignment_seed` | `postcommitment-confirmatory-v1` | Seed used with the rollout ID after successful B. |

## Recorded endpoints

The trace metadata records eligibility, assignment, exposure, all interstage calls,
R2 activation, the frozen second message, Phase-2 missingness, and the actual B→A or
B→B tool transition. Missing Phase 2 is retained and reported rather than excluded.
