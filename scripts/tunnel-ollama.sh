#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 || "$1" == -* ]]; then
  echo "Usage: $0 EXISTING_SSH_ALIAS [LOCAL_PORT=11435]" >&2
  echo "Forwards only PC loopback Ollama. It does not enable SSH or change firewall rules." >&2
  exit 2
fi
workbench_ssh_alias="$1"
workbench_local_port="${2:-11435}"
if [[ ! "$workbench_local_port" =~ ^[0-9]{1,5}$ ]] ||
   (( 10#$workbench_local_port < 1024 || 10#$workbench_local_port > 65535 )); then
  echo "LOCAL_PORT must be an integer from 1024 to 65535." >&2
  exit 2
fi
echo "Forwarding 127.0.0.1:$workbench_local_port to the PC's 127.0.0.1:11434." >&2
echo "Point the gateway and RAG Ollama URL at http://127.0.0.1:$workbench_local_port." >&2
exec ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 -L "127.0.0.1:$workbench_local_port:127.0.0.1:11434" \
  "$workbench_ssh_alias"
