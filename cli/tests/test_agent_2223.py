"""#2223: agent create address, register name resolution, discover honest default.

SCENARIO-10 play findings:

* ``agent create`` minted ``0x`` + 32 hex chars (``uuid4().hex[:40]`` — a UUID
  hex string is only 32 chars), which ``register-identity`` rejects: it needs
  a 20-byte EVM address with a valid EIP-55 checksum.
* ``agent register --agent-id <name>`` failed "config not found" — the lookup
  only matched the internal UUID ``agent_id``, not the name or filename that
  ``agent list`` shows.
* ``agent discover`` on a customer node silently targeted
  ``http://localhost:8107`` — a service that is not deployed there.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aitbc_cli.commands import agent_sdk


@pytest.fixture
def agent_dir(tmp_path, monkeypatch):
    """Redirect the local agent config dir into tmp_path."""
    d = tmp_path / "agents"
    d.mkdir()
    monkeypatch.setattr(agent_sdk, "get_agent_config_dir", lambda: d)
    return d


def _write_agent(config_dir: Path, filename: str, data: dict) -> None:
    (config_dir / filename).write_text(json.dumps(data))


def _agent_data(agent_id: str, name: str) -> dict:
    return {
        "agent_id": agent_id,
        "name": name,
        "address": "0x" + "ab" * 20,
        "agent_type": "provider",
        "capabilities": {"compute_type": "inference"},
    }


# --------------------------------------------------------------------------- #
# Finding 1: minted addresses must pass register-identity validation
# --------------------------------------------------------------------------- #


class TestMintedAgentAddress:
    def test_sdk_address_is_valid_evm_checksum(self):
        """All three SDK factories mint a 0x+40hex EIP-55 address."""
        from aitbc.utils.validation import validate_address
        from aitbc_agent.agent import Agent, generate_agent_address
        from aitbc_agent.compute_consumer import ComputeConsumer
        from aitbc_agent.compute_provider import ComputeProvider

        caps = {"compute_type": "inference"}
        for addr in (
            generate_agent_address(),
            Agent.create(name="a", agent_type="general", capabilities=caps).identity.address,
            ComputeProvider.create_provider(name="p", capabilities=caps, pricing_model={}).identity.address,
            ComputeConsumer.create(name="c", agent_type="consumer", capabilities=caps).identity.address,
        ):
            assert addr.startswith("0x") and len(addr) == 42
            assert validate_address(addr), f"register-identity would reject {addr}"


# --------------------------------------------------------------------------- #
# Finding 2: register resolves name / filename / agent_id
# --------------------------------------------------------------------------- #


class TestLoadAgentConfigResolution:
    def test_resolves_by_agent_id_name_and_filename(self, agent_dir):
        _write_agent(agent_dir, "shop-agent.json", _agent_data("agent_abc12345", "shop-agent"))
        _write_agent(agent_dir, "oddfile.json", _agent_data("agent_def67890", "other-name"))

        by_id = agent_sdk._load_agent_config("agent_abc12345")
        by_name = agent_sdk._load_agent_config("shop-agent")
        by_file = agent_sdk._load_agent_config("oddfile")
        assert by_id is not None and by_id["name"] == "shop-agent"
        assert by_name is not None and by_name["agent_id"] == "agent_abc12345"
        assert by_file is not None and by_file["agent_id"] == "agent_def67890"
        assert agent_sdk._load_agent_config("missing") is None

    def test_ambiguous_name_raises(self, agent_dir):
        _write_agent(agent_dir, "a.json", _agent_data("agent_1", "dup"))
        _write_agent(agent_dir, "b.json", _agent_data("agent_2", "dup"))
        with pytest.raises(ValueError, match="multiple"):
            agent_sdk._load_agent_config("dup")

    def test_exact_agent_id_beats_name_collision(self, agent_dir):
        # agent_2's id equals agent_1's name — the exact id match must win.
        _write_agent(agent_dir, "a.json", _agent_data("shared", "first"))
        _write_agent(agent_dir, "b.json", _agent_data("agent_2", "second"))
        resolved = agent_sdk._load_agent_config("agent_2")
        assert resolved is not None and resolved["name"] == "second"


class TestRegisterAgentResolution:
    def _client(self):
        client = MagicMock()
        client.post.return_value = {"message": "ok"}
        return client

    def test_register_by_name_posts_resolved_agent_id(self, agent_dir):
        _write_agent(agent_dir, "shop-agent.json", _agent_data("agent_abc12345", "shop-agent"))
        client = self._client()
        config = MagicMock(chain_id="ait-test", api_key=None)
        with (
            patch.object(agent_sdk, "get_config", return_value=config),
            patch.object(agent_sdk, "auth_client_kwargs", return_value={}),
            patch.object(agent_sdk, "AITBCHTTPClient", return_value=client),
        ):
            result = asyncio.run(agent_sdk.register_agent("shop-agent", "http://coord:8107"))

        assert result["registered"] is True
        assert result["agent_id"] == "agent_abc12345"
        posted = client.post.call_args.kwargs["json"]
        assert posted["agent_id"] == "agent_abc12345"
        assert posted["metadata"]["name"] == "shop-agent"

    def test_register_unknown_ref_names_all_lookup_keys(self, agent_dir):
        with patch.object(agent_sdk, "get_config", return_value=MagicMock(chain_id="c", api_key=None)):
            result = asyncio.run(agent_sdk.register_agent("ghost", "http://coord:8107"))
        assert "error" in result
        assert "id, name, or file" in result["error"]
        assert "agent list" in result["error"]

    def test_register_network_error_is_honest(self, agent_dir):
        _write_agent(agent_dir, "shop-agent.json", _agent_data("agent_abc12345", "shop-agent"))
        from aitbc_cli.utils.http_client import NetworkError

        client = MagicMock()
        client.post.side_effect = NetworkError("connection refused")
        config = MagicMock(chain_id="ait-test", api_key=None)
        with (
            patch.object(agent_sdk, "get_config", return_value=config),
            patch.object(agent_sdk, "auth_client_kwargs", return_value={}),
            patch.object(agent_sdk, "AITBCHTTPClient", return_value=client),
        ):
            result = asyncio.run(agent_sdk.register_agent("shop-agent", "http://coord:8107"))
        assert "Cannot reach the agent coordinator" in result["error"]


# --------------------------------------------------------------------------- #
# Finding 3: discover on the localhost default says the service is hub-side
# --------------------------------------------------------------------------- #


class TestCheckAgentCoordinatorLocalDefault:
    def _probe_fails(self):
        client = MagicMock()
        client.get.side_effect = RuntimeError("connection refused")
        return client

    def test_localhost_default_message_is_honest(self, capsys):
        config = MagicMock(api_key=None, agent_coordinator_url="")
        with (
            patch.object(agent_sdk, "resolve_coordinator_url", return_value="http://localhost:8107"),
            patch.object(agent_sdk, "get_config", return_value=config),
            patch.object(agent_sdk, "auth_client_kwargs", return_value={}),
            patch.object(agent_sdk, "AITBCHTTPClient", return_value=self._probe_fails()),
        ):
            assert agent_sdk._check_agent_coordinator(None, None) is False
        out = capsys.readouterr().out
        assert "hub-side service" in out
        assert "agent_coordinator_url" in out or "HUB_AGENT_URL" in out

    def test_configured_localhost_keeps_service_message(self, capsys):
        # agent_coordinator_url explicitly set to localhost → not the bare
        # fallback, so the 'start the service' advice still applies.
        config = MagicMock(api_key=None, agent_coordinator_url="http://localhost:8107")
        with (
            patch.object(agent_sdk, "resolve_coordinator_url", return_value="http://localhost:8107"),
            patch.object(agent_sdk, "get_config", return_value=config),
            patch.object(agent_sdk, "auth_client_kwargs", return_value={}),
            patch.object(agent_sdk, "AITBCHTTPClient", return_value=self._probe_fails()),
        ):
            assert agent_sdk._check_agent_coordinator(None, None) is False
        out = capsys.readouterr().out
        assert "hub-side service" not in out
        assert "aitbc-agent-coordinator" in out

    def test_unreachable_remote_keeps_service_message(self, capsys):
        config = MagicMock(api_key=None, agent_coordinator_url="http://hub:8107")
        with (
            patch.object(agent_sdk, "resolve_coordinator_url", return_value="http://hub:8107"),
            patch.object(agent_sdk, "get_config", return_value=config),
            patch.object(agent_sdk, "auth_client_kwargs", return_value={}),
            patch.object(agent_sdk, "AITBCHTTPClient", return_value=self._probe_fails()),
        ):
            assert agent_sdk._check_agent_coordinator(None, None) is False
        out = capsys.readouterr().out
        assert "Cannot reach the agent coordinator at http://hub:8107" in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
