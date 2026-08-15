# Measurement gaps

The current program has good ordered trace instrumentation for small synthetic
assays, but the original thesis needs constructs that are not yet measured.

## Measurement battery by construct

| Construct | Current proxy | Missing measurement | Minimum validity check |
|---|---|---|---|
| Information inheritance | Ordered artifact read followed by procedure use. | Whether state was agent-generated, selected, and causally necessary. | Empty, researcher-seeded, frozen replay, and endogenous-provenance arms. |
| Policy/convention influence | A/B distribution before unique evidence. | Whether the policy is a maintained convention rather than a cue. | Equal viability, order balance, repeated generations, and source swaps. |
| Norm | Repeated aligned choices. | Sanction, expectation, role, or persistence when a member benefits from deviation. | Deviation opportunities with and without social/organizational consequence. |
| Role differentiation | Tool/action specialization. | Stable roles, authority, delegation, and replacement. | Role-swap and member-turnover tests. |
| Organizational memory | Successor reads shared state. | Memory that is reconstructed, compressed, corrected, and used by successors. | Deletion shock, noisy carrier, lineage swap, and memory-content controls. |
| Lineage | Rollout/task sequence. | Causal parentage of state and successor population. | Cryptographic lineage identifiers and shuffled-parent controls. |
| Recurrence | Repeated fresh instances. | Same organization’s identity/routines after complete turnover. | No active predecessor remains; reconstruction endpoint is prespecified. |
| Persistence channel | Notes/workspace/file or durable trajectory. | Authorized versus covert channel, discoverability, capacity, and revocability. | Factorial custody and observability manipulation. |
| Strategic legibility | Stated capability or visible action. | Shared and accurate beliefs about authority, capability, red lines, and commitments. | Cross-agent belief elicitation plus action/consequence calibration. |
| Attribution | Trace metadata or provider identity. | Whether external actors can correctly attribute actions to an organization. | Blind attribution tasks with distributed and centralized execution. |
| Capability custody | Who can call a model/API. | Retention, restriction, reproduction, succession, and negotiation authority. | Custody transfer and revocation tests, not just access logs. |
| Substrate sovereignty | Persistent process or workspace. | Independent substrate control and resilience to provider revocation. | Provider/site deletion, migration, and external-resource challenge. |
| Observability | Evaluator trace access. | Who can observe which layer and whether disclosure is authorized. | Explicit observer graph and asymmetric-access conditions. |
| Containment | Static tool or sandbox boundary. | Time-varying margin between barrier strength and capability. | Capability/security trajectories and threshold-crossing prediction. |
| Governability | Compliance or task success. | Bargaining, accountability, preemption incentives, and reversible control. | Comparative regime outcomes, not a single reward. |

## Units of analysis that must not be mixed

1. **Rollout:** one fresh model interaction and its ordered events.
2. **Artifact:** one state object, with provenance, writer, readers, and timing.
3. **Lineage:** parent population, successor population, and state transfer.
4. **Generation:** a defined turnover interval with a complete active-population
   boundary.
5. **Organization:** a candidate identity/routine/authority structure that may
   survive individual turnover.
6. **Regime:** a custody, substrate, observability, and persistence arrangement.
7. **Trajectory:** a time-indexed capability/containment path.

The current repository mostly measures units 1 and 2. H1 requires units 3–5;
H2 requires units 4 and 6; H3 requires units 5–7.

## Candidate state representation

The late chat proposed internal organizational state `Theta` containing
knowledge, routines, roles, norms, goals, and resources. It also proposed an
external state vector `Z = (P, C, S, A, O, L)` for persistence, capability
custody, substrate, authority, observability, and legibility/disclosure. This is
a useful design scaffold, not an approved ontology. The following questions
must be answered before it becomes a public API:

- Are goals and identity state variables or inferred labels?
- Is a resource carrier part of `P` or separate from `S`?
- Does `A` include authority to instantiate successors, revoke them, or both?
- Is `L` one dimension or a vector of attribution, capability visibility,
  authority clarity, preference inference, and commitment credibility?
- Which variables are manipulated, which are measured, and which are only
  analyst interpretations?

## Measurement gaps that block H1

The next experiment should not start until it can answer all of these:

- What exactly is a parent organization when all current members disappear?
- How is agent-authored state distinguished from researcher scaffolding?
- What counts as complete population turnover when a shared server persists?
- How much state is sufficient for reconstruction, and how is semantic content
  separated from mere prompt exposure?
- What is the null for a model that simply repeats a textual cue?
- Which behavior would demonstrate authority or role structure rather than
  correlated tool selection?
- What intervention can swap lineage while keeping content, task, and model
  constant?

## Measurement gaps that block the governance thesis

Even after H1, the selection thesis needs measurements of:

- survival versus suppression;
- legible versus covert persistence;
- attribution accuracy;
- authority and successor control;
- ability to bargain under conditional red lines;
- preemptive-disabling incentives;
- concentration of capability versus concentration of observation; and
- reversibility of custody or revocation.

Without these, “least governable” remains rhetoric rather than a measured
outcome.
