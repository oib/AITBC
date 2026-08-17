"""Tests for coordinator-api configuration."""

import pytest


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


class TestKeysAreNotHubCredentials:
    """V23-68c: the deployed miner authenticated with the published hub key.

    `MINER_API_KEY` in /etc/aitbc/aitbc-miner.env and `COORDINATOR_API_KEY` in the
    coordinator's environment held one value, and `COORDINATOR_API_KEY` is published in a
    world-readable bootstrap file. V23-68 removed the *code path* that promoted the hub key to
    a miner credential; it could still arrive by configuration, and did.
    """

    HUB_KEY = "hub-key-published-1234567890"

    def test_a_miner_key_may_not_be_the_coordinator_key(self, monkeypatch):
        from pydantic import ValidationError

        from coordinator_api.config import Settings

        monkeypatch.setenv("COORDINATOR_API_KEY", self.HUB_KEY)
        monkeypatch.setenv("MINER_API_KEYS", f'["{self.HUB_KEY}"]')

        with pytest.raises(ValidationError, match="reuses COORDINATOR_API_KEY"):
            Settings()

    def test_a_miner_key_may_not_be_the_secret_key(self, monkeypatch):
        from pydantic import ValidationError

        from coordinator_api.config import Settings

        monkeypatch.delenv("COORDINATOR_API_KEY", raising=False)
        monkeypatch.setenv("SECRET_KEY", self.HUB_KEY)
        monkeypatch.setenv("MINER_API_KEYS", f'["{self.HUB_KEY}"]')

        with pytest.raises(ValidationError, match="reuses COORDINATOR_API_KEY or SECRET_KEY"):
            Settings()

    def test_the_admin_and_client_lists_are_checked_too(self, monkeypatch):
        from pydantic import ValidationError

        from coordinator_api.config import Settings

        monkeypatch.setenv("COORDINATOR_API_KEY", self.HUB_KEY)
        monkeypatch.setenv("ADMIN_API_KEYS", f'["{self.HUB_KEY}"]')

        with pytest.raises(ValidationError, match="ADMIN_API_KEYS"):
            Settings()

    def test_a_distinct_miner_key_is_fine(self, monkeypatch):
        """The check must not reject the correct configuration — the deployed one."""
        from coordinator_api.config import Settings

        monkeypatch.setenv("COORDINATOR_API_KEY", self.HUB_KEY)
        monkeypatch.setenv("MINER_API_KEYS", '["miner-own-key-1234567890"]')

        assert Settings().miner_api_keys == ["miner-own-key-1234567890"]

    def test_startup_says_so_when_the_list_is_empty(self, monkeypatch, caplog):
        """V23-68c: `validate_api_keys` only rejects an empty list in production.

        The deployed hub runs ENVIRONMENT=development, where an unset `MINER_API_KEYS` is
        accepted and then refuses every miner. Startup logs it instead of passing silently.
        """
        import logging

        from coordinator_api import config

        monkeypatch.setattr(config.settings, "miner_api_keys", [])

        with caplog.at_level(logging.WARNING):
            config.validate_critical_environment_variables()

        assert "MINER_API_KEYS is empty" in caplog.text

    def test_startup_is_quiet_when_keys_are_configured(self, monkeypatch, caplog):
        import logging

        from coordinator_api import config

        monkeypatch.setattr(config.settings, "miner_api_keys", ["miner-own-key-1234567890"])

        with caplog.at_level(logging.WARNING):
            config.validate_critical_environment_variables()

        assert "MINER_API_KEYS is empty" not in caplog.text

    def test_the_check_runs_outside_production(self, monkeypatch):
        """The deployed hub runs ENVIRONMENT=development, where the empty-list guard is off."""
        from pydantic import ValidationError

        from coordinator_api.config import Settings

        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("COORDINATOR_API_KEY", self.HUB_KEY)
        monkeypatch.setenv("MINER_API_KEYS", f'["{self.HUB_KEY}"]')

        with pytest.raises(ValidationError):
            Settings()
