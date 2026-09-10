# Local Workbench

A local inference gateway and task runner for evidence-based workflows. It maps model aliases to Ollama profiles, limits concurrent generation and validates structured output. Request measurements exclude prompts and responses.

Existing clients connect through Chat Completions. A separate task API prepares immutable evidence packets for product briefs, requirement matching and decision review. Results include citations and remain unreviewed drafts.

## Run

Requires Python 3.10+ and a running Ollama installation. The tested environment uses Python 3.12. Install in a virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'

# Choose an absolute state directory outside this public checkout.
export LOCAL_WORKBENCH_STATE=/absolute/path/to/local-workbench-state
.venv/bin/local-workbench --config config/mac.json doctor
.venv/bin/local-workbench --config config/mac.json serve
```

The server listens on `127.0.0.1:8090`. `config/mac.json` selects `qwen3.5:9b` with an 8,192-token context, a 768-token output budget and a two-minute keep-alive. Install it with `ollama pull qwen3.5:9b`. On the tested 24 GB M5 Pro, this model passed all six synthetic fixture checks at a median 4.80 seconds per model request and 31.00 output tokens/s. It replaces the 27B Mac profile, which caused substantial memory pressure. These are local workflow measurements, not general quality scores; see [live validation](docs/live-validation.md) and [model selection](docs/model-selection.md). `config/mac-small.json` retains the 4B baseline.

Model downloads, Ollama startup and profile selection are manual. Keep private configuration outside the checkout and use `LOCAL_WORKBENCH_CONFIG` to select its location.

Run the synthetic example:

```sh
.venv/bin/local-workbench --config config/mac.json run \
  --input fixtures/product-brief.json
```

The [stack launcher](scripts/start-stack.sh) runs the gateway alongside [Evidence RAG](https://github.com/oguzhanozfe/evidence-rag). Install both projects locally and ingest the corpus explicitly.

## API

| Endpoint | Behavior |
| --- | --- |
| `GET /health` | Provider reachability, installed model digests and queue state. |
| `GET /v1/models` | Configured public aliases. |
| `POST /v1/chat/completions` | Nonstream text messages forwarded to an Ollama model profile. |
| `POST /v1/tasks` | Prepare an evidence packet, run a bounded task and validate the result. |

```sh
curl http://127.0.0.1:8090/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"local-workbench","stream":false,"messages":[{"role":"user","content":"Return a JSON object with ready set to true."}],"response_format":{"type":"json_object"}}'
```

The chat route preserves message contents and order without adding retrieval, a system prompt or tool execution. It accepts text messages with `system`, `user` and `assistant` roles. Streaming, vision, tool-call messages and other unsupported fields return validation errors.

`response_format` accepts `text`, `json_object`, or `json_schema` with a `json_schema.schema` object. The supported JSON Schema subset includes object, array and value constraints, plus acyclic document-local `#/$defs/` references. External or recursive references, `$id`, dynamic references and regular-expression constraints are rejected before inference. Size and nesting are bounded, and reference resolution cannot fetch network resources.

Native Ollama calls set `stream:false`, context, completion budget and temperature explicitly. The per-model `thinking` boolean defaults to `false`; an [explicit reasoning alias](docs/reasoning.md) can enable it. The gateway returns final content and excludes the separate thinking trace from responses and logs. `max_tokens` or `max_completion_tokens` can lower the profile's completion budget. Exhausted budgets and malformed responses return errors. The optional `gateway_strip_json_fence` setting removes one complete Markdown JSON fence before parsing, without a model rewrite.

## Evidence tasks

`product_brief`, `evidence_match` and `decision_review` have separate small output schemas. Facts, matches and findings cite evidence IDs and include exact quotes. Product proposals and decision assessments are labeled as unreviewed suggestions.

```json
{
  "kind": "evidence_match",
  "model": "local-workbench",
  "task": "Find evidence for SQL analysis. Identify missing Kubernetes experience.",
  "evidence": [
    {
      "id": "claim.sql",
      "text": "The fictional candidate wrote SQL queries for a tutorial funnel.",
      "approved": true,
      "status": "current"
    }
  ]
}
```

Only current evidence with explicit `approved:true` enters a packet; omitted approval defaults to false. An empty approved set returns an abstention without calling the model. For nonempty evidence, checks validate the schema, citation IDs and exact quotes. Relevance and interpretation still require review, so `factual_review` remains `pending` after validation.

