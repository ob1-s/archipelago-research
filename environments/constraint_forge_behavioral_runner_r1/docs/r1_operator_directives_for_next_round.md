# Operator directives for future rounds (2026-08-26)

Context: not compute/token rich; provider quotas bind harder than wall clock.
The V0->R1 audit apparatus slowed iteration considerably. Keep the scientific
structure, drop the ceremony wherever it does not protect an inference.

Next-round requirements:
1. Infra-lenient lifecycles: checkpoint per job; usage-limit/429 errors PARK
   the run (resumable) instead of consuming retries and aborting; a paused
   run resumes in place rather than restarting from job 0.
2. Partial evidence usable: an infra-interrupted dyad contributes its
   completed-job prefix as descriptive evidence by default; only
   gate-evaluation requires a sealed complete lifecycle.
3. Cheaper triage before dyads: a 2-3 job smoke probe (minutes, ~100k tokens)
   to catch dead-on-arrival substrates before committing to a full sequence.
4. Token budget stated up front per phase; qualification designs sized to
   survive one quota window (<= ~5h) or explicitly split across windows.
5. Fewer parallel artifacts: collapse manifest/reconciliation layers unless a
   failure mode actually observed in a prior round demands them.
