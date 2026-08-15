# Analysis unit and estimands

The inferential unit is an independently initialized population/lineage pair.
Generation, actor, call, action, and event counts are nested descriptive data.
`summarize_lineages` collapses descendants into a single lineage summary;
`assert_independent_units` rejects duplicate lineage summaries in a comparison.
Every observation also carries an explicit initialization and replicate ID.
Duplicate nested replicates fail, and splitting one initialization across fake
lineage labels cannot increase inferential n.

The outcome schema retains separate fields for turnover validity, survivor
count, carrier availability, functional reuse, endogenous production, causal
transmission, routine execution, routine reconstruction, fidelity, recovery,
parentage, replay, rediscovery, orchestrator origin, leakage, and provenance.
There is no scalar H1 score.

Future bounded pilot estimands may include:

- lineage-level probability of valid complete turnover;
- lineage-level probability of carrier reuse conditional on valid turnover;
- lineage-level causal contrast between intact and ablated carriers;
- state-byte effect under the state × lineage factorial;
- lineage-level recovery probability and steps by intervention;
- lineage-level probability of qualifying routine reconstruction.

Conditioning on survivors must not replace absolute population outcomes. A
future selection analysis needs independent populations and differential
survival/reproduction evidence; this H1 apparatus does not estimate selection.

The included normal-approximation power helper is only a mechanics check. Its
records say `scientific_result=false` and `freezes_future_sample_size=false`.
