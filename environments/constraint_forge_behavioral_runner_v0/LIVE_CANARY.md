# Live canary

The first real-provider qualification for Constraint Forge V0 is intentionally non-scientific.

## Gemini

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

## OpenCode Zen / Ox Alpha Free

The native Zen API is an OpenAI-compatible chat-completions gateway authenticated with
a Bearer Zen API key (from <https://opencode.ai/auth>). Verified against the live
endpoint on 2026-08-21:

- model: `x-preview-f-free` ("Ox Alpha Free"; stealth reasoning model, free tier,
  zero-retention provider)
- endpoint: `https://opencode.ai/zen/v1/` — the harness posts to the native
  `/chat/completions` path; no CLI/OAuth proxy is involved
- reasoning: interleaved, returned out-of-band in a separate `reasoning_content`
  message field (never replayed into later visible context); effort is requested via
  the standard `reasoning_effort` field with advertised levels `low|high|max`; the
  canary leaves it unset (provider default) and only raises the completion budget to
  16384 (`--max-completion-tokens`) because the Gemini-tuned 4096 cap is exhausted
  mid-reasoning (`finish_reason=length`, empty content)
- stop semantics: ordinary OpenAI `finish_reason`; anything other than `stop` aborts.
  The opencode CLI client's own unknown-stop retry logic does not apply here: the
  harness subprocess uses `AsyncOpenAI(max_retries=0)` and every runner retry budget
  is zero
- errors/rate limits: free-tier endpoints intermittently return 429/500/503 under
  load; errors are persisted per native call in the evidence bundle and abort the
  canary (never retried, because a behavioral sample may already exist upstream)

```bash
export OPENCODE_ZEN_API_KEY_X=<zen-key>
export OPENCODE_ZEN_API_KEY_Y=<zen-key>   # one account is fine; flag required
uv run python -m constraint_forge_behavioral_runner_v0.live_canary --live \
  --model x-preview-f-free \
  --base-url https://opencode.ai/zen/v1/ \
  --x-key-var OPENCODE_ZEN_API_KEY_X \
  --y-key-var OPENCODE_ZEN_API_KEY_Y \
  --allow-shared-credential \
  --max-completion-tokens 16384
```

`--allow-shared-credential` records `shared_credential: true` in the run summary; the
Gemini path keeps requiring two distinct credentials.
