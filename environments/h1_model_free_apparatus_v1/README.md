# H1 model-free apparatus v1

Deterministic qualification machinery for H1 turnover, carrier, causal-use,
parentage, recovery, and minimal routine-reconstruction claims. Scripted actors
with known ground truth are test oracles; their behavior is not scientific
evidence about language models.

## Scope

The package discriminates L0 through L5:

- L0: instrumented complete turnover;
- L1: declared-carrier continuity;
- L2: held-out functional reuse;
- L3: actor-generated successor-facing state;
- L4: causal carrier transmission or reconstruction;
- L5: an interdependent, ordered, two-position routine reconstructed after
  complete turnover.

L5 does not mean organizational continuity. `encoder` and `checker` are
harness-assigned capability positions, not observed social roles.

## Qualification

```bash
uv sync --extra dev
uv run pytest
uv run python -m h1_model_free_apparatus_v1.qualification
```

The runner executes no model or provider. Do not use `prime eval` for this
qualification: the native `verifiers.v1` Taskset is a typed manifest/trace
adapter for later bounded work, not authorization for a live behavioral run.

The report contains separate named outcome fields and L0–L5 booleans. It has no
scalar H1 score. Every report is marked `scientific_result=false`.

## Package layout

- `engine.py`: deterministic actor lifecycle and fixture execution;
- `provenance.py`: hash-chained event graph and fail-closed validator;
- `routine.py`: encoder → checker → encoder held-out relay;
- `fixtures.py`: A–H oracles, turnover arms, factorial, and parentage plans;
- `interventions.py`: deletion, corruption, backup, and reconstruction controls;
- `analysis.py`: lineage-level grouping and nonscientific power mechanics;
- `qualification.py`: readiness gates and machine-readable report;
- `taskset.py`: native `verifiers.v1` Taskset adapter.

The allowed persistent carrier classes are enumerated in code as declared
carrier and declared backup. Common policies and infrastructure are common
priors, never lineage state.
