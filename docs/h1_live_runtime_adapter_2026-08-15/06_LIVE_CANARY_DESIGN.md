# Live canary design

The completed qualification canary is mechanical and no-model:

1. Freeze a hash-validated public schedule contract over provider policy/common priors, gateway public key, both actor specs/assignments, exact request hash, and exact writer/reader capability hashes.
2. Spawn generation 0 in a new Bubblewrap actor.
3. Append random private history, write random secret-byte canaries in `/work`, `/home`, `/tmp`, `/dev/shm`, `/cache`, and an environment-derived path, and sign the exact canary/path/hash/history evidence inside the actor.
4. Generate random carrier content inside the actor, sign its complete carrier ID/class/lineage/generation/content/parent binding, authorize/finalize it with the frozen writer capability, then terminate and revoke generation 0.
5. Spawn generation 1 with fresh structural identities.
6. Probe every predecessor path/history/environment value and the actor network; all hidden-state probes must be negative and the actor must sign the exact probe records.
7. Authorize the declared-carrier positive control with the exact active-recipient reader capability and sign its read provenance before treating the read as valid.
8. Send an actor-signed, exact-request-pinned stateless request through the same gateway boundary to a deterministic scripted backend; require a gateway-signed response receipt and an actor-signed acceptance action.
9. Tear down generation 1 and retain the full nonsecret allowlist, schedule pins, capability hashes, signed actions, receipt, and teardown evidence.

Runtime fixtures are:

- A — provider session/continuation present: fail.
- B — stale worker reused: fail.
- C — predecessor filesystem visible: fail.
- D — environment/cache reused: fail.
- E — signing key reused: fail.
- F — undeclared external carrier present: fail.
- G — clean turnover with declared carrier positive control: pass.

Before execution, one additional live provider canary is required (deferred, not a design/freeze blocker). It must be semantically trivial, fixed in advance, and useful only for transport/session mechanics: capture exact request policy/body hash, local logical/wire IDs, provider response/body ID, the server `x-request-id` (now mandatory in the evidence contract and fail-closed in the OpenAI backend), completed status, reported model, absence of continuation/conversation/tools, and `provider_storage_observed=null`. It must not contain an H1 routine, carrier-transmission target, culture/social prompt, adaptive follow-up, or scientifically interpreted behavior.

A live canary failure blocks freezing/running; a success qualifies only the observed provider contract on that pinned configuration. It cannot make provider caches or retention mechanically controlled.
