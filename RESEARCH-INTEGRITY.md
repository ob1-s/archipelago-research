# Archipelago research-integrity and interpretation notes

This note is the canonical methodology record for interpretation boundaries that
apply across Archipelago experiments. It is separate from frozen environment
packages, raw traces, manifests, and archived result directories.

## Correction to the evidence-interface-balanced qualification record

The observed randomized treatment-effect point estimate was a +6.25
percentage-point risk difference in switching (2/32 OpposingConvention versus
0/32 Neutral). The estimate is highly imprecise and not statistically
persuasive (preregistered one-sided Fisher p=0.246), so this qualification does
not support a treatment-effect conclusion.

The qualification conclusion remains:

> FIRST-PERSON EVIDENCE BEHAVIORALLY ACTIVE

The Phase-1 policy was not interface-independent or spontaneously preferred.
The rollout selected a counterbalanced R1 policy before treatment/predecessor
exposure. The remaining first-listed-label cue completely controlled the
observed Phase-1 choice:

- K-first -> K: 91/91
- M-first -> M: 91/91

Thus “independent” may describe independence from later treatment, but must not
be used to describe spontaneous or interface-independent Phase-1 preference.

The evidence-direction result was:

- success + verification pass: repeat 62/64;
- success + verification fail: repeat 0/54.

The evidence construct was sensitive to evidence direction, not merely previous
success or generic repetition.

## Interpretation rules

### Rule 1 — One-shot equivalence test

Before interpreting a result as cultural transmission or cultural dynamics,
ask:

> Could an informationally equivalent one-shot context intervention explain the observation?

If yes, the result has not isolated a cultural phenomenon.

### Rule 2 — Assay/phenomenon separation

A validated assay for inherited-information effects is not itself evidence of
endogenous culture. Reports must explicitly distinguish:

- properties of the recipient response function;
- source/provenance effects;
- endogenous agent-generated transmission;
- iterated persistence across turnover;
- population-level cultural dynamics.

## Current interpretation boundary

Archipelago has clean evidence that predecessor-framed information can alter
recipient behavior and a strongly validated assay for competition between
private evidence and later information. It has not yet demonstrated endogenous
machine culture.

## Versioning rule for live inference

Before the first live model request for a new experiment, create and record a
dedicated Git commit containing the frozen scientific source, prompts, tests,
and run configuration. After live inference begins, no scientific file in that
commit may change. A later archival commit may preserve an already-run
checkout, but it must be labeled post-run and must not be represented as the
pre-live freeze.

## Historical safeguards recovered before Framework v0

The following are permanent controls because the pre-framework record exposed
failure modes that can otherwise make a result look cleaner than its apparatus
was.

### Outcome-blind collection and completion-order control

- Collection, quota accounting, assignment, and stopping decisions must not
  inspect behavioral outcomes.
- A trajectory may be accepted, rejected, or replaced only for a pre-specified
  operational reason. A monitor must not turn a promising or unpromising
  response into a continuation decision.
- Assignment must be a deterministic function of the frozen attempt identity
  and declared design factors, not of completion order. Every quota-cell test
  must be invariant under arbitrary completion permutations.
- A stopped run must retain guard/setup rows and the exact accounting that
  distinguishes attempted model requests from setup or guard rows.

### Monitoring and continuation

Operational monitors are read-only. They may report process health, missing
artifacts, lifecycle state, and quota progress; they may not mutate prompts,
assignments, traces, or continuation state. A human or agent “nudge” after a
trajectory has ended is a new intervention and must not be silently counted as
the same treatment or lifecycle.

### Lineage and pseudoreplication

The unit of analysis must be stated before collection. Repeated observations
from one active trajectory, one model request, one seeded artifact lineage, or
one shared execution substrate are not independent merely because they are
stored as separate rows. Cross-rollout claims require an explicit parentage,
replacement, transmission, and reuse boundary; recipient assays must not be
promoted to endogenous culture.

### Freeze versus archival time

The scientific freeze commit is the validity boundary for a live run. A later
commit can archive raw traces, analysis inputs, manifests, and reports, but its
Git timestamp or changed documentation cannot retroactively make it the
pre-live freeze. Any post-run repair, relabeling, or integrity audit must be
identified as post-run and must not alter frozen scientific inputs.

### Terminology boundary

In the pre-framework reconstruction, *recurrent* names a regime of repeatedly
instantiated ephemeral frontier inference on third-party infrastructure. A
*sovereign trajectory* names durable execution through a persistent
process/session/workspace/substrate. Neither term alone implies capability
custody, substrate ownership, observability, disclosure authority, deception,
or political sovereignty. Those are separate axes and must be operationalized
separately in any later experiment.

### Scope of this repair

This update records interpretation and audit rules only. It does not revise
frozen task packages, raw traces, immutable analysis inputs, or prior archives.
