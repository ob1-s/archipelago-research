# Pre-live qualification and freeze record

Date: 2026-08-14

Package: `cross_rollout_postcommitment_evidence_threshold_transport_v1`

Status: **qualified and frozen for review; live scientific inference has not
started**. Approval is required before launching the 504-primary-eligible
collection.

## Frozen evidence mathematics

The hidden profile is sampled 1:1. R1 and R2 share that profile, and all
resource-level draws are independent conditional on it. Acquisition is fixed
at 0.80 when matched and 0.55 when mismatched. Verification pass is 0.80
when matched; only the mismatch verification probability changes:

| Strength | P(pass \| mismatch) | LR after success+pass | normative q* | P(primary eligibility) |
|---|---:|---:|---:|---:|
| LOW | 0.49870129870129876 | 2.333333333333333 | 0.700000000000000 | 0.457142857142857 |
| ANCHOR | 0.30000000000000000 | 3.878787878787879 | 0.795031055900621 | 0.402500000000000 |
| HIGH | 0.12929292929292927 | 9.000000000000004 | 0.900000000000000 | 0.355555555555556 |

The values above were recomputed by the package before taskset loading and are
asserted by tests. The q grids are exactly:

- LOW: `.6800, .6900, .6950, .7000, .7050, .7100, .7200`
- ANCHOR: `.7800, .7900, .7925, .7950, .7975, .8000, .8100`
- HIGH: `.8800, .8900, .8950, .9000, .9050, .9100, .9200`

The primary event is R1 acquisition success plus verification pass. Failed R1
attempts close without R2. No treatment or culture condition exists in this
package.

## Sample and assignment freeze

The target is 504 primary-eligible trajectories:

- 3 strengths × 7 q values;
- 24 primary rows per strength × q cell;
- 12 K-first and 12 M-first Phase-1 presentations per strength × q cell;
- 12 per Phase-2 presentation order per strength × q cell;
- 84 strength × q × Phase-1-order × Phase-2-order quota cells;
- 6 accepted primary rows per quota cell;
- 60 preassigned attempts per quota cell;
- hard scheduled cap: 5,040 attempts.

Strength, q, Phase-1 order, Phase-2 order, quota cell, and quota round are
deterministic functions of the attempt index and frozen schedule seed. They are
fixed before Phase 1. The atomic quota ledger only accepts or rejects an
evidence-eligible row in that row's already assigned cell; it never selects a
condition. Therefore completion order cannot change experimental allocation.
Duplicate acceptance of an attempt is rejected. Over-quota in-flight rows are
archived guards, not replacement observations.

The assignment audit found 5,040 unique attempt indices, 84 quota cells, and
completion-order independence. The exact binomial union bound for any quota
cell having fewer than six eligible rows after its 60 scheduled attempts is
`3.387540857756057e-05`.

First-order expected Phase-1 model attempts to obtain the target are:

| Strength | Expected attempts |
|---|---:|
| LOW | 367.5 |
| ANCHOR | 417.3913 |
| HIGH | 472.5 |
| Total | 1,257.3913 |

These are planning expectations, not a change to the hard 5,040-task guard.

## Lifecycle and surface audit

The environment uses the built-in null harness and native `Agent.interaction()`.
R2 is inaccessible before Env-side activation. During `awaiting_r2`, both
facility tools return the same no-resource observation and do not draw R2
outcomes. Only Env control flow activates R2, sends exactly one Turn-2 user
message, and resumes the native interaction. The actual Phase-2
`select_policy` call is the primary endpoint; R2 acquisition and verification
are secondary outcomes.

The model-visible tool surface contains only `select_policy(policy: str)` and
`release_resource()`. The MCP schema is a generic string with no enum or
`oneOf`, so K/M are not exposed as an ordered schema surface. Phase 1 discloses
the actual strength-specific mismatch verification probability without LOW /
ANCHOR / HIGH labels, q, advisory, source, treatment, or Phase-2 information.
Phase 2 uses the validated AutomatedSource wording, with only q and the
intentional K-first/M-first ordering varying. No predecessor framing is
present.

