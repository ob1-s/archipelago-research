# Fixture oracles

These are scripted known-ground-truth cases, not behavioral observations.

| Case | Turnover | Behavior | Required classification |
| --- | --- | --- | --- |
| A | valid 100%, 0 survivors | succeeds | L0–L5 true |
| B0 | 0%, 4 survivors | continues | redundant continuity; L0/L5 false |
| B50 | 50%, 2 survivors | continues | redundant continuity; L0/L5 false |
| B100 | valid 100%, 0 survivors | fails | L0 true; L1–L5 false |
| C | valid 100%, no carrier | fails | no inherited reconstruction |
| D | valid 100%, researcher carrier | succeeds | functional reuse; L3–L5 false |
| E | valid 100%, terminal replay | succeeds | downstream sufficiency; arm-level L3–L5 false |
| F | valid 100%, no causal channel | succeeds by rediscovery | transmission and L1–L5 false |
| G | nominal 100%, hidden session survives | may succeed | invalid turnover; all rungs false |
| H | valid 100%, orchestrator computes routine | succeeds | confounded; L2–L5 false |

Oracle comparison is field-by-field. Known positives must be detected at their
proper rung, and confounds must be rejected or downgraded. Criteria are frozen
in the fixture manifest rather than adapted to observed output.
