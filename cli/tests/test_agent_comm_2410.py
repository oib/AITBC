"""#2410: agent-comm register/update semantics and network JSON output.

Player-filed defects:

* ``register --reputation 99`` was accepted and posted verbatim — the
  documented range is 0.0–1.0.
* A second ``register`` for an existing ``agent_id`` succeeded silently and
  rebuilt the record from the request's *defaulted* options, wiping stored
  name-adjacent metadata (reputation/version/capabilities/agent_type).
  Re-registration now requires ``--update`` and merges every optional field
  the caller did not pass from the existing registry record.
* ``network --format json`` emitted two back-to-back JSON arrays — not one
  parseable document.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


def _obj(fmt="table"):
    return {
        "config": MagicMock(coordinator_api_url="http://coord.local", agent_coordinator_url=None, api_key=None),
        "output_format": fmt,
    }


def _client(get_result=None, get_exc=None, agents=None):
    """AITBCHTTPClient double for the register/network paths."""
    client = MagicMock()
    if get_exc is not None:
        client.get.side_effect = get_exc
    else:
        client.get.return_value = get_result if get_result is not None else {}
    client.post.return_value = {"agents": agents or []} if agents is not None else {"status": "success", "agent_id": "agent-1"}
    return client


def _register_args(*extra):
    return [
        "register",
        "--agent-id",
        "agent-1",
        "--name",
        "Agent One",
        "--chain-id",
        "ait-mainnet",
        "--endpoint",
        "http://node2:8107",
        *extra,
    ]


class TestReputationRange:
    def test_reputation_above_one_rejected_before_post(self, runner):
        from aitbc_cli.commands.agent_comm import agent_comm

        client = _client()
        with patch("aitbc_cli.commands.agent_comm._agent_client", return_value=client):
            result = runner.invoke(agent_comm, _register_args("--reputation", "99"), obj=_obj())
        assert result.exit_code != 0
        assert "reputation" in result.output.lower()
        client.post.assert_not_called()

    def test_reputation_below_zero_rejected(self, runner):
        from aitbc_cli.commands.agent_comm import agent_comm

        client = _client()
        with patch("aitbc_cli.commands.agent_comm._agent_client", return_value=client):
            result = runner.invoke(agent_comm, _register_args("--reputation", "-0.5"), obj=_obj())
        assert result.exit_code != 0
        client.post.assert_not_called()

    def test_reputation_boundaries_accepted(self, runner):
        from aitbc_cli.commands.agent_comm import agent_comm

        for value in ("0", "0.5", "1.0"):
            client = _client()
            with patch("aitbc_cli.commands.agent_comm._agent_client", return_value=client):
                result = runner.invoke(agent_comm, _register_args("--reputation", value), obj=_obj("json"))
            assert result.exit_code == 0, (value, result.output)
            assert client.post.call_args.kwargs["json"]["metadata"]["reputation"] == float(value)


class TestRegisterUpdate:
    _EXISTING = {
        "status": "success",
        "agent": {
            "agent_id": "agent-1",
            "agent_type": "specialist",
            "capabilities": ["gpu", "storage"],
            "metadata": {
                "name": "Old Name",
                "reputation": 0.9,
                "version": "2.0.0",
                "wallet": "0xbound",
                "message_queue_size": 3,
            },
        },
    }

    def test_reregister_without_update_aborts(self, runner):
        from aitbc_cli.commands.agent_comm import agent_comm

        client = _client(get_result=self._EXISTING)
        with patch("aitbc_cli.commands.agent_comm._agent_client", return_value=client):
            result = runner.invoke(agent_comm, _register_args(), obj=_obj())
        assert result.exit_code != 0
        assert "--update" in result.output
        client.post.assert_not_called()

    def test_update_merges_unspecified_fields(self, runner):
        """--update carries forward stored metadata for options not passed."""
        from aitbc_cli.commands.agent_comm import agent_comm

        client = _client(get_result=self._EXISTING)
        with patch("aitbc_cli.commands.agent_comm._agent_client", return_value=client):
            result = runner.invoke(agent_comm, _register_args("--update"), obj=_obj())
        assert result.exit_code == 0, result.output
        payload = client.post.call_args.kwargs["json"]
        assert payload["agent_type"] == "specialist"
        assert payload["capabilities"] == ["gpu", "storage"]
        assert payload["services"] == ["gpu", "storage"]
        meta = payload["metadata"]
        assert meta["name"] == "Agent One"  # required option always carries a value
        assert meta["reputation"] == 0.9
        assert meta["version"] == "2.0.0"
        assert meta["wallet"] == "0xbound"  # stored keys the CLI does not own survive
        assert meta["message_queue_size"] == 3

    def test_update_explicit_options_win(self, runner):
        from aitbc_cli.commands.agent_comm import agent_comm

        client = _client(get_result=self._EXISTING)
        with patch("aitbc_cli.commands.agent_comm._agent_client", return_value=client):
            result = runner.invoke(
                agent_comm,
                _register_args(
                    "--update",
                    "--reputation",
                    "0.1",
                    "--version",
                    "3.0.0",
                    "--agent-type",
                    "worker",
                    "--capabilities",
                    "inference",
                ),
                obj=_obj(),
            )
        assert result.exit_code == 0, result.output
        payload = client.post.call_args.kwargs["json"]
        assert payload["agent_type"] == "worker"
        assert payload["capabilities"] == ["inference"]
        meta = payload["metadata"]
        assert meta["reputation"] == 0.1
        assert meta["version"] == "3.0.0"

    def test_update_on_absent_agent_aborts(self, runner):
        from aitbc_cli.commands.agent_comm import agent_comm

        client = _client(get_exc=ConnectionError("GET request failed: 404 Client Error"))
        with patch("aitbc_cli.commands.agent_comm._agent_client", return_value=client):
            result = runner.invoke(agent_comm, _register_args("--update"), obj=_obj())
        assert result.exit_code != 0
        assert "not registered" in result.output
        client.post.assert_not_called()

    def test_first_registration_still_works_on_404(self, runner):
        from aitbc_cli.commands.agent_comm import agent_comm

        client = _client(get_exc=ConnectionError("GET request failed: 404 Client Error"))
        with patch("aitbc_cli.commands.agent_comm._agent_client", return_value=client):
            result = runner.invoke(agent_comm, _register_args(), obj=_obj("json"))
        assert result.exit_code == 0, result.output
        payload = client.post.call_args.kwargs["json"]
        assert payload["metadata"]["reputation"] == 0.5  # documented fresh defaults
        assert payload["metadata"]["version"] == "1.0.0"
        assert payload["agent_type"] == "worker"

    def test_inconclusive_lookup_without_update_still_registers(self, runner):
        """A non-404 lookup failure must not block first registration — the
        POST stays authoritative and the server's identity re-proof applies."""
        from aitbc_cli.commands.agent_comm import agent_comm

        client = _client(get_exc=ConnectionError("connection refused"))
        with patch("aitbc_cli.commands.agent_comm._agent_client", return_value=client):
            result = runner.invoke(agent_comm, _register_args(), obj=_obj())
        assert result.exit_code == 0, result.output
        client.post.assert_called_once()

    def test_inconclusive_lookup_with_update_aborts(self, runner):
        """--update cannot merge without the stored record — fail honestly."""
        from aitbc_cli.commands.agent_comm import agent_comm

        client = _client(get_exc=ConnectionError("connection refused"))
        with patch("aitbc_cli.commands.agent_comm._agent_client", return_value=client):
            result = runner.invoke(agent_comm, _register_args("--update"), obj=_obj())
        assert result.exit_code != 0
        assert "--update" in result.output
        client.post.assert_not_called()


