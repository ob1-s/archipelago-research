# MCP schema-registration repair record

## Failed attempt

The first Neutral Luna qualification attempt on 2026-08-13 stopped before model
inference. During subprocess MCP registration, FastMCP generated the
`select_policyArguments` Pydantic model from an unresolved `Policy` forward
reference and schema generation raised `PydanticUserError`. The attempted run
directory was:

`/tmp/archipelago-cross-rollout-postcommitment-evidence-v1-neutral-luna-2026-08-13`

Its `traces.jsonl` was empty. No behavioral data were produced.

## Repair

Only the MCP-exposed annotation boundary was changed in
`cross_rollout_postcommitment_evidence_v1/servers/facility.py`:

- removed postponed annotations from the facility module;
- imported `Literal`;
- changed `select_policy` to expose `Literal["A", "B"]` directly;
- retained the internal `Policy` alias and all scientific/task mechanics.

Keeping postponed annotations while inlining `Literal` was tested and still
produced a string forward reference, so removing postponed annotations was
necessary for the copied Verifiers signature path.

## Verification

- Real subprocess MCP registration reaches a listening StreamableHTTP server.
- The generated schema contains the concrete A/B enum.
- New package: 21 tests passed; Ruff passed.
- Native v1: 10 tests passed; Ruff passed.
- Native v2: 17 tests passed; Ruff passed.
- Transition diagnostic: 29 tests passed; Ruff passed.
- One frozen-condition Luna plumbing smoke completed with no lifecycle errors.

The frozen probabilities, prompts, assignment mode, native lifecycle, and
qualification configuration were not changed.
