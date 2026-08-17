"""Tests for coordinator-api configuration."""


def test_settings_singleton():
    """Test that settings can be loaded."""
    from coordinator_api.config import settings

    assert settings.app_name == "AITBC Coordinator API"
    assert settings.port == 8203


def test_database_config():
    """Test database configuration defaults."""
    from coordinator_api.config import DatabaseConfig

    db = DatabaseConfig()
    assert db.adapter in ("sqlite", "postgresql")
    assert db.pool_size == 10
    assert db.max_overflow == 20


def test_cors_validation():
    """Test CORS origins include localhost in development."""
    from coordinator_api.config import Settings

    settings = Settings()
    origins = settings.allow_origins
    assert "http://localhost:8203" in origins


def test_rate_limits():
    """Test rate limit configuration values."""
    from coordinator_api.config import settings

    assert settings.rate_limit_jobs_submit == "100/minute"
    assert settings.rate_limit_miner_register == "30/minute"
    assert settings.rate_limit_exchange_payment == "20/minute"


class TestApiKeyLists:
    """V23-68b: the documented way to set these keys used to stop Settings from constructing.

    `parse_api_keys` handles a comma-separated string, but pydantic-settings JSON-decodes a
    complex-typed environment variable before any validator sees it and raises SettingsError
    when that fails. So `MINER_API_KEYS=a,b` — what docs/ops/follower-api-key.md asks
    operators for — raised at import, which is where coordinator-api reads its settings.
    """

    def test_comma_separated_env_is_accepted(self, monkeypatch):
        from coordinator_api.config import Settings

        monkeypatch.setenv("MINER_API_KEYS", "miner-key-1234567890,miner-key-0987654321")

        assert Settings().miner_api_keys == ["miner-key-1234567890", "miner-key-0987654321"]

    def test_json_env_is_still_accepted(self, monkeypatch):
        from coordinator_api.config import Settings

        monkeypatch.setenv("ADMIN_API_KEYS", '["admin-key-1234567890"]')

        assert Settings().admin_api_keys == ["admin-key-1234567890"]

    def test_unset_stays_empty(self, monkeypatch):
        from coordinator_api.config import Settings

        monkeypatch.delenv("CLIENT_API_KEYS", raising=False)

        assert Settings().client_api_keys == []
