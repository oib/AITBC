"""Fail-loud chain-id resolution for the agent_sdk agent-identity paths.

The converted sites used to fall back to os.getenv("CHAIN_ID",
"ait-localnet") on probe failure — signing or POSTing for a chain no node
serves. They now resolve explicit > CHAIN_ID > strict probe of the URL
the request actually goes to. Reads pass required=False and omit the
chain_id parameter when the probe fails (the node applies its own chain).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

ACCOUNT = "0x6dB6EBAda5ab0d00041FDCa3a409EE0aA15B5F2f"
PROVIDER = "0x17B9ED0c7b8b0d0B30Fa3d4BbE2F6a0Abb679d"


@pytest.fixture
def runner():
    return CliRunner()


def _failing_probe():
    prober = MagicMock()
    prober.get.side_effect = RuntimeError("connection refused")
    return patch("aitbc_cli.utils.chain_id.AITBCHTTPClient", return_value=prober)


def _ok_probe(chain_id="ait-probed"):
    prober = MagicMock()
    prober.get.return_value = {"chain_id": chain_id}
    return patch("aitbc_cli.utils.chain_id.AITBCHTTPClient", return_value=prober)


def _agent_ctx(**extra):
    return {"output_format": "table", **extra}


def _agent_patches(prober):
    config = MagicMock()
    config.blockchain_rpc_url = "http://rpc:8202"
    client = MagicMock()
    client.post.return_value = {}
    client.get.return_value = {}
    return (
        patch("aitbc_cli.commands.agent_sdk.get_config", return_value=config),
        patch("aitbc_cli.commands.agent_sdk.AITBCHTTPClient", return_value=client),
        prober,
        client,
    )


def _invoke_agent(runner, args, **obj):
    from aitbc_cli.commands.agent_sdk import agent

    return runner.invoke(agent, args, obj=_agent_ctx(**obj))


# --- agent register-identity (mutating POST /rpc/identity/register) ---


def test_register_identity_aborts_when_chain_probe_fails(runner):
    cfg_p, client_p, probe, client = _agent_patches(_failing_probe())
    with cfg_p, client_p, probe:
        result = _invoke_agent(runner, ["register-identity", "--agent-id", "a1", "--agent-address", ACCOUNT])
    assert result.exit_code != 0
    client.post.assert_not_called()


def test_register_identity_env_chain_id_wins(runner, monkeypatch):
    monkeypatch.setenv("CHAIN_ID", "env-chain")
    cfg_p, client_p, probe, client = _agent_patches(_failing_probe())
    with cfg_p, client_p, probe as prober_cls:
        result = _invoke_agent(runner, ["register-identity", "--agent-id", "a1", "--agent-address", ACCOUNT])
    assert result.exit_code == 0, result.output
    prober_cls.assert_not_called()
    assert client.post.call_args.kwargs["json"]["chain_id"] == "env-chain"


def test_register_identity_explicit_chain_id_wins(runner):
    cfg_p, client_p, probe, client = _agent_patches(_failing_probe())
    with cfg_p, client_p, probe as prober_cls:
        result = _invoke_agent(
            runner,
            ["register-identity", "--agent-id", "a1", "--agent-address", ACCOUNT],
            chain_id_explicit="flag-chain",
        )
    assert result.exit_code == 0, result.output
    prober_cls.assert_not_called()
    assert client.post.call_args.kwargs["json"]["chain_id"] == "flag-chain"


# --- agent verify-identity (mutating POST /rpc/identity/verify) ---


def test_verify_identity_aborts_when_chain_probe_fails(runner):
    cfg_p, client_p, probe, client = _agent_patches(_failing_probe())
    with cfg_p, client_p, probe:
        result = _invoke_agent(runner, ["verify-identity", "--agent-id", "a1", "--verifier-address", PROVIDER])
    assert result.exit_code != 0
    client.post.assert_not_called()


def test_verify_identity_env_chain_id_wins(runner, monkeypatch):
    monkeypatch.setenv("CHAIN_ID", "env-chain")
    cfg_p, client_p, probe, client = _agent_patches(_failing_probe())
    with cfg_p, client_p, probe:
        result = _invoke_agent(runner, ["verify-identity", "--agent-id", "a1", "--verifier-address", PROVIDER])
    assert result.exit_code == 0, result.output
    assert client.post.call_args.kwargs["json"]["chain_id"] == "env-chain"


# --- agent get-identity (read; omits chain_id when unresolved) ---


def test_get_identity_omits_chain_id_when_probe_fails(runner):
    cfg_p, client_p, probe, client = _agent_patches(_failing_probe())
    with cfg_p, client_p, probe:
        result = _invoke_agent(runner, ["get-identity", "--agent-id", "a1"])
    assert result.exit_code == 0, result.output
    assert client.get.call_args.args[0] == "/rpc/identity/a1"


def test_get_identity_sends_chain_id_when_probed(runner):
    cfg_p, client_p, probe, client = _agent_patches(_ok_probe("ait-probed"))
    with cfg_p, client_p, probe:
        result = _invoke_agent(runner, ["get-identity", "--agent-id", "a1"])
    assert result.exit_code == 0, result.output
    assert client.get.call_args.args[0] == "/rpc/identity/a1?chain_id=ait-probed"
