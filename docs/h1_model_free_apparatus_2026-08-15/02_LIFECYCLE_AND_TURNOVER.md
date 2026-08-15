# Lifecycle and turnover

Each scripted actor receives deterministic but nonreused identifiers for actor,
lifecycle, process, session, and write authority. Local memory is mutable only
while its handle is active.

At turnover the engine:

1. records revocation of predecessor write authority;
2. records termination of actor/process/session state;
3. clears actor-local memory;
4. invalidates the old handle and authority;
5. creates successors with fresh namespaces;
6. exposes only declared persistent carriers.

The final validator also requires every successor actor/lifecycle/process/session/
authority namespace to be disjoint from every predecessor namespace. Reactivation
attempts are sticky audit facts: temporarily reviving a terminated handle and
terminating it again cannot erase the violation.

L0 requires requested turnover fraction 1.0, no active generation-0 handle,
empty predecessor memory, revoked authority, no forbidden carrier, and a valid
provenance graph. This proves turnover only within the instrumented apparatus;
it cannot certify opaque provider-side caches in a later live run.

The redundant fixture starts with two copies of each harness position. At 0%
turnover four actors survive; at 50%, one encoder/checker pair survives. Both
can continue, but `complete_turnover=false` and L0–L5 cross-turnover credit is
withheld. At 100% none survive and, because this control has no declared
carrier, the routine stops. This is the core separator between continuity
through surviving redundancy and reconstruction after replacement.

The hidden-leak oracle deliberately leaves forbidden session state accessible.
It can produce apparent task success, but turnover and provenance both fail.
