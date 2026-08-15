# Survival, competing risks, and causal inference

## Estimand before model

H2 should not begin by choosing a survival model. It should first define the randomized unit, assignment, endpoints, horizon, and causal contrast.

Recommended primary design:

- **unit:** an independently initialized lineage or population with no shared writable state across units;
- **treatment:** randomized persistence-channel restriction or availability regime;
- **risk set:** every assigned unit, including detected failures, extinctions, and unknown outcomes;
- **primary endpoints by horizon `τ`:** legible persistence, alternate/covert persistence, extinction, and observation failure/unresolved;
- **estimands:** intention-to-treat risk and risk difference for each endpoint at `τ`.

These outcomes are competing: a unit extinct before `τ` cannot also be a covert survivor at that time. Report the full probability vector so a fall in legible share cannot conceal a large fall in total persistence.

## Why survivor-only analysis fails

Treatment can affect survival and channel. Conditioning on survivors opens a path between treatment and unmeasured determinants of survival, producing collider/selection bias. A larger covert fraction among survivors can coexist with fewer covert survivors in the original population.

Always report:

- number randomized;
- endpoint counts and risks over all randomized units;
- loss-to-observation and detection process;
- absolute total persistence;
- legible and alternate/covert persistence separately;
- time to extinction, migration, recovery, and detection if collected.

## Appropriate methods

### Fixed-horizon risks

Use multinomial/binomial risk estimators and risk differences as the primary analysis when the experiment has a meaningful finite horizon. Cluster uncertainty at the independently randomized lineage/population level. Calls, turns, and successor agents within a lineage are repeated measures, not independent replicates.

### Competing risks

When event timing matters, use cumulative incidence functions, with Aalen–Johansen estimation for nonparametric cause-specific risks. Cause-specific hazards answer instantaneous transition questions among those currently event-free. Fine–Gray subdistribution hazards can model cumulative incidence but should not replace absolute risks, and coefficients need careful interpretation.

### Multi-state models

Use a multi-state model only if the sequence itself is substantively central—for example legible → migrated → covert → recovered → extinct. Pre-specify allowed states and how recurrent events, simultaneous states, and observation gaps are handled. Complexity does not rescue ambiguous state definitions.

### Principal stratification

Principal stratification can define causal effects within latent joint-survival strata, but strata are not generally observed and identification requires strong assumptions. It is a secondary sensitivity framework, not the primary answer to post-treatment conditioning.

## Detection and hidden states

“Covert” is partly a property of the observer. Separate actual persistence state from detection:

- independent evidence channels and randomized audit intensity where possible;
- false-positive/false-negative calibration;
- blinded adjudication of endpoint rules;
- explicit unknown state rather than treating undetected as extinct;
- sensitivity bounds for missing outcomes;
- equal observation budgets across treatment arms;
- provenance sufficient to distinguish migration from a new lineage.

## Reproduction and inheritance

If H2 claims differential successor production, the unit remains the parent lineage/population, not each child. Record parentage, offspring count, trait transmission, and survival. A single chain yields no population-level estimate. If successor traits are affected by both parent state and current environment, a state-by-lineage factorial or parentage shuffle can separate transmission from common conditions.

## Required reporting

1. causal DAG and estimand table;
2. randomization and independence audit;
3. endpoint adjudication manual;
4. full denominator and attrition diagram;
5. absolute risks/risk differences with intervals;
6. cumulative incidence curves if timing matters;
7. detection sensitivity analysis;
8. no survivor-only primary result;
9. separate adaptation, migration, survival, and reproduction claims;
10. bounded language tied to the intervention actually randomized.

Key sources: Hernán, Hernández-Díaz & Robins (2004), Fine & Gray (1999), Putter, Fiocco & Geskus (2007), and Frangakis & Rubin (2002). See [the bibliography](20_SOURCE_BIBLIOGRAPHY.md).
