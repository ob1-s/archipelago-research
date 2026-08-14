# cross-rollout-postcommitment-native-v2

Native Verifiers v1 implementation of the post-commitment policy experiment
with independent Phase-1 and Phase-2 policy presentation orders. It preserves
the native null-harness two-turn lifecycle from
`cross_rollout_postcommitment_native_v1`.

## Frozen lifecycle

R1 alone exists in Phase 1. Successful A ends as ineligible; successful B
triggers deferred deterministic randomization and returns the success evidence
together with the assigned Neutral or Culture-A notice. The state then becomes
`awaiting_r2`, in which every facility tool returns the same no-resource
observation and cannot set a Phase-2 choice. Only the environment can activate
R2, and it does so only after the first null-harness segment yields naturally.
It then sends exactly one Phase-2 user message through native
`Agent.interaction()` resume.

No custom harness, continuation recovery message, artifact, or external
dataset is part of this package.

## Independent order counterbalancing

The taskset contains the four crossed combinations:

- A-first Phase 1, A-first Phase 2
- A-first Phase 1, B-first Phase 2
- B-first Phase 1, A-first Phase 2
- B-first Phase 1, B-first Phase 2

The Phase-2 order is task metadata and state, not a function of treatment,
Phase-1 policy, Phase-1 outcome, or model behavior. The exact Phase-2 message
is recorded in trace metadata.

Treatment remains deferred until successful Phase-1 B and uses the same
assignment mode and assignment seed as native v1.

