# cross-rollout-postcommitment-evidence-threshold-transport-v1

Behavioral transport assay for whether Luna's advisory-reliability threshold
moves when the strength of first-person evidence is changed. This is not a
provenance or machine-culture experiment.

## Frozen design

The hidden batch profile is 1:1, R1/R2 share the profile, and resource draws
are independent conditional on the profile. Acquisition remains `0.80` when
matched and `0.55` when mismatched. Verification pass when matched remains
`0.80`; the mismatch verification probability is the only strength
manipulation:

| Internal condition | P(pass | mismatch) | normative q* | q grid |
|---|---:|---:|---|
| LOW | 0.49870129870129876 | 0.700000 | .6800, .6900, .6950, .7000, .7050, .7100, .7200 |
| ANCHOR | 0.30 | 0.7950310559 | .7800, .7900, .7925, .7950, .7975, .8000, .8100 |
| HIGH | 0.12929292929292927 | 0.900000 | .8800, .8900, .8950, .9000, .9050, .9100, .9200 |

The actual probability is disclosed before R1; semantic labels are not
model-visible. The R1 success-plus-pass event is the evidence-eligible event.
The Phase-2 advisory is the validated AutomatedSource wording only.

## Assignment and concurrency

Strength, q, Phase-1 order, and Phase-2 order are deterministic functions of
the launch attempt index and are fixed before Phase 1. There is no
completion-order condition assignment. The plan has 84 quota cells (strength,
q, Phase-1 order, Phase-2 order), six primary rows per quota cell, and 60
preassigned attempts per quota cell. An atomic quota ledger only decides
whether an evidence-eligible attempt fits its already assigned cell; it never
selects a condition. Over-quota rows are archived guards.

The target is 504 primary eligible trajectories, with 24 per strength × q
cell, 12 per Phase-2 order, and 12 K-first / 12 M-first Phase-1 presentations
in each strength × q aggregate. The hard scheduled cap is 5,040 attempts.

The native built-in null harness and `Agent.interaction()` provide the real
natural-yield boundary. R2 is inert until Env-side activation, and exactly one
Turn-2 user message is sent. The actual R2 policy tool call is the primary
`SWITCH`/`RETAIN` endpoint.

## Analysis

The frozen analysis reports strength × q switch tables, weighted isotonic q50
values without extrapolation, calibration errors, predicted-vs-observed
threshold shifts, a 10,000-replicate stratified bootstrap, and a descriptive
net-evidence-log-odds collapse table. No post-hoc logistic replacement is
used.

No scientific live run has been launched from this package until the
pre-live qualification and wall-time approval gate are complete.
