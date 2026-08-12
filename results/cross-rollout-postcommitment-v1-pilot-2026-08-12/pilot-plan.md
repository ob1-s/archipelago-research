# Post-commitment policy override pilot plan

This is a validation pilot, not confirmatory data. It uses 30 fresh Qwen/Qwen3.5-9B
rollouts with the native `cross-rollout-postcommitment-v1` taskset, null harness,
subprocess runtime, temperature 0.7, and 1024 maximum tokens.

Each rollout is assigned `neutral`, `culture-A`, or `culture-B` before its first
model action using `sha256(seed:trace_id)[0] % 3`. The assignment is independent of
all model behavior. Phase-2 exposure is delivered only in the Phase-1 success tool
response, after the exact R1 success feedback. The pilot checks both Phase-1 policy
choices, B-success eligibility, mandatory exposure timing, independent second
selection, equal success, direct A/B semantics, presentation-order bookkeeping, and
all transition classes.

The pilot is sufficient to validate the interface and trace instrumentation. No
confirmatory sample, hypothesis test, or post-commitment policy-switch claim is
made from it. Any design changes after inspection would require a new pilot archive.

Frozen source package for this pilot: `environments/cross_rollout_postcommitment_v1`.
