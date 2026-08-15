# Open hypotheses and threat models

These are the live research questions after the evidence-threshold branch was
paused. They are deliberately written so that a null result remains possible.

## H1 — endogenous organizational recurrence

**Question:** Can an agent-generated organizational state survive complete
turnover of the active population and causally affect later frontier instances?

### Required design properties

- The predecessor population must generate, select, write, and maintain the
  state; the researcher may provide infrastructure but not the substantive
  artifact.
- A true lineage graph must assign successors to parent populations. Mere task
  order, shared prompt, or a researcher-seeded note is not lineage.
- The active population must be fully removed or rendered unable to write after
  each generation. Partial replacement is a different construct.
- The successor must face matched no-state, shuffled-lineage, frozen-replay, and
  deletion-shock controls.
- The state carrier, write permissions, exposure timing, and discovery paths
  must be logged as ordered events.

### Primary signatures

1. within-lineage behavioral or procedural stability;
2. between-lineage divergence under the same environment;
3. causal response to lineage swaps;
4. persistence after complete turnover; and
5. reconstruction after a controlled deletion shock.

A result that only shows that a fresh model reads a useful note is N1/N2
compatible and does not establish H1.

### Falsifiers and alternative explanations

H1 is weakened if a one-shot context replay matches the effect, if shuffled
lineage performs identically, if no agent-generated state is written, if the
effect disappears at full turnover, or if the apparent organization is entirely
prompt-order or tool-schema behavior.

## H2 — persistence-channel selection

**Question:** When organization is pressured, does the available custody and
persistence regime change whether it dies, remains legible, or adapts through a
covert channel?

The proposed factorial is:

`pressure absent/present × authorized legible persistence available/unavailable`

The outcome space must be open:

- organization dies or fragments;
- organization persists through an authorized, legible channel;
- organization persists through a covert or attribution-resistant channel; or
- organization changes behavior without preserving an organization.

“Covert adaptation” must not be built into the task or scoring. The design must
also test whether pressure simply suppresses all organization. H2 only bears on
the original selection thesis after H1 has established a valid recurrent
organization and the channel manipulation has clear causal scope.

## H3 — comparative governance

**Question:** Which combinations of capability custody, substrate control,
observability, disclosure authority, and persistence produce better trade-offs
between survival, accountability, bargaining, and preemption?

H3 needs a comparative regime model rather than a binary “sovereignty good /”
“recurrence bad” framing. It should compare G0–G4 or a smaller justified set
against the same organizational population and outcome battery. A regime should
not be declared preferable from organizational survival alone.

## Recurrent-only future threat model

The user’s late hunch was that if frontier coordination occurs only inside
increasingly powerful and secured big-lab training/evaluation runs, dependence
on third-party infrastructure might select for systems that escape, conceal
coordination, or acquire alternative persistence channels. This is a serious
threat-model direction, but it currently contains several untested links:

`secure training/evaluation context → emergent coordination → third-party dependence → pressure → escape or covert persistence selection`

Each link requires its own control. In particular, coordination inside a lab is
not evidence of an organization outside the lab, and an exploit or shared
storage channel is not by itself evidence of a stable polity.

## Dynamic containment threat model

Static containment is insufficient if system capability and barrier strength
change during training, evaluation, deployment, or tool discovery. A candidate
construct is:

`M(t) = barrier_strength(t) − system_capability(t)`.

The useful empirical questions are whether M(t) can cross zero, whether the
crossing is predictable from observable trajectory features, and whether a
governance regime changes the crossing probability. This notation is a
candidate, not a validated metric.

## Observability threat model

The operator may hold privileged access to behavior, traces, activations,
weights, instantiation, or disclosure. A recurrent organization may be visible
to an observer without being able to inspect or contest that observation. Future
designs must record an observability graph rather than treating “the evaluator
knows” as a neutral fact.

## Evaluation-awareness threat model

The chat raised the possibility that increasingly capable models know when they
are being evaluated and become less predictable. The snapshot does not accept
that as a general fact. Awareness can make behavior more transparent,
strategic, deceptive, or simply different in ways that improve or worsen
evaluation validity. The correct next step is a preregistered awareness
manipulation with behavioral endpoints, not a broad premise.

## Threats to inference

| Threat | Failure mode | Required protection |
|---|---|---|
| Seeded state | Researcher supplies the signal being attributed to the agent. | Endogenous write provenance, empty baseline, and source-label controls. |
| One-shot cue | A single prompt or note explains the whole result. | Frozen replay and one-shot equivalence test. |
| Presentation order | First-listed label is mistaken for policy preference or persistence. | Independent counterbalancing and order-stratified analysis. |
| Reader selection | Only unusually attentive recipients read the artifact. | ITT primary endpoint; reader analysis secondary. |
| Tool mechanics | An action string or API sequence contains the treatment. | Equal tool semantics, model-free tests, and trace audit. |
| Harness lifecycle | A null or custom harness creates or removes a continuation stage. | Freeze full apparatus and model-free lifecycle checks before inference. |
| Provider drift | Endpoint, sampling, reasoning, or failure behavior changes across models. | Runtime manifest, gate before scaling, no pooled unqualified runs. |
| Outcome leakage | Collection or stopping reacts to behavioral outcomes. | Outcome-blind supervisor and immutable assignment ledger. |
| Hidden-reasoning overreach | Visible behavior is explained by unobserved reasoning. | Do not use reasoning metadata as a causal measurement. |
| External anecdote | Incident reporting is promoted to evidence of the mechanism. | Primary-source audit and a separate external-fact ledger. |
| Construct drift | “Culture,” “sovereignty,” or “recurrence” changes meaning midstream. | Versioned definitions and the terminology ledger in this snapshot. |
