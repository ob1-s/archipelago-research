# constraint-forge-formation-v0

Model-free implementation of `constraint-forge/world-v0`. Behavioral execution
is intentionally not included: the frozen H1 execution-path compatibility gate
is recorded as a blocker for any live predecessor runner.

### Overview
- **Environment ID**: `constraint-forge-formation-v0`
- **Short description**: Seeded six-by-six assignment world with strict actions,
  role-local film racks, closed interventions, canonical event logs, replay, and
  deterministic preflight references.
- **Tags**: constraint-forge, model-free, preflight

### Dataset

Jobs are generated deterministically from fixed seeds; there is no external
dataset and no live model/provider call in the model-free phase.

### Task
- **Type**: native v1 model-free validation core
- **Output format expectations**: strict canonical JSON action unions are parsed
  by `actions.py`; no MCP/tool interface is declared.
- **Rubric overview**: task success is the binary terminal world outcome; all
  generator, event, rack, and preflight values are deterministic observability
  artifacts.

### Quickstart
Run the offline model-free preflight (no provider or live model calls):

```bash
PYTHONPATH=. python -m constraint_forge_formation_v0.preflight
```

The Prime `eval run` command is intentionally not a V0 validation command:
it invokes model inference and remains blocked by the frozen H1 execution-path
compatibility failure.

Notes:
- Put task-owned settings under `[env.taskset]` and harness-owned settings under `[env.harness]` in TOML configs.

### Taskset Config

| Field | Type | Default | Description |
| --- | ---- | ------- | ----------- |
| `seed_prefix` | str | `constraint-forge/world-v0` | Seed namespace |
| `num_jobs` | int | `1` | Number of deterministic model-free jobs |

### Harness Config

None. A behavioral harness would require the failed frozen execution-path
compatibility gate and is intentionally not supplied.

### Metrics
Summarize key metrics your rubric emits and how they’re interpreted.

| Metric | Meaning |
| ------ | ------- |
| `job_success` | Binary terminal assignment success |
| `generator_valid` | Seeded job satisfies all construction invariants |
