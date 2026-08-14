# cross-rollout-postcommitment-transition-diagnostic-v1

Exploratory Verifiers v1 diagnostic for the native two-turn post-commitment
transition matrix. It is derived from the native v2 lifecycle while removing
all culture and deferred-assignment behavior.

Both successful Phase-1 policies continue to `awaiting_r2`. The built-in null
harness and native `Agent.interaction()` provide the natural-yield boundary and
resume. R2 is absent until environment control flow activates it, and exactly
one frozen Turn-2 user message is sent. The actual Phase-2 tool choice records
the transition.

The taskset contains all four independent Phase-1/Phase-2 presentation-order
combinations. No treatment, predecessor notice, custom harness, continuation
message, or external dataset is part of this package.
