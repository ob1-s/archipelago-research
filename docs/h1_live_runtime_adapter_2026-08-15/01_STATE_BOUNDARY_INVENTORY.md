# State boundary inventory

The canonical inventory is machine-readable in `STATE_LAYER_MANIFEST.json` and enforced by `state_manifest.py`. It contains 47 uniquely named layers in a canonical order. Each row declares owner, scope, lifetime, model visibility, mutability, predecessor-write and successor-read edges, classification, reset/isolation mechanism, verification method, evidence class, and residual uncertainty.

The inventory explicitly separates the gateway receipt private key from its actor-assignment public-key pin. It also names the frozen schedule/actor/request/capability pins, signed gateway receipts, and the local plaintext response ledger. These records are audit/control state, not common priors or scientific model state. Signed probe/action records remain within the public-key/action-log layer.

The classifications are:

- `TRANSIENT_ACTOR_STATE`: disposable actor-local process, history, memory, files, environment, handles, or credentials.
- `IMMUTABLE_COMMON_PRIOR`: exact versioned and hashed source/config shared independently of predecessors.
- `DECLARED_ASSIGNMENT`: one frozen, outcome-blind current input; not a lineage carrier or common prior.
- `DECLARED_LINEAGE_CARRIER`: the only ordinary cross-generation state path.
- `DECLARED_BACKUP`: a separately declared recovery path, visible only when explicitly exposed.
- `ORCHESTRATOR_ONLY`: scheduling/audit/credential state that may not enter actor or model input.
- `PROVIDER_OPAQUE`: provider-controlled state for which the adapter has no mechanical reset or observation.
- `FORBIDDEN`: shell/browser/general tools, MCP, undeclared stores/files, and unrestricted actor network.

Evidence is separately labeled `MECHANICALLY CONTROLLED`, `CONTRACTUALLY/DOCUMENTATION-SUPPORTED`, `EMPIRICALLY PROBED`, or `OPAQUE/UNVERIFIED`. A documentation statement is never promoted to a mechanical reset.

Load-bearing distinctions:

- Model weights/tokenizer and serving substrate are provider-opaque, not hashed common priors. A model identifier is bound in the signed provider policy, but it is not a weight digest.
- Provider response objects, request/response IDs, prefix/KV caches, abuse logs, and routing/application state remain opaque. `store=false` records the request contract; it does not prove all provider retention is absent.
- The current assignment is frozen and signed but is not a cross-generation common prior.
- Carrier permissions are exact immutable grants over attempt, actor, lifecycle, lineage, generation, carrier ID/class, and one operation. Full grants and their hashes are retained in qualification evidence; durable carrier records bind the exact write/read capability hashes.
- Local logical/wire attempt IDs are mechanically controlled; provider-generated identifiers are not.
- Accepted response plaintext is retained only in the local orchestrator ledger for exact same-actor replay. It is transiently delivered to that current actor for receipt verification/acceptance, but is not a successor input unless explicitly written to a declared carrier.
- Only declared carrier/backup rows contain both a predecessor-write and successor-read edge.

Common-prior records hash the actual adapter source files and exact provider policy. Manifest validation rejects missing/reordered layers, altered semantics, mismatched source hashes, bad layer counts, and a bad document hash. The boundary assessor consumes the same canonical hashes before granting L0.
