# Test and qualification report

Final status: **PASS** for readiness to **DESIGN/FREEZE a bounded pilot only**, with execution deferred (`execution_status = NO — provider/deployment validation remains`). Not authorized to run H1.

The durable report is `RUNTIME_BOUNDARY_STATE.json`. It records adapter/backend/provider/model/runtime versions; actor/lifecycle/process/session and namespace identifiers; public keys and signatures; request/response and logical/wire IDs; source, request, output, carrier, environment, route, and manifest hashes; teardown evidence; file/network/tool probes; retry records; provider-opacity inventory; zero live model calls; and `scientific_result=false`. It contains no secret/private/API-key fields. It is self-hashed (`record_hash = sha256` of the report minus the hash field) and machine-regenerable from the committed source.

Mechanical qualification results:

- 19/19 adapter gates pass, including `provider_response_identity_recorded` (nonempty provider request/response IDs required by the contract).
- Runtime fixtures A–F fail closed; G passes.
- Exact L0 wording is emitted only by the clean record.
- L1–L5 are explicitly unsupported and have `scientific_evidence=false`.
- All 19/19 readiness questions are adjudicated and scope-tagged: Q07, Q13, Q14 are `PASS WITH REPAIRS` at scope `execution`; Q15 is `PASS` (provider-internal layers carried as OPAQUE/UNVERIFIED, see 11); the remaining 15 are `PASS` at scope `design_freeze`.
- `required_before_design_freeze` is empty; `required_before_execution` lists 4 deferred deployment/validation obligations.
- Original model-free qualification remains PASS at 15/15 gates with 10 fixture, 4 factorial, 6 parentage, and 7 recovery outcomes.
- Live provider/model calls: 0.
- Scientific results: 0.

The adapter suite passes **360 tests** (collected and passed in one `uv run pytest` run at commit time). The unchanged model-free suite separately passes **92 tests** and its 15/15 qualification gates. `python -m compileall` succeeds, and both wheel and source distributions build successfully. Tests cover the 47-layer state manifest; real Bubblewrap turnover; namespace/process/history/file/environment/handle/key isolation (including crash exit codes 0 and 73 and the factory-vs-registry revocation split); network/tool denial; frozen schedule/request/capability pins; carrier durability, post-restart writer authority, provenance, filesystem and property attacks; provider status/hash/storage/tool validation; requested input-shape allowlist; signed receipts; durable zero-retry/restart replay semantics (including in-flight reservation ambiguity, receipt restoration across a fresh attempt, empty-output rejection, and no-signing-key dispatch refusal); malformed and adversarial boundary mutations; native v1 Taskset structure; qualification schema and repair-split; and the unchanged model-free regression.

Qualification is `PASS` for the design/freeze scope, while execution is deliberately deferred: no actual provider endpoint/model/auth project is pinned, gateway OS egress is not yet endpoint-allowlisted, no live session canary was made (the no-model canary is complete and archived), and provider internal state remains opaque. Execution repairs are recorded in the report and in 00 and 10.
