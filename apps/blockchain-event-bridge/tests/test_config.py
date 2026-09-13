"""Regression tests for the event-bridge production localhost-RPC guard.

Same contract as coordinator-api and wallet: production declared through
ENVIRONMENT, APP_ENV or NODE_ENV rejects a localhost BLOCKCHAIN_RPC_URL unless
ALLOW_LOCAL_BLOCKCHAIN_RPC explicitly opts in.
"""

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    for var in ("ENVIRONMENT", "APP_ENV", "NODE_ENV", "ALLOW_LOCAL_BLOCKCHAIN_RPC", "BLOCKCHAIN_RPC_URL"):
        monkeypatch.delenv(var, raising=False)


class TestLocalhostRpcGuard:
    @pytest.mark.parametrize("var", ["ENVIRONMENT", "APP_ENV", "NODE_ENV"])
    def test_localhost_rejected_in_production(self, monkeypatch: pytest.MonkeyPatch, var: str):
        from pydantic import ValidationError

        from blockchain_event_bridge.config import Settings

        monkeypatch.setenv(var, "production")
        monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8202")
        with pytest.raises(ValidationError, match="localhost in production"):
            Settings()

    @pytest.mark.parametrize("var", ["ENVIRONMENT", "APP_ENV", "NODE_ENV"])
    def test_localhost_allowed_with_opt_in(self, monkeypatch: pytest.MonkeyPatch, var: str):
        from blockchain_event_bridge.config import Settings

        monkeypatch.setenv(var, "production")
        monkeypatch.setenv("ALLOW_LOCAL_BLOCKCHAIN_RPC", "1")
        monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
        assert Settings().blockchain_rpc_url == "http://localhost:8202"

    def test_localhost_allowed_outside_production(self, monkeypatch: pytest.MonkeyPatch):
        from blockchain_event_bridge.config import Settings

        monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8202")
        assert Settings().blockchain_rpc_url == "http://127.0.0.1:8202"

    def test_environment_development_beats_node_env_production(self, monkeypatch: pytest.MonkeyPatch):
        """Precedence: an explicit non-production ENVIRONMENT wins over NODE_ENV."""
        from blockchain_event_bridge.config import Settings

        monkeypatch.setenv("NODE_ENV", "production")
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8202")
        assert Settings().blockchain_rpc_url == "http://127.0.0.1:8202"

    def test_remote_url_needs_no_opt_in(self, monkeypatch: pytest.MonkeyPatch):
        from blockchain_event_bridge.config import Settings

        monkeypatch.setenv("NODE_ENV", "production")
        monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "https://hub.example.com")
        assert Settings().blockchain_rpc_url == "https://hub.example.com"
