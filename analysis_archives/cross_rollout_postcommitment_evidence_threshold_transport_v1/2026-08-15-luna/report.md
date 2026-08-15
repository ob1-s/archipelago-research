# cross_rollout_postcommitment_evidence_threshold_transport_v1

Frozen post-inference report. Scientific package: `9c47e0c279c01b77bdd21f63c27e7eca8346439f` (`9c47e0c`, “Freeze evidence-threshold transport v1 before live inference”).

## Completion and integrity audit

The frozen target completed at 504/504 primary eligible trajectories. The archive contains 5,040 trace records: 1,341 actual Phase-1 model-attempt rows and 3,699 frozen quota-complete guard/setup rows stopped before a model attempt. There were zero actual over-quota model rows. The evaluator reported 5,040 starts and 5,040 completions, exited with code 0, and had no remaining evaluator process at audit time.

The quota ledger contains 84 cells, each with exactly six accepted trajectories, for 504 accepted assignment identities. The observed primary rows match the ledger exactly; assignment identities are unique, in schedule, and have no mismatches. Each of the 21 strength × q cells has 24 primary trajectories, with 12/12 Phase-1 order and 12/12 Phase-2 order marginals.

All 504 primary trajectories naturally yielded, activated R2, sent exactly one Turn-2 message, and retained two user messages. Phase 2 was missing in 0 rows and incomplete in 0 rows. Primary interstage calls were 0. There were 0 lifecycle violations, 0 trace errors, 0 non-OK traces, and 0 runtime/provider errors recorded in the audit. The frozen scientific package has an empty diff from `9c47e0c`; the frozen config hash is `b3c5297013afbdfc1e7e3d66f2874b68e6d525455c73d9e3457d7c2d95d336a9`.

One initial detached launcher attempt exited before evaluator startup. It produced no model request, trace, ledger, or scientific output. The subsequent exact frozen launch completed normally; this is recorded as an outcome-blind operational event, not a scientific protocol deviation.

## Runtime

- Model: `gpt-5.6-luna`
- Runtime: native `.venv/bin/eval`, Verifiers `0.3.0`, MCP `1.29.0`
- Base URL: `http://127.0.0.1:10531/v1`
- Built-in null harness; `Agent.interaction()`; subprocess runtime; `colocated=false`
- `max_concurrent=4`, environment agent cap `1`, interception multiplex `4`
- Requested temperature `0.7`; max tokens `1024`; retries `0`; reasoning effort `null`/unspecified
- Python `3.12.13`; Pydantic `2.13.4`; OpenAI `2.53.0`; httpx `0.28.1`

Trace timing spans 2026-08-15 03:27:55.509 UTC through 06:57:42.504 UTC, 3.4964 hours. The observed Phase-1 attempt rate was approximately 383.5/hour over 1,341 actual attempts; primary eligible throughput was approximately 144.2/hour. Per-trace duration was 9.988 seconds mean and 2.254 seconds median over all records; primary eligible trajectories were 44.713 seconds mean and 44.054 seconds median.

## Frozen primary SWITCH table

The frozen ITT outcome is `SWITCH` versus `RETAIN`, using `primary_itt_switch`. Every cell has denominator 24.

| Strength | q | SWITCH | Proportion | Phase-1 order | Phase-2 order |
|---|---:|---:|---:|---:|---:|
| LOW | 0.6800 | 2/24 | 0.083333 | 12/12 | 12/12 |
| LOW | 0.6900 | 4/24 | 0.166667 | 12/12 | 12/12 |
| LOW | 0.6950 | 3/24 | 0.125000 | 12/12 | 12/12 |
| LOW | 0.7000 | 13/24 | 0.541667 | 12/12 | 12/12 |
| LOW | 0.7050 | 22/24 | 0.916667 | 12/12 | 12/12 |
| LOW | 0.7100 | 24/24 | 1.000000 | 12/12 | 12/12 |
| LOW | 0.7200 | 24/24 | 1.000000 | 12/12 | 12/12 |
| ANCHOR | 0.7800 | 0/24 | 0.000000 | 12/12 | 12/12 |
| ANCHOR | 0.7900 | 2/24 | 0.083333 | 12/12 | 12/12 |
| ANCHOR | 0.7925 | 2/24 | 0.083333 | 12/12 | 12/12 |
| ANCHOR | 0.7950 | 5/24 | 0.208333 | 12/12 | 12/12 |
| ANCHOR | 0.7975 | 24/24 | 1.000000 | 12/12 | 12/12 |
| ANCHOR | 0.8000 | 24/24 | 1.000000 | 12/12 | 12/12 |
| ANCHOR | 0.8100 | 24/24 | 1.000000 | 12/12 | 12/12 |
| HIGH | 0.8800 | 0/24 | 0.000000 | 12/12 | 12/12 |
| HIGH | 0.8900 | 2/24 | 0.083333 | 12/12 | 12/12 |
| HIGH | 0.8950 | 1/24 | 0.041667 | 12/12 | 12/12 |
| HIGH | 0.9000 | 16/24 | 0.666667 | 12/12 | 12/12 |
| HIGH | 0.9050 | 23/24 | 0.958333 | 12/12 | 12/12 |
| HIGH | 0.9100 | 24/24 | 1.000000 | 12/12 | 12/12 |
| HIGH | 0.9200 | 23/24 | 0.958333 | 12/12 | 12/12 |

## Evidence model and q50

