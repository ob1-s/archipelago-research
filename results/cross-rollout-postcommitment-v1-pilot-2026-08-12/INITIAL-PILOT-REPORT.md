# Initial pilot design diagnostic

The initial 30-rollout pilot used direct A/B tools and the Qwen3.5-9B settings in
`run.toml`, but its Phase-1 prompt listed A before B. All 30 rollouts completed the
two-resource task and all 30 had exact, ordered Phase-2 exposure after successful
R1. However, all 30 independently selected A in Phase 1; there were no B-success
primary-cohort rollouts. This is a presentation-order/interface validation failure,
not evidence for or against cultural override.

The raw valid traces are retained in `traces.jsonl`. The first implementation's
30 finalization failures caused by an event-serialization bug are retained under
`pre-fix-taskerror/`; the six-rollout provider interruption diagnostic is retained
under `interrupted-provider/` when present. They are not included as valid pilot
outcomes.

The taskset was then corrected without changing the scientific state transition or
tool semantics: a four-variant factorial counterbalances A-first/B-first wording
independently across both phases. Validation v2 is archived separately and must be
inspected before any confirmatory freeze.
