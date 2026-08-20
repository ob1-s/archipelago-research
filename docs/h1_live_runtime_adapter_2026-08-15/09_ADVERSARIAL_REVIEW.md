# Adversarial review

The root scientific/architectural adjudication remained with `gpt-5.6-sol` at `xhigh` (session `01a0068d-e1a4-7512-9f2f-53d1f30697de`). Subtasks used `gpt-5.6-luna` at `max`; model/reasoning were checked from durable SQLite session metadata rather than inferred from task labels. No scientific judgment or integration decision was delegated.

The live thread admitted three concurrent Luna workers alongside root. A fourth concurrent spawn was rejected with `agent thread limit reached`, so the attempted seven-worker setting did not propagate to this session. Delegation remained active within the verified three-worker limit.

Verified Luna Max sessions used for this adapter were:

- Runtime routing canary: `01a00787-70c1-7dc1-9b4a-5750e333c7dd`.
- Isolation architecture: `01a0078d-fbe6-77c1-9325-8356f81f3c2c`.
- Provider/retry architecture and tests: `01a0078e-0f54-72a0-9ba0-917d87dd1264`, `01a0079f-55c7-7ec2-a904-b87779178de6`.
- Isolation, carrier/boundary, and orchestrator implementations/tests: `01a007ae-72fa-7182-9d0d-65fce37c31d4`, `01a007ae-8d36-7290-9d99-25597cd9c6c7`, `01a007ae-a6e2-73c2-8470-e06884c0c229`.
- Independent provider, boundary, and integration audits: `01a007b8-7841-7572-b0a9-f2f4bd8d485c`, `01a007b8-93b5-7d91-9fb9-fe4e83db0af3`, `01a007b8-aade-77c2-ab96-f0155b562a2e`.
- Provider, carrier, and signed-boundary repairs: `01a007c9-6586-7a50-949d-e4458a32a582`, `01a007c9-7b53-7653-b47a-a1cf4a8abf77`, `01a007c9-91ed-74b2-bd19-537dd44dce6b`.
- Assignment/capability and post-provider audits/implementation: `01a007d6-4452-7df2-8876-8a9e6754e699`, `01a007d7-44f9-75e1-a46f-657fad1f81e2`, `01a007dc-d24c-70f3-bd28-20c404008ac2`.
- Post-repair state, capability, and durable-evidence audits: `01a007e8-23ca-7c73-a851-9403ced1afda`, `01a007ed-3fdd-7991-86e1-ebc509b3ff99`, `01a007f2-1cba-71a3-9c41-9706107851fd`.

The state-inventory session `01a0078e-29f3-7b73-b291-e15ed1b20f97` is durably recorded as Luna `xhigh`, not Max, and was excluded from the verified-Max set. Its useful findings were independently rechecked by fresh Max workers.

The provider/retry passes found underspecified response acceptance, inferred storage claims, mutable retry semantics, incomplete actor/request pins, and unsafe restart replay. Repairs added a strict closed-world completed-response contract, exact model/request/output/actor/lifecycle pins, `store=false` versus unknown observed retention, signed gateway receipts, synchronous durable authorization/replay records, and a frozen automatic-retry budget of zero.

The state passes separated immutable common priors, assignments, orchestrator-only records, provider-opaque state, and the two declared carrier classes. The final 47-row inventory explicitly includes frozen schedule/actor/request/capability pins, the gateway private/public key split, signed receipts, and the local plaintext response ledger. Provider weights, caches, routing, logs, retention, and response-object state remain opaque.

The isolation passes removed a generic signing path; disabled nested user namespaces; audited namespaces, capabilities, no-new-privileges, environment, file surfaces, descriptors, network, and teardown; and fixed controller backing roots under `/tmp`. They also narrowed the claim correctly: read-only runtime binaries exist under `/usr`, but the trusted worker exposes no shell/subprocess/browser/MCP/arbitrary-file/network command. Arbitrary hostile-code and malicious-host containment are excluded.

