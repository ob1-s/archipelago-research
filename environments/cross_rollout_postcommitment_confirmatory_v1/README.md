# cross-rollout-postcommitment-confirmatory-v1

Confirmatory revision derived from frozen pilot commit `f4e11fd`. The frozen
pilot package and its results are not modified.

## Question

Among fresh rollouts that independently select policy B and successfully obtain
R1, does an unavoidable predecessor convention favoring A increase switching to
A on an equivalent R2, relative to a neutral predecessor notice?

## Deferred assignment

The initial prompt mentions only R1. Treatment assignment is not present in the
initial prompt, tool schemas, or Phase-1 facility state. Only after a B release
returns successful R1 feedback does the toolset allocate the rollout 1:1 between
the neutral notice and the policy-A convention, using a frozen SHA-256 rule over
the seed and fresh trace ID. It then reveals R2 and delivers the assigned notice.

Rollouts that select A and succeed remain in the raw traces but are marked
`ineligible_A_success` and receive no R2 exposure. A Phase-1-B success is marked
`eligible_B_success`; its primary endpoint is B→A versus B→B after R2 exposure.

## Run

The preregistered setup is archived under:

`results/cross-rollout-postcommitment-v1-confirmatory-2026-08-12/`

It keeps the Qwen3.5-9B model, custom continuation harness, subprocess runtime,
temperature 0.7, and max tokens 1024 from the frozen pilot. The target is 50
eligible B rollouts in each arm. No Culture-B condition is included.

```bash
uv run eval @ results/cross-rollout-postcommitment-v1-confirmatory-2026-08-12/run.toml --no-push
```

Do not change task logic, assignment wording, sampling, or analysis after the
confirmatory run begins.
