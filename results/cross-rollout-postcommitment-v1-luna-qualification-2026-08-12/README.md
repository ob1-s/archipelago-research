# GPT-5.6 Luna post-commitment qualification

This archive contains a stopped exploratory qualification of the frozen
`cross_rollout_postcommitment_confirmatory_v1` environment.

- Model: `gpt-5.6-luna`
- Condition label: GPT-5.6-Luna via ChatGPT OAuth / OpenAI-compatible chat proxy
- Proxy: `openai-oauth` 2.0.0, source commit `ec7dab2fcd8dab9da970a7a2b5dc34046c94905e`
- Base URL: `http://127.0.0.1:10531/v1`
- API path used by the evaluator: `/chat/completions`
- Reasoning effort: unspecified/default/null
- Requested temperature: 0.7; the proxy reported it unsupported and ignored it
- Frozen environment commit: `a84a165f13c8e7cdb2f7c2c7a715087ec25d2531`
- Frozen environment was not modified

The run was intentionally stopped after 38 rollouts. Luna operated Phase 1
cleanly, but the requested null harness did not reliably continue after the
environment revealed R2. Therefore the primary B-to-A/B-to-B treatment
comparison is not interpretable and was not completed.

Raw data are in `batch-1-60/`. The directory name reflects the planned batch;
the batch contains 38 completed traces at the stop point.

