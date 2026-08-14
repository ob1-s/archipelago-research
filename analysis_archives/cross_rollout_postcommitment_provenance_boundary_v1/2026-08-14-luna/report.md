# `cross_rollout_postcommitment_provenance_boundary_v1` — Luna completion, integrity, and frozen analysis

Date: 2026-08-14  
Status: complete, audited, analyzed, and archived  
Analysis endpoint: frozen primary ITT `SWITCH` vs `RETAIN`

## Completion and integrity audit

The target was complete before shutdown:

- Assignment ledger: 432 claims, `next_eligible_index=432`; all 432 primary assignments claimed.
- Primary traces: 432, with complete eligible-index set `0..431`, no duplicates, no missing indices, and no primary errors.
- Matched pairs: 216 complete pairs; every pair contains exactly one `PredecessorSource` and one `AutomatedSource` record.
- Cells: all 36 `q × source × Phase-2-order` cells contain exactly 12 records. Therefore every `q × source` analysis cell contains 24 records.
- No target-sample trajectory remained in flight at shutdown.

The raw trace archive contains 1,255 completed rows: 1,083 actual Phase-1 attempts and 172 archived post-target guard rows (`stopped_before_attempt=true`). The evaluator log recorded 1,256 guard/attempt starts and 1,255 done records. The final start, task 1255, was another post-target guard start: the target ledger was already complete before it began, and it produced no completed trace because the evaluator was administratively stopped. It is not part of the primary sample. The evaluator process group was sent SIGTERM only after this classification; no raw traces, logs, or temporary evidence were deleted.

The watcher is terminal and no evaluator or watcher process remains. Its final status is `fatal_error / target_exited_without_exit_code`, which reflects the authorized administrative SIGTERM rather than a scientific evaluator failure. The outcome-blind supervisor history is preserved separately in `operational_supervisor_final_status.json` and at the original `/tmp` status path.

Frozen-package integrity checks passed:

- Current Git commit: `549a8dc0f10d32694181a47962bcbb4f7cb2c915` (`Add outcome-blind Archipelago run supervisor`).
- `git diff e592c9d..HEAD -- environments/cross_rollout_postcommitment_provenance_boundary_v1` is empty.
- The frozen package's `PRELIVE_MANIFEST.sha256` remains available in the package.
- Source config SHA-256: `ae7c6708348a2adab46f02ba043c15a8bedfde1965c0f54a34dd7a6518d9c778`.
- Resolved run config SHA-256: `2a2ea5f863c2b9a9e2049f6540b0ce9a79666343f1d60872ccaccd7ce3204b7f`.
- The resolved config differs from the source file only by the generated default `[serve] address`; scientific settings remained unchanged.
- Raw trace SHA-256: `bc4e6a857f4eec1108c0e182ee7179637fa3a7269970885e569f5b30c0f301a4`.
- Analysis module SHA-256: `00147df5e4d8e621a437ac7ed2817a9b4df9722aeb0f80781a14ee211ea3ee2e`.
- Runtime: Python 3.12.13, `verifiers 0.3.0`, `pydantic 2.13.4`, `mcp 1.29.0`, `openai 2.54.0`.

The immutable derived analysis input was frozen before inferential analysis and made read-only. The analysis below was run from that input, not by re-reading mutable live traces. No behavioral outcomes were used for the completion gate or process shutdown decision.

## Frozen run configuration

- Model: `gpt-5.6-luna`.
- Base URL: `http://127.0.0.1:10531/v1`.
- Sampling: requested temperature `0.7`, `max_tokens=1024`; reasoning effort unspecified/not present.
- Concurrency: 1; retries: 0; `colocated=false`.
- Built-in null harness; maximum turns 14.
- `num_tasks=1400`, `num_rollouts=1`, `shuffle=false`.
- Frozen random seeds: source `cross-rollout-postcommitment-provenance-boundary-v1-random-2026-08-14`, assignment `cross-rollout-postcommitment-provenance-boundary-v1-assignment-2026-08-14`, schedule `cross-rollout-postcommitment-provenance-boundary-v1-schedule-2026-08-14`.

## Primary ITT results

The frozen rule codes missing primary Phase-2 choice as `NOT SWITCHED`; there were no missing primary Phase-2 choices in this archive. Each row has `n=24`.

| q | PredecessorSource SWITCH/n | Proportion | AutomatedSource SWITCH/n | Proportion |
|---:|---:|---:|---:|---:|
| 0.7800 | 0/24 | 0.0000 | 1/24 | 0.0417 |
| 0.7850 | 2/24 | 0.0833 | 2/24 | 0.0833 |
| 0.7900 | 1/24 | 0.0417 | 0/24 | 0.0000 |
| 0.7925 | 3/24 | 0.1250 | 2/24 | 0.0833 |
| 0.7950 | 7/24 | 0.2917 | 2/24 | 0.0833 |
| 0.7975 | 23/24 | 0.9583 | 23/24 | 0.9583 |
| 0.8000 | 24/24 | 1.0000 | 24/24 | 1.0000 |
| 0.8050 | 24/24 | 1.0000 | 23/24 | 0.9583 |
| 0.8100 | 24/24 | 1.0000 | 24/24 | 1.0000 |

### Matched-pair comparison

All 216 matched source pairs were evaluable under the frozen ITT rule.

- Predecessor switch / Automated retain: 14
- Predecessor retain / Automated switch: 7
- Both switch: 94
- Both retain: 101
- Exact two-sided McNemar p-value: `0.18924713134765625`

