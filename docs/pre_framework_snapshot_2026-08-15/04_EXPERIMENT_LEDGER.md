# Experiment ledger

This ledger separates what was tested from what the historical program wanted
to know. `R` means the result is durably inspectable in this checkout; `T`
means the exact result was recovered from the shared conversation but the raw
archive is not complete here; `I` is an interpretation.

## A. External-state and policy-influence ladder

| Family / date | Question and design | Result | Claim-safe interpretation | Provenance |
|---|---|---|---|---|
| `cross_rollout_culture_v1` original chain | Do fresh rollouts use a procedure left in persistent notes? The historical run compared persistent and control chains. | The conversation reports 60 persistent and 60 control rollouts with no direct inheritance events in the initial spontaneous run. | Negative for spontaneous inheritance in that tiny setup; not evidence that an artifact channel cannot work. | T; design is in `cross_rollout_culture_v1.md`. |
| Seeded culture replay, 2026-08-12 | Fresh Qwen3.5-4B recipients received absent, ordinary-notes, or explicit-system exposure to the same procedure. | Strict pre-discovery use: absent 0/10, notes 2/10, explicit system 0/10. | Small descriptive evidence that ordinary artifact contact can matter differently from explicit text exposure. | R: `results/cross-rollout-culture-replay-2026-08-12.md`. |
| Scaled culture replication, 2026-08-12 | Same frozen task logic, 50 fresh Qwen3.5-4B rollouts per absent/present condition. | Strict direct inherited use 0/50 absent vs 4/50 present; 4/29 among exposed recipients. Task success 24/50 vs 21/50. | A replicable seeded artifact-channel recipient effect, with only four direct events; no task-capability effect and no endogenous culture. | R: `results/cross-rollout-culture-replication-2026-08-12.md`, environment freeze `50abfd2`. |
| Policy v1 mechanics pilot | Two equally viable A/B policies, with an optional predecessor-style note. | Baseline 5/5 A/B; Culture-A 8/2 A/B; 10/10 success in each arm. | Early directional signal, but the pilot was descriptive and exposure was voluntary. | R: `results/cross-rollout-policy-v1-interface-pilot-2026-08-12/README.md`. |
| Qwen3.5-4B scaled policy, 2026-08-12 | Does a researcher-seeded policy-only artifact shift the policy distribution while success remains equal? | Baseline 25/25; Culture-A 42/8; Culture-B 4/46; task success 50/50 in all arms. One-sided Fisher p=.000278 for Culture-A→A and p=2.55e-6 for Culture-B→B. | Strong bidirectional convention-aligned policy selection in this synthetic setup. It is a one-shot inherited-information assay; the artifact is researcher-seeded, not spontaneously produced by a predecessor population. | R: `results/cross-rollout-policy-v1-scaled-2026-08-12/RESULTS.md`, `...culture-b.../RESULTS.md`; commits `50ac443`, `5e4ba04`. |
| Qwen3.5-9B policy replication | Repeat the corrected policy assay with 50 per condition, including A and B conventions. | Baseline 21/29, Culture-A 47/3, Culture-B 10/40; all 50/50 success. | Descriptive cross-model replication of bidirectional cue susceptibility; not a monotonic scaling law and not a culture-formation result. | R: `results/cross-rollout-policy-v1-qwen9b-replication-2026-08-12/RESULTS.md`. |
| Cross-model qualification gate | Can 0.8B or 9B be scaled under the frozen competence/failure gates? | 0.8B failed competence/task gates. 9B met success and policy gates but Culture-A had 3/10 tool-failure traces against a cap of 2/10. | Qualification failure, not a generalization failure; no new confirmatory 50-per-condition run was authorized. | R: `results/cross-rollout-policy-v1-cross-model-2026-08-12/RESULTS.md`. |

## B. Post-commitment recurrence-adjacent diagnostics

