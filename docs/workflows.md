# Resumable document workflows

A long writing request can exceed a local model's output budget even when its prompt fits. A workflow divides the document into ordered stages, checks each stage, and saves progress before starting the next one. Completed stages are reused after an interruption. This is a small document runner, with no agents, shell commands or model-controlled tools.

Requires the same Python environment, configured Ollama endpoint and installed model as the gateway. The CLI calls the shared runtime directly; it does not require a running HTTP gateway. Use one active inference process for a shared GPU.

```sh
export LOCAL_WORKBENCH_STATE=/absolute/private/path/metrics
.venv/bin/local-workbench --config config/mac.json workflow \
  --recipe recipes/application-brief.json \
  --output-dir /absolute/private/path/application-trial

# Resume failed or interrupted stages with the same inputs and model profile.
.venv/bin/local-workbench --config config/mac.json workflow \
  --recipe recipes/application-brief.json \
  --output-dir /absolute/private/path/application-trial --resume
```

`recipes/mobile-gdd.json` is a three-stage mobile hybrid-casual design sketch. Both recipes use fictional evidence. Their default alias and 768-token stage budgets fit the Mac profile; select a different configured alias in your own recipe. These examples demonstrate the workflow and do not implement a complete CV or production GDD process.

On completion, open `document.md` and `report.json` in the output directory. `checkpoint.json` contains stage outputs and is saved after each attempt. A failed run exits with code 1 and reports its error and completed stages; it does not publish an incomplete document. The checkpoint retains the failed attempt's error, latency and any available token counts. Resuming reruns only unfinished stages. A completed run can also be resumed to verify its saved artifacts without generating again.

## Recipe contract

A JSON recipe contains `version: 1`, `title`, `model`, `language`, `evidence`, `stages`, and optional `repairs` (0 or 1). Each stage has:

| Field | Meaning |
| --- | --- |
| `id`, `title`, `instructions` | Stable stage ID, document heading and bounded writing request. |
| `depends_on` | IDs of earlier stages whose unreviewed output is included. |
| `evidence_ids` | Explicit selection of current evidence with `approved: true`. |
| `output_tokens` | Completion cap, no higher than the configured model profile. |
| `min_words` | Minimum whitespace-separated word count in the stage text. |
| `required_headings` | Exact Markdown heading labels required in the stage text. |

Unknown fields, forward dependencies, duplicate IDs, and missing or unapproved selected evidence are rejected. Recipes are limited to twelve stages and fifty evidence items. They cannot contain executable tools, interpolation, file includes or dynamic network destinations. Links in evidence are text and are not fetched. Previous stage output is labeled as an unreviewed draft and does not become approved evidence.

Each stage returns JSON with `text`, `used_evidence_ids`, `quotes`, `assumptions`, and `unknowns`. Checks enforce the output schema, selected citation IDs, matching used IDs and quotes, exact quote substrings, minimum length and required headings. Structured output and completion checks use the same runtime as Chat Completions. The runtime rejects tool calls, empty answers, malformed responses and exhausted completion budgets.

One repair may be requested for a schema, citation, quote, heading or minimum-length failure. Repair preserves the original evidence and stage request. Transport failures, context rejection and output truncation stop the stage immediately. A resume is an explicit new bounded attempt; there is no background retry loop.

## Integrity and limits

Resume binds the checkpoint to exact recipe bytes, evidence content, the configured model profile and the installed model digest reported by Ollama. Recipe formatting changes also require a fresh output directory. Model inventory is checked before and after generation; it is provider-reported identity, not a cryptographic proof of which weights ran.

The checkpoint is an atomic JSON envelope with an integrity hash. Completed stage inputs and outputs are hash-checked and revalidated on resume. Final artifact bytes are checked against the checkpoint; changes or deletions are rejected. An interrupted artifact-publication step can finish from its checkpoint. Process locks are released by the operating system after a process exits. POSIX and Windows locking are implemented; offline interruption tests currently run on the development platform.

Checkpoint reads and writes are limited to 8 MiB. Payload, stage and attempt fields are validated before resume; unknown fields and inconsistent state are rejected. Source quotations are rendered in literal code blocks so their Markdown headings, images and HTML remain quoted text.

Use a fresh absolute output directory. The runner refuses unrelated files and symlink paths, and replaces only files in its checkpoint format. Keep this directory private: unlike metadata-only request logs, checkpoints and documents contain model outputs and evidence quotations. Hashes detect corruption and mismatches; they do not authenticate a checkpoint against an attacker who can rewrite it and all its hashes.

Atomic writes use unique temporary files. A process crash may leave a `.workflow-*.tmp` file beside a valid checkpoint; resume preserves that file and creates a new temporary for later writes. Orphans are not automatically deleted because their ownership cannot be established after a crash. Existing hardlinked workflow files are rejected.

A quote's presence does not prove that the document interprets it correctly. Word counts do not measure completeness, and heading checks do not evaluate design quality. Cross-stage consistency, claim entailment, language quality and any application-specific policy still need review. Every artifact remains an `unreviewed_draft`, with factual review pending. The runner never treats a model's own review as approval and never submits, sends or publishes the document.

## Measured examples

These synthetic runs were recorded on 10 September 2026. All stages used a 768-token completion cap with thinking disabled. Times sum the recorded model attempts, including runtime checks around each call; they are not end-to-end CLI wall times.

| Machine and recipe | Completed stages | Attempts | Recorded attempt time |
| --- | --- | --- | --- |
| Mac M5 Pro 24 GB, Qwen3.5 9B, application brief | 2/2 | 2 | 23.78 seconds total |
| Mac M5 Pro 24 GB, Qwen3.5 9B, mobile GDD | 3/3 | 3 | 48.99 seconds total |
| Windows RTX 3090, Qwen3.8 27B, initial application brief | 0/2 | 2 on the first stage | 31.42 seconds total |
| Windows RTX 3090, Qwen3.8 27B, mobile GDD | 3/3 | 3 | 49.81 seconds total |

The [Mac application](../reports/workflow-mac-app.json) and [GDD](../reports/workflow-mac-gdd.json) reports record an 8,192-token model context. The PC reports use a `pc-draft` alias with a 65,536-token context and an 8,192-token profile maximum; each recipe stage still requested only 768 output tokens. These are short inputs and do not validate long-context accuracy.

The [initial PC application](../reports/workflow-pc-app-768-initial.json) failed the exact Markdown heading check on its first attempt and its one permitted repair. It generated 534 and 532 completion tokens, respectively, without exhausting the cap. The second stage was not run and no document was published. Failed response text is not persisted, so the precise formatting variant cannot be determined from this report. The [PC GDD](../reports/workflow-pc-gdd-768.json) passed its structural checks on all three first attempts; its design quality remains unreviewed.

The application recipe now names the literal Markdown heading lines explicitly. Earlier reports retain the original recipe and evidence hashes; the PC reports also identify the source commit. Completed structural checks do not establish that a real application or production GDD is complete or factually correct.
