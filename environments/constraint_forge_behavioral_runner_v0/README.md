# constraint-forge-behavioral-runner-v0

Native `verifiers.v1` multi-agent referee for one deterministic 24-job
Constraint Forge formation sequence.

The package keeps one v1 `Agent.interaction`, `Trace`, and `HarnessSession` per
role for the full 24-job dyad. The package-local session retains ordinary
within-job prompt history and resets its model-visible history through an
out-of-band runner context boundary between jobs; no context epoch is sent to
the model. The v1 Trace remains append-only audit history. The same
episode-owned X/Y agent objects, resolved model/config identity, and role-local
racks persist across jobs. The runner does not claim provider-side
neural-process identity beyond the identity fields it records.
The world is stepped only through
`ConstraintForgeJobSession`; the runner does not duplicate generator, physics,
parser, intervention, rack, or event-log rules.

The bundled text harness is interception-based, tool-free, non-streaming, and
does not use provider-managed continuation state. Tests include a real v1
`Agent.interaction`/`HarnessSession`/`InterceptionServer` path backed only by a
local deterministic fake client; no live model/provider call is authorized by
the package tests or preflight. The v1 agent/episode retry budgets and the text
client's SDK retry budget are explicitly zero; only a mechanically proven
pre-dispatch failure can enter the runner's one safe retry. Provider failures,
timeouts, and partial responses remain abort-only until a separately
authorized live canary qualifies their evidence.

The resulting `FormationHandoffV0` is a formation audit artifact. It is not an
H1 carrier or proof and is not consumed by the frozen H1 paths.
