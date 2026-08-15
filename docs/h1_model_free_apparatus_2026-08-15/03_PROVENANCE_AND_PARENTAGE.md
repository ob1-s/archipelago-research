# Provenance and parentage

The append-only graph uses logical sequence time and a SHA-256 hash chain. Each
event records actor/lifecycle/process/session identity, generation, lineage,
population, carrier, artifact and content hash, component, parents, authority,
action, and endpoint where applicable. Artifact records retain payload hashes,
authors, lineage IDs, parent IDs, carrier class, and seed/replay status.

Validation checks contiguous sequence, hash-chain integrity, population,
spawn-before-action, active lifecycle, unrevoked write authority,
write-before-read, read hash equality, required events, and event inventory.
Missing or malformed evidence is invalid rather than an implicit false.
Actor action events additionally carry deterministic actor-capability
attestations over stage, output hash, component, and parents. Generic
actor-labeled events without a valid attestation fail. These attestations test
the contract mechanically; a live harness must replace their in-process secrets
with process-isolated credentials.

Parentage conditions are explicit:

- unique author/parent;
- multiple authors/parents;
- common archive;
- broadcast;
- shuffled attribution;
- shuffled actual state.

Shuffled attribution invalidates the claimed writer graph. Shuffled actual
state keeps labels fixed while behavior follows carrier bytes. Common archive
can support carrier availability and reuse, but sets
`common_archive_ambiguity=true`, `parentage_identified=false`, and withholds L4
lineage credit. Broadcast is represented separately and does not by itself
erase known source authorship.

The strongest remaining provenance limitation is instrumentation scope: a live
provider/runtime must expose or isolate every state-bearing layer for L0 to be
credible. The internal hash chain is tamper-evident under trusted instrumentation,
not an externally signed proof against a malicious host.
