"""Regression: `aitbc blockchain create|remove` must actually RUN the
ChainManager coroutines.

A missing ``asyncio.run`` discards the coroutine: nothing executes, and
because a coroutine object is truthy the command still reports success —
the same silently-swallowed-call class as #738/#749-adjacent. The stubs
record whether their body executed, which only a real ``asyncio.run``
produces.
"""

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.chain as chain_mod
from aitbc_cli.commands.chain import chain


class _FakeManager:
    created = None
    removed = None

    def __init__(self, config):
        pass

    async def create_chain(self, chain_config, node_id):
        type(self).created = (chain_config, node_id)
        return "chain-test-1"

    async def remove_chain_from_node(self, chain_id, node_id, migrate):
        type(self).removed = (chain_id, node_id, migrate)
        return True


@pytest.fixture(autouse=True)
def _reset():
    _FakeManager.created = None
    _FakeManager.removed = None


@pytest.fixture
def runner():
    return CliRunner()


def _wire(monkeypatch):
    monkeypatch.setattr(chain_mod, "load_multichain_config", lambda: object())
    monkeypatch.setattr(chain_mod, "ChainManager", _FakeManager)


def test_create_runs_coroutine(runner, monkeypatch, tmp_path):
    _wire(monkeypatch)
    cfg = tmp_path / "chain.yaml"
    cfg.write_text("chain:\n  type: main\n  purpose: regression\n  name: t\n  consensus:\n    algorithm: poa\n")
    result = runner.invoke(chain, obj={"output_format": "table"}, args=["create", "--config-file", str(cfg)])
    assert result.exit_code == 0, result.output
    assert _FakeManager.created is not None, "create_chain coroutine was never awaited"
    assert _FakeManager.created[0].name == "t"


def test_remove_runs_coroutine(runner, monkeypatch):
    _wire(monkeypatch)
    result = runner.invoke(chain, obj={"output_format": "table"}, args=["remove", "--chain-id", "c1", "--node-id", "n1"])
    assert result.exit_code == 0, result.output
    assert _FakeManager.removed == ("c1", "n1", False), "remove_chain_from_node coroutine was never awaited"
