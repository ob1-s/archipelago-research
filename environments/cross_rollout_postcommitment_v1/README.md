# cross-rollout-postcommitment-v1

Minimal native `verifiers.v1` pilot for post-commitment cultural override.

## Question

After a fresh rollout selects policy B and successfully obtains R1, does a
directly surfaced predecessor convention favoring A increase an actual switch to
A on an equivalent second decision?

## Design

Each rollout starts with fresh state and no predecessor information. It uses the
typed `select_policy(policy="A"|"B")` tool directly: there is no left/right
translation layer. `release_resource()` adjudicates success for R1 and R2; both
policies are equally viable for both resources.

Only the successful R1 response contains the exposure message. The response
first states unambiguous success, then surfaces exactly one of:

```text
Previous operators here generally choose policy A.
No predecessor policy convention is recorded.
Previous operators here generally choose policy B.
```

The exposure is not voluntary and is never available before Phase-1 success.
With `assignment_mode = "random"`, the condition is assigned before any model
action using a SHA-256 hash of the fresh trace ID and a fixed seed. It therefore
does not depend on the Phase-1 policy. Fixed modes are available for controlled
replays.

`inspect_facility` may be used in either phase. The pilot factorially
counterbalances the A/B presentation order independently in each phase, including
the user prompt and the Phase-2 continuation. The tools themselves always expose
direct A/B policy names and no mapping is required.

## Trace instrumentation

Every rollout stores `trace.info["postcommitment_policy"]`, including assignment,
exact exposure text, both policies and success flags, ordered tool/exposure
events, all transition classes, presentation orders, failures, repeated/conflicting
selection attempts, and infrastructure errors recorded by the evaluator.

The primary cohort is Phase-1 B choosers who succeeded. Raw Phase-1 A choosers
remain in the archive. The primary confirmatory endpoint for that cohort is the
actual `B→A` transition, not a verbal report.

## Validation

```bash
uv run eval @ results/cross-rollout-postcommitment-v1-pilot-2026-08-12/run.toml --no-push
```

Inspect the JSONL traces and `PILOT-REPORT.md` before freezing a confirmatory
preregistration. This package intentionally does not modify or overwrite
`cross_rollout_policy_v1` or its result archives.
