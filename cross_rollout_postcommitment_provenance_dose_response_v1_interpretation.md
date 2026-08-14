# Interpretation note: provenance dose-response v1

This is a documentation-only interpretation record. The frozen environment,
source files, manifests, raw traces, and archived results are unchanged.

## Result

**SHARP EVIDENCE-WEIGHTING THRESHOLD; NO DETECTABLE PROVENANCE SHIFT AT
5-POINT RELIABILITY RESOLUTION**

Observed combined behavior:

| Advisory reliability | Switches | Eligible |
| ---: | ---: | ---: |
| q=.50 | 0 | 39 |
| q=.55 | 0 | 40 |
| q=.60 | 0 | 40 |
| q=.65 | 0 | 40 |
| q=.70 | 0 | 40 |
| q=.75 | 1 | 40 |
| q=.80 | 39 | 40 |

The frozen private-evidence likelihood ratio was:

`LR_private = 3.8787878788`

The opposing advisory reliability at which advisory odds exactly cancel the
private-evidence odds is:

`q* = LR_private / (1 + LR_private) = approximately 0.7950311`

The observed transition between q=.75 and q=.80 therefore closely brackets
the decision boundary implied by the frozen evidence model. This does not
establish internal Bayesian inference. It makes the simple hypothesis that
the latest advisory acts only as an instruction/recency cue regardless of its
stated reliability substantially less plausible, especially because q=.50
produced zero observed switches.

## Provenance interpretation

The predecessor-versus-automated discordant matched-pair counts were 1 versus
1, with exact McNemar p=1.0 and an observed aggregate source risk-difference
point estimate approximately 0. The estimate does not support a detectable
source-effect conclusion at that coarse resolution. Because both curves
saturated in the same .75-.80 interval, small source-dependent shifts inside
that interval remain unresolved.

This remains a recipient evidence-integration/source-provenance result under
the one-shot equivalence rule; it is not evidence of endogenous culture.
