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
