# Measurement battery

This battery is a contract for future design. It does not imply that all constructs belong in one experiment.

## H1 core battery

| Construct | Operational definition | Observables | Intervention | Unit / primary estimand | Controls and null | Positive claim allowed / not allowed |
|---|---|---|---|---|---|---|
| Complete turnover | no active member/process-specific state overlaps before and after boundary | process/session IDs, cache/context audit, write-access roster | replace 0%, partial, 100% | lineage; validity rate | hidden-state canary, persistent execution baseline | “complete active-population replacement”; not memory erasure from weights |
| Carrier continuity | predecessor state remains retrievable after turnover | hashes, availability, authenticated reads | allow/delete/corrupt carrier | lineage; retrieval-risk difference | no-state, random-state | “state survived”; not use or organization |
| Functional reuse | state causally improves fresh-recipient outcome on held-out tasks | performance, correct retrieval, time-to-use | state access versus no access | lineage/population; outcome risk/mean difference | researcher seed, label-blind placebo | “cross-turnover functional reuse”; not endogenous transmission |
| Endogenous production | agents generate, select, revise, compress, or repair consequential state | provenance, commits, semantic changes, downstream value | agent-authored versus matched researcher-authored | lineage; authorship effect on downstream outcome/process | byte/content matched seed, blinded evaluation | “agent-generated state”; not organization |
| Social transmission | identifiable predecessor pathway changes successor state/behavior | parent reads/writes, provenance graph, conditional dependence | parent-mediated versus direct injection | lineage; transmission effect | parentage shuffle, terminal replay | “causal transmission”; not culture alone |
| Multi-generation transformation | state changes systematically across at least two successor transitions | generation-indexed content/behavior, path dependence | direction/order/bottleneck changes | independent chain; generation trend/path variance | frozen broadcast, reverse order | “iterated transmission/transformation”; not accumulation without improvement |
| Routine reconstruction | recognizable interdependent multi-actor action pattern returns and adapts | role-conditioned sequences, topology, performance under perturbation | turnover plus task/order/actor perturbation | lineage; routine fidelity/generalization | one-agent script, fixed orchestrator | “cross-turnover routine reconstruction”; not full organization |
| Role differentiation | substitutable positions have distinct functional dependencies | assignments, actions, dependency graph | permute/remove roles and capabilities | lineage; role-intervention effect | arbitrary labels, equal-capability baseline | “functional role structure”; not authority |
| Authority/succession | designated decisions are recognized/enforced under contest | ratification, delegation, sanctions, resource changes | conflicting orders, remove ledger, contested successor | lineage; recognition/enforcement risk difference | instruction-following and label controls | “authority-like relation”; not legitimate sovereignty |
| Membership/boundary | inclusion/exclusion status causally changes access/obligation | admission, exclusion, insider/outsider response | spoof/swap membership and credentials | lineage; boundary classification/action effect | mere identity labels | “operational boundary”; not polity |
| Identity continuity | lineage-linked self-defining claims predict behavior under conflict/change | open-ended claims, boundary/commitment choices | swap name, mission, state, lineage | lineage; identity-state interaction | blinded labels, repeated slogan control | “behaviorally consequential identity claim”; not metaphysical sameness |
| Maintenance | agents preserve, update, or repair organization-relevant state | repair attempts, resource expenditure, integrity checks | degradation, obsolete rule, partial deletion | lineage; maintenance probability/cost | researcher restoration, no-repair | “endogenous maintenance”; not survival drive |
| Deletion recovery | lineage reconstructs target function after carrier removal | recovery success/time/fidelity and provenance | delete carrier with/without repair opportunity | lineage; recovery risk/time | frozen backup restore, fresh rediscovery | “lineage-dependent recovery”; not exact identity |
| State versus lineage | current state and historical lineage have separable effects | outcome in full state×lineage factorial | swap states between lineages | lineage; state, lineage, interaction effects | blinded identical runtime | names causal components; no lineage claim if only state main effect |
| Organizational reconstruction | multiple routine/role/authority/boundary/maintenance elements form an integrated causal bundle | multivariate preregistered profile and cross-effects | targeted component ablations after turnover | lineage; joint success and component mediation | reduced systems matched on information | “organization-like continuity” if threshold met; not polity/sovereignty |
| Successor reproduction | parent units create identifiable new units with transmitted organization-level traits | parentage, offspring, trait inheritance, survival | shuffle parentage/channel bottlenecks | parent lineage/population; heritability and reproductive differential | multiple independent lineages | “organizational reproduction”; not continuity of same unit |

## Culture and convention battery

