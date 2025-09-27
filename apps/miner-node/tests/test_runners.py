import asyncio
from pathlib import Path

import pytest

from aitbc_miner.runners.cli.simple import CLIRunner
from aitbc_miner.runners.python.noop import PythonNoopRunner


@pytest.mark.asyncio
async def test_python_noop_runner(tmp_path: Path):
    runner = PythonNoopRunner()
    job = {"payload": {"value": 42}}
    result = await runner.run(job, tmp_path)
    assert result.ok
    assert result.output["echo"] == job["payload"]


@pytest.mark.asyncio
async def test_cli_runner_success(tmp_path: Path):
    runner = CLIRunner()
    job = {"runner": {"command": ["echo", "hello"]}}
    result = await runner.run(job, tmp_path)
    assert result.ok
    assert result.artifacts is not None
    stdout_path = result.artifacts["stdout"]
    assert stdout_path.exists()
    assert stdout_path.read_text().strip() == "hello"


@pytest.mark.asyncio
async def test_cli_runner_invalid_command(tmp_path: Path):
    runner = CLIRunner()
    job = {"runner": {}}
    result = await runner.run(job, tmp_path)
    assert not result.ok
    assert result.output["error_code"] == "INVALID_COMMAND"