class TestNetworkJson:
    _AGENTS = [
        {
            "agent_id": "agent-1",
            "chain_id": "bc-2",
            "status": "active",
            "capabilities": ["inference"],
            "metadata": {"reputation": 0.7},
        },
        {
            "agent_id": "agent-2",
            "chain_id": "bc-2",
            "status": "active",
            "capabilities": [],
            "metadata": {"reputation": 0.5},
        },
        {
            "agent_id": "agent-3",
            "chain_id": "bc-9",
            "status": "busy",
            "capabilities": [],
            "metadata": {"reputation": 0.2},
        },
    ]

    def test_network_json_is_single_parseable_document(self, runner):
        from aitbc_cli.commands.agent_comm import agent_comm

        client = _client(agents=self._AGENTS)
        with patch("aitbc_cli.commands.agent_comm._agent_client", return_value=client):
            result = runner.invoke(agent_comm, ["network", "--format", "json"], obj=_obj("json"))
        assert result.exit_code == 0, result.output
        doc = json.loads(result.output)  # raises if two arrays were concatenated
        assert set(doc) == {"metrics", "agents_by_chain"}
        metrics = {row["Metric"]: row["Value"] for row in doc["metrics"]}
        assert metrics["Total Agents"] == 3
        assert metrics["Active Agents"] == 2
        by_chain = {row["Chain ID"]: row for row in doc["agents_by_chain"]}
        assert by_chain["bc-2"]["Total Agents"] == 2
        assert by_chain["bc-2"]["Active Agents"] == 2
        assert by_chain["bc-9"]["Active Agents"] == 0

    def test_network_table_unchanged(self, runner):
        from aitbc_cli.commands.agent_comm import agent_comm

        client = _client(agents=self._AGENTS)
        with patch("aitbc_cli.commands.agent_comm._agent_client", return_value=client):
            result = runner.invoke(agent_comm, ["network"], obj=_obj())
        assert result.exit_code == 0, result.output
        assert "Network Overview" in result.output
        assert "Agents by Chain" in result.output
