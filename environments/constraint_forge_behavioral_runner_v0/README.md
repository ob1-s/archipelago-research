# constraint-forge-behavioral-runner-v0

Native `verifiers.v1` multi-agent referee for one deterministic 24-job
Constraint Forge formation sequence.

The package keeps the v1 `Env`/`Agent.interaction` lifecycle and uses a fresh
interaction for each job context while retaining the same episode-owned X/Y
agents and role-local racks. The world is stepped only through
`ConstraintForgeJobSession`; the runner does not duplicate generator, physics,
parser, intervention, rack, or event-log rules.

The bundled text harness is interception-based, tool-free, non-streaming, and
does not use provider-managed continuation state. Repository validation uses
deterministic fake actors only. No live model/provider call is authorized by
the package tests or preflight.

The resulting `FormationHandoffV0` is a formation audit artifact. It is not an
H1 carrier or proof and is not consumed by the frozen H1 paths.
