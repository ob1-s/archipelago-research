# Fresh actor definition

A successor counts as structurally fresh only if all controlled state surfaces satisfy the following definition:

1. A new operating-system process is exec'd; no worker, thread pool, fork/COW image, heap, or interpreter is borrowed.
2. It has new actor, lifecycle, session, process-start, and public-key identities.
3. It is PID 1 in fresh PID, mount, IPC, UTS, user, cgroup, and network namespaces.
4. Its predecessor has exited, its process group is absent, its private root is removed, and its public key is revoked before successor exposure. Revocation is recorded in the durable controller lifecycle journal (`spawn` / `teardown_complete` / `authorization_revoked` per lifecycle, each row bound to its frozen assignment attempt/actor/lineage/generation) and is mechanically required L0 evidence before any successor spawn, independent of the teardown episode's factory-scope `key_invalidated` snapshot. The journal is append-only SQLite; the controller commits each row before proceeding, verifies the registry reports the lifecycle inactive before journaling `authorization_revoked`, and accepts every successor admission through the same full-chain predicate L0 later requires. The reusable runtime will not expose a successor unless every required predecessor lifecycle already satisfies the same durable lifecycle predicate later required for L0 qualification: a complete `spawned` < `teardown_complete` < `authorization_revoked` chain (each row unique, bound to its frozen assignment, globally contiguous in sequence) that survives a controller restart. `teardown_complete` is persisted only after the returned teardown evidence itself satisfies the qualified teardown predicate (matching actor/lifecycle, process and process group absent, private root removed, key invalidated, exit code 0).
5. It starts with empty actor history and receives no provider `previous_response_id` or Conversation object.
6. It receives fresh private `/work`, `/home`, `/tmp`, `/dev/shm`, `/cache`, and environment-derived storage; predecessor secret-byte canaries are absent.
7. Its environment is cleared and rebuilt from an exact allowlist with a fresh sentinel. Provider credentials are absent.
8. It has zero Linux effective capabilities, `NoNewPrivs=1`, nested user namespaces disabled, and no open descriptor above stdio except the sandbox's fresh immutable `/dev/urandom` entropy source.
9. It has no default route, DNS resolution, or external connection and no shell/browser/general-tool/MCP interface.
10. The only predecessor-authored input it may receive is an explicitly enumerated, hash-finalized declared carrier or backup with valid signed provenance and an exact frozen read capability for the active recipient lifecycle.

Freshness is structural, not a label. Replacing an actor ID while retaining a process, transcript, provider continuation, filesystem, environment/cache, key, undeclared external state, or stale worker fails L0.

The threat model covers ordinary runtime/controller bugs and predecessor state leakage. It does not claim resistance to a malicious host root, compromised kernel, altered Bubblewrap binary, or hostile provider internals. Those limits are explicit rather than silently included in “complete turnover.”
