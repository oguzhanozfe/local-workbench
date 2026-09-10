# Existing workflow integration

Local Workbench accepts the nonstream Chat Completions shape used by an external workflow's HTTP bridge. Start the gateway and select the `local-workbench` alias. These commands run from the external application's checkout; `$REPO_ROOT` is that checkout, not this project.

```sh
cd "$REPO_ROOT"
python3 tools/setup.py --non-interactive --backend http \
  --model-name local-workbench \
  --endpoint http://127.0.0.1:8090/v1/chat/completions

# After inspecting the setup preview:
python3 tools/setup.py --non-interactive --backend http \
  --model-name local-workbench \
  --endpoint http://127.0.0.1:8090/v1/chat/completions --apply

python3 run.py --config config/local.json --doctor
```

The external setup command writes its ignored local provider configuration. Credentials and machine paths belong in operator-managed configuration, outside this public repository. Explicit `http` selection avoids a provider's `auto` mode choosing another installed model client.

A one-off packet can use the existing bridge directly:

```sh
python3 "$REPO_ROOT/tools/model_bridge.py" \
  --packet /absolute/private/path/packet.json \
  --output /absolute/private/path/new-draft.md \
  http --model local-workbench \
  --endpoint http://127.0.0.1:8090/v1/chat/completions
```

These examples assume the external tools expose those flags. They do not copy or install those tools. A small synthetic packet is sufficient to check transport compatibility before sending private material.

The gateway preserves full messages. Long existing packets may exceed its conservative admission limit and receive HTTP 413. Increasing a context profile requires checking real memory use; the gateway does not truncate source material to make the request succeed.

## Retrieval and reviewed state

Transparent HTTP integration changes only inference transport. Use the separate task API when new retrieval is needed. A retrieval result cannot silently acquire authority inside an existing reviewed packet:

- Prepare or register new evidence before hashing the consuming application's packet.
- Keep source IDs, spans, revision hashes and approval status attached.
- Preserve the application's approved-claim filter, current-state checks and human review/import rules.
- Treat every model result as an unreviewed draft. Schema and citation checks do not constitute factual approval.

Local Workbench's task packet is a separate contract with its own hash. It is not an importable review for another application. Private adapters can map it to their own evidence proposal workflow; this public project does not ship adapters containing private source data or application code.

With `config/mac.json` and its 4,096-token context, request retrieval explicitly with `limit:1`:

```json
{
  "kind": "decision_review",
  "model": "local-workbench",
  "task": "Review the evidence for the release decision.",
  "retrieval": {"query": "release decision", "limit": 1, "mode": "hybrid"}
}
```

The API's generic default of five spans is intended for larger budgets. A result set that does not fit is rejected in full; no evidence disappears silently. A single large span can still exceed the Mac profile, particularly after including the task and output schema.

## PC backend

With Ollama bound to PC loopback, explicitly invoke the SSH tunnel script from the Mac. Forward a local port to PC port 11434, then set the gateway's `ollama_url` to that Mac loopback port. The workflow still talks to gateway port 8090. No existing client needs access to the raw PC endpoint.

An alternative is an explicitly selected HTTPS backend with authentication. A plain LAN HTTP address is rejected. An SSH/VPN transport does not grant a model permission to execute commands or perform external actions.
