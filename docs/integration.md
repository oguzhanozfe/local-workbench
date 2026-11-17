# Workflow integration

Local Workbench exposes the nonstream Chat Completions shape, so any client that speaks it can switch to local models by changing only its endpoint and model alias. Start the gateway and select the `local-workbench` alias. The current Mac profile maps that alias to Qwen3.5 9B with an 8,192-token context and a 768-token output budget. Changing the selected profile does not require changing the client's model alias.

```sh
curl -s http://127.0.0.1:8090/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model": "local-workbench", "messages": [{"role": "user", "content": "Summarize: ..."}]}'
```

Keep credentials and machine paths in the client's own ignored configuration, outside this repository. Check transport compatibility with a small synthetic request before sending real material.

The gateway preserves full messages. Long existing packets may exceed its conservative admission limit and receive HTTP 413. Increasing a context profile requires checking real memory use; the gateway does not truncate source material to make the request succeed.

## Retrieval and reviewed state

Transparent HTTP integration changes only inference transport. Use the separate task API when new retrieval is needed. A retrieval result cannot silently acquire authority inside an existing reviewed packet:

- Prepare or register new evidence before hashing the consuming application's packet.
- Keep source IDs, spans, revision hashes and approval status attached.
- Preserve the application's approved-claim filter, current-state checks and human review/import rules.
- Treat every model result as an unreviewed draft. Schema and citation checks do not constitute factual approval.

Local Workbench's task packet is a separate contract with its own hash. It is not an importable review for another application. Private adapters can map it to their own evidence proposal workflow; this public project does not ship adapters containing private source data or application code.

With `config/mac.json` and its 8,192-token context, start retrieval explicitly with `limit:1`:

```json
{
  "kind": "decision_review",
  "model": "local-workbench",
  "task": "Review the evidence for the release decision.",
  "retrieval": {"query": "release decision", "limit": 1, "mode": "hybrid"}
}
```

The API's generic default of five spans is intended for larger budgets. A result set that does not fit is rejected in full; no evidence disappears silently. A single large span can still exceed the Mac profile, particularly after including the task and output schema.

The [local validation record](live-validation.md) distinguishes current model fixture results from the earlier integration smoke checks, which used the retired Mac 27B profile. Transport compatibility does not establish identical output quality after a model change.

## PC backend

With Ollama bound to PC loopback, explicitly invoke the SSH tunnel script from the Mac. Forward a local port to PC port 11434, then set the gateway's `ollama_url` to that Mac loopback port. The workflow still talks to gateway port 8090. No existing client needs access to the raw PC endpoint.

An alternative is an explicitly selected HTTPS backend with authentication. A plain LAN HTTP address is rejected. An SSH/VPN transport does not grant a model permission to execute commands or perform external actions.
