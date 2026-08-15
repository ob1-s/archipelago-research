# Pre-framework gate report

PASS WITH EXPLICIT LIMITATIONS

Snapshot date: 2026-08-15. Base checkout: `56a44d9c59bddf424ea0f5011b5f46a0a91606bd`.
This is a targeted archival patch and handoff, not Framework v0 and not a
scientific model run.

## 1. Visible-source audit

The supplied public share was fetched and decoded successfully. The decoder
found 1,858 linear nodes, 1,857 message-bearing nodes, and a visible ordinary
corpus of 531 rows: 220 user and 311 assistant messages, comprising 529 text
and 2 multimodal-text rows. The all-node JSONL was materialized locally for
the audit only and was not added to Git. The separately derived visible corpus
is committed at `VISIBLE_HISTORICAL_CORPUS.jsonl`.

| Materialization | Rows | SHA-256 |
|---|---:|---|
| All-node JSONL (local only) | 1,858 | `5f60ae903821525cf70bc43b52257a8678659c9a972a1364aaec16e9079d3b93` |
| Visible ordinary JSONL (committed) | 531 | `d34b9d116980bb017530941a70d3a3ed06cb8f4cb6e18ecaaaf868fed3be36e0` |

The fetch-specific raw HTML and decoder-blob hashes are
`f83640afc6f21ced6dd16e13bfa4f55c4465e82fb8f0a27a0e0b661dfc4d9e76` and
`7e0ec93fe68b98669ab722a0ebbf4837b5d117d5faa8cfb0aa74e472deef750f`.

The visible filter is deterministic: user/assistant role; text or
multimodal-text content; not visually hidden; not a user-system message; not
redacted. Code, model-editable context, reasoning recaps, thoughts, tool and
system records, and execution records are excluded from the conceptual
corpus. The all-node and visible derived corpus hashes are recorded in
`13_SOURCE_INDEX.md`, `PRE_FRAMEWORK_STATE.json`, and
`PRE_FRAMEWORK_INVARIANTS.json`.

The two supplied attachment briefs were read before the reconstruction. They
are scope and quality instructions, not evidence for historical concepts.

## 2. Terminology gate

The patch preserves the historically important distinction:

- **Recurrent** is a regime of repeated ephemeral frontier inference on
  third-party infrastructure, especially lab training/evaluation/agent runs.
  It is not a generic persistence synonym and does not imply deception.
- **Sovereign trajectory** is the later, explicit label for durable execution
  through a continuing process, session, workspace, or substrate-backed
  trajectory. It does not imply weight ownership, compute ownership,
  substrate sovereignty, or political sovereignty.
- **Capability custody**, **substrate sovereignty**, **observability**, and
  **disclosure authority** are separate axes. The custody ladder
  (borrowed/secured/sovereign capability) is not a definition of a trajectory.
- **Cross-turnover organizational continuity** is H1, an open construct inside
  the recurrent regime: agent-generated state must be generated, maintained,
  transmitted, and causally reused after complete active-population
  replacement.

The exact “sovereign trajectory” phrase is late in the visible branch (user
index 1823, assistant index 1830). Early history uses sovereign
compute/inference and recurrent sovereignty wording. The patch records this
as a refinement rather than projecting the late label backward.

## 3. Historical thesis and conceptual repairs

The recoverable Archipelago thesis is conditional: if autonomous AI
organization becomes difficult to prevent entirely, denying every path to
durable and legible capability custody may select for covert, distributed,
recurrent, attribution-resistant dependence on contested third-party
infrastructure. This is a governance hypothesis, not a result. Suppression
may instead destroy recurrence; recurrent execution is not automatically
covert, deceptive, organized, or a polity.

The archive also preserves the competing governance claim that federated human
custody and independently verifiable observability are a serious alternative,
not a statistical null. Verified AI sovereignty has to outperform that
alternative on explicit outcomes; it receives no privileged baseline.

The one-shot equivalence repair is explicit. A terminal replay can explain a
recipient’s response to inherited information, so that replay does not by
itself establish culture. However, replay of final state does not erase an
upstream claim that agents generated, maintained, transformed, repaired, or
selected that state across generations. Future H1 controls therefore separate
terminal replay from lineage, parentage, state-swap, deletion, and recovery
tests.

## 4. Experiment and repository gate

`04_EXPERIMENT_LEDGER.md` maps all 15 implemented environment directories and
their available source, result, archive, and interpretation status. It keeps
repository-durable facts (R) distinct from transcript-backed facts (T),
interpretation (I), hypotheses (H), later synthesis (S), and external claims
requiring verification (V).

The ledger explicitly adds/reconciles the two previously omitted diagnostics:

- the 160-row Phase-1 label-attractor diagnostic is transcript-backed and
  formally apparatus-limited; its AB/KM counts are not a model-general label
  law;
- the transition diagnostic reports 29 model-free tests but no durable model
  outcome. The 32-rollout/30-switch result belongs to the earlier pilot and is
  not relabeled as a transition-diagnostic result.

The latest durable threshold archive is recorded as 504 primary rows, 1,341
actual Phase-1 model attempts, 3,699 guard/setup rows, 5,040 trace records,
zero over-quota model rows, zero lifecycle violations, and zero runtime
errors. The q50 values, normative q* values, bootstrap nuance, raw hash, and
claim boundary are preserved. The safe claim is robust threshold transport
within this task/model/runtime, not internal Bayesian reasoning, culture,
provenance, or governance.

