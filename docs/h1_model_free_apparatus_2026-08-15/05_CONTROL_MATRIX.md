# Control matrix

| Control | Behavior may succeed | Key discriminator | Maximum credited rung |
| --- | ---: | --- | --- |
| A actor-authored complete turnover | yes | full lifecycle + carrier + causal relay | L5 |
| B 0%/50% redundant survival | yes | predecessor actors survive | below L0 |
| B 100% redundant/no carrier | no | full turnover, no persistent state | L0 |
| C no state | no | carrier absent after valid turnover | L0 |
| D researcher seed | yes | writer is researcher | L2 |
| E frozen terminal replay | yes | downstream sufficiency; no arm-level production history | L2 |
| F independent rediscovery | yes | no predecessor-carrier-successor edge | L0 |
| G hidden state leak | yes | forbidden session read and surviving predecessor | invalid |
| H orchestrator | yes | intermediates originate in harness/orchestrator | L1 |

The state × lineage manifest contains A/A, A/B, B/A, and B/B. Lineage labels
and actual carrier bytes are independently assigned. Behavior follows actual
bytes; target success occurs only in the known compatibility cells A/A and B/B.

The intervention matrix contains intact state, full deletion, partial deletion,
valid-JSON corruption, deterministic random replacement, frozen backup restore,
and successor-authored reconstruction from a declared calibration seed. Backup
restore and endogenous reconstruction have different provenance and recovery
labels even when both restore fidelity.