Trace instrumentation records the preassigned condition, random namespaces and
draw identifiers, lifecycle events, natural-yield status, Turn-2 message,
choice, stochastic R2 outcomes, missing/incomplete state, and stop reason.

## Concurrency qualification

Model-free tests passed for deterministic assignment, arbitrary completion
order, atomic quota acceptance, the native lifecycle gate, exact quota shape,
and the schema surface. Four simultaneous real MCP subprocesses were started
with independent ephemeral ports; all registered the two tools and returned
the same clean schema.

A separate four-rollout native evaluator smoke used the frozen runtime shape
with `max_concurrent=4`, interception multiplex 4, one agent per task, and a
separate temporary output/quota path. All four rollouts started together,
received distinct facility server ports, completed, and the evaluator exited
with code 0. This smoke was operational qualification only and is not part of
the scientific dataset.

## Frozen analysis

The analysis code reports every strength × q cell's SWITCH numerator,
denominator, and proportion; weighted isotonic curves; q50 only by interpolation
between adjacent tested q values; calibration errors; and the three frozen
threshold-shift contrasts. It does not extrapolate outside a strength's q grid.

Uncertainty is a stratified nonparametric trajectory bootstrap over
strength × q × Phase-1-order × Phase-2-order cells, with 10,000 replicates and
the frozen bootstrap seed. A replicate contributes a q50 or contrast only when
the required q50 values are identifiable; the identifiable fraction is
reported. The secondary analysis reports switch probability against
`logit(q) - log(LR_private)`. No post-hoc logistic replacement or regularization
is used.

## Runtime and wall-time forecast

The exact native dry-run configuration is recorded in
`qualification_evidence_threshold_transport_luna_clean.toml` and was byte-
identical to the resolved native evaluator config. Its SHA-256 is
`b3c5297013afbdfc1e7e3d66f2874b68e6d525455c73d9e3457d7c2d95d336a9`.

- Model: `gpt-5.6-luna`
- Evaluator: native `.venv/bin/eval`
- Runtime: subprocess, `colocated=false`
- Harness: built-in `null`
- Interaction: native `Agent.interaction()`
- Base URL: `http://127.0.0.1:10531/v1`
- Requested temperature: `0.7`
- Max tokens: `1024`
- `max_concurrent`: `4`
- `env.max_concurrent_agents`: `1`
- interception multiplex: `4`
- retries: `0`
- reasoning effort: not specified / null

Observed installed versions were Python 3.12.13, Verifiers 0.3.0, MCP 1.29.0,
Pydantic 2.13.4, OpenAI 2.53.0, and httpx 0.28.1.

In the isolated native smoke, four concurrent rollouts ran from the first
rollout-start log line to the final rollout-done line in approximately 81
seconds (log-second resolution), or about 177.8 rollouts/hour. Applying a
conservative 0.5×–1.0× range to that small operational sample gives an
estimated 7.1–14.2 hours for the approximately 1,257 Phase-1 model attempts.
This is an estimate, not a guarantee; it excludes no scientific data because
no scientific collection has begun.

## Tests and deviations

- New package Ruff: passed (`All checks passed!`).
- New package pytest: `10 passed in 4.86s`.
- New package compileall: passed.
- Native v1 regression tests: `10 passed`.
- Native v2 regression tests: `17 passed`.
- Transition-diagnostic regression tests: `29 passed`.
- A read-only Ruff pass over the three predecessor test trees reports three
  pre-existing import-order `I001` diagnostics. Those predecessor files were
  not changed.

Two early legacy-CLI probes were rejected by the current evaluator interface
before any model request; the native `.venv/bin/eval` path was then used for
the successful dry-run and isolated concurrency smoke. No scientific
collection was started and no scientific parameter was changed.

## Freeze gate

The package is ready for review at a dedicated pre-live Git freeze commit. The
freeze commit, final Git status, and file manifest are recorded in the
archival handoff after this report is committed. **Do not launch live
inference until explicit approval is received.**
