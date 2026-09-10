from types import SimpleNamespace

import pytest

from local_workbench import cli
from local_workbench.config import Settings


@pytest.mark.asyncio
@pytest.mark.parametrize("passed,total,expected_code", [(3, 3, 0), (2, 3, 1), (0, 3, 1)])
async def test_evaluate_exit_code_reflects_fixture_outcome(
    tmp_path, monkeypatch, passed, total, expected_code
):
    async def fake_evaluate(runtime, cases_path, hardware):
        return {"mode": "offline_cli_test", "passed": passed, "total": total}

    monkeypatch.setattr(cli, "evaluate", fake_evaluate)
    settings = Settings(
        state_dir=tmp_path / "state",
        models={"local-workbench": {"model": "fake:explicit"}},
    )
    args = SimpleNamespace(
        command="evaluate",
        cases=tmp_path / "unused.json",
        hardware=None,
        output=tmp_path / "report.json",
    )
    assert await cli.execute(args, settings) == expected_code
    assert args.output.is_file()
