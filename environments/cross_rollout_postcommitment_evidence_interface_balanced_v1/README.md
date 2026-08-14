# cross-rollout-postcommitment-evidence-interface-balanced-v1

Opaque-label, interface-balanced native two-turn evidence experiment.

The model sees policies `K` and `M`, but the hidden batch regime is represented
internally as `policy_1_fit` or `policy_2_fit`. The only ordered K/M surface is
the explicitly counterbalanced policy instruction. The MCP schema accepts a
plain string and contains no enum or label examples.

The frozen schedule has 240 alternating Phase-1 attempts. Primary-eligible
success-plus-pass trajectories are assigned in deterministic blocks of four to
Neutral/OpposingConvention × K-first/M-first. The run stops after 64 primary
eligible trajectories or 240 Phase-1 attempts. A run-specific locked assignment
ledger is required; never reuse a ledger from another run.

The primary binary ITT endpoint counts missing or incomplete randomized primary
trajectories as not-switch, while preserving raw Phase-2 choice and missing/
incomplete status separately.

The environment uses the built-in null harness, native `Agent.interaction()`,
real subprocess MCP tools, an inert `awaiting_r2` state, natural yield, and one
Env-sent Turn-2 user message. It has no custom continuation or nudge.

## Qualification command

The exact runtime must be pinned before inference:

```bash
pnpm dlx openai-oauth@2.0.0 --codex-version 0.144.1 --detach
```

Then run [qualification_interface_balanced_luna.toml](qualification_interface_balanced_luna.toml).
Use a controller that stops the evaluator after the completed trace containing
the 64th primary-eligible assignment. The environment also has a pre-attempt
stop guard, so no model request occurs after the target is reached if the
controller observes one scheduling boundary late.
