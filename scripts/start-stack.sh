#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: $0 ABSOLUTE_CORPUS_DB ABSOLUTE_GATEWAY_CONFIG [EVIDENCE_RAG_CHECKOUT]" >&2
  echo "Install both projects in their .venv directories and index a corpus first." >&2
  echo "Set LOCAL_WORKBENCH_STATE to an absolute runtime directory outside Git." >&2
  exit 2
fi
workbench_root="$(cd "$(dirname "$0")/.." && pwd)"
workbench_db="$1"
workbench_config="$2"
workbench_rag_root="${3:-$(dirname "$workbench_root")/evidence-rag}"
: "${LOCAL_WORKBENCH_STATE:?Set LOCAL_WORKBENCH_STATE to an absolute runtime directory}"
for workbench_path in "$workbench_db" "$workbench_config" "$LOCAL_WORKBENCH_STATE"; do
  if [[ "$workbench_path" != /* ]]; then
    echo "Database, configuration and state paths must be absolute." >&2
    exit 2
  fi
done
if [[ ! -f "$workbench_db" || ! -f "$workbench_config" ]]; then
  echo "The database and configuration must already exist. This launcher never ingests files." >&2
  exit 2
fi
if [[ ! -x "$workbench_rag_root/.venv/bin/evidence-rag" ||
      ! -x "$workbench_root/.venv/bin/local-workbench" ]]; then
  echo "Create .venv and pip install -e . in both project directories first." >&2
  exit 2
fi
workbench_rag_pid=""
workbench_gateway_pid=""
workbench_cleanup() {
  for workbench_child in "$workbench_rag_pid" "$workbench_gateway_pid"; do
    if [[ -n "$workbench_child" ]]; then
      kill "$workbench_child" 2>/dev/null || true
      wait "$workbench_child" 2>/dev/null || true
    fi
  done
}
trap workbench_cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

"$workbench_rag_root/.venv/bin/evidence-rag" --db "$workbench_db" \
  --ollama-url "${OLLAMA_BASE_URL:-http://127.0.0.1:11434}" \
  --chat-model "${OLLAMA_CHAT_MODEL:-qwen3.5:9b}" \
  --embedding-model "${OLLAMA_EMBEDDING_MODEL:-qwen3-embedding:0.6b}" \
  --context-tokens "${OLLAMA_CONTEXT_TOKENS:-8192}" \
  --max-output-tokens "${OLLAMA_MAX_OUTPUT_TOKENS:-768}" \
  serve --host 127.0.0.1 --port 8091 &
workbench_rag_pid=$!
"$workbench_root/.venv/bin/local-workbench" --config "$workbench_config" \
  serve --host 127.0.0.1 --port 8090 &
workbench_gateway_pid=$!
echo "Evidence API: http://127.0.0.1:8091  Gateway: http://127.0.0.1:8090" >&2
echo "Ollama must already be running. Ctrl-C stops both application services." >&2
while kill -0 "$workbench_rag_pid" 2>/dev/null &&
      kill -0 "$workbench_gateway_pid" 2>/dev/null; do
  sleep 1
done
echo "An application service exited; stopping its companion." >&2
exit 1
