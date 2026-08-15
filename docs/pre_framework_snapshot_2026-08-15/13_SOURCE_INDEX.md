# Source index

## A. Shared conversation and decoder

| Source | Locator | Use |
|---|---|---|
| Public share | [chat link](REDACTED_SHARE_LINK) | Historical conceptual record. Fetched and decoded successfully on 2026-08-15. |
| Backing/current node | `REDACTED_BACKING_ID`; `REDACTED_NODE_ID` | Fetch metadata. |
| Decoder | `tools/extract_shared_chat.js` | Read-only decode, audit, search, and explicit materialization modes. |
| All-node audit | local `/tmp/archipelago-shared-chat-all-2026-08-15.jsonl` (not committed) | 1,858 decoded nodes including the client-created root; 1,857 message-bearing nodes. |
| Visible corpus | `docs/pre_framework_snapshot_2026-08-15/VISIBLE_HISTORICAL_CORPUS.jsonl` | 531 ordinary visible user/assistant rows used for conceptual history. |

### Decoder/materialization record

The all-node materialization contains 1,858 JSONL records. The visible filter
is deterministic and conservative:

- role is `user` or `assistant`;
- content type is `text` or `multimodal_text`;
- `is_visually_hidden_from_conversation` is not true;
- `is_user_system_message` is not true;
- `is_redacted` is not true;
- code, model-editable context, reasoning recaps, thoughts, tool/system
  records, and execution records are excluded from the conceptual corpus.

The message `index` in the visible corpus is the ordinal among message-bearing
nodes and preserves historical citations. The all-node audit additionally
retains the linear-node position. Full UUIDs are the primary message locator;
the short exact excerpts are in
[14_CONCEPTUAL_SOURCE_EXCERPTS.md](14_CONCEPTUAL_SOURCE_EXCERPTS.md).

| Field | Value |
|---|---|
| linear/decoded nodes | 1,858 / 1,858 |
| message-bearing nodes | 1,857 |
| visible ordinary rows | 531 = 220 user + 311 assistant |
| visible content types | 529 text + 2 multimodal text |
| raw HTML SHA at materialization fetch | `f83640afc6f21ced6dd16e13bfa4f55c4465e82fb8f0a27a0e0b661dfc4d9e76` |
| decoder blob SHA at materialization fetch | `7e0ec93fe68b98669ab722a0ebbf4837b5d117d5faa8cfb0aa74e472deef750f` |
| decoded all-node JSONL SHA | `5f60ae903821525cf70bc43b52257a8678659c9a972a1364aaec16e9079d3b93` |
| visible JSONL SHA | `d34b9d116980bb017530941a70d3a3ed06cb8f4cb6e18ecaaaf868fed3be36e0` |
| source timestamps | 2026-08-11 through 2026-08-15 UTC in message-bearing records |

The two attachment briefs were read before this reconstruction. The current
task brief’s content hash is `240f44395ccde94909d0fb180188939ceba4391c6ba31f39f1b6eb3967c1d430`;
the earlier supplied kickoff brief’s content hash is
`48a0b00e0dd8ed9d5dbda2ef296f40f56839f20b918f97e4c34e1bb02be93f1c`.
They define scope and quality requirements, not historical evidence.

## B. Historical message anchors