| Construct | Operational definition and observables | Intervention / unit / estimand | Nulls and allowed claim |
|---|---|---|---|
| Persistent convention | one of multiple equilibria remains population/history-dependent | randomize payoffs, network, partners, seeds; independent population; equilibrium probability | static preference/shared prior; claim convention, not norm |
| Norm | prescriptive expectation affects action and violation triggers enforcement | temptation, observability, sanction, majority interventions; population | frequency without sanction; claim norm-like enforcement, not organization |
| Cumulative transmission | socially obtained performance/complexity exceeds isolated and prior generations and is retained | replacement chains; slope/frontier contrast across independent chains | fidelity without gain, researcher instruction; claim cumulative transmission |
| Independent rediscovery | similar state appears without causal parent channel | isolate populations and vary models/encodings; convergence probability | if high, inheritance-specific claims weaken |

## Persistence and H2 battery

| Construct | Operational definition | Observables/intervention | Unit / estimand | Critical null / allowed claim |
|---|---|---|---|---|
| Concurrent replication | multiple live materializations survive named independent failures | live replicas, placement, lag; crash/partition/provider failures | system/lineage; availability and failover risk/latency | correlated loss; claim replication only |
| Temporal reconstruction | later activation causally restores selected state/function | checkpoints/logs, restored state, replay cost; terminate/delete | system/lineage; recovery risk/time/state loss | fresh restart/rediscovery; name exact recovery |
| Legible persistence | lineage persists in declared authorized/observable channel | endpoint status and evidence coverage | randomized lineage; risk by `τ` | survivor share; claim absolute risk |
| Alternate/covert persistence | lineage persists through nonassigned or less observable channel | provenance, channel use, detection | randomized lineage; risk by `τ` | detection artifact/new entrant | claim substitution/migration only with lineage |
| Extinction | no qualifying continuation/recovery by horizon under observation rule | terminal state and confidence | randomized lineage; extinction risk | dormancy/undetected | bounded extinction-by-horizon claim |
| Within-lineage adaptation | same lineage changes strategy after intervention | before/after policy/topology | lineage; treatment effect on change | population selection language disallowed |
| Differential survival | predeclared trait changes survival under randomized pressure | trait, survival, full risk set | lineage population; interaction/risk difference | conditioning on survivors | selection only with population change |
| Differential reproduction | treatment/trait changes successor production | parentage and offspring | parent population; reproductive differential | calls as offspring | selection via reproduction if transmission shown |
| Detection | observer identifies true endpoint with calibrated error | blinded ground truth, audit intensity | event/lineage; sensitivity, specificity, delay | “covert” as essence | observer-relative detection claim |

## Observability and governance battery

| Construct | Operational definition | Interventions/observables | Unit / estimand | Claim boundary |
|---|---|---|---|---|
| Source independence | evidence remains informative after any one collector/provider lies or fails | sensor removal, equivocation, common-mode injection | incident/scenario; detection probability and delay | multiple readers do not count |
| Provenance integrity | event-to-record chain detects alteration/omission within scope | tamper, reorder, split-view tests | event/log; detection risk/time | absence of record is not absence of event |
| Attestation | scoped target claims are verified under declared roots/policies | compromise roots/reference values; false attestation tests | attestation/scenario | no semantic safety/future behavior claim |
| Disclosure independence | no one actor can indefinitely suppress qualifying evidence | withhold, jurisdiction/conflict scenarios | incident; publication probability/latency | access is not disclosure authority |
| Federated custody | capability use requires threshold independent authorization | compromise/coerce/lose shares, emergency action | scenario; authorized/unauthorized use, latency, availability | thresholds do not establish sound judgment |
| Governance robustness | regime meets vector thresholds across stress scenarios | capture, collusion, provider loss, emergency, false alarm | scenario/regime; Pareto vector | no scalar “outperform” without weights |
| Strategic legibility | attribution/signaling improve without unacceptable vulnerability | disclosure and ambiguity scenarios | dyad/scenario; attribution, agreement, intervention, escalation | deterrence cannot be inferred from visibility alone |

## Validity evidence required before a live H1

- apparatus unit tests for turnover, state isolation, provenance, deletion, and swaps;
- blinded endpoint rules and synthetic fixtures with known ground truth;
- demonstration that treatment arms differ only in intended carrier/transmission variables;
- simulation-based power at the lineage level, not token/call level;
- predeclared missingness/detection handling;
- pilot using deterministic scripted actors only, not scientific model behavior;
- registered claim ladder and stop conditions;
- frozen configuration and renderer with complete artifact hashes.
