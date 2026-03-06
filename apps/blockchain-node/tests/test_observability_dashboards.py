"""Tests for the observability dashboard helpers."""

from __future__ import annotations

import json
from pathlib import Path

from aitbc_chain.observability.dashboards import generate_default_dashboards
from aitbc_chain.observability import exporters


def test_generate_default_dashboards_creates_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "dashboards"

    generate_default_dashboards(output_dir, datasource_uid="prometheus")

    expected_files = {
        "blockchain-node-overview.json",
        "coordinator-overview.json",
    }
    actual_files = {path.name for path in output_dir.glob("*.json")}

    assert actual_files == expected_files

    for file_path in output_dir.glob("*.json"):
        with file_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        assert payload["uid"] in {"aitbc-coordinator", "aitbc-node"}
        assert payload["title"].startswith("AITBC")
        assert payload["panels"], "Dashboard should contain at least one panel"


def test_register_exporters_tracks_names() -> None:
    exporters.REGISTERED_EXPORTERS.clear()

    exporters.register_exporters(["prometheus", "loki"])

    assert exporters.REGISTERED_EXPORTERS == ["prometheus", "loki"]
