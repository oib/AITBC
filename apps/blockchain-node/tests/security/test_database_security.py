"""Security tests for database access restrictions.

The fail-closed DB-encryption gate: DB_ENCRYPTION_ENABLED=true with a
missing key file must refuse instead of opening a plaintext chain db.
"""

import pytest

import aitbc_chain.database as d


class TestDatabaseSecurity:
    """Test database security measures."""

    def test_missing_key_raises(self, monkeypatch, tmp_path):
        monkeypatch.setattr(d.settings, "db_encryption_enabled", True, raising=False)
        monkeypatch.setattr(d.settings, "db_encryption_key_path", tmp_path / "nokey", raising=False)
        with pytest.raises(RuntimeError):
            d._encryption_enabled()

    def test_flag_off_returns_false(self, monkeypatch):
        monkeypatch.setattr(d.settings, "db_encryption_enabled", False, raising=False)
        assert d._encryption_enabled() is False

    def test_flag_on_with_key_returns_true(self, monkeypatch, tmp_path):
        key = tmp_path / "key.bin"
        key.write_bytes(b"k" * 32)
        monkeypatch.setattr(d.settings, "db_encryption_enabled", True, raising=False)
        monkeypatch.setattr(d.settings, "db_encryption_key_path", key, raising=False)
        assert d._encryption_enabled() is True
