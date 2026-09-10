"""Optional stdio bridge; no filesystem, shell or arbitrary network tools."""

from .contracts import TaskRequest
from .runtime import Runtime


def run(settings):
    from mcp.server import MCPServer

    server = MCPServer("Local Workbench", version="0.1.0")
    service = Runtime(settings)

    @server.tool()
    async def model_health() -> dict:
        """Inspect configured model availability."""
        return await service.health()

    @server.tool()
    async def run_task(
        kind: str, task: str, evidence: list[dict], model: str = "local-workbench"
    ) -> dict:
        """Run one bounded evidence task; results remain unreviewed drafts."""
        request = TaskRequest.model_validate(
            {"kind": kind, "task": task, "evidence": evidence, "model": model}
        )
        return await service.task(request)

    server.run(transport="stdio")
