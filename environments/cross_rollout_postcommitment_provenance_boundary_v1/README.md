# cross-rollout-postcommitment-provenance-boundary-v1

High-resolution native two-turn assay for whether quantitatively identical
opposing evidence receives different behavioral weight when attributed to
previous operators versus an automated facility diagnostic. This is a
one-shot source-provenance/evidence-integration experiment, not an endogenous
culture experiment.

## Frozen scientific contract

The package preserves the opaque `K`/`M` private-evidence apparatus from the
validated evidence-interface environment: a hidden 1:1 batch profile, shared
profile across R1/R2, independent resource-level draws, acquisition
probabilities `0.80`/`0.55`, verification probabilities `0.80`/`0.30`, and
primary eligibility after R1 acquisition success plus verification pass.

Phase 1 is counterbalanced K-first/M-first and contains no source or advisory
information. Assignment occurs only after primary eligibility. The frozen q
grid is:

`0.7800, 0.7850, 0.7900, 0.7925, 0.7950, 0.7975, 0.8000, 0.8050, 0.8100`.

There are two conditions only: `PredecessorSource` and `AutomatedSource`.
Twelve macro-blocks contain one matched source pair for every q × Phase-2
order cell. Each cell therefore receives 24 eligible trajectories overall,
with 12 K-first and 12 M-first Phase-2 messages.

The target is 432 primary-eligible trajectories with a hard cap of 1400 actual
Phase-1 attempts. Guard records after the target are not model attempts.

## Native lifecycle

The built-in null harness and native `Agent.interaction()` provide the real
natural-yield boundary. After R1 success plus verification pass, the state
enters inert `awaiting_r2`; source and q remain hidden from the model. Only the
environment activates R2 after a natural non-tool yield and sends exactly one
Turn-2 user message. The actual R2 `select_policy` call is the primary outcome;
R2 acquisition and verification are secondary outcomes.

No custom harness, continuation nudge, recommendation, consensus count, or
NoAdvisory arm is part of this package.

## Runtime

The frozen qualification uses `gpt-5.6-luna`, the validated
`openai-oauth`/OpenAI-compatible subprocess stack, `colocated=false`, the
built-in null harness, max tokens 1024, requested temperature 0.7 (recorded as
ignored if the provider rejects it), concurrency 1, retries 0, and unspecified
reasoning effort.