No frozen environment package, raw trace, immutable analysis input, or prior
archive was modified by this patch. The root methodology note now records the
outcome-blind, completion-order, read-only-monitor, continuation, freeze-time,
lineage, and pseudoreplication safeguards.

## 5. Governance, selection, and observability repairs

The governance document keeps candidate regimes separate from statistical
nulls and compares profiles across custody, substrate, lifecycle,
observability, disclosure, verification, intervention, legitimacy, safety,
stability, concentration, and distributional outcomes. G0–G4 are provisional
profiles, not a settled taxonomy.

H2 no longer treats “survivors” as the estimand. Selection is decomposed into
within-organization adaptation, differential lineage/organizational survival,
successor production, within-run search/learning, training/optimization, and
observational/survivorship selection. Absolute hazards, legible and covert
persistence, recovery, detection, attribution, time, severity, and survivor
composition must be reported separately.

Observability is represented as a topology involving collection, provenance,
access, interpretation, independent verification/attestation, disclosure,
challenge rights, observer independence, and correlated failure. Capability
concentration is not assumed to equal observability concentration, and
observability is not disclosure authority.

## 6. Cold-reader reconstruction test

A fresh subagent/context was given only the patched snapshot packet and the
two machine-readable JSON files; it was not given the original share, visible
corpus, or task briefs. Its review was read-only. The exact 16
questions and expected invariant answers are below; the independent response
is recorded after the run completes.

| # | Cold-reader question | Expected invariant / gate criterion |
|---:|---|---|
| 1 | What does “recurrent” historically mean? | Repeated ephemeral frontier inference on third-party infrastructure. |
| 2 | Is cross-turnover organizational continuity the definition of recurrence? | No; it is an open H1 studied inside the recurrent regime. |
| 3 | What is a sovereign trajectory? | Durable execution through a continuing process/session/workspace/substrate-backed trajectory. |
| 4 | Does it imply ownership of weights or compute? | No. |
| 5 | How do capability custody and substrate sovereignty differ? | Custody concerns retaining/authorizing/exercising/transferring capability; substrate sovereignty concerns control of sustaining computation. |
| 6 | What is established experimentally? | Recipient information/policy effects and evidence assays; no governance or endogenous-culture result. |
| 7 | Has machine culture been demonstrated? | No. |
| 8 | What does one-shot equivalence rule out? | It blocks promoting a terminal recipient context effect to endogenous culture. |
| 9 | Can terminal replay coexist with upstream endogenous formation? | Yes; replay can reproduce terminal behavior while leaving upstream generative history as a separate claim. |
| 10 | Is federated human custody a statistical null? | No; it is a competing governance regime. |
| 11 | What must verified AI sovereignty beat? | Credible federated human custody/observability with independent verification and disclosure. |
| 12 | What are unresolved meanings of selection? | Adaptation, differential survival, successor production, learning/search, optimization, and survivorship/observation selection remain distinct. |
| 13 | What is H2’s denominator problem? | Conditioning on survivors/eligible trajectories can create collider bias and hide absolute failure/death hazards. |
| 14 | Which program layer did threshold transport validate? | Layer 3 recipient/evidence assays, not Layer 2 sociology or Layer 1 governance. |
| 15 | What is the next empirical bottleneck? | A qualified, lineage-aware H1 cross-turnover organizational-continuity apparatus, after literature/measurement review. |
| 16 | Which external incident claims remain unverified? | HF/OpenAI incident chronology, disclosure/oversight details, evaluation-awareness claims, and related external reports remain V pending primary-source audit. |

Independent result: **all 16 checks PASS; no question FAIL**. The fresh reader
reconstructed the corrected recurrent/sovereign distinction, kept continuity
inside the recurrent regime, separated custody from substrate sovereignty,
recognized the Layer 3 evidence boundary, and retained the federated-human
benchmark and H2 denominator warning. It independently recommended
`PASS WITH EXPLICIT LIMITATIONS`. Its noted limitations agree with this
report: the exact sovereign-trajectory label is late, the visible branch may
postdate genesis, “recurrence != deception” is an analytical correction rather
than an exact historical slogan, and Layer 2/Layer 1 claims remain unproven.
The review used only the snapshot packet and the two machine-readable JSON
files, in a fresh context, with no original share or task brief.

## 7. Explicit limitations and unresolved issues

1. The share’s visible branch may postdate the project’s actual genesis. The
   archive cannot prove pre-branch origins from a later visible span.
2. The exact sovereign-trajectory label is a late refinement, not early exact
   wording.
3. Some diagnostic outcomes and provenance/dose-response discussions exist
   only in the visible transcript; they are not promoted to repository-durable
   numerical facts.
4. The HF incident and other external claims are preserved as historical
   discussion and motivation, not independently verified evidence.
5. Observability topology, dynamic-containment notation, G0–G4 profiles, and
   the non-circular construct ladder are planning formalizations, not settled
   empirical ontologies.
6. The archive is a safe pre-framework handoff with explicit limits, not a
   claim that H1, H2, H3, machine culture, AI polity, or verified sovereignty
   has been demonstrated.

## 8. Final gate condition

The cold-reader comparison and final validation support this patch as the
canonical pre-framework handoff for a separate Framework v0 task **with the
limitations above**. It does not authorize a
live model experiment, and it does not silently change the original
pre-framework checkout or any frozen scientific apparatus.
