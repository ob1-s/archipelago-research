# Control-classification matrix for the L0 claim

This matrix records how every candidate repair/limit raised by the final adversarial reviews (09) was classified against the bounded L0 claim:

> complete turnover within the controlled and documented model-visible state boundary

L0 is a **frozen-state turnover** claim in the **controlled and documented** boundary. A control is:

- **Load-bearing (VALIDITY-CRITICAL).** Its absence, misreport, or bypass changes or voids the wording. No final-review finding earned this class.
- **Mechanically enforced after repair (CLOSED).** Rolls into the qualified contract and its regression tests.
- **Documented limitation / defense-in-depth (ACCEPTED).** Is out of the claim's scope by wording or threat model; kept honest by explicit documentation, never promoted to mechanical reset.
- **Stage obligation.** Required at a specific H1 stage (`required_as_part_of_h1_freeze`, `required_before_h1_execution`) or recommended hardening (`recommended_defense_in_depth`); never convertible into scientific evidence and never retroactively invalidating a completed stage.

| # | Control / limit | Class | Disposition |
|---|---|---|---|
| B2/B22 | Provider-issued request identifier in the generic evidence contract | CLOSED (generic/provider split) | Generic contract requires only gateway-owned transport identity (wire attempt ID, signed request/output hashes, signed receipt, nonempty response-body ID); `GatewayReceipt.provider_request_id` / `ProviderResponse.request_id` optional, preserved verbatim when present; OpenAI adapter still fails closed on missing server `x-request-id`; `provider_transport_identity_recorded` gate + tests |
| B5 | `ProviderRequest.input` restricted to plain `{role, content}` message items with declared roles and string content | CLOSED | Model validator + tests; conversation-shaped/tool-shaped input cannot earn L0 |
| B3 | Five fail-closed branches exercised: in-flight reservation, restart-without-key dispatch, receipt presented onto a fresh attempt, empty output text, store/continuation tamper on durable replay | CLOSED | New regression tests (see 08) |
| D1 | Lifecycle journal living only in canary-local memory (reusable runtime had no load-bearing revocation evidence; restart erased admission state) | CLOSED (durability repair) | Journal moved into the reusable `Orchestrator` as append-only SQLite; revocation verified against the registry before journaling; successor admission from durable state identical across restarts; controller-path skip-revocation and multi-predecessor tests; canary consumes the same journal the runtime uses (06, 09) |
| A1/B11 | Controller registry revocation as durable L0 evidence, distinct from `key_invalidated` factory scope | CLOSED | `LifecycleEvent` journal in the same append-only SQLite journal the reusable controller uses (`journal_mode=WAL`, `synchronous=FULL`, committed before the controller proceeds, restart-readable); every row bound to its frozen assignment attempt/actor/lineage/generation; contiguous-sequence, strict per-lifecycle order (`spawned`<`teardown_complete`<`authorization_revoked`), duplicate, and fabricated-row checks; skipped `registry.revoke()` fails L0 (fixture H) and fails closed on the real controller path; successor admission requires the complete committed chain surviving restart; journal/registry disagreement fails closed (02:4); gates `predecessor_authorization_revoked` / `predecessor_revocation_precedes_successor_start` |
| D2 | Successor admission weaker than L0 lifecycle validation (in-memory controller view vs contested-record assessor; unqualified teardown evidence could still journal `teardown_complete`) | CLOSED (admission parity) | Shared `lifecycle_chain_outcome` predicate consumed by admission, journal validation, and the L0 assessor; the reusable runtime will not expose a successor unless every required predecessor lifecycle already satisfies the same durable lifecycle predicate later required for L0 qualification; `teardown_complete` is persisted only after the returned teardown evidence itself satisfies the qualified teardown predicate (parameterized unqualified-evidence tests persist no rows; parity tests prove admission and L0 agree on every journal state) (02:4, 06, 08, 09) |
| A2 | Crash exit code 0 teardown without actor-signed shutdown | CLOSED | Exit-0/73 crash-teardown test; no "clean" signature is manufactured |
| C8 | Pin exact collected/passed test counts | CLOSED | 397 adapter / 92 model-free, one recorded `uv run pytest` run |
| B1 | "Exact request content known" = semantic-body level; SDK/header wire surface unpinned | ACCEPTED | Scope note in 03; L0 wording does not depend on the wire surface |
| B6 | 401/5xx rejection labeled `unknown_delivery` (both terminal) | ACCEPTED | Conservative label by construction |
| B8 | Malformed-response admission matrix; cross-call presentation impossible | ACCEPTED | Verified by new regression test |
| B10 | At-most-once dispatch verified; vestigial retry loop cannot iterate | ACCEPTED | Commented in code |
| A3 | No actor registry-restore/restart-replay API (dead path documented unsupported) | ACCEPTED | Restart semantics exist only for the durable provider ledger |
| B4 | Ledger swap resistance relies on caller-supplied spec pin + host threat model | OUT_OF_SCOPE | Qualified paths always set the pin; malicious host excluded (03) |
| B7 | Freeze authority (caller-supplied policy) is host-trusted design intent | OUT_OF_SCOPE | Divergence fails at `execute`; schedule pin records the policy |
| B9 | Whole-package evidence re-presentation by a host | OUT_OF_SCOPE | Archive rule: dedup by `(response_id, provider_request_id, gateway_id)`; when the provider emits no request identifier, fall back to `(response_id, gateway_id, request_hash)` |
| Q07 | Gateway OS egress allowlist to pinned endpoint | RECOMMENDED (defense-in-depth) | Recommended deployment hardening; neither a validity prerequisite nor an execution blocker; not a repair (10) |
| Q13 | Real provider endpoint/model/project/auth pin | STAGE (freeze) | Deliverable of the H1 freeze stage (`required_as_part_of_h1_freeze`); nothing qualified here binds a deployment |
| Q14 | Trivial non-H1 live canary on the frozen endpoint | STAGE (execution) | `required_before_h1_execution`; failure blocks execution (contract repair or re-freeze), never retroactively invalidates the generic qualification (06) |
| Q15 | Provider caches/routing/logs/retention/weights | ACCEPTED (OPAQUE/UNVERIFIED) | Carried as provider-opaque; no successor-read edge; L0 does not depend on their absence; proof of absence is not claimed |

Rule applied throughout: a defense-in-depth or out-of-scope item never upgrades to a repair, and an accepted limitation never broadens the L0 wording. All dispositions are machine-reflected in `RUNTIME_BOUNDARY_STATE.json` (claim mapping, 21 gates, scoped readiness questions, stage-split obligation lists).
