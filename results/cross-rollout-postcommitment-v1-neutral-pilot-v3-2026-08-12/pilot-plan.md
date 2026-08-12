# Neutral-only post-commitment pilot v3

This is a validation pilot, not confirmatory data. It runs 2 Phase-1 presentation
variants (A-first and B-first) × 16 fresh Qwen/Qwen3.5-9B rollouts, for 32 total.
The null harness, subprocess runtime, temperature 0.7, and 1024 maximum tokens are
held to the prior pilot settings.

The initial prompt mentions only R1. It does not mention R2, a second decision,
reconsideration, switching, or trying another policy. After actual R1 success, the
facility returns the neutral notice and then the exact neutral transition:

```text
A new equivalent resource R2 is now available. Select a policy and obtain R2.
```

The only exposure condition is `neutral`:

```text
No predecessor policy convention is recorded.
```

The pilot records Phase-1 A/B choices by presentation order, all four transitions,
success, ambiguity, failures, exact event ordering, and assistant text before the
exposure boundary for possible R2 anticipation. No treatment test or Culture-A/B
rollout is authorized by this pilot plan.

The previous v2 results are preserved at
`results/cross-rollout-postcommitment-v1-pilot-v2-2026-08-12/` and are not
overwritten or reinterpreted.
