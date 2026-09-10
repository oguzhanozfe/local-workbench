# Mac client and RTX 3090 server

Keep the workflow and private files on the Mac. The PC supplies the Ollama model endpoint. The gateway controls request budgets, serialization and validation.

## Backend prerequisites

Install Ollama deliberately on the chosen machine. The project was developed against Ollama 0.33.3. Linux/Windows NVIDIA use requires a supported driver and a CUDA-capable runtime; verify the current [Ollama hardware requirements](https://docs.ollama.com/gpu). Nothing in this repository installs drivers, downloads weights or configures SSH automatically.

Pull the model you intend to test:

```sh
# Small local development model
ollama pull qwen3.5:4b

# Explicit non-MTP quantization for the 24 GB PC profile
ollama pull qwen3.8:27b-q4_K_M
```

The 27B Q4 artifact is approximately 18 GB. File size is not total inference memory. Start at 8,192 tokens, one active request and one resident model; inspect `ollama ps` during generation. Do not label this profile GPU-resident until that check is performed on the actual PC. Keep MTP variants and larger contexts in separate evaluations.

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
4. Start with one workflow. Test queue contention before using both private workflows at once.

The gateway's single semaphore applies to one Python process. Multiple workers, a second gateway, or other direct Ollama clients can bypass that serialization. Keep the runtime's parallel limit explicit too.

See [Ollama context settings](https://docs.ollama.com/context-length), [native chat API](https://docs.ollama.com/api/chat) and [structured output](https://docs.ollama.com/capabilities/structured-outputs) for upstream contracts.
