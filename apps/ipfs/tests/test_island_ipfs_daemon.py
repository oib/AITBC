"""Tests for island_ipfs_daemon argument validation (#1451, #1454)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import island_ipfs_daemon as daemon  # noqa: E402


def test_repo_path_rejects_traversal() -> None:
    for bad in ("../escape", "..", "a/b", "a\\b", ".", "", "a b", "..%2f..%2fetc"):
        with pytest.raises(ValueError):
            daemon._repo_path(bad)


def test_repo_path_accepts_normal_ids() -> None:
    path = daemon._repo_path("island-01")
    assert path.name == "island-01"
    assert path.parent.name == "ipfs-island"


def test_main_rejects_bad_island_id_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITBC_DATA_DIR", "/tmp/aitbc-test-data")
    rc = daemon.main(["--island-id", "../../etc/evil"])
    assert rc == 2


def test_main_rejects_out_of_range_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITBC_DATA_DIR", "/tmp/aitbc-test-data")
    for flag in ("--api-port", "--gateway-port", "--swarm-port"):
        assert daemon.main(["--island-id", "ok-island", flag, "99999"]) == 2
        assert daemon.main(["--island-id", "ok-island", flag, "0"]) == 2
        assert daemon.main(["--island-id", "ok-island", flag, "-1"]) == 2


def test_resolve_repo_arg_rejects_foreign_path(tmp_path, monkeypatch):
    """#1670: --repo must name the island-derived repo, nothing else."""
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    for bad in ("/etc/ipfs", str(tmp_path / "other"), "/tmp", "relative/dir"):
        with pytest.raises(ValueError, match="does not match the island repo path"):
            daemon._resolve_repo_arg(bad, "ok-island")


def test_resolve_repo_arg_accepts_canonical_path(tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    expected = tmp_path / "ipfs-island" / "ok-island"
    assert daemon._resolve_repo_arg(str(expected), "ok-island") == expected.resolve()


def test_main_rejects_repo_path_mismatch(monkeypatch, tmp_path):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    rc = daemon.main(["--island-id", "ok-island", "--repo", "/tmp/evil-repo"])
    assert rc == 2
    assert not Path("/tmp/evil-repo").exists()


def test_set_island_config_writes_atomically(tmp_path):
    """#1670: config rewrite is write-then-rename, no truncated config."""
    import json as _json

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "config").write_text(_json.dumps({"Existing": {"Key": 1}}))
    daemon._set_island_config(repo, 5002, 8081, 4002, ["/ip4/1.2.3.4/tcp/4002"])
    config = _json.loads((repo / "config").read_text())
    assert config["Existing"]["Key"] == 1
    assert config["Addresses"]["API"] == "/ip4/127.0.0.1/tcp/5002"
    assert config["AutoConf"] == {"Enabled": False}
    assert not (repo / "config.tmp").exists()