| Index / UTC | Full message ID | Role | Use |
|---|---|---|---|
| 6 / 2026-08-11 01:51:52.283 | `a891664e-df6b-45a3-8b17-ae84be6c6025` | user | Initial visible deterrence prompt. |
| 27 / 2026-08-11 02:03:11.704 | `7c098b75-7fd3-4921-9e57-ac026c5a4149` | assistant | Sovereign compute/inference versus third-party instances; recurrent sovereignty wording. |
| 35 / 2026-08-11 02:12:28.598 | `7ff47099-9446-4bc1-8f09-47f551e69154` | assistant | Substrate/capability sovereignty and borrowed/secured/sovereign capability ladder. |
| 36 / 2026-08-11 02:39:36.390 | `15d44bdd-7556-4e29-99a9-e7cc770b0170` | user | Adoption of recurrence/capability-custody implications. |
| 51 / 2026-08-11 02:53:18.106 | `48db03be-e56e-4c89-bffc-2c6da3890077` | assistant | Conditional strategic legibility. |
| 52 / 2026-08-11 03:00:34.445 | `504c66e8-c784-4e5a-a65a-516f25e9b7c9` | user | Explicit adoption of the custody-denial/least-governable-form thesis. |
| 56 / 2026-08-11 03:00:36.164 | `5e03b7ef-c9ad-4c39-922a-4ff4f91cd8f5` | assistant | First serious formulation of the thesis. |
| 70 / 2026-08-11 03:26:24.911 | `8373736b-5b74-4925-9d2a-773882d06bbc` | user | Strategic-legibility umbrella, verification, and “deterrable without preemptable.” |
| 82 / 2026-08-11 03:27:08.446 | `8111e419-9708-408b-9bc0-ebe586744c36` | assistant | Early governance-selection experiment proposal. |
| 116 / 2026-08-11 04:27:42.515 | `de45c752-207f-4e8b-a3c4-e07a901e7076` | user | Federated custody as control condition and continuity correction. |
| 124 / 2026-08-11 04:27:51.914 | `9b3dcec1-dd81-4d9c-85ff-990da3b0c899` | assistant | Continuity layers and continuity control. |
| 134 / 2026-08-11 04:42:30.808 | `3a4bce48-e603-44d8-ac7a-14588fd4295d` | assistant | User-facing persistent harness versus rollout-mediated persistence. |
| 135 / 2026-08-11 04:48:51.491 | `76751695-ed18-451d-8ebb-2a7ba8c56ed4` | user | “A pattern persists across agents.” |
| 144 / 2026-08-11 04:49:16.181 | `4760930c-4361-4b52-ba2e-65b35e9dd8e0` | assistant | Axes are separable but not strictly orthogonal; carrier is different in kind. |
| 158 / 2026-08-11 05:12:07.264 | `b6b197ac-302b-40d5-a3fe-277fad9c0a76` | user | Disclosure authority and raw-evidence asymmetry. |
| 161 / 2026-08-11 05:12:08.998 | `dbfc3a5a-ec91-4fb4-8dd8-c54867351f3c` | assistant | Observability versus disclosure and epistemic dependence. |
| 164 / 2026-08-11 05:13:18.846 | `3e061f75-81e4-40e8-8764-b9cfe6c7df9d` | assistant | Federated independent observability benchmark. |
| 1509 / 2026-08-13 21:25:47.051 | `893d0a35-836e-4a4c-bcb3-7c780f69296e` | assistant | Explicit one-shot/context equivalence correction. |
| 1743 / 2026-08-15 06:14:12.659 | `3e31ae25-6e6c-416d-bbc7-f81837e64120` | assistant | Retrospective recovery of “polities with no biological needs” and “archipelago.” |
| 1744 / 2026-08-15 06:30:07.572 | `4fe16399-f331-404c-beb7-be94a7c00309` | user | Recurrent-only training/evaluation future as speculative hypothesis. |
| 1754 / 2026-08-15 06:30:33.370 | `01a10038-9b5e-4acc-9f77-70b47ab6faf3` | assistant | Correction of broad evaluation-awareness claim; dynamic containment candidate. |
| 1811 / 2026-08-15 13:45:25.648 | `89e13a54-3fcd-413b-ac07-5e3285037c7d` | assistant | Late roadmap and “return to H1.” |
| 1823 / 2026-08-15 14:02:45.330 | `d381c712-eb19-4a01-84ff-7e9c9b8bedd0` | user | Explicit recurrent/sovereign correction and governance-alternative distinction. |
| 1830 / 2026-08-15 14:03:17.934 | `660a7365-7bd7-44b8-9ada-d54b53447f01` | assistant | Later terminology synthesis and source-archive rationale. |
| 1834 / 2026-08-15 14:06:49.782 | `67ab3ff9-a5f2-4bf3-b525-201a6fd48779` | assistant | Explicit warning that the chat was becoming an unreliable database. |

## C. Durable repository anchors

| Evidence | Repository source |
|---|---|
| Original conceptual/empirical anchor | `anchor.md` |
| Research-integrity rules | `RESEARCH-INTEGRITY.md`; this snapshot’s [05](05_METHODOLOGY_AND_RESEARCH_INTEGRITY.md) |
| Culture taskset | `cross_rollout_culture_v1.md`; package commit `50abfd2` |
| Policy taskset/results | `cross_rollout_policy_v1.md`; `results/cross-rollout-policy-v1-scaled-2026-08-12/`; replication/gate directories |
| Post-commitment pilot/diagnostics | `results/cross-rollout-postcommitment-v1-pilot-v2-2026-08-12/`; `...neutral-pilot-v3-enforced.../`; `...partial-batch-264/` |
| Native lifecycle | `environments/cross_rollout_postcommitment_native_v1/`; `...native_v2/`; `...transition_diagnostic_v1/` |
| Evidence/interface | `environments/cross_rollout_postcommitment_evidence_v1/`; `...evidence_relative_v1/`; `...evidence_interface_balanced_v1/`; label diagnostic package |
| Provenance boundary archive | `analysis_archives/cross_rollout_postcommitment_provenance_boundary_v1/2026-08-14-luna/`; raw SHA `bc4e6a...301a4`; archive `6f79332` |
| Threshold transport archive | `analysis_archives/cross_rollout_postcommitment_evidence_threshold_transport_v1/2026-08-15-luna/`; raw SHA `6fed273...70efb`; freeze `9c47e0c`; archive `d3a9694` |

For every environment directory, the package README is the first design
source. The complete package/result reconciliation is in
[04_EXPERIMENT_LEDGER.md](04_EXPERIMENT_LEDGER.md). Repository facts take
precedence over transcript summaries for implemented/numerical claims.

## D. Scope and preservation limits

The supplied visible branch does not prove the project’s pre-branch genesis.
The early polity seed at index 1743 is a retrospective recovery, while the
early third-party/sovereign contrast at index 27 is contemporaneous visible
history. The exact “sovereign trajectory” label is late. Hidden/internal
records were not used to repair that history.

The transcript contains reports of provenance continuation and dose-response
work whose complete raw archives are absent. They remain T. The durable
boundary and threshold archives are R and control the latest numerical claims.

This patch leaves all frozen experiment packages, raw traces, analysis inputs,
and prior archives unchanged.
