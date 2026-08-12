# Post-commitment policy override validation pilot v2

This is a validation pilot, not confirmatory data. It uses 4 factorial presentation
tasks × 8 fresh Qwen/Qwen3.5-9B rollouts, native `cross-rollout-postcommitment-v1`,
null harness, subprocess runtime, temperature 0.7, and 1024 maximum tokens.

The four task variants independently cross A-first/B-first wording in Phase 1 and
Phase 2. They still use direct `select_policy(policy="A"|"B")` calls, with no
left/right translation layer. Each rollout is assigned neutral, Culture-A, or
Culture-B before its first model action using SHA-256 of the fixed seed and fresh
trace ID. The condition is independent of both policy choices.

Phase-2 exposure is delivered only in the Phase-1 success tool response, after exact
R1 success feedback. The pilot checks both Phase-1 policy choices, B-success
eligibility, mandatory exposure timing, actual second selection, equal success,
direct A/B semantics, transition logging, factorial presentation bookkeeping, and
failures/ambiguity.

No confirmatory sample, hypothesis test, or post-commitment policy-switch claim is
made from this pilot. The earlier fixed-A-wording pilot remains archived separately
as a design diagnostic.
