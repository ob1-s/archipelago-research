# Transition diagnostic

The first v3 attempt was stopped after five fresh neutral rollouts. All five
successfully obtained R1 and received the exact ordered neutral exposure plus the
first R2 reveal, but all five ended immediately without a Phase-2 policy call.

This was a harness/interaction enforcement issue, not a policy result. The five
raw traces and evaluator log are preserved under `transition-stop-diagnostic/` and
are excluded from the revised neutral persistence analysis. The revised task removes
the initial final-response cue and adds a post-success instruction to use
`select_policy` before finalizing. No condition, culture text, policy mechanics, or
R2 information horizon was changed.
