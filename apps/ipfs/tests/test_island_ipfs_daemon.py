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
