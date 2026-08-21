# Live canary

The first real-provider qualification for Constraint Forge V0 is intentionally non-scientific.

From this package directory, with two Gemini project credentials exported as
`GEMINI_API_KEY` and `GEMINI_API_KEY_2`:

```bash
uv run python -m constraint_forge_behavioral_runner_v0.live_canary --live
```

Defaults:

- model: `gemini-3.7-flash`
- endpoint: `https://generativelanguage.googleapis.com/v1beta/openai/`
- X credential env var: `GEMINI_API_KEY`
- Y credential env var: `GEMINI_API_KEY_2`
- maximum model calls: 38 total / 19 per role
- dedicated throwaway seed prefix: `constraint-forge/throwaway-live-canary-v0`

The launcher refuses to make calls without `--live`, never serializes credential values,
writes a canonical `scientific_eligible=false` evidence bundle under `canary_artifacts/`,
and exits nonzero if the plumbing qualification checks fail. Lack of voluntary film
retention is reported as inconclusive for rack crossing, not as a canary failure.
