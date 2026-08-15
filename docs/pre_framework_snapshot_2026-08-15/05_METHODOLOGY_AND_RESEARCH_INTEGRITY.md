# Methodology and research integrity

This snapshot preserves methodology as an object of audit. A clean result is
not enough if the apparatus, lifecycle, allocation, or interpretation makes a
different estimand.

## Source and interpretation hierarchy

For historical concepts, use this order:

1. visible user proposal, adoption, or explicit correction;
2. visible assistant proposal that the user visibly adopted;
3. visible assistant synthesis;
4. retrospective recovery or later summary.

For empirical and operational facts, use:

1. frozen experiment package and pre-live manifest;
2. raw archive and immutable analysis input;
3. frozen analysis/report;
4. Git history and operational logs;
5. visible conversation when no durable artifact exists.

An assistant’s external factual claim in the conversation is not a source for
an external fact. Mark it V until independently verified.

## Permanent rules

1. **One-shot equivalence:** test whether an informationally equivalent
   recipient intervention explains the result. A recipient effect is not
   endogenous culture.
2. **Assay/phenomenon separation:** report recipient response, source effect,
   endogenous transmission, turnover persistence, and population dynamics as
   different claims.
3. **Freeze before live inference:** commit prompts, source, tests, config,
   assignment, and analysis before the first scientific model request.
4. **No scientific edits after freeze:** archive later; do not rewrite or
   backdate the pre-live commit.
5. **Outcome-blind collection:** operational monitoring may expose attempts,
   eligibility counters, throughput, ETA, process health, and errors, but not
   SWITCH/RETAIN behavior, treatment summaries, q-specific outcomes, or
   threshold locations.
6. **Immutable assignment:** conditions and quota cells must be deterministic
   functions of attempt/trace identity before behavior and independent of
   asynchronous completion order.
7. **Preserve raw data:** copy byte-for-byte, hash source and destination, and
   derive an immutable analysis input before inferential analysis.
8. **Missingness is data:** missing or incomplete phase-2 actions remain
   visible; the frozen ITT rule must not silently turn lifecycle failure into
   exclusion.
9. **Lineage-aware units:** descendant rollouts from one lineage are not
   automatically independent. Use independent populations/lineages as the
   primary unit where appropriate and nested resampling otherwise.
10. **Do not infer agency:** persistence, concealment, or policy following does
    not establish self-preservation, intention, deception, culture, or polity.

## Historical failures and repairs

### A. Outcome-blind exact resume

An operational interruption can be a provenance/integrity problem without
being scientific contamination. If the evaluator stopped before producing
behavioral output, or if an exact continuation resumes the frozen state, and no
behavioral outcome informed any design/analysis change, the scientific state is
unchanged. Outcome-blind controls protect against outcome-conditioned choices;
they do not prohibit transparent recovery from an operational failure.

### B. Completion-order allocation hazard

The dangerous scheduler is: concurrent attempts finish in arbitrary order, and
the next available quota slot is assigned in completion order. Latency then
becomes part of the treatment allocation. Concurrency greater than one is
unsafe under that design. The repair is to derive condition and nominal cell
from immutable attempt/trace identity before launch; an atomic ledger may
accept/reject an already assigned eligible row, but may not choose its
condition. The threshold package records and tests this property.

### C. Read-only progress monitors

The boundary and transport monitors are operational tools. They may read
assignment counters, attempt counts, process status, timestamps, throughput,
ETA, and evaluator health. They must not open trace contents, derive behavior,
inspect treatment cells, acquire the live allocator lock, or mutate the run.
This is an observability boundary, not a claim that the monitor is blind to all
operational metadata.

### D. Continuation-nudge contamination

A continuation message inserted by a custom harness after a treatment or
natural yield is part of the episode and can change the estimand. It is not a
generic harmless lifecycle repair. The failed Luna qualification exposed this
problem: the null harness ended its segment before the environment could send
R2. The native `Agent.interaction()` design repairs the lifecycle by making the
environment own the resume and sending one frozen Turn-2 message after natural
yield, without a treatment-dependent nudge.

### E. Scientific freeze versus Git timestamp

The commit timestamp is operational evidence of when a commit was recorded; it
is not the integrity criterion. Integrity means the scientific choices were not
changed after live inference or based on observed outcomes. Do not rewrite,
backdate, or pretend a post-run archive commit was the pre-live freeze.

### F. Interface and order confounds

“B-first” in the last line of a prompt is not globally B-first if descriptive
prose, explicit instruction, tool docstrings, and serialized schemas expose
other orderings. The 160-row label diagnostic showed that K/M choices tracked
the majority of three order surfaces. Future assays remove or explicitly
balance every model-visible ordering surface.

### G. Survivor and denominator conditioning

If only surviving or eligible trajectories are analyzed, the denominator can
be a collider affected by pressure, capability, detection, and observability.
H2 must report absolute persistence, authorized/legible persistence, covert
persistence, survivor composition, severity/capability, detection, attribution,
time, and hazard separately. Do not make “among survivors” the main conclusion.

### H. Pseudoreplication

Repeated descendants from a shared artifact, state, model lineage, or
population do not supply independent observations merely because they have
different trace IDs. Record lineage, generation, carrier, and independent
initialization. Bootstrap/randomization must respect the nesting.

## Evidence and visibility boundary

The conversation contains hidden thoughts, reasoning recaps, tool outputs,
system messages, and operational metadata. The conceptual archive uses only
the conservative visible ordinary corpus. Tool records can support operational
facts when directly audited, but never establish conceptual adoption. The
public share also contains assistant-authored external claims; those are
preserved as historical claims, not silently verified facts.

## Current integrity state

The threshold archive’s audit records 504/504 primary rows, 1,341 actual
Phase-1 attempts, 3,699 pre-attempt guard/setup trace rows, 0 over-quota model
rows, no errors, no lifecycle violations, immutable attempt identities, and an
empty package diff from freeze `9c47e0c`. Its raw trace SHA is
`6fed273c28e4ed07cd3fdbd915411955bb67aafc87f440b0ea36550e70d70efb`.

This pre-framework patch changes only documentation, the read-only source
decoder/materialization support, the visible historical corpus, and audit
artifacts. It does not modify a frozen scientific package or prior analysis.
