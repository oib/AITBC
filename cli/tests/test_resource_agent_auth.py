"""#2418: `resource allocate|optimize|status` can authenticate as the agent.

The coordinator-api owner check accepts an agent-session JWT whose ``agent_id``
claim matches the target agent. The CLI mints that JWT from the signing wallet
(``--wallet``, the same wallet bound by ``agent register --wallet``) via the
agent-coordinator login endpoint, then sends it as Bearer to coordinator-api.
"""

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.resource as res_mod


@pytest.fixture
def runner():
    return CliRunner()


class _AllocClient:
    def __init__(self, seen):
        self._seen = seen

    def post(self, endpoint, json=None):
        self._seen.append((endpoint, json))
        return {"allocation_id": "alloc-1", "agent_id": "agent-1", "status": "active"}


def test_allocate_uses_agent_session_token(runner, monkeypatch):
    """When the wallet login mints a token, allocate sends it to _client."""
    seen: list[tuple[str, dict | None]] = []
    monkeypatch.setattr(res_mod, "_agent_session_token", lambda *a, **k: "agent-jwt")
    monkeypatch.setattr(res_mod, "_client", lambda token=None: _AllocClient(seen) if token == "agent-jwt" else None)
    result = runner.invoke(
        res_mod.resource,
        obj={"output_format": "table"},
        args=["allocate", "--agent-id", "agent-1", "--cpu-cores", "2", "--wallet", "w1"],
    )
    assert result.exit_code == 0, result.output
    assert seen and seen[0][0] == "/v1/agent-performance/resources/allocate"


def test_allocate_without_wallet_uses_default_client(runner, monkeypatch):
    """No --wallet: no agent login attempt, default credential path."""
    called = []

    def _no_token(*a, **k):
        called.append(True)
        return None

    monkeypatch.setattr(res_mod, "_agent_session_token", _no_token)
    monkeypatch.setattr(res_mod, "_client", lambda token=None: _AllocClient([]) if token is None else None)
    result = runner.invoke(
        res_mod.resource,
        obj={"output_format": "table"},
        args=["allocate", "--agent-id", "agent-1", "--cpu-cores", "2"],
    )
    assert result.exit_code == 0, result.output
    # signing lookup still runs (returns None when no wallet configured) but
    # the request proceeds on the default credential
    assert called == [True]


def test_optimize_requires_metric_flag(runner, monkeypatch):
    """The doc gap: optimize without --current-* must fail client-side."""
    result = runner.invoke(
        res_mod.resource,
        obj={"output_format": "table"},
        args=["optimize", "--agent-id", "agent-1", "--target-metric", "latency"],
    )
    assert result.exit_code != 0
    assert "current" in result.output.lower()
