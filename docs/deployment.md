# Mac client and RTX 3090 server

The Mac can run its own smaller model or use the PC's Ollama endpoint through SSH. Keep workflow files on the client. The gateway controls request budgets, serialization and validation.

## Backend prerequisites

Install Ollama deliberately on the chosen machine. The project was developed against Ollama 0.33.3. Linux/Windows NVIDIA use requires a supported driver and a CUDA-capable runtime; verify the current [Ollama hardware requirements](https://docs.ollama.com/gpu). Nothing in this repository installs drivers, downloads weights or configures SSH automatically.

Pull the model you intend to test:

```sh
# Current Mac default
ollama pull qwen3.5:9b

# Smaller development baseline
ollama pull qwen3.5:4b

# Explicit non-MTP quantization for the 24 GB PC profile
ollama pull qwen3.8:27b-q4_K_M
```

The Mac default in `config/mac.json` uses Qwen3.5 9B at 8,192 context tokens, a 768-token output budget and a two-minute keep-alive. Ollama reported its loaded model entirely on GPU at about 5.62 GB on the tested M5 Pro. It passed all six bundled fixture checks. The earlier 27B Mac run caused substantial memory pressure, so that model has been removed from the tested Mac. See [measurements](live-validation.md) for the comparison and its limits.

The PC's 27B Q4 artifact is approximately 18 GB. File size is not total inference memory. The tested Windows RTX 3090 passed all six fixtures at both 8,192 and 32,768 context tokens. Its current main profile uses 32,768 context tokens, a 2,048-token output budget and thinking disabled. A separate `pc-reasoning` alias enables thinking with 65,536 context tokens and an 8,192-token output budget. The PC profile allows up to 600 seconds per provider request. See [PC measurements](pc-validation.md) and [reasoning limits](reasoning.md).

Keep one active generation and inspect `ollama ps` on the actual host after a profile change. The tested 32K and 64K allocations were entirely on GPU, but short fixture inputs do not establish long-context accuracy or peak memory requirements. Keep MTP variants and further context increases in separate evaluations.

Native Windows NVIDIA support is sufficient for this setup; a Linux partition is not required. See [model selection](model-selection.md) for the runtime rationale.

Linux/macOS: use `scripts/serve-ollama.sh` after ensuring another Ollama service is not occupying the port. Windows: use `scripts/serve-ollama.ps1` from PowerShell under the intended account. These foreground scripts set loopback binding and explicit local runtime settings. Review the script before use. Flash attention and quantized KV-cache behavior depend on the selected backend.

## Connection

Configure an SSH host alias using your operating system's normal SSH client. After verifying that connection, run the tunnel script explicitly from the Mac:

```sh
./scripts/tunnel-ollama.sh YOUR_SSH_HOST_ALIAS
```

Read the script's usage for its chosen forwarding port. Configure `ollama_url` accordingly in a private copy of the gateway JSON profile. The forwarding process stays in the foreground and reports connection failure; it does not create persistent SSH keys, services or network rules.

The gateway also defaults to loopback. If it must listen elsewhere, configure `api_token_env`, supply that environment variable and put authenticated TLS in front of the listener. Do not publish an unauthenticated Ollama listener.

## Verification

1. `ollama ps`: inspect the actual loaded model and CPU/GPU split.
2. `local-workbench --config /absolute/config.json doctor`: verify the configured aliases map to installed model digests.
3. Run the synthetic evaluation set and preserve its case/model hashes and measured values.
4. Start with one workflow. Test queue contention before running several workflows at once.

The gateway's single semaphore applies to one Python process. Multiple workers, a second gateway, or other direct Ollama clients can bypass that serialization. Keep the runtime's parallel limit explicit too.

See [Ollama context settings](https://docs.ollama.com/context-length), [native chat API](https://docs.ollama.com/api/chat) and [structured output](https://docs.ollama.com/capabilities/structured-outputs) for upstream contracts.