An optional `retrieval` object supplies `query`, `limit` and `mode` (`lexical` or `hybrid`). Before creating the packet, the task runner queries the configured Evidence RAG service with `approved_only:true` and `statuses:["current"]`. The returned packet preserves its exact spans and source hashes. The model has no search or tool loop, and the chat route never adds retrieval.

For the Mac's 8,192-token profile, start with `"retrieval":{"query":"Your evidence question","limit":1,"mode":"hybrid"}` and increase the limit only after checking packet size. The API default of five spans can exceed this profile's conservative budget. Even one long span may be rejected. Use a shorter span or narrower task, or validate a larger model context; the gateway never silently drops retrieved sources.

The response includes `packet`, `packet_id`, `packet_sha256`, result, validation status and actual provider attempts. Save it to retain the evidence used. A repair keeps the original packet unchanged and appends the failed output with a correction request. Configuration allows zero to two repairs, with one by default. Exhausted budgets or invalid output return errors.

## Context and queue limits

Each model alias has a context and output budget. Admission estimates an upper token bound from UTF-8 bytes and per-message overhead, reserving space for completion. This can reject prompts that a model-specific tokenizer would fit. Packets are never silently truncated. Ollama's token counts are recorded separately as measured usage.

Each process runs one generation at a time. The default queue holds four waiting requests for up to 20 seconds; a full queue or expired wait returns HTTP 429. Use one server process per shared GPU because each Uvicorn worker has its own queue. Provider calls have a separate timeout. RAG requests are bounded and do not occupy a generation slot.

`config/rtx3090.json` uses Qwen3.8 27B Q4_K_M at 32,768 context tokens and a 2,048-token output budget, with one active generation. On the tested Windows RTX 3090, this profile passed all six fixtures at a median 5.35 seconds per model request and 40.05 output tokens/s; a separate snapshot showed the model entirely on GPU. The optional `pc-reasoning` alias uses 65,536 context tokens with thinking enabled. These context settings have not been validated with long-input accuracy tests. See [PC measurements](docs/pc-validation.md), [reasoning profiles](docs/reasoning.md) and [deployment](docs/deployment.md).

## Integration and privacy

[Existing workflow integration](docs/integration.md) covers HTTP bridge configuration and packet boundaries. Run the gateway on the Mac and connect to Ollama on the PC through an explicitly started SSH tunnel. The [Ollama launch scripts](scripts/serve-ollama.sh), also available in [PowerShell](scripts/serve-ollama.ps1), bind the backend to loopback.

Metrics are written to `requests.jsonl` in the configured external state directory. They include request IDs, input hashes, model aliases, durations, status codes, attempt counts and available provider token/timing values. They omit prompts, responses, credentials and source paths. HTTP access logs are disabled. Saved task responses contain evidence and need the same privacy protections as the input corpus.

The listener and upstream default to loopback. Other upstreams require an explicit HTTPS URL and `allow_remote:true`. Set `api_token_env` for gateway bearer authentication and `ollama_token_env` for an upstream token; both name environment variables, not token values. Serving beyond loopback requires gateway authentication and a separate TLS boundary. The API exposes no shell, browser, arbitrary URL or model-controlled tool execution.

## Evaluation

Offline tests use a fake HTTP backend. They cover exact prompt forwarding, context rejection, malformed output, bounded repair, unsupported citations/quotes, approved-evidence filtering, retrieval provenance, timeouts, queue limits and request/schema validation.

```sh
.venv/bin/python -m pytest -q
.venv/bin/local-workbench --config config/mac.json evaluate \
  --cases fixtures/evaluation.json \
  --hardware 'Describe the machine actually running Ollama' \
  --output /absolute/path/to/new-evaluation.json
```

Live evaluation requires reachable Ollama and installed configured models. It records full model digests, case hashes, latency, provider token/timing fields and fixture expectations, and exits nonzero if a fixture fails. The operator supplies the hardware description; the runner does not measure GPU residency or fill in missing metrics. Results apply to the synthetic fixtures and do not establish general model quality.

## Optional MCP

Install `pip install -e '.[mcp]'`, then run `local-workbench --config /absolute/config.json mcp` for stdio tools `run_task` and `model_health`. The adapter uses the MCP Python SDK v2.2 interface and the same bounded task contracts. It has no filesystem or command tools.

## Development

Code in `src/local_workbench/` covers configuration, API contracts, Ollama transport, admission control, task validation, FastAPI routes, CLI and live evaluation. Install `requirements.lock` before an editable install to reproduce the tested dependency set. Fixtures are synthetic and contain no private career or product data.

MIT licensed. Copyright 2026 Oğuzhan Özdemir.
