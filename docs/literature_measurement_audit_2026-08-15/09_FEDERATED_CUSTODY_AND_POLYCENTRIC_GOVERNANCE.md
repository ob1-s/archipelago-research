# Federated custody and polycentric governance

## Comparator, not null

Credible federated human custody is a governance alternative, not a statistical control and not a deliberately weak baseline. It asks whether distributed human institutions can deliver continuity, legibility, and capture resistance without transferring high-consequence capability custody to an autonomous actor.

The relevant design families include:

- threshold cryptographic authorization;
- dual control and separation of duties;
- multi-party key/capability custody;
- independent audit and evidence collection;
- institutional checks and appeals;
- geographically and jurisdictionally diverse infrastructure;
- polycentric governance with overlapping, partly autonomous decision centers;
- emergency authority with time bounds and post hoc review.

## What the literature supports

Shamir secret sharing and threshold-scheme guidance establish that a capability can be made inaccessible to any one share-holder while remaining recoverable by a quorum. This distributes a cryptographic secret, not judgment, legitimacy, or operational security. Collusion, compromised endpoints, bad randomness, share loss, coercion, and incorrect threshold choice remain.

Saltzer and Schroeder support separation of privilege, least privilege, complete mediation, and avoidance of unnecessary common mechanisms. These principles argue for independent approval and narrow capabilities, while warning that shared mechanisms create common vulnerability.

Ostrom's polycentric work rejects both the presumption that a single center is always necessary and the presumption that polycentricity is a panacea. Multiple centers can learn, adapt, and check one another; they can also generate coordination costs, inconsistent policy, weak accountability, and free-riding.

IAEA safeguards provide a mature high-consequence comparator for evidence architecture: operator records are combined with independent measurements, inspectors, seals, cameras, unattended monitoring, environmental samples, and random or short-notice access. “Continuity of knowledge” is maintained through multiple measures rather than one telemetry stream. This remains a centrally adjudicated treaty regime with legal access and expert staffing, not proof that peer-to-peer federation is sufficient.

## Comparator architecture

A credible baseline must be stronger than “several people share a password.” At minimum:

| Property | Required implementation evidence |
|---|---|
| Authorization | threshold actions with distinct authenticated principals |
| Key/control independence | shares and signing devices in separate control domains |
| Infrastructure diversity | failure-domain and provider separation |
| Observability | independently collected and append-only evidence |
| Disclosure | more than one route to oversight/publication |
| Challenge | audit, appeal, and cross-view comparison |
| Continuity | tested succession, recovery, and quorum-loss procedures |
| Emergency response | bounded break-glass authority with mandatory trace and review |
| Anti-capture | rotation, conflict-of-interest rules, external review, and collusion tests |
| Reversibility | ability to suspend or narrow capability without irreversible transfer |

For threshold control, record `(t,n)`, distinct legal/control domains, coordinator power, share generation/rotation, quorum-loss recovery, and denial-of-service behavior. Cryptographic distribution without administrative independence should be reported as thresholded but operationally centralized.

## Failure modes

- quorum capture or cartelization;
- coercion of enough custodians;
- correlated cloud, software, vendor, or jurisdiction failure;
- slow response under fast-moving hazards;
- deadlock and denial of service;
- lowest-common-denominator policy;
- fragmented responsibility and blame shifting;
- secret evidence unavailable to challengers;
- selective disclosure and reputational incentives;
- loss of shares or institutional memory through turnover;
- emergency exceptions becoming routine;
- public observability increasing targetability or leaking capability.

These failures make federated custody a research object, not an automatic winner.

## Why “outperform” is too scalar

Compare governance regimes on a declared vector:

`G = (safety, continuity, capture resistance, auditability, response latency, reversibility, disclosure, privacy, capability exposure, jurisdictional robustness)`.

A regime dominates only if it is no worse on all priority dimensions and better on at least one, under declared scenarios. Otherwise report a Pareto frontier and value judgments. Weighting all properties into one score can conceal unacceptable catastrophic weakness.

AI capability custody faces an additional burden: even if it improves continuity or bargaining, it may reduce human revocability and create a survivable high-capability actor. Human federation may be slower or capturable, but it preserves a different distribution of agency. The comparison must include tail failure, not average convenience.

## Judgment

**ONE OF SEVERAL.** Federated human custody with genuinely independent observability is the mandatory empirical comparator and may be the strongest known alternative in some scenarios. Its dominance is unresolved. No reviewed evidence establishes that autonomous AI sovereignty outperforms it.

Key sources: Shamir (1979), NISTIR 8214, NIST SP 800-57 Part 1 Rev. 5, Saltzer & Schroeder (1975), Ostrom (2010), RFC 9334, and RFC 9162. See [the bibliography](20_SOURCE_BIBLIOGRAPHY.md).
