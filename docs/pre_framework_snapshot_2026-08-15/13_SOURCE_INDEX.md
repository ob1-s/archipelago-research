# Source index

## A. Historical source

| Source | Locator | Use and provenance |
|---|---|---|
| Shared conversation | [public share](REDACTED_SHARE_LINK) | Historical reconstruction and transcript-backed result extraction. Retrieved 2026-08-15; public page decoded successfully. |
| Decoder | `tools/extract_shared_chat.js` | Read-only extraction of the serialized share payload. Reproduce with `node tools/extract_shared_chat.js <URL> summary`, `search <query>`, or `jsonl`. |
| Conversation summary | title `Branch · Frontier Intelligence Watch`; 1,858 linear entries; 1,857 messages; 115 system / 225 user / 1,037 assistant / 480 tool | Counts and time span are source metadata, not a claim about experiment validity. |
| Kickoff brief | `/home/ob1/.codex/attachments/19ec3db3-44d2-4786-9ac2-0cc872d412df/pasted-text-1.txt` | User-required scope and deliverable specification; read before reconstruction. |

## B. Key conversation locators

Message indices are positions in decoder JSONL output. UUIDs make the selected
records independently addressable within the decoded payload.

| Index / UTC time | UUID | Historical use |
|---|---|---|
| 56 / 2026-08-11 03:00:36 | `5e03b7ef-c9ad-4c39-922a-4ff4f91cd8f5` | First serious formulation of the custody-denial / least-governable-form thesis. |
| 1567 / 2026-08-14 06:41:57 | `fd2c92c2-d7ef-47b6-a517-ed773b75777d` | Transcript-backed provenance continuation audit and 160-trajectory source result. |
| 1586 / 2026-08-14 11:26:29 | `c0ce7d45-1bf9-4ec2-8a68-f62e43baffd2` | Transcript-backed provenance dose-response result and threshold interpretation. |
| 1743 / 2026-08-15 06:14:12 | `3e31ae25-6e6c-416d-bbc7-f81837e64120` | Recovery of the original “polities with no biological needs” / “archipelago of polities” seed and custody distinction. |
| 1744 / 2026-08-15 06:30:07 | `4fe16399-f331-404c-beb7-be94a7c00309` | User’s recurrent-only future, secured big-lab, and escape-selection hunch. |
| 1754 / 2026-08-15 06:30:33 | `01a10038-9b5e-4acc-9f77-70b47ab6faf3` | Correction of broad evaluation-awareness claim; dynamic containment margin and framework gaps. |
| 1811 / 2026-08-15 13:45:25 | `89e13a54-3fcd-413b-ac07-5e3285037c7d` | Latest roadmap: pause Luna battery, build Framework v0, return to H1. |
| 1830 / 2026-08-15 14:03:17 | `660a7365-7bd7-44b8-9ada-d54b53447f01` | Terminology correction: recurrent is narrow third-party ephemeral inference; sovereign trajectory is durable execution. |

The UUIDs above are full message identifiers from the decoded payload.

For earlier conceptual clusters, use decoder search terms and ranges:

- indices 6–27: deterrence, sovereign compute, third-party instances;
- indices 35–56: custody, substrate/capability sovereignty, core thesis;
- indices 65–82: strategic legibility and first empirical hypotheses;
- indices 91–164: continuity, instantiation, observability, and disclosure;
- indices 213–219: compressed thread summary and ladder.

## C. Durable repository anchors

| Evidence | Durable source |
|---|---|
| Original conceptual/empirical anchor | `anchor.md`, especially the procedure/policy ladder and explicit limits. |
| Methodology and interpretation boundaries | `RESEARCH-INTEGRITY.md`. |
| Culture taskset and trace contract | `cross_rollout_culture_v1.md`, frozen environment commit `50abfd2`. |
| Policy taskset and trace contract | `cross_rollout_policy_v1.md`; corrected commits `1af0970`, `50ac443`, `5e4ba04`. |
| Culture replay / replication | `results/cross-rollout-culture-replay-2026-08-12.md`; `results/cross-rollout-culture-replication-2026-08-12.md`. |
| Policy results | `results/cross-rollout-policy-v1-scaled-2026-08-12/RESULTS.md`; `...culture-b.../RESULTS.md`; `...qwen9b-replication.../RESULTS.md`. |
| Post-commitment diagnostics | `results/cross-rollout-postcommitment-v1-pilot-v2-2026-08-12/PILOT-REPORT.md`; `...neutral-pilot-v3-enforced.../PILOT-REPORT.md`; `...partial-batch-264/PARTIAL-REPORT.md`. |
| Luna qualification and smoke | `results/cross-rollout-postcommitment-v1-luna-qualification-2026-08-12/qualification-report.md`; `...luna-harness-smoke.../SMOKE-REPORT.md`. |
| Evidence integrity | `RESEARCH-INTEGRITY.md`; `environments/cross_rollout_postcommitment_evidence_interface_balanced_v1/`. |
| Provenance boundary archive | `analysis_archives/cross_rollout_postcommitment_provenance_boundary_v1/2026-08-14-luna/report.md`, raw SHA `bc4e6a857f4eec1108c0e182ee7179637fa3a7269970885e569f5b30c0f301a4`, archive commit `6f79332`. |
| Evidence threshold archive | `analysis_archives/cross_rollout_postcommitment_evidence_threshold_transport_v1/2026-08-15-luna/report.md`, raw SHA `6fed273c28e4ed07cd3fdbd915411955bb67aafc87f440b0ea36550e70d70efb`, scientific freeze `9c47e0c`, archive state at `d3a9694`. |

## D. Provenance limitations

The transcript contains exact reports of a provenance continuation and dose
response that were not found as complete raw archives in the current checkout.
They are marked `T` in the experiment and claim ledgers. The durable boundary
and threshold archives are the authoritative repository artifacts for the
latest source/threshold work. No transcript-only result is used to claim a
governance effect.

## E. Frozen-package boundary

This snapshot adds only the pre-framework documents and the read-only source
decoder. It does not edit any frozen environment, prompt, harness, raw trace,
analysis input, or prior result. The dedicated archival commit is recorded in
the handoff after validation.
