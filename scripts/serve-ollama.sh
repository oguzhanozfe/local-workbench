#!/usr/bin/env bash
set -euo pipefail

# Run Ollama in the foreground. This does not install software or open a LAN port.
OLLAMA_BIN="${OLLAMA_BIN:-ollama}"
if ! command -v "$OLLAMA_BIN" >/dev/null 2>&1; then
  echo "Ollama is missing. Install it from https://ollama.com/download or set OLLAMA_BIN." >&2
  exit 1
fi
export OLLAMA_HOST=127.0.0.1:11434
export OLLAMA_NO_CLOUD=1
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_CONTEXT_LENGTH="${OLLAMA_CONTEXT_LENGTH:-8192}"
export OLLAMA_FLASH_ATTENTION=1
export OLLAMA_KV_CACHE_TYPE=q8_0
export OLLAMA_DEBUG_LOG_REQUESTS=false

echo "Ollama: loopback port 11434, context $OLLAMA_CONTEXT_LENGTH, one generation at a time." >&2
echo "Use a second terminal to pull models; Ctrl-C stops this process." >&2
exec "$OLLAMA_BIN" serve
