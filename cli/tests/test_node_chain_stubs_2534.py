"""AUDIT-NODE-CHAIN-STUBS-1 (#2534): ``aitbc node chain start|stop`` were
stubs that printed "started/stopped successfully" without touching any
node. With no node-side lifecycle endpoint they must fail clearly —
non-zero exit and no success text.
"""

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


def test_chain_start_fails_clearly(runner):
    from aitbc_cli.commands.node import node

    result = runner.invoke(node, ["chain", "start", "--chain-id", "side-1"], obj={"output": "table"})
    assert result.exit_code != 0
    assert "started successfully" not in result.output
    assert "not implemented" in result.output


def test_chain_stop_fails_clearly(runner):
    from aitbc_cli.commands.node import node

    result = runner.invoke(node, ["chain", "stop", "--chain-id", "side-1"], obj={"output": "table"})
    assert result.exit_code != 0
    assert "stopped successfully" not in result.output
    assert "not implemented" in result.output
