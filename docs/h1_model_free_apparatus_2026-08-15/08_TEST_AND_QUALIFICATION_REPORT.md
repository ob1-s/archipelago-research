# Test and qualification report

Qualification command:

```text
uv run pytest
uv run python -m h1_model_free_apparatus_v1.qualification
```

Current result: **92 passed; qualification PASS**.

Coverage includes 0%/50%/100% turnover, handle and authority invalidation,
hidden leakage, provenance inventory/hash/missing-event rejection, deterministic
replay, all four state × lineage cells, six parentage topologies, deletion and
recovery, rediscovery, researcher seed, orchestrator confound, fixture oracles,
strict serialization and stable hashing, lineage grouping, and completion-order
invariance. Hypothesis properties cover mapping-order hashes, arbitrary complete
predecessor turnover, and all relay completion permutations.

Adversarial regression tests additionally cover missing turnover events,
post-check and transient reactivation, predecessor/successor namespace reuse,
actor-labeled events without action attestation, static-replay raw-field credit,
terminal flag/API bypasses (including `model_construct`), duplicate replicates,
shared initialization splits, duplicate factorial cells, duplicate artifact
writes, unresolved/incorrect attribution, strict PASS/L5 bundles, nonfinite
analysis values, and ambiguous non-string hash keys.
An empty outcome payload with an arbitrary truthy gate is also rejected; PASS
requires the exact canonical 15-gate set and complete qualification payload.

The qualification record is deterministic, includes complete provenance event
graphs and artifact inventories, identifies itself as model-free and
nonscientific, and contains 15 passing mechanical gates corresponding to the 13
requested readiness questions plus fixture-oracle and hidden-leak checks.

The qualification runner’s compact report SHA-256 at this pass was
`d234e3ce768f13c9308e77a82a05e43957174d410a114578863a72c1e432d661`.
Regenerate the report after any code change; the hash is expected to change when
the event schema or artifacts change.
