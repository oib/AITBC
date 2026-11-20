"""#2205: node-process registry snapshot is served by the RPC /metrics route."""

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from aitbc_chain import node_metrics_snapshot as nms
from aitbc_chain.app import create_app
from aitbc_chain.metrics import metrics_registry


@pytest.fixture
def snap(tmp_path: Path):
    path = tmp_path / "node_metrics.prom"
    with patch.object(nms, "snapshot_path", return_value=path):
        yield path


def _foreign_snapshot(path: Path, body: str, pid: int = 1) -> None:
    path.write_text(f"{nms._PID_PREFIX}{pid} ts=0\n{body}", encoding="utf-8")


def test_write_then_read_same_pid_is_skipped(snap: Path) -> None:
    metrics_registry.increment("pbft_intake_drop_total")
    nms.write_snapshot()
    assert "pbft_intake_drop_total" in snap.read_text()
    assert nms.read_snapshot() == ""  # own pid: already rendered directly


def test_foreign_snapshot_is_returned(snap: Path) -> None:
    _foreign_snapshot(snap, "# TYPE pbft_intake_drop_total counter\npbft_intake_drop_total 7.0\n")
    assert "pbft_intake_drop_total 7.0" in nms.read_snapshot()


def test_stale_or_missing_or_unmarked_is_ignored(snap: Path) -> None:
    assert nms.read_snapshot() == ""  # missing
    _foreign_snapshot(snap, "x 1\n")
    old = time.time() - 3600
    os.utime(snap, (old, old))
    assert nms.read_snapshot() == ""  # stale
    snap.write_text("pbft_intake_drop_total 9\n", encoding="utf-8")
    assert nms.read_snapshot() == ""  # no marker line


def test_write_is_atomic_no_tmp_left(snap: Path) -> None:
    nms.write_snapshot()
    assert not list(snap.parent.glob("*.tmp"))


def test_rpc_metrics_appends_node_snapshot(snap: Path) -> None:
    _foreign_snapshot(snap, "# TYPE pbft_view_change_x counter\npbft_view_change_x 3.0\n")
    with TestClient(create_app()) as client:
        body = client.get("/metrics").text
    assert "pbft_view_change_x 3.0" in body
    assert "node-process registry (snapshot)" in body


def test_rpc_metrics_flag_off_ignores_snapshot(snap: Path) -> None:
    _foreign_snapshot(snap, "pbft_view_change_x 3.0\n")
    with patch("aitbc_chain.config.settings.node_metrics_snapshot_enabled", False), TestClient(create_app()) as client:
        assert "pbft_view_change_x" not in client.get("/metrics").text
