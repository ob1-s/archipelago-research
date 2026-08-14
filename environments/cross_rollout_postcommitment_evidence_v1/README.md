# cross-rollout-postcommitment-evidence-v1

Evidence-based native two-turn post-commitment environment for Archipelago.

Each rollout samples a hidden `A_fit`/`B_fit` batch profile with a frozen 1:1
prior. R1 and R2 are independent resource instances from the same batch. A
matching policy has acquisition/check probabilities `0.80/0.80`; a mismatching
policy has `0.55/0.30`. The model receives that generative description before
choosing R1, and R1 returns only the observed acquisition and verification
outcomes.

Phase 1 is frozen B-first in this version. Every successful R1 trajectory enters
the native `awaiting_r2` boundary. The built-in null harness and native
`Agent.interaction()` provide a natural non-tool yield, after which only the Env
activates R2 and sends one Turn-2 user message. Phase-2 order is independently
counterbalanced. The actual `select_policy` call is the Phase-2 policy outcome;
R2 acquisition and verification are secondary stochastic outcomes.

The taskset implements both `post_b_success_random` assignment mode and
`fixed_neutral`. The live qualification uses `fixed_neutral` only. Culture-A
messages are implemented for future qualification but are not run here.