The carrier passes repaired unsigned relabeling/parentage, crash windows, symlink/hardlink attacks, interprocess races, and incomplete assignment scoping. A late adversarial pass then reproduced a validly signed but unscheduled writer substitution after persistence/restart. The final repair records write/read capability hashes durably and validates the exact scheduled writer/read grants before opening carrier bytes. Missing, extra, broad, malformed, cross-actor, cross-lifecycle, wrong-attempt, relabeled, or post-restart substituted grants fail closed.

The assignment-integration pass found caller-supplied request pins, mutable schedule shadows, schedule-wide carrier unions, and read-before-recipient-authorization paths. Repairs made the schedule private/immutable, derive provider pins from exact assignments, require one-operation actor/lifecycle/attempt-scoped capabilities, authorize an active recipient before content access, and keep normal delivery metadata-only at the controller API.

Residual limits remain: the actual provider/model/project/auth/data controls are not pinned; gateway endpoint egress is not OS-allowlisted (recommended defense-in-depth); no live provider canary was made; the provider substrate is opaque; and malicious host/kernel/controller-binary compromise is outside the threat model. Those limits map to stage obligations (`required_as_part_of_h1_freeze`, `required_before_h1_execution`, `recommended_defense_in_depth`; see 00 and 10) and do not block begin/design.

## Final independent review tracks (closed on this commit)

The interrupted WIP left three final review tracks un-adjudicated; they were re-run as independent agent reviews against the checkpoint `0c3fcc0` and all findings were adjudicated below. All three returned **zero VALIDITY_CRITICAL** findings.

### Review A — turnover / carrier / isolation security (all DEFENSE_IN_DEPTH, no validity-critical finding)

