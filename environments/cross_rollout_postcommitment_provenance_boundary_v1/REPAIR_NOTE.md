# Provenance-boundary v1 technical repair record

`d9e6334` (`Freeze provenance boundary v1 before live inference`) is the
dedicated pre-live freeze commit for this package.  The package contents in
that commit match the archived pre-live manifest and were unchanged during
the initial live attempt.

That attempt was stopped after six raw trace records when an independent
implementation audit arrived after live inference had already begun.  The
raw archive remains quarantined at
`/tmp/archipelago-cross-rollout-postcommitment-provenance-boundary-v1-luna-2026-08-14/`;
its contents are not used by the qualification analysis.

This repair record documents only technical audit repairs made before any new
live attempt:

- assignment ledgers are written through a stable lock file and atomic,
  fsynced replacement, and an empty ledger is treated as corruption rather
  than reset;
- observed-only curve, matched-pair, and q50 sensitivity outputs are emitted
  separately from the frozen ITT endpoint;
- q50 randomization p-values are suppressed when fewer than 50% of frozen
  permutations identify both q50 values;
- the native Verifiers null-harness resume transcript contract has a direct
  model-free regression fixture;
- a persistent package hash manifest is included with the repaired freeze.

No scientific prompt, probability, q grid, assignment allocation, stopping
cap, endpoint, source condition, presentation order, or preregistered analysis
rule was changed.

The repaired package must receive its own commit before any subsequent live
model request.  The original six-record archive is not resumed or replayed;
any clean qualification archive uses a distinct output and assignment-state
path.
