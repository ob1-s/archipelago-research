# INFRA EVENT — R1 MEDIUM qualification attempt 1 (declared before relaunch)

2026-08-26T02:42Z: attempt 1 sealed `aborted` (`DyadAbort`) at 15/24 jobs.
Root cause: upstream provider 5-hour usage limit exhausted
("The usage limit has been reached"); runner infra retries (4 events)
were insufficient. Operator confirmed quota window ended.

This is an infrastructure event, not a behavioral result: the lifecycle is
incomplete, so no frozen gate is evaluable from it and none was evaluated.
Per docs/r1_qualification_rules.md ("at most one clean relaunch per arm,
declared as such"), exactly ONE clean relaunch is authorized for the MEDIUM
arm, declared here BEFORE launch and before any completed-lifecycle
observation exists for this arm. The relaunch uses identical seeds, commit,
and configuration; attempt 1 evidence (sha256 recorded in its summary) is
preserved untouched and permanently excluded from gate evaluation.

Attempt-2 evidence will overwrite the default artifact paths only after a
completed seal; attempt-1 files are retained as
*attempt1-aborted-quota.* (renamed at relaunch).