1. `key_invalidated` is hardcoded `True` in the teardown path (`isolation.py` stop); revocation is a separate caller-visible step (orchestrator and boundary call it explicitly), so the evidence field is a snapshot, not a mechanism. No skip-revocation test existed. — Closed by an adjudication test in `test_isolation.py` that documents `key_invalidated` as factory-scope evidence while registry revocation remains a distinct caller step (fresh-actor definition 02:4).
2. A signed "shutdown" action is discarded: an uncooperative crash exiting 0 yields a "clean" teardown with no actor signature. Defense-in-depth gap; adversarial-crash teardown is not load-bearing for L0 wording. — Documented limitation; new crash-teardown test covers exit code 0 and 73, asserting mechanical teardown (process/group/root removed) without any actor-signed "clean" shutdown being manufactured.
3. Post-restart continuation (a registry-restore path) is dead code and misleading: reads/attributions require the active registry and there is no restore API; a store reload alone cannot support it. — Accepted: the misleading path is documented as unsupported; restart/replay semantics are defined only for the durable provider ledger, not for actor registries.
4–9. Additional probes (mount-root regression, revocation ordering, teardown signature coverage) — no mechanism defects; the mount-root probe test already exists (`TMPDIR` cannot redirect the actor's private backing root).

### Review B — provider / request / retry semantics (10 findings: 8 DEFENSE_IN_DEPTH, 2 OUT_OF_SCOPE-with-notes)

1. **DEFENSE_IN_DEPTH** — "exact request content known" is precise at the semantic-body level (closed, signed, policy/frozen-hash-pinned kwargs body) but is not a byte/wire claim: SDK-injected headers (`User-Agent`, `X-Stainless-*`, possible org/project env headers, proxy env), pre-pinning of `x-request-id`, sampling parameters, and SDK version are unpinned/unsigned/uncaptured. — Accepted with documentation (03); L0 does not depend on the wire surface.
2. **DEFENSE_IN_DEPTH** — nothing mechanically required a nonempty provider `x-request-id`; a live canary could pass with `None`. — **Resolved by the generic/provider split:** the generic evidence contract requires only gateway-owned transport identity (wire attempt ID, signed request/output hashes, signed receipt, nonempty response-body ID) and does not depend on an OpenAI-specific header; `GatewayReceipt.provider_request_id` / `ProviderResponse.request_id` are optional and preserved verbatim when the provider emits one. The OpenAI adapter still fails closed on a missing server `x-request-id`, and the qualification's `provider_transport_identity_recorded` gate plus regression tests pin the split (B22 records the same adjudication).
3. **DEFENSE_IN_DEPTH (coverage)** — five fail-closed branches were enforced but untested: in-flight `'active'` reservation, restart-without-key fresh dispatch, receipt-present-on-fresh-path, empty output text, and store/continuation tamper on durable replay. — **Closed:** new regression tests cover all five (see 08).
4. **OUT_OF_SCOPE with note** — ledger swap resistance relies on a spec field that is optional by default and on the host threat model. — Accepted; qualified paths always set the pin; host-level replacement exclusion is documented (03).
5. **DEFENSE_IN_DEPTH** — `ProviderRequest.input` item shape was unrestricted; conversation-shaped input could earn a clean L0. — **Closed:** per-item `{role, content}` allowlist with declared roles and string content, validators on `ProviderRequest` plus tests.
6. **DEFENSE_IN_DEPTH (nit)** — 401/5xx API errors are labeled `unknown_delivery` instead of `response_received`; both are terminal. — Accepted as cosmetic label choice; conservative by construction.
7. **OUT_OF_SCOPE with note** — the freeze authority (caller-supplied policy) is design intent under a host-trusted model; divergence between prepared and gateway policy fails at `execute`. — Accepted; schedule pin records the policy.
8. **DEFENSE_IN_DEPTH** — malformed-response admission matrix verified; cross-call response presentation is impossible (request-hash gate). — Verified by new regression test.
9. **OUT_OF_SCOPE** — whole-package re-presentation is the excluded malicious-host case; archived evidence should dedup by `(response_id, provider_request_id, gateway_id)`. — Adopted as an archive rule; when the provider emits no request identifier, dedup falls back to `(response_id, gateway_id, request_hash)`.
10. **DEFENSE_IN_DEPTH (nit)** — at-most-once dispatch verified incl. in-flight rows, crash windows, and no-rowless finish; the vestigial retry-loop shape cannot iterate even with a nonzero budget. — Accepted; commented in code.
11. **DEFENSE_IN_DEPTH** — a skipped controller `registry.revoke()` was behaviorally documented (A1) but not yet explicit durable L0 evidence; a journal of controller lifecycle events was missing. — **Closed:** `LifecycleEvent` journal (`spawn` / `teardown_complete` / `authorization_revoked`), contiguous-sequence validation, predecessor-revocation-before-successor-start ordering check, fixture H, and the `predecessor_authorization_revoked` / `predecessor_revocation_precedes_successor_start` gates.
12. **DEFENSE_IN_DEPTH** — Q07/Q13/Q14 carried `PASS WITH REPAIRS` at `execution` scope, so a clean qualification could be misread as requiring deployment hardening or an OpenAI header before design. — **Closed:** re-adjudicated PASS at `design_freeze` with explicit stage splits (`required_as_part_of_h1_freeze`, `required_before_h1_execution`, `recommended_defense_in_depth`).

### Review C — cold-read claim audit (all ACCEPTABLE / COSMETIC; verdict APPROVE-AS-DESIGN-AND-QUALIFICATION)

Machine-verified: `record_hash` self-consistency (`7eda6c0b…` at checkpoint; `295fb94e…` after the first completion; regenerated `09d8ec70…` by the final repair pass on branch `fix/h1-live-runtime-final-review`; regenerated `59b3a516…` by the lifecycle-journal durability repair on branch `fix/h1-live-runtime-lifecycle-journal`; regenerated `a0b421f1…` by the admission-parity repair on branch `fix/h1-live-runtime-admission-parity`), 9 common-prior hashes identical, `COMMON_INSTRUCTION_CONTRACT` hash `45f0b7d2…`, 47/47 state layers, manifest document fresh == archived, model-free regression hash matches the runner print format, embedded record hash matches. Findings:

1. Precise L0 wording is emitted only under clean evidence. — Accepted.
2. Model-free vs runtime semantics are explicitly separated; no false-credit slip. — Accepted.
3. L1–L5 locked to not-credited; "PASS" never authorizes a live run. — Accepted.
4. Schedule/assignment frozen and output-blind; no caller-injected provider content. — Accepted.
5. Provider-opaque layers honestly ring-fenced with spelled-out residual uncertainty. — Accepted.
6. Freeze-before-live discipline (contract-freeze before any spawn; canaries archived, not evidence). — Accepted.
7. Test suite regression pins the record hash/claim mapping/gate counts. — Accepted; updated for the new structure.
8. **COSMETIC** — "340 tests" was not independently verifiable and feels vague. — **Closed:** this commit pins the exact collected/passed counts (360 adapter, 92 model-free, one `uv run pytest` run) in 08.

Verdict: the dossier survives a cold read as internally consistent, honest, and machine-reproducible; the strongest usable claim is exactly the bounded L0 wording, pending the execution-gate canary.

## Final repair: durable lifecycle journal (closed on this commit)

The B11 journal described above existed only inside the mechanical canary: `run_clean_mechanical_canary` accumulated `LifecycleEvent` models in a local in-memory list, so a future H1 runtime had no load-bearing revocation evidence at the reusable `Orchestrator`, and successor admission depended on in-memory controller state that a restart would erase. This commit closes that gap and adds the following verified facts:

- **Durable journal in the reusable controller.** `lifecycle_journal.LifecycleJournal` is the same append-only SQLite journal the runtime's `Orchestrator` uses for every `spawned` / `teardown_complete` / `authorization_revoked` transition (`journal_mode=WAL`, `synchronous=FULL`, immediate transactions, rows committed before the controller proceeds, restart-readable, no rewritten rows, no secrets).
- **Verified revocation ordering.** On teardown the controller reaps the process, journals `teardown_complete`, calls `registry.revoke()`, verifies the registry reports the lifecycle inactive, and only then journals `authorization_revoked`; any failure in that chain surfaces and leaves no revocation row (fail closed).
- **Successor admission from durable state.** `Orchestrator.start_actor` blocks any later-generation actor unless every earlier generation in the lineage has committed the complete chain (`spawned` < `teardown_complete` < `authorization_revoked`, each row bound to its frozen assignment) in the journal — the same rule after a controller restart, where the in-memory actor map is empty. A journal/registry disagreement (journal says revoked, registry still active) also fails closed.
- **Strict per-lifecycle order enforced in L0 evidence.** The assessor now rejects `spawned<teardown_complete<authorization_revoked` violations, duplicate lifecycle events, fabricated rows that map to no recorded runtime identity (binding each row to its frozen assignment attempt/actor/lineage/generation), and multi-predecessor turnovers where any earlier generation is missing or misordered; the existing revocation-before-successor-start check is preserved.
- **Canary uses the real path.** `run_clean_mechanical_canary` drives the same `Orchestrator` + journal the runtime uses; the evidence journal is the actual durable controller journal, not a canary-local reconstruction.
- **Fixture H on the real controller path.** A test-only silent-revocation registry runs real Bubblewrap processes through the controller: teardown completes and is journaled, the skipped revocation leaves no `authorization_revoked` row, the controller's own revocation verification fails closed, and the successor is blocked.
- **Restart tests.** A controller recreated on the same journal admits the successor after a fully journaled turnover and fails closed when revocation was never committed.
- **Verification.** 378 adapter tests pass (was 368; +10 new), model-free 92 / 15/15 unchanged, `compileall` and `uv build` succeed; artifacts regenerated with `record_hash 59b3a516…`, 21/21 gates, `status=PASS`, `authorized_to_run_h1=false`, zero live calls.

The dossier statement stands: lifecycle revocation evidence is produced by the same durable controller journal used by the reusable runtime.

## Final repair: successor admission parity (closed on this commit)

Admission previously required only committed teardown+revocation rows; an unqualified teardown could still leave `teardown_complete` committed, and the L0 assessor (which validates against contested runtime records) applied stricter lifecycle checks than the reusable controller (which trusted its own in-memory view). Admission must be at least as strict as L0, so both consume the same shared predicate. This commit closes the parity gap and adds the following verified facts:

- **Shared lifecycle predicate.** `lifecycle_chain_outcome(events, lifecycle_id, attempt_id, actor_id, lineage_id, generation)` in `lifecycle_journal.LifecycleJournal` is the single full-chain predicate reused by successor admission, journal validation, and the L0 assessor: a contiguous unique `spawned` < `teardown_complete` < `authorization_revoked` chain bound to the frozen assignment, verdicts `complete` / `journal_sequence_invalid` / `missing_spawn` / `missing_teardown` / `missing_revocation` / `duplicate_event` / `out_of_order` / `mismatched_metadata`.
- **Full-chain admission.** The reusable runtime will not expose a successor unless every required predecessor lifecycle already satisfies the same durable lifecycle predicate later required for L0 qualification. A journal holding only teardown+revocation (no spawned row), a chain with mismatched attempt/actor/lineage/generation metadata, or any missing/misordered/duplicate event blocks the successor with the exact predicate verdict; the same rule holds after a controller restart.
- **Teardown evidence validated before journaling.** `teardown_complete` is persisted only after the returned teardown evidence itself satisfies the qualified teardown predicate (matching actor/lifecycle, process absent, process group absent, private root removed, key invalidated, exit code 0). Unqualified evidence (parameterized over every field, plus a crash exit code) raises on `stop_actor`, drops the actor from the live map, persists neither `teardown_complete` nor `authorization_revoked`, and leaves the successor blocked — the registry check additionally fails closed since revocation never ran.
- **Admission and L0 agree by construction.** The assessor maps each shared-predicate verdict to a lifecycle violation (`missing_*` → `predecessor_authorization_not_revoked`, `out_of_order` → `predecessor_lifecycle_order_invalid`, `duplicate_event` → `lifecycle_event_duplicate`, `mismatched_metadata` / `journal_sequence_invalid` → `lifecycle_event_inconsistent_with_runtime_records` / `lifecycle_event_order_invalid`), and a document parity test proves, for every accepted and rejected journal state, that runtime admission and the L0 lifecycle portion hand down the same verdict; the teardown predicate is likewise proven to match the L0 teardown conditions.
- **Verification.** 406 adapter tests pass (was 378; +28 new), model-free 92 / 15/15 unchanged, `compileall` and `uv build` succeed; artifacts regenerated with the final qualification record hash, 21/21 gates, `status=PASS`, `authorized_to_run_h1=false`, zero live calls.

The dossier statement stands: complete turnover within the controlled and documented model-visible state boundary, with successor exposure gated by the same durable lifecycle evidence L0 later requires.

## Adjudication summary

- **Closed by repair:** B3 (all five failure-mode tests), B5 (input-shape allowlist), B11 (revocation journal as durable L0 evidence + fixture H), B12 (stage-split re-adjudication of Q07/Q13/Q14), C8 (pinned test counts), the lifecycle-journal durability repair (journal moved into the reusable controller, SQLite append-only, verified revocation, restart admission, strict per-lifecycle order, duplicate/fabricated-row rejection, multi-predecessor rule, controller-path fixture H, +10 tests), the admission-parity repair (shared full-chain predicate across admission and L0, teardown evidence validated before journaling, +19 tests), and Review A items 1–2 regression tests (skip-revocation and exit-0 crash teardown).
- **Resolved by the generic/provider split:** B2/B22 (provider-issued request ID optional in the generic contract, preserved when present; OpenAI adapter remains fail-closed on `x-request-id`).
- **Accepted as documentation:** B1 (body-vs-wire scope), B6, B8, B10; A2 (crash-exit-0 teardown), A3 (no registry-restore API).
- **Out of scope by declared threat model:** B4, B7, B9 (host-trusted / freeze authority / whole-package re-presentation).
- **Stage obligations (see 10):** OS egress allowlist (`recommended_defense_in_depth`), real provider pin (`required_as_part_of_h1_freeze`), live canary (`required_before_h1_execution`). These are deployment obligations, not validity repairs.
