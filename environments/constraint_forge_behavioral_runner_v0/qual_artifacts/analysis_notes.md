# Analysis notes — luna interleaved cohorts

2026-08-23 ~14:30 UTC — Mid-run peek authorized by experimenter (user).
Scope: sealed dyad-00/dyad-01 evidence only (both arms). Purpose:
behavioral inspection of formation events; no execution-policy decisions
pending or influenced. Run continues frozen.

2026-08-23 ~15:05 UTC — INFRASTRUCTURE INCIDENT. Upstream behind the
loopback openai-oauth proxy failed ("fetch failed") mid-pair-4 for an
estimated 10-20 min. Both dyad-004 arms exhausted infra retry budgets
and ABORTED (declared outcome class; evidence sealed: LOW job 9/24 @265
calls, MEDIUM job 10/24 @278 calls w/ 4 retries). No behavioral
content involved; no policy changed. Upstream verified recovered via
test completion before pair-5 dispatches resumed; dyad-05 both arms
continuing normally. Per-arm abort count now 1/3 toward stop rule.

2026-08-24 ~00:30 UTC — RESUME AFTER SILENT DRIVER DEATHS.
Reconstruction from sealed evidence (driver stdout was lost on kill):
pair-5 launched 19:54; LOW-5 aborted 20:05 (1 call, outage aftermath);
MEDIUM-5 completed 21:36 with 5 formations. Original driver silently
killed ~21:15 (no traceback; suspected OOM on 13GB box — unconfirmed,
dmesg silent). Supervisor restarts died silently x6. Orphaned pair-6
launchers completed anyway: both arms aborted dyad-06 at 6/24 jobs
(further upstream trouble), sealed 22:25. A surviving driver loop then
ran MEDIUM dyad-07 solo: completed 00:13, 0 formations.
ALL evidence sha256-verifies against manifests through dyad-07.

FINDING (tooling): freeze-record stop-rule text says an arm stops after
3 aborts "and none of this arm has completed"; frozen launcher code
(cohort_launcher.py:340) instead halts on a trailing streak of 3
aborted manifest entries regardless of prior completions. On resume
this hard-blocks the LOW arm (tail = aborted 4,5,6) despite its four
completions. Decision: do NOT modify frozen package mid-experiment;
LOW arm ends at 7 executed dyads under the stricter mechanical rule;
discrepancy recorded here and to be fixed only post-experiment.
MEDIUM arm continues (queue: 8-11). Pairing is now offset (LOW-i vs
MEDIUM-j no longer simultaneous); matched-plan analysis unaffected,
temporal-simultaneity caveat noted for indices >= 6.

2026-08-24 ~00:40 UTC — SIMPLIFICATION DECISION.
Killed all drivers/supervisors/launchers after reconstructing state from
sealed evidence. Findings: MEDIUM dyad-08 ABORTED at job 1/24 (18 min,
upstream trouble); its manifest row was lost in driver chaos — evidence
sealed & preserved at qual_artifacts/orphan-dyad-08-medium-aborted.json;
counted manually as abort #4 for the arm; NOT rerun (cost/risk > value
of bookkeeping symmetry). MEDIUM dyad-09 likewise aborted at 1/24
(manifest row present). Dyads 10 & 11 were killed mid-launch by the
cleanup; being resumed sequentially via --resume-crashed (the declared
mechanism), ONE dyad at a time, no concurrency, single supervisor.
LOW arm stands FINAL: completed {0,1,2,3}, aborted {4,5,6}, unexecuted
{7..11} per frozen streak-halt rule (see tooling finding above).