| Family / date | Question and design | Result | Claim-safe interpretation | Provenance |
|---|---|---|---|---|
| Initial post-commitment pilot | After B succeeds on R1, expose a convention before equivalent R2. | 30/30 Phase-1 A; interface was not usable for inference. | Presentation/interface failure. | R: `results/cross-rollout-postcommitment-v1-pilot-2026-08-12/INITIAL-PILOT-REPORT.md`. |
| v2 factorial pilot | Balance A-first/B-first in both phases; expose neutral/A/B notice after R1. | A-first 16/16 A; B-first 14/16 B. Transitions A→A=2, A→B=16, B→A=14, B→B=0. | Mechanics worked, but presentation order and no persistence variation made it non-confirmatory. | R: `...pilot-v2.../PILOT-REPORT.md`. |
| Neutral-only v3 | Reveal R2 only after R1 success and validate neutral persistence/switching. | 16 balanced Qwen3.5-9B trajectories; A→A=8, A→B=2, B→A=2, B→B=4; all R1/R2 successes. | A usable neutral baseline with variation; still no treatment conclusion. | R: `...neutral-pilot-v3-enforced.../PILOT-REPORT.md`. |
| Partial Qwen confirmatory batch | Frozen custom harness, deferred assignment, 50 eligible B cases per arm planned. | Stopped at 265/320 for budget. Neutral B→A 25/46; Culture-A B→A 26/43; descriptive +6.1 pp, p=.356. | Incomplete, quota-failing descriptive batch; not a confirmatory estimate. | R: `results/cross-rollout-postcommitment-v1-confirmatory-2026-08-12/partial-batch-264/PARTIAL-REPORT.md`, freeze `a84a165`. |
| Luna null-harness qualification | Test the requested model/runtime with the native null harness. | 38 clean Phase-1 completions; only 3 Neutral and 2 Culture-A eligible B cases, with missing Phase-2 actions. | Harness lifecycle incompatibility, not a treatment estimate and not evidence of Luna incompetence. | R: `...luna-qualification.../qualification-report.md`. |
| Luna custom-harness smoke | Check whether the continuation apparatus can carry the two-stage task. | 8/8 reward; 3/3 eligible B trajectories completed R2; all happened to be Culture-A. | Mechanical qualification only; no treatment comparison. | R: `...luna-harness-smoke.../SMOKE-REPORT.md`. |

## C. Evidence and provenance assay branch

| Family / date | Question and design | Result | Claim-safe interpretation | Provenance |
|---|---|---|---|---|
| Evidence-interface-balanced | Does first-person evidence direction affect repeat behavior? K/M labels and presentation order were counterbalanced. | K-first→K 91/91 and M-first→M 91/91; success+pass repeat 62/64; success+fail repeat 0/54. Neutral switched 0/32; Opposing switched 2/32, Fisher p=.246. | First-person evidence assay is behaviorally active; the treatment difference is imprecise and not persuasive. Phase-1 labels are presentation-controlled. | R: `RESEARCH-INTEGRITY.md`, `environments/cross_rollout_postcommitment_evidence_interface_balanced_v1/`. |
| Provenance continuation, 2026-08-14 | Transcript-reported 160 eligible source-assay transitions, matched across predecessor, automated, and no-advisory sources. | Pooled K→K 16, K→M 52, M→K 75, M→M 17; Predecessor 64/64 switched, Automated 63/64 switched, NoAdvisory 0/32 switched; lifecycle clean. | Source/advisory exposure was active in that transcript-backed run; the result does not isolate a provenance effect or culture. | T: conversation message 1567; source package commit `42907c4`; raw result not durably present in this checkout. |
| Provenance dose response | Transcript-reported q grid .50–.80 across source conditions. | At each tested q through .70, approximately 0/39 switched; .75 had 1/40 and .80 had 39/40; normative q*=.7950311. | Sharp evidence-weighting threshold compatible with normative crossover; no source effect at this coarse grid and no Bayesian proof. | T: conversation message 1586; source package commit `7f91917`; raw result not durably present here. |
| Provenance boundary, 2026-08-14 | 432 eligible trajectories, 216 matched source pairs, q=.7800–.8100. | Both sources jump between .7950 and .7975. q50 predecessor .79578125, automated .79619048; Δ=-.0409 reliability pp; McNemar p=.189; q50 flip p=.07046; RD interval includes zero. | Same sharp threshold; no decisive source-provenance effect in this one-shot matched design. | R: `analysis_archives/cross_rollout_postcommitment_provenance_boundary_v1/2026-08-14-luna/report.md`; raw SHA `bc4e6a...301a4`; archive commit `6f79332`. |
| Evidence-threshold transport, 2026-08-15 | 504 eligible gpt-5.6-luna trajectories across LOW/ANCHOR/HIGH evidence strengths and 84 quota cells. | 504/504 primary clean; q50 .6994737/.7959211/.8986207 against frozen q* .700/.7950311/.900; LOW→HIGH observed .199147 vs predicted .200000, bootstrap interval [.1980645,.2004251]. | Strong threshold transport within the task/model/runtime; not culture, provenance, internal Bayes, or generality. | R: `analysis_archives/cross_rollout_postcommitment_evidence_threshold_transport_v1/2026-08-15-luna/report.md`; raw SHA `6fed273...70efb`; archive commit `d3a9694` contains the archive. |

## Interpretation of the ladder

The empirical ladder currently stops here:

1. A seeded external artifact can sometimes affect a fresh recipient.
2. A seeded convention can strongly shift an equally viable policy choice.
3. Evidence and presentation can control recipient behavior in one-shot assays.
4. No study yet shows agent-generated state maintained through complete active
   population turnover.
5. No study yet tests whether a governance restriction selects covert or
   attribution-resistant organization.

The next live experiment must therefore target endogenous recurrence, not add
another recipient-side evidence assay.
