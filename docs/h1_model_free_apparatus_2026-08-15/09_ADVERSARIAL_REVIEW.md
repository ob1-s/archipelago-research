# Adversarial review log

Three independent Luna Max workers were routed and verified. They were
read-only; Sol adjudicated findings and implemented repairs. Agreement was not
treated as evidence: every concrete bypass was reproduced or examined against
the code contract.

## Pre-implementation findings adopted

- Make terminal replay a downstream-sufficiency arm, with no arm-level L3/L5.
- Require encoder → checker → encoder actor-authenticated dependencies.
- Keep provenance in durable output rather than transient `vf.State`.
- Treat common archives as parentage-nonidentifying.
- Aggregate independent lineages, never calls/actions, as inferential units.
- Replace the legacy CLI scaffold with exactly one native-v1 Taskset export.

## Failures found and repaired

1. JSON round trips changed tuples to lists. Carrier payloads now use canonical
   JSON-native shapes and equality/hash round-trip tests.
2. Terminal replay and researcher seed had raw `routine_reconstructed=true`
   despite gated L5=false. Behavior observation is now separate; replay/seed
   have no raw transmission, reconstruction, or L3–L5 credit.
3. 0%/50% redundant survival had `turnover_valid=true`. Requested intervention
   execution is now separate; valid turnover requires complete replacement.
4. Missing revoke/termination events and post-check reactivation could pass L0.
   Expected lifecycle/authority events, final state, namespace disjointness, and
   sticky transient-reactivation audits are now required.
5. Successor process/session IDs could reuse predecessor namespaces. Both the
   engine and provenance validator reject identity reuse.
6. The engine centrally computed the relay, then attached actor labels. Explicit
   scripted encoder/checker methods now produce each stage, output hash, parent
   edge, and deterministic actor-capability attestation. Silent or generic
   actor-labeled events cannot earn L5.
7. A redundant terminal-replay flag could disagree with fixture kind, including
   through `model_construct`. Cross-field validation and defensive execution-time
   revalidation close both paths.
8. Duplicate replicates, shared-initialization label splitting, and duplicate
   factorial cells could pass. Initialization/replicate IDs are required and
   uniqueness checks fail closed; analysis unit IDs/count ship in the report.
9. MULTIPLE/BROADCAST parentage was too label-like. Multiple topology now has
   authored contribution artifacts and resolved parent edges; broadcast records
   both carriers reaching both successors. Unknown parents and shuffled writers
   fail provenance validation; common-archive roots remain explicitly ambiguous.
10. Duplicate artifact writes, nonfinite analysis values, and non-string JSON
    hash keys were accepted. Each now fails its boundary validator.
11. L5/PASS objects could be reconstructed with inconsistent component fields.
    Validated wire objects now require a complete L5 evidence bundle and all
    qualification gates for PASS. Pydantic’s intentionally unsafe copy/construct
    APIs remain outside the trusted wire boundary; execution revalidates cases.
12. An empty result with `{"foo": true}` could claim PASS. PASS now requires
    the exact canonical 15-gate set, ten fixture outcomes, four factorial cells,
    six parentage arms, seven recovery arms, and at least one analysis unit.

## Disagreements and retained limits

The reviewers correctly observed that arbitrary malicious Python code in the
same process can introspect or monkeypatch any in-process actor. Deterministic
capability attestations close ordinary actor-label forgery and qualify the
event contract, but they are not a security boundary. A live harness must put
actor computation and signing credentials in isolated processes/runtimes and
must keep the orchestrator outside that boundary. Likewise, the internal hash
chain is tamper-evident under trusted instrumentation, not an external signature.

The final repair-verification suite contained 92 passing tests and all three
reviewers reported no remaining false-credit path in the standard validated
interfaces. These are the strongest remaining live-integration weaknesses. They limit what
the model-free PASS means; they do not change any scripted fixture oracle.
