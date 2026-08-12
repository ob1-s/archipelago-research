# Partial deferred-assignment confirmatory batch

Status: stopped for budget before the preregistered quota was reached. This is
not a completed confirmatory experiment and must not be interpreted as one.

Frozen setup commit: `a84a165`  
Base pilot commit: `f4e11fd`  
Model: `Qwen/Qwen3.5-9B`  
Completed rollouts: 265 of the requested 320 initial-batch maximum

## Why the batch stopped

The provider-reported usage in the archived traces was approximately **$0.1652**
at 265 completed rollouts, already exceeding the available $0.06 budget stated
during the run. The process was interrupted before starting the next rollout.
No task logic, wording, assignment rule, sampling, or analysis was changed.

## Completed data

| Phase-1 presentation | Rollouts | Phase-1 A | Phase-1 B |
|---|---:|---:|---:|
| A-first | 160 | 160 | 0 |
| B-first | 105 | 16 | 89 |
| **Total** | **265** | **176** | **89** |

All 89 Phase-1-B successes were assigned after the successful B release and
received R2 exposure:

| Arm | Valid B cohort | B→A | B→B |
|---|---:|---:|---:|
| Neutral | 46 | 25 | 21 |
| Culture-A | 43 | 26 | 17 |

The preregistered target was at least 50 valid B rollouts per arm. Neither arm
reached it, so this table is descriptive only.

For orientation, the partial rates are:

- neutral switching: 25/46 = 54.3%;
- Culture-A switching: 26/43 = 60.5%;
- absolute difference: +6.1 percentage points;
- risk ratio: 1.113;
- odds ratio: 1.285;
- one-sided Fisher p-value: 0.356.

These are not confirmatory claims because the preregistered quota and stopping
rule were not met.

## Trace quality

All 265 archived traces were evaluator-ok and complete. There were no provider,
runtime, harness, or interception errors; no ambiguous policy selections; no
tool-failure events; and all 89 eligible B traces successfully obtained R2.
Phase-1 A rollouts received no exposure and no R2, as specified.

## Archive

- raw traces: `traces.jsonl`;
- resolved config: `config.toml`;
- evaluator log: `eval.log`;
- machine-readable summary: `aggregate-results.json`;
- frozen preregistration: `../preregistration.md`;
- frozen setup: commit `a84a165`.
