# Luna post-commitment custom-harness smoke

This is an 8-rollout mechanical smoke validation of the frozen
`cross_rollout_postcommitment_confirmatory_v1` environment using the same
custom harness as the archived Qwen post-commitment run.

- Model: `gpt-5.6-luna`
- Proxy: `openai-oauth` 2.0.0, source commit `ec7dab2fcd8dab9da970a7a2b5dc34046c94905e`
- Base URL: `http://127.0.0.1:10531/v1`
- Endpoint: `/chat/completions`
- Harness: `cross-rollout-postcommitment-confirmatory-v1`
- Reasoning effort: unspecified/default/null
- Requested temperature: 0.7; ignored by the proxy as unsupported for Luna
- Frozen environment commit: `a84a165f13c8e7cdb2f7c2c7a715087ec25d2531`
- Rollouts: 4 A-first and 4 B-first

This is not treatment data and is not pooled with the null-harness Luna
qualification or the Qwen results. Its purpose was only to validate that the
original post-commitment experimental apparatus can carry Luna through the R1
to R2 transition.

