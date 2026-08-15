# Redundant and recurrent persistence

## Historical anchor

The source-audited Archipelago distinction was:

- **redundant:** continuity because copies, machines, or state remain alive;
- **recurrent:** short-lived frontier-inference instances end while information, pattern, or state can recur and affect later instances.

This history must remain visible. It is not, however, a complete scientific ontology.

## Literature mapping

Distributed systems distinguishes mechanisms that the historical pair bundles:

| Axis | Mature terms | Question |
|---|---|---|
| Concurrent multiplicity | active replication, primary-backup, hot standby, state-machine replication | Are multiple materializations live at once? |
| Durable information | stable storage, write-ahead log, checkpoint, event history | Does information survive the specified failure? |
| Temporal reconstruction | crash recovery, checkpoint/restart, log replay, actor rehydration, workflow replay | Can a later process be causally reconstructed? |
| Coordination | consensus, total ordering, quorum, membership/reconfiguration | Do copies agree, and under which faults? |
| Failure independence | placement and correlated-failure model | Which shared causes can remove all copies? |
| Identity | physical process, logical service/actor, data lineage | What, exactly, is claimed to remain the same? |
| Organization | roles, boundaries, authority, routines, commitments, interaction topology | Does a social/organizational pattern persist? |

State-machine replication provides service continuity through multiple replicas processing ordered commands. Rollback-recovery work separates checkpoints, message logs, replay, and recovery lines. Actor and durable-workflow systems make the identity split explicit: a logical actor or workflow can persist while activations disappear. These are engineering properties with testable fault models. They are not evidence of organizational persistence.

## Orthogonal, layer-relative model

Use a vector rather than a binary:

`P = (M, D, R, C, F, I, L, O, layer)`

where:

- `M`: concurrent live multiplicity;
- `D`: durable state or history;
- `R`: temporal reinstantiation/recovery;
- `C`: coordination/consistency;
- `F`: failure-domain model and correlation;
- `I`: physical versus logical identity;
- `L`: causal lineage/provenance;
- `O`: organization-like continuity measured separately.

Examples:

| Configuration | Multiplicity | Reconstruction | What survives |
|---|---:|---:|---|
| One uninterrupted process | low | no | physical process while it remains alive |
| Single service with checkpoint/restart | low | yes | selected durable state and logical service |
| Volatile hot replicas | high | maybe | service under bounded independent crashes, not total correlated loss |
| Replicated durable service with replica recovery | high | yes | service/data under its stated quorum and storage assumptions |
| Ephemeral LLM calls reading an external ledger | low per call; possibly high at service layer | yes | whatever the ledger plus interpreter can reconstruct |

A system can therefore be redundant and recurrent at different layers. Multiple provider endpoints may be redundant for inference availability while every call is recurrent at the process layer. One database may be recurrent through backup recovery without live redundancy. A cold artifact may be durable without being a live copy.

## Organizational and ecological critique

Organizational continuity and organizational reproduction are different outcomes. Continuity asks whether a role-bearing collective remains the same organization across change; reproduction asks whether it produces a successor unit. Population ecology treats founding, survival, transformation, and mortality as population events, not as byte preservation. Routine theory further warns that an artifact is not the performed routine: ostensive understandings, concrete performances, and material artifacts interact.

Thus “lineage reproduction” should not be used for log replay unless an identifiable successor unit, parentage, and transmitted organization-level features exist. “Recurrence” can describe a temporal execution pattern without implying a recurrent organization.

## Collision failures

- Replication is not durability when all replicas share power, storage, software, or control plane.
- Failover selects an existing copy; recovery reconstructs a failed component.
- Restart is not state recovery; a supervisor can restore liveness from default state.
- A checkpoint is not exact continuation when post-checkpoint work or external effects are lost or repeated.
- Deterministic replay can reproduce outputs without preserving process identity.
- Consensus orders state but cannot survive loss of every durable copy.
- Equal bytes do not imply equal semantics under changed code, tools, policies, or environment.
- A lineage graph is provenance, not proof of organization.
- Similar patterns can recur from pretrained priors or independent rediscovery without causal inheritance.
- Custody and sovereignty concern control rights, not topology or temporal persistence.

## Measurement contract

Every persistence claim must name:

1. unit and layer;
2. failure model, including correlated failures;
3. physical and logical identity criteria;
4. live-copy count and placement;
5. durable state, checkpoint/log semantics, and state-loss window;
6. recovery latency and success distribution;
7. provenance from prior state to later behavior;
8. custody and instantiation authority;
9. organization-specific observables, if an organizational claim is made.

Useful interventions include process crash, storage loss, simultaneous replica loss, provider loss, code/schema change, state deletion, state swap, lineage shuffle, and external-side-effect replay. Report both success and loss, including tail latency.

## Decision

**MODIFY.** Preserve “redundant” and “recurrent” in historical and umbrella discussion. In scientific claims, report **concurrent replication** and the exact **temporal recovery/reconstruction** mechanism. Never infer organization, custody, or sovereignty from either.

Key sources: Lamport, Shostak & Pease (1982), Schneider (1990), Chandra & Toueg (1996), Elnozahy et al. (2002), Mohan et al. (1992), Bykov et al. (2011), and Pentland & Feldman (2008); full metadata is in [the bibliography](20_SOURCE_BIBLIOGRAPHY.md).
