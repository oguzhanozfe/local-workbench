# Model selection

Selection notes dated **September 10, 2026**. The target machines are an Apple M5 Pro with 24 GB unified memory and an RTX 3090 with 24 GB VRAM and 64 GB system RAM. Local fixture tests support Qwen3.5 9B as the Mac default and Qwen3.8 27B Q4_K_M as the PC default.

## Mac: leave room for the desktop

Qwen3.8 27B Q4_K_M passed the six bundled fixture checks, but the Mac run produced a median 1.80 output tokens/s and a 66.80-second median request time across the five model calls. System swap reached roughly 19 GB with other applications running. This was a single run, with different context and output lengths from the smaller-model comparison. The 27B model has been removed from the tested Mac. Its [historical report](../reports/mac-27b.json) remains available.

The replacement comparison used 8,192 context tokens, a 768-token output budget and thinking disabled:

| Model | Ollama package | Fixture checks | Median request time | Median output rate |
| --- | --- | ---: | ---: | ---: |
| Qwen3.5 9B | `qwen3.5:9b`, Q4_K_M | 6 / 6 | 4.80 s | 31.00 tokens/s |
| Gemma 4 12B | `gemma4:12b-it-q4_K_M` | 5 / 6 | 7.45 s | 22.29 tokens/s |

Each full profile was run once. Medians cover five model calls; the sixth case abstains without inference because it has no approved evidence. Gemma abstained on the decision-uncertainty fixture and its single repeat, returning no cited findings despite identifying confounding in its counterarguments. The fixture requires an answerable review with cited findings, so this was a contract failure rather than an unsupported causal claim. The repeat is excluded from the aggregate timings. These small fixture results do not establish general model superiority.

Ollama reported both models entirely on GPU in separate loaded-model snapshots: about 5.62 GB for Qwen9B and 7.83 GB for Gemma12B. Qwen9B is the current Mac default because it met all fixture checks with lower observed latency and memory use. The profile keeps the model loaded for two minutes after a request. See the [full measurement record](live-validation.md), [Qwen9B report](../reports/mac-qwen9.json) and [Gemma12B report](../reports/mac-gemma12.json).

Google reports LiveCodeBench v6 at 72.0 and GPQA Diamond at 78.8 for Gemma 4 12B. Qwen reports 65.6 and 81.7 respectively for Qwen3.5 9B, plus IFEval at 91.5. These are separate producers' evaluations, not a controlled comparison of our quantized packages. They justify testing both models; they do not establish one winner for this workflow. Both model cards list Apache 2.0. [Gemma model card](https://huggingface.co/google/gemma-4-12B), [Qwen model card](https://huggingface.co/Qwen/Qwen3.5-9B).

Ollama also lists Gemma 4 12B QAT at about 7.2 GB and an MLX package at about 7.7 GB. Those variants were not tested here. A package's download size is not its total runtime memory requirement. [Ollama Gemma tags](https://ollama.com/library/gemma4/tags).

## RTX 3090: larger model, bounded context

The main model is `qwen3.8:27b-q4_K_M`, approximately 17.7 GB. Both the 8,192-token and 32,768-token profiles passed all six synthetic fixture checks on the Windows RTX 3090. Their median request times were 5.32 and 5.35 seconds, with approximately 40 output tokens/s. A separate snapshot showed the 32K model entirely on GPU at about 17.63 GB. The current default uses 32,768 context tokens, a 2,048-token output budget and thinking disabled. [PC measurements](pc-validation.md), [Ollama Qwen tags](https://ollama.com/library/qwen3.8/tags).

The separate reasoning alias uses a 65,536-token context. One small planning test with thinking enabled completed correctly in 17.47 seconds, with a GPU-only loaded-model snapshot of about 18.94 GB. This verifies that tested request and allocation, not accuracy across a long input. The configured 8,192-token output allowance is larger than the 4,096-token budget used in that smoke test. [Reasoning profile and limits](reasoning.md).

Artificial Analysis currently places Qwen3.8 27B at the top of its 4B–40B open-model intelligence comparison in the xhigh and medium reasoning configurations. That supports its inclusion in the shortlist. It does not transfer those scores to a local Q4 package with thinking disabled and a short output budget. The official model uses Apache 2.0. [Artificial Analysis](https://artificialanalysis.ai/models/open-source/small), [Qwen model card](https://huggingface.co/Qwen/Qwen3.8-27B).

## Runtime and acceptance checks

Windows is sufficient for the current single-user setup: Ollama supports native NVIDIA acceleration and provides a standalone Windows distribution. A Linux partition is unnecessary for this deployment. Linux or WSL can be considered if a later requirement calls for vLLM, whose official GPU installation requires Linux and does not support native Windows. [Ollama on Windows](https://docs.ollama.com/windows), [vLLM requirements](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/).

For each subsequent model or runtime change, run the same synthetic task fixtures, retrieval integration and JSON-output checks. Record the model digest, quantization, runtime version, context, output budget, thinking mode, request times and memory behavior. Repeat failed cases before treating one run as a stable quality difference. Use public benchmarks to choose candidates and measured workflow results to choose the default.
