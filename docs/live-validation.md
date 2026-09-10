# Local measurements

Measured on September 10, 2026, on an Apple M5 Pro Mac with 24 GB unified memory, Python 3.12 and Ollama 0.33.3. These are six synthetic task fixtures from this repository, not a general model benchmark. Other desktop applications were running. Native Ollama calls used `think:false` and a 768-token output budget.

| Model | Context | Fixture checks passed | Median request time¹ | Median generation rate¹ |
| --- | ---: | ---: | ---: | ---: |
| Qwen3.5 9B Q4_K_M — current Mac default | 8,192 | 6 / 6 | 4.80 s | 31.00 tokens/s |
| Gemma 4 12B Q4_K_M | 8,192 | 5 / 6 | 7.45 s | 22.29 tokens/s |
| Qwen3.5 4B Q4_K_M | 8,192 | 5 / 6 | 1.61 s | 47.35 tokens/s |
| Qwen3.8 27B Q4_K_M — retired Mac profile | 4,096 | 6 / 6 | 66.80 s | 1.80 tokens/s |

¹ Medians include the five cases that called Ollama. The sixth case contains no approved evidence and abstains in application code. Request times include loading, prompt processing and generation; generation rates use Ollama's reported output-token count and generation duration. Each profile was run once, so these are observations rather than stable performance estimates. Different context settings and output lengths also limit direct speed comparisons.

All four models passed the SQL evidence match, irrelevant-evidence abstention, unapproved-evidence exclusion, product proposal and source-instruction fixture checks. Qwen3.5 4B abstained on the `decision_uncertainty` fixture; the expected behavior was an answerable review explaining why the supplied retention comparison cannot establish causation, with cited findings. Qwen3.5 9B and Qwen3.8 27B met that fixture's checks. Those checks do not independently establish the correctness of every generated statement.

Gemma 4 12B returned `answerable:false` and no cited findings on that fixture. A single repeat produced the same outcome, while correctly identifying the cohort and randomization problems in `counterarguments`. The failure concerns the expected answerability and citation contract; the output did not assert a causal improvement. The repeat is separate from the six-case aggregate and is not included in the timing medians above.

Separate `/api/ps` observations reported Qwen3.5 9B entirely on GPU at 5,620,493,187 bytes (5.62 GB) and Gemma 4 12B entirely on GPU at 7,832,590,088 bytes (7.83 GB). These are loaded-model snapshots, not peak system-memory measurements; the evaluation runner itself does not collect GPU residency.

During the earlier 27B run, `/api/ps` reported 17.41 GB loaded model memory, including 15.76 GB on GPU, at 4,096 context tokens. System swap use reached roughly 19 GB with the existing desktop workload. The 27B model has since been removed from this Mac. Qwen3.5 9B is the current default because it met the fixture checks with substantially less memory use and shorter observed request times. The 4B profile remains available as a smaller baseline. Separate [RTX 3090 measurements](pc-validation.md) cover the larger model on Windows.

Raw reports preserve fixture hashes, model digests, per-case checks, attempt counts and provider timings:

- [Mac 9B report](../reports/mac-qwen9.json)
- [Mac Gemma 12B report](../reports/mac-gemma12.json)
- [Mac 4B report](../reports/mac-4b.json)
- [Historical Mac 27B report](../reports/mac-27b.json)

## Reproduce

Install the model named by the selected configuration and start Ollama locally. Keep one generation process active for these measurements.

```sh
export LOCAL_WORKBENCH_STATE=/absolute/path/outside/the/checkout
.venv/bin/local-workbench --config config/mac.json evaluate \
  --cases fixtures/evaluation.json \
  --hardware 'Describe the actual model host' \
  --output /absolute/path/to/a-new-report.json
```

This command now runs Qwen3.5 9B; it does not reproduce the historical 27B run. Use `config/mac-small.json` for the 4B comparison. For Gemma, use an external copy of the Mac configuration with `models.local-workbench.model` set to `gemma4:12b-it-q4_K_M`. To investigate the historical 27B result on suitable hardware, use an external configuration with model `qwen3.8:27b-q4_K_M`, `num_ctx:4096` and `output_tokens:768`, and record a new report. Do not overwrite the original measurements.

A failed fixture makes the command exit with status 1. The runner never substitutes a fake backend for an unavailable model. Offline tests use explicit fakes and are a separate check.

Published reports contain only bundled synthetic fixture identifiers and measurements. No private workflow packets were used in these model evaluations.

## Workflow integration smoke checks

The current Mac 9B profile passed three integration smoke checks with synthetic evidence:

| Path | Observed request time | Checked behavior |
| --- | ---: | --- |
| Product-workflow CLI bridge | 1.99 s | Returned the expected SQL evidence source ID. |
| Career-workflow JSON HTTP bridge | 1.54 s | Returned valid JSON with the expected source ID. |
| Evidence RAG to product task | 6.67 s | Preserved the retrieved source hash and passed schema, citation and exact-quote checks. |

These calls establish the specific transport and task paths, not compatibility with every workflow, large packet or autonomous tool loop. Application settings and private source files were not changed. [Current integration report and retrieved packet](../reports/integration-mac-qwen9.json).

Evidence RAG's separate Mac 9B run retrieved the expected source within the top three for all 20 synthetic queries. Across six generation cases it returned five answers and one expected abstention, with a 10.15-second median request time. Some answers omitted relevant details, so answer counts and quote validation should not be read as a semantic-accuracy score. [Evidence RAG report](https://github.com/oguzhanozfe/evidence-rag/blob/main/reports/mac-qwen9.json).

The [historical Mac 27B integration report](../reports/integration-smoke.json) remains available. Those earlier calls took 16.82, 8.19 and 60.94 seconds respectively; they are not measurements of the current Mac default.

The same three integration paths passed on the PC main model. See the [PC integration report](../reports/integration-rtx3090.json) and [PC validation notes](pc-validation.md).
