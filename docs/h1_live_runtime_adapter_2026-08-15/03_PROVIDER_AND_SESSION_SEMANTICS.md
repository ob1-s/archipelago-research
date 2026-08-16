# Provider and session semantics

The package contains a real OpenAI Responses adapter, but qualification invoked only the scripted mechanical backend. The locked qualification environment records OpenAI Python SDK 3.1.0; the workspace path audited before package sync had SDK 2.53.0. The live configuration is not yet pinned or exercised.

The signed wire policy requires:

```json
{
  "store": false,
  "previous_response_id": null,
  "conversation": null,
  "tools": [],
  "background": false,
  "stream": false,
  "include": [],
  "max_retries": 0
}
```

`model`, HTTPS `base_url`, full ordered input, instructions, logical attempt ID, frozen assignment hash, and exact common-prior hashes are also signed. A durable public schedule contract pins the provider policy/common priors, gateway public key, actor specs, assignment/request hashes, and per-assignment carrier capability hashes. The gateway additionally pins the exact request hash predeclared for that attempt, so pairing a known assignment hash with altered input is rejected. The adapter omits provider continuation identifiers from the request, supplies a distinct `X-Client-Request-Id` per wire attempt, and accepts only a completed response with no error/incomplete details, no continuation/conversation, no tool output, the pinned reported model, a nonempty response-body ID, and valid request/output hashes. The server `x-request-id` is captured when returned; the future live canary must require and confirm it on the frozen endpoint rather than pretending the no-model backend observed one.

After response validation, the gateway signs a receipt binding its pinned public key, gateway/logical-attempt identity, assignment and request hashes, response/request IDs, and output hash. The actor receives only the public-key pin, verifies the receipt, and then signs a response-acceptance action; the receipt private key remains gateway-only. The attempt ledger durably pins the receipt gateway ID/public key; restart replay validates the old receipt, while a new dispatch requires the same externally retained private key. This blocks controller-injected output through the qualified protocol; it does not claim resistance to a malicious host that replaces the trusted gateway or actor binary.

OpenAI distinguishes the server `x-request-id` from the caller-supplied `X-Client-Request-Id`; both are audit/correlation identifiers, not scientific-unit IDs or an idempotency guarantee. See [API request IDs](https://platform.openai.com/docs/api-reference/backward-compatibility).

OpenAI documents manual message management as independent requests, while `previous_response_id` and the Conversations API preserve state across calls. It also documents `store=false` as disabling the ordinary stored Response-object behavior. Those are contract/documentation facts, not proof that abuse-monitoring logs, prompt caches, routing state, or other provider infrastructure is empty. See [Conversation state](https://developers.openai.com/api/docs/guides/conversation-state) and [Data controls](https://developers.openai.com/api/docs/guides/your-data#default-usage-policies-by-endpoint).

The current SDK Response object does not expose a `store` response field. Accordingly, the record distinguishes `store_requested=false` from `provider_storage_observed`, which is `null` for the real adapter. It never hard-codes the request flag as proof of provider-internal deletion.

No encrypted reasoning/native provider state is carried forward. That is deliberate: provider-managed or manually replayed hidden reasoning continuation is outside this L0 boundary. A later pilot design may use only model output that is explicitly written into a declared carrier; it may not smuggle provider session state around turnover.
