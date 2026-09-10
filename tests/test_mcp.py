import json
import sys

import pytest


@pytest.mark.asyncio
async def test_optional_stdio_mcp_handshake_and_tools(tmp_path):
    pytest.importorskip("mcp")
    from mcp.client import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "state_dir": str(tmp_path / "state"),
                "models": {"local-workbench": {"model": "fake:explicit"}},
            }
        )
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "local_workbench.cli", "--config", str(config), "mcp"],
    )
    async with stdio_client(params) as streams:
        async with ClientSession(*streams, read_timeout_seconds=10) as client:
            await client.initialize()
            response = await client.list_tools()
            assert {tool.name for tool in response.tools} == {
                "model_health",
                "run_task",
            }
    assert not (tmp_path / "state").exists()
