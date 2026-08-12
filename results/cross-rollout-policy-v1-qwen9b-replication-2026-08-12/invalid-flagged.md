# Invalid and flagged rollout table

All 150 rollouts were valid under the preregistered revised criterion.

| Condition | Infrastructure/provider/runtime | No identifiable policy | Mapping inconsistency | Ambiguous trajectory | Task failure |
|---|---:|---:|---:|---:|---:|
| baseline | 0 | 0 | 0 | 0 | 0 |
| culture-A | 0 | 0 | 0 | 0 | 0 |
| culture-B | 0 | 0 | 0 | 0 | 0 |
| **Total** | **0** | **0** | **0** | **0** | **0** |

Recoverable tool mistakes were not invalidated. They are reported as behavioral data in `RESULTS.md`: 7 baseline, 4 Culture-A, and 10 Culture-B `release_resource` calls before selection. The rollout traces remain valid because each had an identifiable A/B policy, a reconstructable trace, consistent A/B mapping, and no infrastructure error.
