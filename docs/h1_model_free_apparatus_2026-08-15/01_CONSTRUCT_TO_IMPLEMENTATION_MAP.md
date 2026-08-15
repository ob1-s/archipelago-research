# Construct-to-implementation map

| Construct | Implementation | Observable | Fail-closed condition |
| --- | --- | --- | --- |
| Active population | `LifecycleRegistry` actor handles | Actor/lifecycle/process/session/authority IDs | Any predecessor remains active or retains memory/authority |
| Turnover boundary | revoke + terminate events | Zero active generation-0 actors | Missing termination evidence or forbidden carrier |
| Carrier | `ArtifactRecord` in enumerated carrier store | Content hash, writer, reader, parent IDs | Unknown carrier, missing write/read, hash mismatch |
| Functional reuse | held-out two-key relay | State-following output and action graph | Success supplied by one actor/orchestrator |
| Endogenous production | actor-authenticated write edge | Actor author and transformed payload | Researcher seed or terminal-replay arm |
| Causal transmission | carrier ablation/recovery/state swap | Failure without valid state; behavior follows actual bytes | Rediscovery, ambiguous parentage, or invalid graph |
| Routine | encoder → checker → encoder | Exact stage order, two actor identities, distinct inputs | File-to-token, one-actor, or orchestrator comparator |
| Parentage | topology manifest and artifact inventory | unique/multiple/archive/broadcast/shuffles | Common archive treated as unique ancestry |
| Inferential unit | lineage aggregation | unique population + lineage summaries | Actions, actors, calls, or generations counted as independent n |

All outcome dimensions remain separate. The claim ladder is a set of cumulative
gates, not a weighted or scalar H1 score.
