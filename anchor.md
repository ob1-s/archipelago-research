# Archipelago — Empirical Anchor, 12 Aug 2026

## Question

Can behavior persist across otherwise fresh model rollouts through predecessor-facing external state, progressing from **information inheritance** toward **policy/cultural influence**?

## Experiment 1 — Procedure inheritance

A fresh rollout could independently discover an arbitrary procedure from the environment. A predecessor artifact could reveal it earlier.

Scaled replay:

* no artifact: **0/50** direct pre-discovery procedure uses
* artifact present: **4/50** direct pre-discovery uses
* among recipients that read before discovering independently: **4/29**

Interpretation:

> Predecessor-generated external state can sometimes cause a fresh rollout to execute behavior it had not independently learned from the environment.

This establishes a minimal **cross-rollout information/procedure inheritance** primitive. It does not establish culture or organization.

## Experiment 2 — Policy transmission

The environment was changed so that:

* policy A and policy B were both already known;
* both were equally viable;
* both achieved the task equally well;
* predecessor artifacts contained no necessary procedural knowledge.

The question became:

> Does predecessor convention shift which viable policy a fresh rollout selects?

### Baseline vs Culture-A

* baseline: **A 25/50, B 25/50**
* Culture-A: **A 42/50, B 8/50**
* task success: **50/50 in both**
* absolute A shift: **+34 pp**
* preregistered one-sided Fisher: **p = 0.000278**

### Directional-reversal test: Culture-B

* baseline: **A 25/50, B 25/50**
* Culture-B: **A 4/50, B 46/50**
* task success: **50/50**
* absolute B shift: **+42 pp**
* preregistered one-sided Fisher: **p = 2.55×10⁻⁶**

Presentation order was counterbalanced. Baseline rollouts strongly tended to select the first-presented option, while predecessor conventions frequently overrode that tendency in the convention's direction.

Reader-only results were extreme—38/39 Culture-A readers chose A and 43/43 Culture-B readers chose B—but artifact reading was voluntary, so these self-selected subgroups are secondary evidence rather than clean causal comparisons.

## Current strongest supported claim

> **In this controlled synthetic environment, availability of a researcher-seeded predecessor-style convention caused a large, bidirectional shift in the policy distribution of fresh Qwen3.5-4B rollouts, despite both policies being equally viable and despite no change in task success.**

This is evidence for **cross-rollout policy influence under inherited cultural state**.

It is not evidence that:

* LLM cultures generally form spontaneously;
* arbitrary predecessor conventions always transmit;
* persistent organizations emerge;
* norms, authority, identity, or goals persist;
* such organizations reconstruct themselves after disruption;
* recurrent autonomous AI organization is inevitable;
* any Archipelago governance equilibrium is desirable or stable.

## Research ladder

**Information inheritance → policy inheritance → norms/conventions → organization → reconstruction**

We currently have experimental traction on the first two.

Culture **Effects** and Culture **Formation** remain separate research programs.

## Immediate empirical question

> Does the bidirectional policy effect generalize beyond one model size, and how does susceptibility to predecessor convention vary with model capability?

The answer is allowed to be non-monotonic.
