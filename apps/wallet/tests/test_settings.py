"""Regression tests for the wallet production localhost-RPC guard.

The guard previously read only ENVIRONMENT/APP_ENV, so production declared
through NODE_ENV — how the fleet actually declares it — never engaged, and the
coordinator-api ALLOW_LOCAL_BLOCKCHAIN_RPC opt-in did not exist here.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    for var in (
        "ENVIRONMENT",
        "APP_ENV",
        "NODE_ENV",
        "ALLOW_LOCAL_BLOCKCHAIN_RPC",
        "BLOCKCHAIN_RPC_URL",
        "TRUSTED_RECEIPT_KEY_IDS",
        "REQUIRE_TRUSTED_RECEIPT_KEYS",
    ):
        monkeypatch.delenv(var, raising=False)


class TestLocalhostRpcGuard:
    @pytest.mark.parametrize("var", ["ENVIRONMENT", "APP_ENV", "NODE_ENV"])
    def test_localhost_rejected_in_production(self, monkeypatch: pytest.MonkeyPatch, var: str):
        from pydantic import ValidationError

        from wallet_app.settings import Settings

        monkeypatch.setenv(var, "production")
        monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8202")
        with pytest.raises(ValidationError, match="localhost in production"):
            Settings()

    @pytest.mark.parametrize("var", ["ENVIRONMENT", "APP_ENV", "NODE_ENV"])
    def test_localhost_allowed_with_opt_in(self, monkeypatch: pytest.MonkeyPatch, var: str):
        from wallet_app.settings import Settings

        monkeypatch.setenv(var, "production")
        monkeypatch.setenv("ALLOW_LOCAL_BLOCKCHAIN_RPC", "1")
        monkeypatch.setenv("TRUSTED_RECEIPT_KEY_IDS", "key-1")  # F4 guard: production requires the trust set
        monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
        assert Settings().blockchain_rpc_url == "http://localhost:8202"

    def test_localhost_allowed_outside_production(self, monkeypatch: pytest.MonkeyPatch):
        from wallet_app.settings import Settings

        monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8202")
        assert Settings().blockchain_rpc_url == "http://127.0.0.1:8202"

    def test_environment_development_beats_node_env_production(self, monkeypatch: pytest.MonkeyPatch):
        """Precedence: an explicit non-production ENVIRONMENT wins over NODE_ENV."""
        from wallet_app.settings import Settings

        monkeypatch.setenv("NODE_ENV", "production")
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
        assert Settings().blockchain_rpc_url == "http://localhost:8202"

    def test_remote_url_needs_no_opt_in(self, monkeypatch: pytest.MonkeyPatch):
        from wallet_app.settings import Settings

        monkeypatch.setenv("NODE_ENV", "production")
        monkeypatch.setenv("TRUSTED_RECEIPT_KEY_IDS", "key-1")  # F4 guard: production requires the trust set
        monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "https://hub.example.com")
        assert Settings().blockchain_rpc_url == "https://hub.example.com"


class TestTrustedReceiptKeysGuard:
    """F4: production (or the dedicated flag) refuses to start without
    TRUSTED_RECEIPT_KEY_IDS — any-key verification is the spoofing surface."""

    def test_production_without_trust_set_refuses(self, monkeypatch: pytest.MonkeyPatch):
        from pydantic import ValidationError

        from wallet_app.settings import Settings

        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("ALLOW_LOCAL_BLOCKCHAIN_RPC", "1")
        with pytest.raises(ValidationError, match="TRUSTED_RECEIPT_KEY_IDS"):
            Settings()

    def test_production_with_trust_set_starts(self, monkeypatch: pytest.MonkeyPatch):
        from wallet_app.settings import Settings

        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("ALLOW_LOCAL_BLOCKCHAIN_RPC", "1")
        monkeypatch.setenv("TRUSTED_RECEIPT_KEY_IDS", "key-1,key-2")
        s = Settings()
        assert s.trusted_receipt_key_id_set == frozenset({"key-1", "key-2"})

    def test_dedicated_flag_refuses_without_trust_set(self, monkeypatch: pytest.MonkeyPatch):
        """The wallet env does not carry ENVIRONMENT=production; the flag is the fleet gate."""
        from pydantic import ValidationError

        from wallet_app.settings import Settings

        monkeypatch.setenv("REQUIRE_TRUSTED_RECEIPT_KEYS", "true")
        with pytest.raises(ValidationError, match="TRUSTED_RECEIPT_KEY_IDS"):
            Settings()

    def test_unset_trust_set_allowed_in_development(self, monkeypatch: pytest.MonkeyPatch):
        """Legacy behavior preserved where neither gate applies."""
        from wallet_app.settings import Settings

        s = Settings()
        assert s.trusted_receipt_key_id_set is None
