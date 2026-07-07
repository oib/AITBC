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
