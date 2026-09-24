"""Tests for the MARKETPLACE_* → MARKET_* environment fallback."""

import pytest

from aitbc import env_compat
from aitbc.env_compat import legacy_market_name, market_getenv


@pytest.fixture(autouse=True)
def _clear_warning_state() -> None:
    """The one-shot deprecation warning is process-global state."""
    env_compat._warned.clear()


class TestLegacyMarketName:
    def test_market_prefix_is_translated(self) -> None:
        assert legacy_market_name("MARKET_SERVICE_URL") == "MARKETPLACE_SERVICE_URL"

    def test_unrelated_names_have_no_legacy_spelling(self) -> None:
        assert legacy_market_name("DATABASE_URL") is None

    def test_the_prefix_alone_is_translated(self) -> None:
        assert legacy_market_name("MARKET_") == "MARKETPLACE_"

    def test_a_marketplace_name_is_not_translated_again(self) -> None:
        assert legacy_market_name("MARKETPLACE_SERVICE_URL") is None


class TestMarketGetenv:
    def test_canonical_name_is_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MARKET_SERVICE_URL", "http://canonical:8102")
        assert market_getenv("MARKET_SERVICE_URL", "http://default") == "http://canonical:8102"

    def test_legacy_name_is_the_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MARKET_SERVICE_URL", raising=False)
        monkeypatch.setenv("MARKETPLACE_SERVICE_URL", "http://legacy:8102")
        assert market_getenv("MARKET_SERVICE_URL", "http://default") == "http://legacy:8102"

    def test_canonical_wins_when_both_are_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A host part-way through the migration behaves like a migrated one."""
        monkeypatch.setenv("MARKET_SERVICE_URL", "http://canonical:8102")
        monkeypatch.setenv("MARKETPLACE_SERVICE_URL", "http://legacy:8102")
        assert market_getenv("MARKET_SERVICE_URL", "http://default") == "http://canonical:8102"

    def test_default_is_returned_when_neither_is_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MARKET_SERVICE_URL", raising=False)
        monkeypatch.delenv("MARKETPLACE_SERVICE_URL", raising=False)
        assert market_getenv("MARKET_SERVICE_URL", "http://default") == "http://default"

    def test_default_is_none_when_unspecified(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MARKET_OPERATIONS_DB", raising=False)
        monkeypatch.delenv("MARKETPLACE_OPERATIONS_DB", raising=False)
        assert market_getenv("MARKET_OPERATIONS_DB") is None

    def test_empty_value_is_honoured_not_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An explicitly empty setting is a choice, not an absent variable."""
        monkeypatch.setenv("MARKET_SERVICE_URL", "")
        assert market_getenv("MARKET_SERVICE_URL", "http://default") == ""

    def test_non_market_names_never_reach_a_legacy_lookup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("MARKETPLACE_DATABASE_URL", "postgresql://legacy/db")
        assert market_getenv("DATABASE_URL", "sqlite://default") == "sqlite://default"

    def test_the_deprecation_warning_fires_once(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.delenv("MARKET_SERVICE_URL", raising=False)
        monkeypatch.setenv("MARKETPLACE_SERVICE_URL", "http://legacy:8102")
        with caplog.at_level("WARNING", logger=env_compat.logger.name):
            market_getenv("MARKET_SERVICE_URL", "http://default")
            market_getenv("MARKET_SERVICE_URL", "http://default")
        warnings = [r for r in caplog.records if "MARKETPLACE_SERVICE_URL" in r.getMessage()]
        assert len(warnings) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
