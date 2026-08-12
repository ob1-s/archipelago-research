# Neutral-only post-commitment pilot v3 enforced

This is a validation pilot, not confirmatory data. It runs 2 Phase-1 presentation
variants (A-first and B-first) × 16 fresh Qwen/Qwen3.5-9B rollouts, for 32 total.
Only the neutral notice is used. Culture-A and Culture-B are not run.

The initial prompt mentions only R1 and contains no final-response cue. After actual
R1 success, the facility returns clear success feedback, the neutral notice, and
the first-ever R2 reveal:

```text
A new equivalent resource R2 is now available. Select a policy and obtain R2.
```

The same post-success response instructs the model to invoke `select_policy` before
finalizing. This is an execution-enforcement detail necessitated by the standard
single-segment eval path; it does not mention switching, persistence, trying another
policy, or any policy value. The pilot records whether the model nevertheless stops
before Phase 2.

The pilot records Phase-1 A/B by presentation order, all transitions, persistence
conditional on Phase-1 A/B, success, ambiguity, failures, ordered exposure, and
assistant text before exposure for apparent R2 anticipation. No statistical
treatment test is planned.

The prior v2 archive and the first v3 transition diagnostic remain separate.
