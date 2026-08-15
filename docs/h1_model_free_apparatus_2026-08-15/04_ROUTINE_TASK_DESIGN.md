# Routine task design

The task is a minimal two-key relay with two externally assigned capability
positions. These positions are not evidence of endogenous social roles.

Before turnover, a left actor derives a lineage-specific permutation from its
private calibration input. A right actor reads the left artifact and derives a
coefficient rule bound to the left artifact’s digest. The two immutable
successor-facing artifacts therefore have distinct contributions and an
auditable dependency.

Held-out inputs are introduced only after turnover:

1. the fresh encoder privately receives `u`, reads the left artifact, and emits
   a permuted intermediate;
2. the fresh checker privately receives `v`, reads the right artifact and the
   intermediate, then emits a modular acknowledgment under a held-out mode bit;
3. the encoder consumes that acknowledgment and produces the final vector.

The required graph is encoder → checker → encoder, with exactly two actor IDs.
Neither position receives the other’s private input or complete rule. The
held-out vector and mode do not occur in carrier payloads.

A single scripted actor given all inputs can compute the correct answer, proving
generic success is separable from routine fidelity; its fidelity is zero. The
orchestrator comparator also returns a correct answer but records orchestrator
action origins and receives no L2/L5 credit.

The terminal-replay control shows that static external memory can be sufficient
for downstream routine behavior. It receives L1–L2, not arm-level L3–L5. This
does not imply that a separate source run’s upstream generation was unnecessary;
it only shows recipients did not need that history once the final artifacts
existed.
