# Test and qualification report

Final status: **PASS WITH REPAIRS** for readiness to **DESIGN/FREEZE a bounded pilot only**. Not authorized to run H1.

The durable report is `RUNTIME_BOUNDARY_STATE.json`. It records adapter/backend/provider/model/runtime versions; actor/lifecycle/process/session and namespace identifiers; public keys and signatures; request/response and logical/wire IDs; source, request, output, carrier, environment, route, and manifest hashes; teardown evidence; file/network/tool probes; retry records; provider-opacity inventory; zero live model calls; and `scientific_result=false`. It contains no secret/private/API-key fields.

Mechanical qualification results:

- 18/18 adapter gates pass.
- Runtime fixtures A–F fail closed; G passes.
- Exact L0 wording is emitted only by the clean record.
- L1–L5 are explicitly unsupported and have `scientific_evidence=false`.
- 19/19 readiness questions are adjudicated; Q07, Q13, Q14, and Q15 require repairs.
- Original model-free qualification remains PASS at 15/15 gates with 10 fixture, 4 factorial, 6 parentage, and 7 recovery outcomes.
- Live provider/model calls: 0.
- Scientific results: 0.

The adapter suite passes **340 tests**. The unchanged model-free suite separately passes **92 tests** and its 15/15 qualification gates. `python -m compileall` succeeds, and both wheel and source distributions build successfully. Tests cover the 47-layer state manifest; real Bubblewrap turnover; namespace/process/history/file/environment/handle/key isolation; network/tool denial; frozen schedule/request/capability pins; carrier durability, post-restart writer authority, provenance, filesystem and property attacks; provider status/hash/storage/tool validation; signed receipts; durable zero-retry/restart replay semantics; malformed and adversarial boundary mutations; native v1 Taskset structure; qualification schema; and the unchanged model-free regression.

Qualification is intentionally `PASS WITH REPAIRS`, not `PASS`: no actual provider endpoint/model/auth project is pinned, gateway OS egress is not yet endpoint-allowlisted, no live session canary was made, and provider internal state remains opaque.
