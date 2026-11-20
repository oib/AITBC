"""Tests for aitbc oracle CID existence checks (#2339)."""

from __future__ import annotations

from unittest.mock import patch

from aitbc_cli.commands import oracle as oracle_mod


def test_cid_exists_uses_kubo_when_daemon_reachable(tmp_path, monkeypatch):
    """Daemon-uploaded CIDs are not in IPFS_DIR — must check Kubo (#2339)."""
    monkeypatch.setattr(oracle_mod, "IPFS_DIR", tmp_path / "ipfs")
    with (
        patch("aitbc_cli.commands.ipfs.resolve_ipfs_api", return_value="http://127.0.0.1:5002"),
        patch("aitbc_cli.commands.ipfs._ipfs_object_size", return_value=36) as size,
    ):
        assert oracle_mod._cid_exists("QmWhatever") is True
        size.assert_called_once()


def test_cid_exists_kubo_miss_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(oracle_mod, "IPFS_DIR", tmp_path / "ipfs")
    with (
        patch("aitbc_cli.commands.ipfs.resolve_ipfs_api", return_value="http://127.0.0.1:5002"),
        patch("aitbc_cli.commands.ipfs._ipfs_object_size", return_value=None),
    ):
        assert oracle_mod._cid_exists("QmMissing") is False


def test_cid_exists_filesystem_fallback(tmp_path, monkeypatch):
    ipfs_dir = tmp_path / "ipfs"
    ipfs_dir.mkdir()
    (ipfs_dir / "QmLocal").write_bytes(b"data")
    monkeypatch.setattr(oracle_mod, "IPFS_DIR", ipfs_dir)
    with patch("aitbc_cli.commands.ipfs.resolve_ipfs_api", return_value=None):
        assert oracle_mod._cid_exists("QmLocal") is True
        assert oracle_mod._cid_exists("QmAbsent") is False
