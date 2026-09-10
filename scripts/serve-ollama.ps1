param([int]$ContextLength = 8192, [string]$OllamaBinary = "ollama")
$ErrorActionPreference = "Stop"

if ($ContextLength -lt 1024 -or $ContextLength -gt 32768) {
    throw "Use a context between 1024 and 32768, after checking memory on your hardware."
}
if (-not (Get-Command $OllamaBinary -ErrorAction SilentlyContinue)) {
    throw "Install Ollama from https://ollama.com/download/windows first."
}
# These environment settings apply to this terminal and the child server.
$env:OLLAMA_HOST = "127.0.0.1:11434"
$env:OLLAMA_NO_CLOUD = "1"
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_MAX_LOADED_MODELS = "1"
$env:OLLAMA_CONTEXT_LENGTH = "$ContextLength"
$env:OLLAMA_FLASH_ATTENTION = "1"
$env:OLLAMA_KV_CACHE_TYPE = "q8_0"
$env:OLLAMA_DEBUG_LOG_REQUESTS = "false"

Write-Host "Ollama: loopback port 11434, context $ContextLength, one generation at a time."
Write-Host "Quit the Ollama tray app first if it already owns this port. Ctrl-C stops this server."
& $OllamaBinary serve
exit $LASTEXITCODE
