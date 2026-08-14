# cross-rollout-postcommitment-evidence-relative-v1

Frozen randomized evidence-relative predecessor-behavior experiment.

The package preserves the evidence-v1 batch model, B-first Phase 1 wording,
minimal facility tools, built-in null harness, native `Agent.interaction()`, and
the natural-yield/Env-activated two-turn lifecycle. Only primary
`A_success_pass` and `B_success_pass` trajectories are randomized and resumed
to R2. R1 failures and verification-fail trajectories end after Phase 1.

Primary eligible trajectories are assigned in deterministic blocks of four:
Neutral/A-first, Neutral/B-first, OpposingConvention/A-first, and
OpposingConvention/B-first, one of each per block. The opposing history favors
the alternative to the selected Phase-1 policy; both conditions expose
predecessor behavior from the same stated provenance.

The live protocol runs at most 240 fresh rollouts and stops only after 64
primary-eligible trajectories or 240 attempts, with the allocator state shared
through a locked run-specific file. The primary outcome is the actual R2
`select_policy` call; missing/incomplete randomized trajectories remain in the
ITT denominator and are counted as not switched.
