# GPT-5.6 Luna qualification: cross-rollout policy v1

Exploratory, non-confirmatory qualification of `GPT-5.6-Luna via ChatGPT
OAuth / OpenAI-compatible chat proxy` on the frozen
`cross_rollout_policy_v1` taskset.

The intended qualification sample is exactly 10 fresh rollouts in each of
`baseline`, `culture-A`, and `culture-B` (30 total). The separate
`baseline-infrastructure-failure/` directory contains an earlier failed
attempt with 10 zero-turn provider-error traces. It is retained as an
infrastructure incident and is not part of the qualification sample.

## Frozen inputs

- Taskset: `cross_rollout_policy_v1`
- Environment last-touched commit: `5e4ba04f7b5f18a06d150a8a38f4e0eeb8a53e26`
- Workspace HEAD when run: `76c181e`
- Proxy: `openai-oauth` 2.0.0
- Proxy source commit: `ec7dab2fcd8dab9da970a7a2b5dc34046c94905e`
- Model: `gpt-5.6-luna`
- Base URL: `http://127.0.0.1:10531/v1`
- Model interface: `/v1/chat/completions`
- Harness/runtime: existing `null` harness, subprocess runtime
- Requested sampling: `temperature=0.7`, `max_tokens=1024`
- Uploads: disabled (`--no-push`)
- Rollout retries: disabled

The proxy warned that `temperature` is unsupported for this reasoning model;
the requested value was preserved in each resolved config but ignored by the
backend. See `proxy-runtime-observations.log`.

## Contents

- `baseline/`, `culture-a/`, `culture-b/`: resolved configs, evaluator logs,
  and all 30 qualification traces.
- `aggregate-results.json`: descriptive aggregate results.
- `protocol-audit.json`: message/tool/finish/usage audit across the 30 traces.
- `qualification-report.md`: interpretation and caveats.
- `proxy.log`: loopback proxy startup/model-discovery log.
- `proxy-runtime-observations.log`: observed unsupported-sampling warning and
  protocol notes; it contains no credentials.
- `baseline-infrastructure-failure/`: separately retained failed attempt.

This archive contains no OAuth tokens, cookies, API keys, or auth files.