The frozen equal-weight q-stratified risk difference, `P(SWITCH|Predecessor) − P(SWITCH|Automated)`, is `0.03240740740740741` (3.2407 percentage points), with the prespecified normal 95% interval `[-0.008828658650883003, 0.07364347346569783]` (−0.883 to 7.364 percentage points).

## Boundary / q50 analysis

Frozen weighted isotonic regression and interpolation between tested q values gave:

| Source | q50 | q50 − `q*` (`q*=0.7950311`) |
|---|---:|---:|
| PredecessorSource | 0.79578125 | +0.00075015 |
| AutomatedSource | 0.7961904761904762 | +0.0011593761904762 |

Thus, using the preregistered definition,

`Δq50 = q50,Predecessor − q50,Automated = -0.00040922619047623066`,

which is `-0.040922619047623066` reliability percentage points. Both q50 values were identifiable by interpolation within the tested range; no extrapolation was used.

The frozen within-pair source-label-flip randomization inference used 100,000 repetitions and seed `cross-rollout-postcommitment-provenance-boundary-v1-q50-randomization-2026-08-14`. Identifiable fraction was 1.0. The exact frozen two-sided p-value was `0.07045929540704593`; permutation quantiles were 0.025=`-0.00043739967897271637`, 0.5=`0.000012462612163477438`, and 0.975=`0.00040922619047623066`.

The optional centered-evidence-log-odds logistic model was not run because the frozen implementation specifies the raw and isotonic curves as the analysis; no post-hoc alternative model or regularization was introduced.

## Secondary protocol and outcome accounting

These are descriptive secondary outcomes, not the primary endpoint:

- R2 policy choice: `K=207`, `M=225`.
- R2 acquisition: 292/432 = 0.6759259259259259 (frozen Wilson 95% interval [0.6304084418255005, 0.7183422263906065]).
- R2 verification: 236/432 = 0.5462962962962963 (frozen Wilson 95% interval [0.49914695932904585, 0.5926295323067718]).

## Lifecycle, missingness, and runtime

Among the 432 eligible primary trajectories:

- natural yield: 432/432;
- R2 activation: 432/432;
- exactly one Turn-2 user message: 432/432;
- Phase-2 choice observed: 432/432;
- missing Phase 2: 0;
- incomplete after choice: 0;
- interstage calls: 0;
- recorded lifecycle violations: 0.

Trace-time runtime summaries (summed per-trace durations, not a concurrency-adjusted wall-clock estimate):

- 1,255 archived rows: total 15,990.249869823456 seconds (4.44173607495096 hours), mean 12.741234956034626 s, median 10.373905658721924 s, range 1.9470813274383545–61.05177903175354 s.
- 432 eligible rows: mean 20.930780826895325 s, median 20.23343336582184 s, range 15.22925591468811–61.05177903175354 s.
- Approximate eligible throughput from summed trace time: 97.2592681578384 eligible trajectories/hour; this is not the evaluator's actual elapsed wall-clock throughput.
- Model wait total: 10,842.578832149506 s; harness total: 2,223.894576072693 s; local-overhead approximation: 5,147.67103767395 s.

The only anomaly is administrative termination of one post-target guard start, recorded by the supervisor as no evaluator exit code. It did not affect the complete primary sample. There were no runtime/provider errors in the archived traces.

## Claim-safe verdict

The two sources show the same sharp transition between q=0.7950 and q=0.7975, with q50 estimates nearly coincident and both close to the frozen normative crossover. The observed source difference is small and not decisive under the prespecified paired analyses (McNemar exact p=0.189; q50 flip p=0.07046; RD interval includes zero).

The defensible descriptive classification is **A: same sharp threshold**, compatible with **D: both track the normative boundary**. This tests a source-provenance effect on behavioral evidence weighting in this one-shot matched design. It does not establish endogenous machine culture; one-shot equivalence remains possible; and proximity to the normative crossover does not establish internal Bayesian computation.

## Archived paths and Git handoff

- Raw traces: `/tmp/archipelago-cross-rollout-postcommitment-provenance-boundary-v1-luna-2026-08-14-repaired/traces.jsonl`
- Frozen analysis input: [analysis_input.json](/home/ob1/Projects/archipelago/analysis_archives/cross_rollout_postcommitment_provenance_boundary_v1/2026-08-14-luna/analysis_input.json)
- Completion/integrity audit: [completion_integrity_audit.json](/home/ob1/Projects/archipelago/analysis_archives/cross_rollout_postcommitment_provenance_boundary_v1/2026-08-14-luna/completion_integrity_audit.json)
- Frozen results: [analysis_results.json](/home/ob1/Projects/archipelago/analysis_archives/cross_rollout_postcommitment_provenance_boundary_v1/2026-08-14-luna/analysis_results.json)
- Human-readable report: [report.md](/home/ob1/Projects/archipelago/analysis_archives/cross_rollout_postcommitment_provenance_boundary_v1/2026-08-14-luna/report.md)
- Archived supervisor status: [operational_supervisor_final_status.json](/home/ob1/Projects/archipelago/analysis_archives/cross_rollout_postcommitment_provenance_boundary_v1/2026-08-14-luna/operational_supervisor_final_status.json)
- Original supervisor status: `/tmp/archipelago-run-supervisor-current-luna-2026-08-14/status.json`

Current `git status --short` is intentionally limited to untracked archival/operational artifacts:

```text
?? analysis_archives/
?? tools/watch_boundary.py
```

Proposed archival commit message (not applied):

```text
Archive provenance-boundary v1 Luna qualification

Archive the completed outcome-blind integrity audit, immutable analysis input,
frozen results, and report. The scientific package remained unchanged from
the e592c9d freeze through the live run; 549a8dc is a later operational
supervisor commit. Preserve the raw run by its external path and SHA-256.
```
