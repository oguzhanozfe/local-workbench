# Local measurements

Measured on September 10, 2026, on an Apple M5 Pro Mac with 24 GB unified memory, Python 3.12 and Ollama 0.33.3. These are six synthetic task fixtures from this repository, not a general model benchmark. Other desktop applications were running.

| Model | Context | Fixture checks passed | Median request time¹ | Median generation rate¹ |
| --- | ---: | ---: | ---: | ---: |
| Qwen3.5 4B Q4_K_M | 8,192 | 5 / 6 | 1.61 s | 47.35 tokens/s |
| Qwen3.8 27B Q4_K_M | 4,096 | 6 / 6 | 66.80 s | 1.80 tokens/s |

¹ Medians include the five cases that called Ollama. The sixth case contains no approved evidence and abstains in application code. Request times include loading, prompt processing and generation; generation rates use Ollama's reported output-token count and generation duration. Each profile was run once, so these are observations rather than stable performance estimates. Different context settings and output lengths also limit direct speed comparisons.

Both models passed the SQL evidence match, irrelevant-evidence abstention, unapproved-evidence exclusion, product proposal and source-instruction fixture checks. The 4B model abstained on the decision-review fixture; the expected behavior was to explain the confounded retention comparison using its supplied evidence. The 27B model satisfied that fixture's schema, citation, quote and answerability checks. Those checks do not independently establish the correctness of every generated statement.

During the 27B run, `/api/ps` reported 17.41 GB loaded model memory, including 15.76 GB on GPU, at 4,096 context tokens. System swap use reached roughly 19 GB with the user's existing desktop workload. This Mac configuration runs the model but has substantial memory pressure and is slow for interactive work. The smaller profile remains available for short tasks. The RTX 3090 profile has not been measured on the PC.

Raw reports preserve fixture hashes, model digests, per-case checks, attempt counts and provider timings:

- [Mac 4B report](../reports/mac-4b.json)
- [Mac 27B report](../reports/mac-27b.json)

## Reproduce

Install the model named by the selected configuration and start Ollama locally. Keep one generation process active for these measurements.

```sh
export LOCAL_WORKBENCH_STATE=/absolute/path/outside/the/checkout
.venv/bin/local-workbench --config config/mac.json evaluate \
  --cases fixtures/evaluation.json \
  --hardware 'Describe the actual model host' \
  --output /absolute/path/to/a-new-report.json
```

Use `config/mac-small.json` for the 4B comparison. A failed fixture makes the command exit with status 1. The runner never substitutes a fake backend for an unavailable model. Offline tests use explicit fakes and are a separate check.

Published reports contain only bundled synthetic fixture identifiers and measurements. No private workflow packets were used in these model evaluations.

## Workflow integration smoke checks

The existing product-workflow CLI bridge and career-workflow JSON HTTP bridge both called the gateway with a synthetic SQL-evidence packet and received the expected source ID. The CLI saved an `unreviewed_draft`. A separate request retrieved an approved onboarding excerpt from Evidence RAG, froze its source hash into a task packet and returned a product proposal that passed schema, citation and exact-quote checks.

These three calls used the Mac 27B profile. Observed request times were 16.82 seconds, 8.19 seconds and 60.94 seconds. They establish these specific transport and task paths; they do not establish compatibility with every workflow, large packet or autonomous tool loop. Application settings and private source files were not changed.

[Inspect the synthetic integration results and retrieved packet](../reports/integration-smoke.json).
