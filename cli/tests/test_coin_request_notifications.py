"""
Tests for the agent notification the coin-request commands send (V23-92).

The old default was `http://localhost:8107`, an agent-coordinator that only a hub runs, and
the request carried no credential. On a follower or shop node that is two failures: the URL
points at nothing, and the URL that does exist answers 401.
"""

from unittest.mock import patch

import pytest
from aitbc_cli.commands.coin_requests import _agent_api_base, send_agent_notification

URL_VARS = (
    "AGENT_COORDINATOR_URL",
    "HERMES_COORDINATOR_URL",
    "HUB_AGENT_URL",
    "HUB_HERMES_URL",
    "HUB_DISCOVERY_URL",
)
KEY_VARS = ("COORDINATOR_API_KEY", "SECRET_KEY", "FOLLOWER_API_KEY")


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """Start from a node that has none of these set.

    The module imports `/etc/aitbc/*.env` at import time, so without this the result depends
    on what is deployed on the machine running the tests. Hub-host resolution also
    reads those files; point it at an empty directory so the suite does not inherit
    the machine's HUB_DISCOVERY_URL.
    """
    for name in URL_VARS + KEY_VARS + ("AGENT_ID", "HERMES_AGENT_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("aitbc.config.hub._env_files", lambda: (tmp_path / "blockchain.env", tmp_path / "node.env"))
    return monkeypatch


class TestAgentApiBase:
    """Which agent API a node resolves."""

    def test_a_node_with_nothing_configured_refuses_to_invent_a_hub(self, clean_env):
        with pytest.raises(RuntimeError, match="HUB_DISCOVERY_URL"):
            _agent_api_base()

    def test_hub_discovery_url_from_env_builds_the_agent_base(self, clean_env):
        clean_env.setenv("HUB_DISCOVERY_URL", "hub.example.net")

        assert _agent_api_base() == "https://hub.example.net/api/v1/agent"

    def test_the_default_is_never_a_local_port(self, clean_env):
        clean_env.setenv("HUB_DISCOVERY_URL", "hub.example.net")
        assert "localhost" not in _agent_api_base()

    def test_a_local_coordinator_wins_when_set(self, clean_env):
        clean_env.setenv("AGENT_COORDINATOR_URL", "http://localhost:8107")

        assert _agent_api_base() == "http://localhost:8107/api/v1/agent"

    def test_the_hermes_name_still_works(self, clean_env):
        clean_env.setenv("HERMES_COORDINATOR_URL", "http://127.0.0.1:8107")

        assert _agent_api_base() == "http://127.0.0.1:8107/api/v1/agent"

    def test_the_agent_name_beats_the_hermes_name(self, clean_env):
        clean_env.setenv("AGENT_COORDINATOR_URL", "http://localhost:9107")
        clean_env.setenv("HERMES_COORDINATOR_URL", "http://localhost:8107")

        assert _agent_api_base() == "http://localhost:9107/api/v1/agent"

    def test_a_local_origin_beats_the_hub_base(self, clean_env):
        clean_env.setenv("AGENT_COORDINATOR_URL", "http://localhost:8107")
        clean_env.setenv("HUB_AGENT_URL", "https://hub.example.net/api/v1/agent")

        assert _agent_api_base() == "http://localhost:8107/api/v1/agent"

    def test_the_hub_base_is_used_prefix_and_all(self, clean_env):
        clean_env.setenv("HUB_AGENT_URL", "https://hub.example.net/api/v1/agent")

        assert _agent_api_base() == "https://hub.example.net/api/v1/agent"

    def test_trailing_slashes_do_not_double_up(self, clean_env):
        clean_env.setenv("AGENT_COORDINATOR_URL", "http://localhost:8107/")

        assert _agent_api_base() == "http://localhost:8107/api/v1/agent"

        clean_env.delenv("AGENT_COORDINATOR_URL")
        clean_env.setenv("HUB_HERMES_URL", "https://hub.example.net/api/v1/agent/")

        assert _agent_api_base() == "https://hub.example.net/api/v1/agent"


class TestSendAgentNotification:
    """What actually goes over the wire."""

    def test_it_posts_to_the_resolved_url(self, clean_env):
        clean_env.setenv("HUB_AGENT_URL", "https://hub.example.net/api/v1/agent")

        with patch("aitbc_cli.commands.coin_requests.requests.post") as post:
            post.return_value.status_code = 200
            send_agent_notification("agent-b", "approved")

        assert post.call_args.args[0] == "https://hub.example.net/api/v1/agent/messages/send"

    def test_a_hub_credential_is_sent(self, clean_env):
        clean_env.setenv("HUB_DISCOVERY_URL", "hub.example.net")
        clean_env.setenv("COORDINATOR_API_KEY", "hub-key")

        with patch("aitbc_cli.commands.coin_requests.requests.post") as post:
            post.return_value.status_code = 200
            send_agent_notification("agent-b", "approved")

        assert post.call_args.kwargs["headers"] == {"x-api-key": "hub-key"}

    def test_the_secret_key_is_the_fallback(self, clean_env):
        clean_env.setenv("HUB_DISCOVERY_URL", "hub.example.net")
        clean_env.setenv("SECRET_KEY", "secret-key")

        with patch("aitbc_cli.commands.coin_requests.requests.post") as post:
            post.return_value.status_code = 200
            send_agent_notification("agent-b", "approved")

        assert post.call_args.kwargs["headers"] == {"x-api-key": "secret-key"}

    def test_the_published_follower_key_is_not_sent(self, clean_env):
        """FOLLOWER_API_KEY is public and reaches /register and /execute only (V23-68)."""
        clean_env.setenv("HUB_DISCOVERY_URL", "hub.example.net")
        clean_env.setenv("FOLLOWER_API_KEY", "published-key")

        with patch("aitbc_cli.commands.coin_requests.requests.post") as post:
            post.return_value.status_code = 200
            send_agent_notification("agent-b", "approved")

        assert post.call_args.kwargs["headers"] == {}

    def test_a_401_says_it_needs_a_hub_credential(self, clean_env, capsys):
        clean_env.setenv("HUB_DISCOVERY_URL", "hub.example.net")
        with patch("aitbc_cli.commands.coin_requests.requests.post") as post:
            post.return_value.status_code = 401
            post.return_value.text = "Unauthorized"
            send_agent_notification("agent-b", "approved")

        out = capsys.readouterr().out
        assert "401" in out
        assert "hub credential" in out

    def test_a_connection_failure_names_the_url(self, clean_env, capsys):
        clean_env.setenv("HUB_DISCOVERY_URL", "hub.example.net")
        with patch("aitbc_cli.commands.coin_requests.requests.post") as post:
            post.side_effect = OSError("connection refused")
            send_agent_notification("agent-b", "approved")

        out = capsys.readouterr().out
        assert "hub.example.net" in out
        assert "connection refused" in out

    def test_a_notification_failure_does_not_raise(self, clean_env):
        """The approve/reject commands call this after committing; it must not undo them."""
        clean_env.setenv("HUB_DISCOVERY_URL", "hub.example.net")
        with patch("aitbc_cli.commands.coin_requests.requests.post") as post:
            post.side_effect = RuntimeError("boom")

            send_agent_notification("agent-b", "approved")


if __name__ == "__main__":
    pytest.main([__file__])
