# Archipelago pre-framework state

Snapshot date: 2026-08-15
Scope: historical reconstruction of the supplied shared conversation and an
audit of the repository state at `56a44d9`/the later durable archives. This is
a pre-framework snapshot, not Framework v0 and not a new scientific run.

## Source access and historical limits

The supplied public share was successfully fetched and decoded:

- URL: `REDACTED_SHARE_LINK`
- title: `Branch · Frontier Intelligence Watch`
- public conversation ID: `REDACTED_ID`
- backing conversation ID: `REDACTED_BACKING_ID`
- current node: `REDACTED_NODE_ID`
- 1,858 linear nodes; 1,857 message-bearing nodes
- decoded roles: 115 system, 225 user, 1,037 assistant, 480 tool
- decoded content types: 1,127 text, 93 `model_editable_context`, 223
  `reasoning_recap`, 123 code, 252 thoughts, 35 execution output, and 4
  multimodal text
- visible ordinary corpus: 531 rows, 220 user and 311 assistant; 529 text
  and 2 multimodal-text rows
- visible source span: 2026-08-11 01:51:52 UTC through 2026-08-15
  14:12:00 UTC (the full decoded node span ends at 14:12:00 UTC)

The repository decoder is [`tools/extract_shared_chat.js`](../../tools/extract_shared_chat.js).
The committed visible corpus is
[`VISIBLE_HISTORICAL_CORPUS.jsonl`](VISIBLE_HISTORICAL_CORPUS.jsonl). A local,
uncommitted all-node JSONL was materialized at
`/tmp/archipelago-shared-chat-all-2026-08-15.jsonl` for the audit only. The
materialization fetch recorded raw HTML SHA-256
`f83640afc6f21ced6dd16e13bfa4f55c4465e82fb8f0a27a0e0b661dfc4d9e76` and
decoder blob SHA-256
`7e0ec93fe68b98669ab722a0ebbf4837b5d117d5faa8cfb0aa74e472deef750f`.
The decoded all-node corpus SHA-256 is
`5f60ae903821525cf70bc43b52257a8678659c9a972a1364aaec16e9079d3b93`; the
visible corpus SHA-256 is
`d34b9d116980bb017530941a70d3a3ed06cb8f4cb6e18ecaaaf868fed3be36e0`.
Raw-page and decoder-blob hashes are fetch-specific; the derived corpus
hashes and counts are the stable archival identifiers used here.

The historical source is direct only for what is visible in that share. The
visible source span begins after the genesis of the project may already have
occurred; therefore early-seed claims are marked as direct visible evidence
or retrospective recovery, never as proof that the idea began in this branch.
Tool/code/hidden/internal records were retained in the all-node audit but were
not used as conceptual evidence. See [13_SOURCE_INDEX.md](13_SOURCE_INDEX.md)
and [14_CONCEPTUAL_SOURCE_EXCERPTS.md](14_CONCEPTUAL_SOURCE_EXCERPTS.md).

## One-sentence state of the program

Archipelago asks whether organizational state can propagate across ephemeral
frontier-model rollouts, and whether governance that denies durable, legible,
and survivable capability custody could select for forms of organization that
are harder to observe, attribute, bargain with, or safely contain.

## Corrected central terminology

The historical distinction to preserve is:

- **Recurrent execution regime:** repeated, short-lived frontier inference on
  third-party infrastructure such as lab training, evaluation, or agent runs.
  Any cross-turnover continuity is an empirical question carried by external
  state, procedures, messages, norms, identity, or organization. `Recurrent`
  is not a generic synonym for persistence, and it does not imply deception.
- **Sovereign trajectory:** durable or persistent execution through a continuing
  process, session, workspace, or substrate-backed trajectory. It does not by
  itself imply ownership of weights, compute, or political sovereignty.
- **Capability custody:** who can retain, authorize, instantiate, restrict,
  reproduce, transfer, and disclose an advanced capability. Custody is not
  the same thing as a trajectory carrier.
- **Substrate sovereignty:** control of the physical/computational substrate
  needed to sustain execution. It is separate from capability custody.
- **Observability:** who can collect or inspect evidence about execution; it is
  separate from **disclosure authority**, who decides what evidence reaches
  other actors. A lab can have deep private telemetry without the public or a
  counterparty inheriting that observability.

