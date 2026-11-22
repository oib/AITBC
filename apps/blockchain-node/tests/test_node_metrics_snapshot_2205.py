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
    assert 'pbft_view_change_x{process="node"} 3.0' in body
    assert "node-process registry (snapshot)" in body


def test_rpc_metrics_flag_off_ignores_snapshot(snap: Path) -> None:
    _foreign_snapshot(snap, "pbft_view_change_x 3.0\n")
    with patch("aitbc_chain.config.settings.node_metrics_snapshot_enabled", False), TestClient(create_app()) as client:
        assert "pbft_view_change_x" not in client.get("/metrics").text


# --------------------------------------------------------------------------
# #2488/#2504: shared names merge by series — one TYPE line, both values
# --------------------------------------------------------------------------


def test_with_node_snapshot_keeps_both_shared_series(snap: Path) -> None:
    """#2504: a snapshot name the RPC render also carries is NOT dropped —
    the node value survives tagged process="node" next to the RPC value,
    and the snapshot's duplicate TYPE/HELP lines are dropped."""
    _foreign_snapshot(
        snap,
        "# TYPE shared_total counter\n"
        "# HELP shared_total node copy\n"
        "shared_total 99.0\n"
        "# TYPE node_only_total counter\n"
        "node_only_total 3.0\n",
    )
    rendered = b"# TYPE shared_total counter\nshared_total 1.0\n"
    out = nms.with_node_snapshot(rendered)
    text = out.decode()
    assert "shared_total 1.0" in text
    assert 'shared_total{process="node"} 99.0' in text
    assert 'node_only_total{process="node"} 3.0' in text
    # exactly one TYPE line for the shared name — the RPC render's
    assert text.count("# TYPE shared_total") == 1
    assert "# HELP shared_total" not in text.split("node-process registry")[1]
    assert "# TYPE node_only_total" in text


def test_with_node_snapshot_summary_suffixes_merge(snap: Path) -> None:
    """Summaries expose _count/_sum samples — each tagged sample is a
    distinct series, so both processes' values survive under one TYPE."""
    _foreign_snapshot(snap, "# TYPE lat summary\nlat_count 4\nlat_sum 9.5\n")
    rendered = b"# TYPE lat summary\nlat_count 1\nlat_sum 2.0\n"
    text = nms.with_node_snapshot(rendered).decode()
    assert "lat_count 1" in text and 'lat_count{process="node"} 4' in text
    assert "lat_sum 2.0" in text and 'lat_sum{process="node"} 9.5' in text
    assert text.count("# TYPE lat") == 1


def test_with_node_snapshot_existing_labels_are_preserved(snap: Path) -> None:
    """A snapshot sample that already carries labels gets process="node"
    appended, not replaced."""
    _foreign_snapshot(snap, 'gauge_total{chain="bc-2"} 5.0\n')
    rendered = b"# TYPE gauge_total gauge\ngauge_total 1.0\n"
    text = nms.with_node_snapshot(rendered).decode()
    assert 'gauge_total{process="node",chain="bc-2"} 5.0' in text


def test_with_node_snapshot_process_label_not_duplicated(snap: Path) -> None:
    """A sample already tagged process= is left alone — no double label."""
    _foreign_snapshot(snap, 'odd_total{process="other"} 5.0\n')
    rendered = b"# TYPE odd_total counter\nodd_total 1.0\n"
    text = nms.with_node_snapshot(rendered).decode()
    assert 'odd_total{process="other"} 5.0' in text
    assert 'process="node",process=' not in text


def test_merged_exposition_parses_without_duplicate_families() -> None:
    """The merged output must be valid text format with no family emitted
    twice and no identical series — checked with the real Prometheus
    parser. #2504: the shared counter now appears as TWO series — the
    RPC process's untagged value and the node's tagged one."""
    from prometheus_client.parser import text_string_to_metric_families

    rendered = b"# TYPE sync_reorgs_total counter\nsync_reorgs_total 2.0\n# TYPE node_only_gauge gauge\nnode_only_gauge 5.0\n"
    snapshot = (
        "# TYPE sync_reorgs_total counter\nsync_reorgs_total 40.0\n# TYPE gossip_mesh_peer gauge\ngossip_mesh_peer 7.0\n"
    )
    with patch.object(nms, "read_snapshot", return_value=snapshot):
        out = nms.with_node_snapshot(rendered)
    families = list(text_string_to_metric_families(out.decode()))
    names = [f.name for f in families]
    assert len(names) == len(set(names)), f"duplicate families: {names}"
    samples = [s for f in families for s in f.samples]
    keys = [(s.name, tuple(sorted(s.labels.items()))) for s in samples]
    assert len(keys) == len(set(keys)), f"duplicate samples: {keys}"
    by_series = {(s.name, tuple(sorted(s.labels.items()))): s.value for s in samples}
    assert by_series[("sync_reorgs_total", ())] == 2.0  # RPC process value
    assert by_series[("sync_reorgs_total", (("process", "node"),))] == 40.0  # node value survives
    assert by_series[("gossip_mesh_peer", (("process", "node"),))] == 7.0  # node-only series survives
