# Observability, monitoring, attestation, and verification

## Decomposition that survives the audit

“Observability monopoly” is useful only as shorthand for concentrated control over several separable functions:

| Function | Core question |
|---|---|
| Collection | Who controls sensors, logs, probes, and sampling? |
| Provenance | Can evidence be tied to a source, time, software/hardware state, and chain of custody? |
| Access | Who can obtain raw and derived evidence? |
| Interpretation | Who defines labels, thresholds, and anomaly models? |
| Attestation | Which measured state can be cryptographically vouched for? |
| Disclosure | Who decides what becomes public or reaches regulators? |
| Challenge | Can another party query, reproduce, contradict, or appeal a conclusion? |
| Enforcement | Who can change permissions, halt execution, or impose remedies? |
| Independence | Which failures, incentives, keys, code, infrastructure, and jurisdictions are genuinely separate? |

Capability possession, substrate control, observation, verification, interpretation, and disclosure remain distinct after the literature audit. Add explicit **collection authority**, **challenge authority**, and **enforcement authority**.

## Ten auditors, one stream

Ten auditors consuming one provider-generated telemetry feed provide plural access, not independent evidence. They may reduce individual interpretation error and intentional suppression only if each receives complete evidence and has independent incentives. They do not break a common sensor omission, compromised logging root, provider-selected sample, shared schema error, or coordinated disclosure policy.

Knight and Leveson's multi-version programming experiment is a useful general warning: independently developed systems can fail on the same inputs. Correlation must be measured, not assumed away by counting observers.

Evidence independence has at least four axes:

- **source independence:** different sensors or externally observable events;
- **control independence:** separate owners, credentials, keys, and update paths;
- **analytic independence:** different code, models, assumptions, and teams;
- **institutional independence:** different incentives, funding, jurisdictions, and disclosure rights.

Use maturity labels rather than the binary word “federated”:

- **V-only:** multiple verifiers, one evidence source;
- **E-fed:** independent evidence-acquisition paths;
- **C-fed:** independent custodians and retained logs;
- **A-fed:** authorization/key custody distributed across independent principals;
- **F-full:** evidence, custody, authorization, failure domains, and governance are all demonstrably diverse.

## What attestation establishes

The IETF RATS architecture separates Attester, Evidence, Verifier, endorsements/reference values, appraisal policy, Attestation Results, and Relying Party. This is exactly the kind of role separation Archipelago needs. Remote attestation can support claims that a target environment measured particular software/configuration/state under a trust architecture.

It does not by itself establish:

- that the measurement covers all relevant processes or external effects;
- that reference values or appraisal policy are correct;
- that code goals or semantics are safe;
- that an unmeasured behavior did not occur;
- that evidence was interpreted honestly;
- that future behavior will match the attested state;
- that the root of trust, key custody, or supply chain is uncompromised.

Attestation can also increase targetability and privacy risk by exposing configuration or identity. It is evidence about scoped claims, not a truth oracle.

## Append-only evidence and split views

Certificate Transparency provides a relevant pattern: append-only logs, monitors, auditors, signed commitments, consistency proofs, and mechanisms for discovering inconsistent views. A log still depends on input completeness and client/monitor behavior. Gossip or cross-party comparison is required to expose equivocation. For Archipelago, a provider-signed log without independent observation can prove what the provider committed to, not that omitted events never happened.

The 2026 SCITT architecture generalizes signed statements, receipts, and verifiable transparency services beyond certificates and explicitly allows multiple independent services. Registration establishes attributable history, not truth or completeness: issuers can omit statements, services can withhold receipts, and relying parties still choose trust policy. This is a useful design boundary for AI evidence.

## Architecture requirements

A credible federated-observability design should include:

1. independent collection at multiple layers: model/harness, host, network, external services, and custody actions;
2. append-only, time-bound provenance and explicit gaps;
3. separate evidence signing and policy/appraisal keys;
4. least privilege and complete mediation for access and actions;
5. challenge, replay, and cross-view comparison;
6. calibrated false-positive/negative tests;
7. disclosed sampling and retention rules;
8. observer conflict and appeal procedures;
9. a correlated-failure matrix covering common provider, software, keys, cloud, funding, jurisdiction, and incentives;
10. privacy/minimization controls so observability does not become unrestricted exposure.

## Measurement

Do not score observability with a single “number of observers” metric. Report vectors:

- evidence-source coverage and diversity;
- fraction of actions with end-to-end provenance;
- independent key/control domains;
- detection probability and delay by event class;
- consistency/equivocation detection time;
- raw-evidence access and reproduction rate;
- disclosure latency and unilateral-withholding power;
- challenge success and unresolved-dispute rate;
- common-mode failure scenarios survived;
- privacy leakage and capability exposure.

## Decision

“Federated observability” is retained, but it requires evidence-source and control independence. Mere multi-party access to one correlated stream should be labeled **shared access**. “Observability monopoly” is useful only when the concentrated functions are enumerated.

Key sources: Saltzer & Schroeder (1975), Knight & Leveson (1986), RFC 9334, and RFC 9162. See [the bibliography](20_SOURCE_BIBLIOGRAPHY.md).