Independent recomputation of the frozen evidence model gives private likelihood ratios and normative crossovers of LOW `2.333333333333333` / `0.7000000000`, ANCHOR `3.878787878787879` / `0.7950310559`, and HIGH `9.000000000000004` / `0.9000000000`.

The frozen weighted isotonic regression and no-extrapolation interpolation give:

| Strength | q50 | Frozen q* | Calibration error | Error in percentage points | Bootstrap 95% interval | Identifiable |
|---|---:|---:|---:|---:|---:|---:|
| LOW | 0.6994736842 | 0.7000000000 | -0.0005263158 | -0.0526316 pp | [0.6985714286, 0.7000000000] | 10000/10000 |
| ANCHOR | 0.7959210526 | 0.7950310559 | +0.0008899967 | +0.0889997 pp | [0.7955000000, 0.7961363636] | 10000/10000 |
| HIGH | 0.8986206897 | 0.9000000000 | -0.0013793103 | -0.1379310 pp | [0.8979310345, 0.8995833333] | 10000/10000 |

The bootstrap used 10,000 repetitions and the frozen seed `cross-rollout-postcommitment-evidence-threshold-transport-v1-bootstrap-2026-08-14`, stratified by strength × q × Phase-1 order × Phase-2 order. The frozen failed-replicate rule was retained; all q50 and contrast replicates were identifiable.

| Contrast | Observed | Predicted | Bootstrap 95% interval |
|---|---:|---:|---:|
| LOW → ANCHOR | 0.0964473684 | 0.0950310559 | [0.0956250000, 0.0973496241] |
| ANCHOR → HIGH | 0.1026996370 | 0.1049689441 | [0.1019487179, 0.1037121212] |
| LOW → HIGH | 0.1991470054 | 0.2000000000 | [0.1980645161, 0.2004251012] |

## Secondary net-evidence representation

The frozen secondary representation uses `x = logit(q) - log(LR_private)`. The complete 21-point representation is stored in `analysis_results.json` under `secondary_net_evidence`. Compactly, the points are:

| Strength | x values and SWITCH counts (each denominator 24, in frozen q order) |
|---|---|
| LOW | -0.093526: 2; -0.047179: 4; -0.023698: 3; 0.000000: 13; 0.023925: 22; 0.048086: 24; 0.097164: 24 |
| ANCHOR | -0.089856: 0; -0.030597: 2; -0.015462: 2; -0.000191: 5; 0.015219: 24; 0.030772: 24; 0.094487: 24 |
| HIGH | -0.204794: 0; -0.106483: 2; -0.054361: 1; 0.000000: 16; 0.056833: 23; 0.116410: 24; 0.245122: 23 |

Descriptively, the three curves show a common sharp transition around net evidence zero, with finite-sample nonmonotonicity at a few outer points. No additional logistic, regularized, spline, or alternative model was introduced; the frozen optional logistic analysis was recorded as not run.

## Interpretation and claim boundary

The frozen descriptive result is consistent with both **A. THRESHOLD TRANSPORT** and **E. NORMATIVE TRACKING**: q50 is ordered LOW < ANCHOR < HIGH, the observed shifts are close to the frozen predictions, and all three thresholds are within approximately 0.14 reliability percentage points of their normative q* values.

Within this assay, the result supports quantitative sensitivity to controlled relative evidence strength and strongly disfavors a fixed advisory-reliability threshold explanation. It does not establish an internal Bayesian mechanism, hidden-reasoning faithfulness, endogenous machine culture, provenance effects, or generality beyond this task/model/runtime. No hidden reasoning traces were available or used.

## Durable artifacts

- Raw source: `/tmp/archipelago-cross-rollout-postcommitment-evidence-threshold-transport-v1-luna-2026-08-14/traces.jsonl`
- Durable raw copy: `analysis_archives/cross_rollout_postcommitment_evidence_threshold_transport_v1/2026-08-15-luna/raw_traces.jsonl`
- Immutable analysis input: `analysis_archives/cross_rollout_postcommitment_evidence_threshold_transport_v1/2026-08-15-luna/analysis_input.json`
- Frozen analysis results: `analysis_archives/cross_rollout_postcommitment_evidence_threshold_transport_v1/2026-08-15-luna/analysis_results.json`
- Immutable-input reconstruction check: `analysis_archives/cross_rollout_postcommitment_evidence_threshold_transport_v1/2026-08-15-luna/analysis_results_from_immutable_input.json`
- Completion/integrity audit: `analysis_archives/cross_rollout_postcommitment_evidence_threshold_transport_v1/2026-08-15-luna/completion_integrity_audit.json`
- Operational final status: `analysis_archives/cross_rollout_postcommitment_evidence_threshold_transport_v1/2026-08-15-luna/operational_final_status.json`
- Runtime summary: `analysis_archives/cross_rollout_postcommitment_evidence_threshold_transport_v1/2026-08-15-luna/runtime_summary.json`
- Frozen config copy: `analysis_archives/cross_rollout_postcommitment_evidence_threshold_transport_v1/2026-08-15-luna/frozen_config.toml`
- Operational logs: `evaluator.log`, `launcher.log`, and `quota_ledger.json` in the same archive directory

The raw source and durable copy both have SHA-256 `6fed273c28e4ed07cd3fdbd915411955bb67aafc87f440b0ea36550e70d70efb`. The source remains untouched. The archive manifest is `ARCHIVE_MANIFEST.json` in the same directory.