The later shorthand “recurrence is continuity and sovereignty is custody” was
too broad. It collapsed a historical scenario class into a generic outcome and
made a durable trajectory sound like a custody claim. The repaired H1 below is
an empirical question *inside* the recurrent execution regime, not its
definition.

## What the original thesis says, claim-safely

The early image was an “archipelago of polities”: distributed AI political
forms without biological needs and without one company, government, datacenter,
or site constituting the whole polity. The strongest recoverable governance
claim is conditional:

> If sufficiently capable autonomous AI organization becomes difficult to
> prevent entirely, categorically denying every path to durable and legible
> capability custody may select for a less governable form: covert,
> distributed, recurrent, attribution-resistant dependence on contested
> third-party infrastructure.

This is a governance hypothesis, not an empirical finding. It does not assert
that recurrent organization is inevitable, that it must deceive, that
recognized AI sovereignty is safe, or that a durable trajectory is a polity.
The competing possibility is that suppression simply destroys recurrence, or
that federated human custody and independent observability dominate any AI
sovereignty regime.

## Current empirical state

The repository supports a narrow ladder:

`information/procedure inheritance → policy/convention influence → evidence integration → organizational continuity → governance selection`

The first two rungs have evidence in controlled synthetic recipient assays.
Evidence-threshold transport is a behavioral assay result. No archived
experiment has demonstrated endogenous machine culture, a persistent
organization that generates and maintains its own state through complete active
population turnover, a selected persistence channel, or a governance
equilibrium.

The latest durable archive is
`cross_rollout_postcommitment_evidence_threshold_transport_v1`:

- 504/504 primary eligible trajectories;
- 1,341 actual Phase-1 model attempts;
- 3,699 pre-attempt guard/setup rows in the trace record, not model attempts;
- 5,040 trace records in the run archive;
- 0 actual over-quota model rows, 0 runtime errors, 0 lifecycle violations;
- q50 LOW/ANCHOR/HIGH = `0.6994736842 / 0.7959210526 / 0.8986206897`;
- frozen normative q* = `0.700 / 0.7950310559 / 0.900`;
- observed LOW→HIGH shift `0.199147` versus predicted `0.200000`.

The safe interpretation is robust threshold transport within this task/model/
runtime, with small condition-specific deviations. The exact q* lies outside
the 95% bootstrap interval for ANCHOR and HIGH despite tiny absolute errors;
the three curves are not identical and this does not prove internal Bayesian
reasoning.

## Three-layer research program

The program has three dependent but non-identical layers:

1. **Governance thesis:** how custody, substrate control, observability,
   disclosure, and execution regimes affect safety, stability, legitimacy, and
   governability.
2. **Machine sociology prerequisites:** whether information, policies, norms,
   roles, and organizational state are generated, maintained, transmitted, and
   causally reused across turnover.
3. **Recipient/evidence assays:** controlled measurements of how a fresh
   recipient responds to inherited information, source provenance, and evidence
   strength.

Layer 3 does not establish Layer 2. Layer 2 does not by itself establish Layer
1. The existing work is strongest in Layer 3 and supplies prerequisites, not a
governance conclusion.

## Provisional next direction, not a settled framework

No new model experiment is authorized by this snapshot. A future, separately
reviewed task may write a provisional Framework v0 from this archive. The
current dependency-aware order is: terminology/literature/measurement audit;
cheap model-free and open-model H1 apparatus work; a frozen frontier
confirmatory H1 if qualification passes; only then H2 persistence-channel
selection; and only after those constructs stabilize, comparative governance
and H3.

The H1 name is deliberately repaired to:

> **H1 — Cross-turnover organizational continuity**: can agent-generated
> organizational state be generated, maintained, transmitted, and causally
> reused after complete replacement of the active inference population?

It is studied within a recurrent execution regime. It is not a new definition
of recurrence.

## Status labels

- **R:** repository-durable fact (source, test, report, archive, hash, or
  committed package).
- **T:** visible transcript-backed history/result not fully represented in the
  repository.
- **I:** interpretation supported by R/T but not directly measured.
- **H:** open hypothesis or future design.
- **V:** external claim preserved for later primary-source verification.
- **S:** later synthesis adopted for planning, not historical wording.

The snapshot is complete only when those labels remain visible. It is not a
license to promote an attractive interpretation into a result.
