# RTX 3090 measurements

Measured on September 10, 2026, with an RTX 3090 (24 GB VRAM), Ryzen 9 5950X, 64 GB system RAM, Windows 11, NVIDIA driver 616.64 and Ollama 0.33.3. The gateway and evaluation client ran on the Mac and reached PC loopback through SSH. The model was `qwen3.8:27b-q4_K_M`, digest `25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e`.

## Evidence task fixtures

| Context | Output budget | Thinking | Fixture checks | Median request time | Median output rate |
| ---: | ---: | --- | ---: | ---: | ---: |
| 8,192 | 768 | Disabled | 6 / 6 | 5.32 s | 40.18 tokens/s |
| 32,768 | 2,048 | Disabled | 6 / 6 | 5.35 s | 40.05 tokens/s |

Each profile ran the same six synthetic fixtures once. Five cases called Ollama; the case with no approved evidence abstained in application code. Medians cover the five model calls. Request time includes loading, prompt processing, generation and client transport; output rate uses Ollama's reported generation count and duration. These checks cover schemas, exact quotes, source IDs and fixture expectations. They do not measure general model quality.

The first 8K request took 65.84 seconds, including 35.93 seconds of reported model loading. Its four subsequent model requests took 1.56, 5.32, 6.94 and 2.25 seconds. The 32K run began with an 8.14-second request, including 5.71 seconds of loading. Cold and warm timings should remain visible when assessing interactive use.

- [8K fixture report](../reports/rtx3090-8k.json)
- [32K fixture report](../reports/rtx3090-32k.json)

The current main PC profile uses the tested 32K context and 2,048-token output budget. These fixtures contain short inputs; passing them with a larger configured context does not demonstrate accurate use of a full 32K input.

## GPU residency and reasoning

A separate Ollama `/api/ps` snapshot reported the 32K model at 17,631,102,892 bytes, entirely on GPU. During a generation, one NVIDIA sample showed 98% GPU utilization, 307.42 W, 68°C and 19,322 MiB of VRAM in use. This was an observation, not a peak-memory or sustained-load measurement. The fixture runner does not collect these GPU values automatically.

A small synthetic planning test with thinking enabled, a 65,536-token context and a 4,096-token output budget completed correctly in 17.47 seconds. Its loaded-model snapshot reported 18,939,725,740 bytes entirely on GPU. It generated a final answer and a separate reasoning trace; the published report records the presence of reasoning without including that trace. [Reasoning test and residency snapshot](../reports/rtx3090-reasoning.json).

The `pc-reasoning` alias permits 8,192 output tokens, but this smoke test used a lower budget and only a short prompt. It is not a long-context accuracy test or a guarantee about maximum memory demand. See [reasoning configuration](reasoning.md) for the response and budget rules.

## Scope

Native Windows NVIDIA inference worked for these tests, so this deployment does not require a Linux partition. These results do not compare operating systems. 
To repeat the main fixture run, use `config/rtx3090.json` with `ollama_url` set to the intended loopback endpoint and an external state directory. Run `local-workbench --config /absolute/config.json evaluate --cases fixtures/evaluation.json --hardware 'Describe the actual host' --output /absolute/path/to/a-new-report.json`. Preserve the original reports and record any changed runtime settings.

## Workflow endpoints

A CLI client, an HTTP JSON client and a RAG-to-task request also passed with the main PC model through the live gateway. Their observed times were 1.76, 1.24 and 9.32 seconds. The packets were synthetic. [Integration report](../reports/integration-rtx3090.json).

The actual Chat Completions gateway also returned the correct structured planning answer through `pc-reasoning` in 15.54 seconds. This validates the opt-in reasoning route for one short request. [Gateway reasoning report](../reports/pc-gateway-reasoning.json).

## Keep retrieval and generation resident

The final runtime allows two resident models while retaining one active generation. With a 4,096-token embedding context, the main 32K model and embedding model were both on GPU: 17,631,102,892 and 2,150,535,004 bytes respectively. The embedding model previously reserved 4,014,903,132 bytes when it inherited the server's 32K context. This request-level limit reduced its observed allocation by about 1.86 GB without changing the model tag or weights. [Combined snapshot](../reports/pc-co-residency.json).

Set `OLLAMA_MAX_LOADED_MODELS=2` before starting `ollama serve` directly; the repository's convenience server scripts default to one. Keep `OLLAMA_NUM_PARALLEL=1`, flash attention and Q8 KV cache explicit. For Evidence RAG set `OLLAMA_EMBEDDING_CONTEXT_TOKENS=4096` or its `--embedding-context-tokens 4096` CLI option. Oversized embedding inputs still fail with `truncate:false`. [Embedding-context control](https://github.com/oguzhanozfe/evidence-rag/blob/main/docs/embedding-context.md).
