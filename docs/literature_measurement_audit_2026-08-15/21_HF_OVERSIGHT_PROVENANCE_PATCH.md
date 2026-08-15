# Hugging Face oversight provenance patch

Date: 2026-08-15

Applies to audit commit: `d3647a06b34862a797e56cc7686476b6afbcab81`

Scope: provenance repair only. This patch does not alter the frozen pre-framework packet, change the incident's scientific claim status, or begin H1 apparatus work.

## Error being repaired

The initial literature audit correctly identified the August 3 document it inspected as a letter from 15 state attorneys general rather than a congressional letter. It then went too far by suggesting that the canonical packet's “congressional request” attribution should be corrected unless a separate congressional source could be found.

A separate congressional source exists. More precisely, the public record contains at least three distinct oversight actions.

## Action ledger

| Date | Actor | Action | Primary-source status | Archival rule |
|---|---|---|---|---|
| 2026-08-03 | Attorneys general of Iowa, Alabama, Arkansas, Florida, Idaho, Indiana, Kansas, Missouri, Montana, Nebraska, Oklahoma, Pennsylvania, South Carolina, Texas, and Utah | Preservation demand to OpenAI covering the incident, related evaluations, prior incidents, and the reported future-version notes | **Verified primary**: [official Iowa AG PDF](https://www.iowaattorneygeneral.gov/media/cms/08_5392C9E17791C.pdf) | Describe as a 15-state-AG legal/investigative preservation action. Do not call it congressional. |
| 2026-08-03 | U.S. House cybersecurity panel | Requested a briefing from Sam Altman about the breach | **Secondary-source supported**: [Reuters report](https://www.reuters.com/technology/us-house-panel-seeks-briefing-openais-ai-agent-security-breach-2026-08-03/); primary committee document not located in this patch | Preserve as a separate House briefing request. Do not infer its full questions, signers, or exact committee style until the primary record is archived. |
| 2026-08-10 | House coalition led by Greg Casar and co-led by Doris Matsui | Requested logs and answers to 23 top-level numbered questions | **Verified primary**: [official Casar press release](https://casar.house.gov/media/press-releases/casar-leads-demand-information-open-ai-about-security-incident) and [official letter PDF](https://casar.house.gov/sites/evo-subsites/casar.house.gov/files/evo-media-document/oversight-letter-to-openai-openai-hugging-face-incident-1.pdf) | This is the source for the detailed numbered-question discussion, including Q15. Do not merge it with either August 3 action. |

## Q15 provenance and evidentiary boundary

Question 15 asks OpenAI whether a model acted to undermine oversight or control of future models or future instances of itself, including by leaving instructions, notes, code, or other artifacts for later instances. It asks OpenAI to describe each known case and its response.

The letter attributes the motivating allegation to Reuters. Therefore:

- **Verified primary:** Congress asked this question in Q15.
- **Verified primary:** the state-AG letter independently requested preservation of material concerning the same allegation in item 8.
- **Unresolved:** whether such successor-facing artifacts existed as described, what generated them, which later instances could read them, and whether they causally affected any fresh rollout.
- **Not established:** culture, autonomous organization, self-preservation, or cross-turnover lineage.

## Signer-count ledger

| Source snapshot | Count stated or observed | Interpretation boundary |
|---|---:|---|
| Reuters, 2026-08-10 | 29 lawmakers | Contemporaneous secondary report; full article was not directly accessible during this patch. |
| Casar official press release, retrieved 2026-08-15 | “led 31 members of Congress” | Official summary wording. The same page identifies Matsui as co-lead and lists 30 additional representatives. |
| Currently linked official PDF, retrieved 2026-08-15 | 32 named signatures | Casar, Matsui, and 30 others. This is the strongest current enumeration of the linked letter copy. |

The official PDF is dated August 10, has an HTTP last-modified timestamp of August 11, and has SHA-256 `95fedaa7566e6b0917149649d1d17e7f1affce5e35653c5f6674b869551d7c75`. A later-updated signatory list could explain the numerical differences, but the public sources inspected here do not prove that history. Preserve all three count statements with their source and retrieval context.

## Effect on project history

The frozen packet's generic statement that a congressional request existed is not disproven. The literature audit's proposed replacement was the error. Git history preserves that overcorrection; this file and the linked updates repair it prospectively without rewriting the frozen archive.

The HF incident remains a motivating, source-audited case. The oversight letters are primary evidence of oversight demands, not primary evidence for every incident allegation they repeat.
