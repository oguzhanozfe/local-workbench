# Optional reasoning profile

Each model profile accepts `thinking`, a strict JSON boolean that defaults to `false`. Setting it to `true` sends native Ollama `think:true` for that alias. Strings such as `"high"` and `"true"`, numbers and null are rejected. This setting depends on model support; it does not select a portable reasoning-effort level. See [Ollama's thinking contract](https://docs.ollama.com/capabilities/thinking).

`config/rtx3090.json` includes a separate `pc-reasoning` alias. In an external configuration, its model entry is:

```json
{
  "pc-reasoning": {
    "model": "qwen3.8:27b-q4_K_M",
    "num_ctx": 65536,
    "output_tokens": 8192,
    "temperature": 0.6,
    "thinking": true,
    "keep_alive": "5m"
  }
}
```

Select `pc-reasoning` explicitly in a chat or task request. The main PC aliases keep thinking disabled. Larger contexts and longer reasoning can increase memory use and request time. The PC configuration allows a 600-second provider timeout; admission checks and the single-generation queue continue to apply.

On the tested RTX 3090, one small synthetic planning problem completed correctly with thinking enabled and a 65,536-token context in 17.47 seconds. The loaded-model snapshot was entirely on GPU at 18,939,725,740 bytes. That request used a 4,096-token output budget; the configured 8,192-token allowance was not consumed or benchmarked by this test. The prompt was short, so this result does not establish long-context accuracy. [Raw reasoning smoke test](../reports/rtx3090-reasoning.json), [PC measurement notes](pc-validation.md).

The gateway returns only the provider's final `message.content`. It neither returns nor logs the separate `message.thinking` trace. Empty final answers, incomplete responses and responses stopped by the output limit remain errors; a reasoning trace cannot substitute for a final answer. JSON, citation and exact-quote validation still apply to the final answer. [Native Ollama chat response](https://docs.ollama.com/api/chat).

`/health` includes the configured `thinking` boolean in each model inventory entry, and subsequent evaluation reports retain that inventory. Older reports may omit the field. Usage values remain the provider's reported counters, so generation rates for reasoning-enabled requests should not be presented as final-answer-only throughput.
