# H1 live-runtime adapter v1

Mechanical, nonscientific qualification of the process, state, credential,
carrier, provider-request, retry, and turnover boundary for a later bounded H1
pilot. It does not run H1 and does not collect model behavior as evidence.

The qualified actor is a fresh Bubblewrap process with new PID, mount, IPC,
UTS, user, cgroup, and network namespaces; fresh private work/home/tmp/cache
mounts; a cleared environment; no model-visible predecessor transcript; and an
internally generated ephemeral Ed25519 action key. A hash-validated frozen
schedule gives exact actor/lifecycle/attempt-scoped carrier capabilities; the
only cross-generation path is the declared carrier API. Model/provider traffic, when later enabled,
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

Current status is `PASS WITH REPAIRS` for designing/freezing a pilot only.
It is not authorization to run H1 or collect scientific model state.
