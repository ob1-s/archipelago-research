# Control-classification matrix for the L0 claim

This matrix records how every candidate repair/limit raised by the final adversarial reviews (09) was classified against the bounded L0 claim:

> complete turnover within the controlled and documented model-visible state boundary

L0 is a **frozen-state turnover** claim in the **controlled and documented** boundary. A control is:

- **Load-bearing (VALIDITY-CRITICAL).** Its absence, misreport, or bypass changes or voids the wording. No final-review finding earned this class.
- **Mechanically enforced after repair (CLOSED).** Rolls into the qualified contract and its regression tests.
- **Documented limitation / defense-in-depth (ACCEPTED).** Is out of the claim's scope by wording or threat model; kept honest by explicit documentation, never promoted to mechanical reset.
- **Deferred execution obligation (DEPLOYMENT).** Required only once a real provider configuration is frozen and run; never convertible into scientific evidence.

| # | Control / limit | Class | Disposition |
|---|---|---|---|
| B2 | Nonempty server `x-request-id` in the evidence contract | CLOSED | `GatewayReceipt.provider_request_id` / `ProviderResponse.request_id` mandatory; OpenAI backend fails closed on missing header; 19th gate + tests |
| B5 | `ProviderRequest.input` restricted to plain `{role, content}` message items with declared roles and string content | CLOSED | Model validator + tests; conversation-shaped/tool-shaped input cannot earn L0 |
| B3 | Five fail-closed branches exercised: in-flight reservation, restart-without-key dispatch, receipt presented onto a fresh attempt, empty output text, store/continuation tamper on durable replay | CLOSED | New regression tests (see 08) |
| A1 | `key_invalidated` factory scope vs registry revocation as caller step | CLOSED | Skip-revocation test documents the split (02:4 requires the caller step) |
| A2 | Crash exit code 0 teardown without actor-signed shutdown | CLOSED | Exit-0/73 crash-teardown test; no "clean" signature is manufactured |
| C8 | Pin exact collected/passed test counts | CLOSED | 360 adapter / 92 model-free, one recorded `uv run pytest` run |
| B1 | "Exact request content known" = semantic-body level; SDK/header wire surface unpinned | ACCEPTED | Scope note in 03; L0 wording does not depend on the wire surface |
| B6 | 401/5xx rejection labeled `unknown_delivery` (both terminal) | ACCEPTED | Conservative label by construction |
| B8 | Malformed-response admission matrix; cross-call presentation impossible | ACCEPTED | Verified by new regression test |
| B10 | At-most-once dispatch verified; vestigial retry loop cannot iterate | ACCEPTED | Commented in code |
| A3 | No actor registry-restore/restart-replay API (dead path documented unsupported) | ACCEPTED | Restart semantics exist only for the durable provider ledger |
| B4 | Ledger swap resistance relies on caller-supplied spec pin + host threat model | OUT_OF_SCOPE | Qualified paths always set the pin; malicious host excluded (03) |
| B7 | Freeze authority (caller-supplied policy) is host-trusted design intent | OUT_OF_SCOPE | Divergence fails at `execute`; schedule pin records the policy |
| B9 | Whole-package evidence re-presentation by a host | OUT_OF_SCOPE | Archive rule: dedup by `(response_id, provider_request_id, gateway_id)` |
| Q07 | Gateway OS egress allowlist to pinned endpoint | DEPLOYMENT | Defense-in-depth hardening required before execution (10) |
| Q13 | Real provider endpoint/model/project/auth pin | DEPLOYMENT | Part of the H1 design/freeze; nothing qualified here binds a deployment |
| Q14 | Trivial non-H1 live canary on the frozen endpoint | DEPLOYMENT | `x-request-id` requirement now mechanized; canary itself is execution-gated (06) |
| Q15 | Provider caches/routing/logs/retention/weights | ACCEPTED (OPAQUE/UNVERIFIED) | Carried as provider-opaque; no successor-read edge; L0 does not depend on their absence; proof of absence is not claimed |

Rule applied throughout: a defense-in-depth or out-of-scope item never upgrades to a repair, and an accepted limitation never broadens the L0 wording. All dispositions are machine-reflected in `RUNTIME_BOUNDARY_STATE.json` (claim mapping, 19 gates, scoped readiness questions, split required-repair lists).