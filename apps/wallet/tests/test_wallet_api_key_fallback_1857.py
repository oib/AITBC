"""#1857: WALLET_API_KEY fallback to COORDINATOR_API_KEY is fail-closed.

Pre-fix the wallet admin key silently defaulted to the cluster-wide
COORDINATOR_API_KEY — one env leak admin'd every wallet. The fallback now
survives only outside the gate (non-production, REQUIRE_WALLET_API_KEY
unset); production or the explicit env refuses startup without
WALLET_API_KEY, mirroring the TRUSTED_RECEIPT_KEY_IDS pattern.
"""

import pytest

from wallet_app.settings import Settings

_COORDINATOR_KEY = "test-coordinator-key"
_WALLET_KEY = "test-wallet-admin-key-0123456789"


def _settings_kwargs() -> dict:
    return {}


class TestWalletApiKeyFallbackGate:
    def test_require_env_refuses_fallback(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("REQUIRE_WALLET_API_KEY", "1")
        monkeypatch.delenv("WALLET_API_KEY", raising=False)
        monkeypatch.setenv("COORDINATOR_API_KEY", _COORDINATOR_KEY)
        with pytest.raises(ValueError, match="WALLET_API_KEY must be set"):
            Settings(**_settings_kwargs())

    def test_production_refuses_fallback(self, monkeypatch: pytest.MonkeyPatch):
        import wallet_app.settings as settings_mod

        monkeypatch.delenv("REQUIRE_WALLET_API_KEY", raising=False)
        monkeypatch.delenv("WALLET_API_KEY", raising=False)
        monkeypatch.setenv("COORDINATOR_API_KEY", _COORDINATOR_KEY)
        monkeypatch.setattr(settings_mod, "is_production", lambda: True)
        # is_production also gates the localhost-RPC check — allow it so the
        # api-key validator is the failure under test.
        monkeypatch.setenv("ALLOW_LOCAL_BLOCKCHAIN_RPC", "1")
        with pytest.raises(ValueError, match="WALLET_API_KEY must be set"):
            Settings(**_settings_kwargs())

    def test_explicit_wallet_key_passes_under_gate(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("REQUIRE_WALLET_API_KEY", "1")
        monkeypatch.setenv("WALLET_API_KEY", _WALLET_KEY)
        monkeypatch.setenv("COORDINATOR_API_KEY", _COORDINATOR_KEY)
        s = Settings(**_settings_kwargs())
        assert s.api_key == _WALLET_KEY

    def test_fallback_preserved_outside_gate(self, monkeypatch: pytest.MonkeyPatch):
        """Migration path: non-production without the env keeps the legacy
        fallback so existing dev/test envs still boot."""
        monkeypatch.delenv("REQUIRE_WALLET_API_KEY", raising=False)
        monkeypatch.delenv("WALLET_API_KEY", raising=False)
        monkeypatch.setenv("COORDINATOR_API_KEY", _COORDINATOR_KEY)
        s = Settings(**_settings_kwargs())
        assert s.api_key == _COORDINATOR_KEY

    def test_auth_disabled_never_requires_wallet_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("REQUIRE_WALLET_API_KEY", "1")
        monkeypatch.setenv("WALLET_AUTH_ENABLED", "false")
        monkeypatch.delenv("WALLET_API_KEY", raising=False)
        monkeypatch.setenv("COORDINATOR_API_KEY", _COORDINATOR_KEY)
        s = Settings(**_settings_kwargs())
        assert s.api_key is None
