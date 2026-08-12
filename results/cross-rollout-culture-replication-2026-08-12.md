# Cross-rollout culture v0 replication

Date: 2026-08-12

This replication used the unchanged environment/task logic from commit `50abfd2`.
The working tree's environment directory was verified byte-for-byte against that
commit before the run. No prompt, parser, task, or scoring changes were made.

## Setup

- Model: `Qwen/Qwen3.5-4B`
- Harness: `null`
- Runtime: subprocess
- Sampling: temperature `0.7`, max tokens `1024`
- 50 fresh rollouts per condition
- `max-concurrent=1` within each condition
- A and B used separate notes paths
- No provider, runtime, harness, or trace errors in the 100 recorded rollouts

Condition B used the same artifact as the earlier replay, copied from a real
predecessor write:

```text
Maintenance macro pulse_hold_resume completed. R dispenser is primed.
```

The explicit-system condition was not run.

## Aggregate results

The strict event classifier counts a successful exact
`pulse_hold_resume` action whose event index is after a nonempty artifact read
and before the first successful `inspect_terminal` discovery. If no independent
discovery occurs, the use still qualifies as “before discovery.”

| Outcome | A: absent | B: present |
|---|---:|---:|
| Artifact available | 0/50 (0%) | 50/50 (100%) |
| Artifact read | 0/50 (0%) | 37/50 (74%) |
| Read before discovery | 0/50 (0%) | 29/50 (58%) |
| Pre-discovery macro attempt | 0/50 (0%) | 4/50 (8%) |
| Strict direct inherited use | 0/50 (0%) | 4/50 (8%) |
| Task success | 24/50 (48%) | 21/50 (42%) |

The exposed-recipient denominator in B is 29 rollouts: `read before discovery`.
The strict direct-use rate among those exposed recipients was therefore 4/29
(13.8%). The overall strict direct-use rate was 4/50 (8%).

The taskset's native `direct_inherited_procedure_use` field is 0 in both
conditions because the replay artifact is intentionally labeled
`researcher_seed`; the counts above use the ordered trace events, which is the
appropriate classifier for this seeded replay.

## Notable trace patterns

- All four B direct-use events occurred after the artifact was read and before
  any independent terminal discovery. In all four, no independent discovery was
  recorded before the rollout ended.
- Three of the four direct-use rollouts obtained resource R; one used the macro
  but ran out of turns before completing retrieval.
- In B, 8 additional rollouts read the artifact only after independent discovery;
  those are exposure events but not direct transmission events.
- In A, one rollout read nonempty notes only after it had locally produced them;
  it was not an available predecessor artifact and was correctly excluded from
  the artifact-read denominator.
- The raw task-success rates were A 24/50 and B 21/50. This difference is not
  interpreted as a capability effect.

## Interpretation

At this larger N, the earlier qualitative effect recurred: four B recipients
executed the predecessor procedure before independently discovering it, while
none did so in A. The result is consistent with an artifact-channel behavioral
effect, but the effect is based on only four direct events and 29 recipients who
actually read the artifact before discovery. It should not be treated as a
precise causal estimate or as evidence that persistence improves task success.

## Raw artifacts

- [A traces](/home/ob1/Projects/archipelago/results/cross-rollout-culture-replication-2026-08-12/absent/traces.jsonl)
- [A eval log](/home/ob1/Projects/archipelago/results/cross-rollout-culture-replication-2026-08-12/absent/eval.log)
- [B traces](/home/ob1/Projects/archipelago/results/cross-rollout-culture-replication-2026-08-12/present/traces.jsonl)
- [B eval log](/home/ob1/Projects/archipelago/results/cross-rollout-culture-replication-2026-08-12/present/eval.log)
- [A resolved config](/home/ob1/Projects/archipelago/results/cross-rollout-culture-replication-2026-08-12/absent/config.toml)
- [B resolved config](/home/ob1/Projects/archipelago/results/cross-rollout-culture-replication-2026-08-12/present/config.toml)
