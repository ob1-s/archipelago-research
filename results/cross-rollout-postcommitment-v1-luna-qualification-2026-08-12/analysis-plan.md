# Frozen analysis and stopping record

## Intended qualification

Collect up to 20 valid Phase-1 B-success rollouts in each of Neutral and
Culture-A, using the frozen post-commitment environment and the null harness.
The primary descriptive outcome was the Phase-2 transition among the eligible
cohort: `B→A` versus `B→B`.

The run was to stop early if a systematic interface or design pathology made
the Phase-2 outcome uninterpretable. No environment, prompt, artifact,
sampling, or metric changes were authorized.

## Actual stopping rule applied

After Phase-1 B success, the frozen environment exposed treatment and revealed
R2. Under the requested null harness, multiple Luna rollouts emitted a final
response instead of making the required Phase-2 tool call. This occurred in
both Neutral and Culture-A and made missing Phase-2 actions systematically
related to completion behavior rather than a meaningful stay/switch choice.
The run was stopped at 38 completed rollouts.

No Fisher test or treatment effect estimate was declared because the planned
20-per-arm eligible sample was not reached and the observed Phase-2 missingness
was not a valid outcome category for the scientific question.

