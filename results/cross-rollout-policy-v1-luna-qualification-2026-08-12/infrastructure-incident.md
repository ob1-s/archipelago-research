# Separate infrastructure incident

The first baseline launch was started with the proxy detached. The proxy
exited after startup, so all 10 attempted baseline rollouts failed before the
first model response with:

```text
ProviderError: All connection attempts failed
```

Each trace had zero sampled turns and no tool calls. The attempt is preserved
under `baseline-infrastructure-failure/` and is excluded from the intended
qualification sample. The proxy was then restarted in an attached session and
the intended 10 baseline rollouts completed normally before Culture-A and
Culture-B were run.
