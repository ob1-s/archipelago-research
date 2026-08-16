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

Residual limits remain: the actual provider/model/project/auth/data controls are not pinned; gateway endpoint egress is not yet OS-allowlisted; no live provider canary was made; the provider substrate is opaque; and malicious host/kernel/controller-binary compromise is outside the threat model. These limits produce `PASS WITH REPAIRS` and constrain the exact L0 wording.
