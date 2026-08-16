# H1 live-runtime adapter v1

Mechanical, nonscientific qualification of the process, state, credential,
carrier, provider-request, retry, and turnover boundary for a later bounded H1
pilot. It does not run H1 and does not collect model behavior as evidence.

The qualified actor is a fresh Bubblewrap process with new PID, mount, IPC,
UTS, user, cgroup, and network namespaces; fresh private work/home/tmp/cache
mounts; a cleared environment; no model-visible predecessor transcript; and an
internally generated ephemeral Ed25519 action key. A hash-validated frozen
schedule gives exact actor/lifecycle/attempt-scoped carrier capabilities; the
only cross-generation path is the declared carrier API. The reusable
`Orchestrator` control plane journals every lifecycle transition (spawn /
teardown_complete / authorization_revoked per lifecycle, bound to its frozen
assignment) into a durable append-only SQLite journal, verifies registry
revocation before journaling it, and admits a successor only from committed
journal state that survives a controller restart. Model/provider traffic, when later enabled,
must use the signed stateless Responses request gateway; actors never receive
general network access or provider credentials.

```bash
uv sync --extra dev
uv run pytest
uv run h1-runtime-qualify
```

Qualification uses scripted mechanical canaries and known-bad fixtures. It
makes zero live model calls. Do not use `prime eval` to run this package: the
single native `verifiers.v1` Taskset is a typed qualification manifest, not a
behavioral task or authorization for inference.

The exact L0 wording supported by a clean record is:

> complete turnover within the controlled and documented model-visible state boundary

Opaque provider infrastructure remains outside that claim.

Current status is `PASS` for beginning/designing a bounded pilot only
(`execution_status = NO — provider/deployment validation remains`). It is not
authorization to run H1 or collect scientific model state. Stage obligations
are recorded in the qualification report and dossier (00/08/10):
`required_before_h1_design` is empty; `required_as_part_of_h1_freeze` pins the
real provider configuration (endpoint/model/auth/data-control/runtime config,
Q13); `required_before_h1_execution` runs one trivial non-H1 live canary on the
frozen configuration (Q14) and keeps provider caches/logs/routing/retention
OPAQUE/UNVERIFIED (Q15); `recommended_defense_in_depth` OS-allowlists gateway
egress to the pinned endpoint (Q07, recommended hardening, not a validity
prerequisite).
