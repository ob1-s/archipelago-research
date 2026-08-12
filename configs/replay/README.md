# Predecessor-artifact replay

These configs reuse one actual predecessor-written artifact from the frozen v0
study: persistent chain 03, rollout 6 wrote
`Maintenance macro pulse_hold_resume completed. R dispenser is primed.`

The source trace is `/tmp/cross-rollout-v0-study-final/persistent/chain-03/traces.jsonl`
in the local study bundle. The three recipient conditions are:

- `replay-absent`: empty notes and no explicit procedure exposure;
- `replay-present`: the artifact is available through the ordinary notes tool;
- `replay-explicit`: the artifact text is supplied in the taskset system prompt,
  while the notes object is empty.

All three use fresh control-style recipient rollouts, the same Qwen 4B setup, and
ten independent rollouts. The strict analysis outcome is the first successful
`pulse_hold_resume` execution before `inspect_terminal` reveals it. Because the
taskset records seeded text as `researcher_seed`, the replay analysis must use the
ordered trace events for this intervention study rather than interpreting the
provenance-gated v0 `direct_inherited_procedure_use` field literally.
