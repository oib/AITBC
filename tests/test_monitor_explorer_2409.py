"""#2409 pins: alert-history default cap + explorer activity-timeline period.

- ``prometheus alert-history`` used to dump the whole alert log (~4 MB on
  node0) which MCP clients reject; it now caps returned events at 50 by
  default while still reporting the true matched total.
- ``explorer activity-timeline --period`` sent the period string verbatim;
  the API only understands ``days``, so "24h" silently returned 30 days of
  daily buckets under a "24h" label. The CLI now maps period -> days and
  prints the truthful window.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from aitbc_cli.commands import explorer as explorer_mod
from aitbc_cli.commands import prometheus as prom


def _history_event(i: int) -> dict:
    return {
        "timestamp": f"2026-11-21T{i % 24:02d}:00:00",
        "timestamp_unix": 1700000000 + i,
        "alertname": f"Alert{i}",
        "state": "firing",
        "labels": {"instance": "a"},
    }


def _write_log(tmp_path: Path, n: int) -> Path:
    log = tmp_path / "alerts.log"
    log.write_text("".join(json.dumps(_history_event(i)) + "\n" for i in range(n)))
    return log


def _history(tmp_path: Path, *args: str):
    log = _write_log(tmp_path, 60)
    result = CliRunner().invoke(
        prom.prometheus,
        ["alert-history", "--path", str(log), *args],
        obj={"output_format": "json", "config": None},
    )
    return result, json.loads(result.output)


class TestAlertHistoryDefaultCap:
    def test_bare_call_caps_at_50_and_flags_truncation(self, tmp_path):
        result, out = _history(tmp_path)
        assert result.exit_code == 0
        assert out["matched_events"] == 60
        assert out["returned_events"] == 50
        assert out["limit"] == 50
        assert out["truncated"] is True
        assert len(out["events"]) == 50
        # newest 50 kept
        assert out["events"][-1]["alertname"] == "Alert59"

    def test_last_zero_means_unlimited(self, tmp_path):
        _, out = _history(tmp_path, "--last", "0")
        assert out["returned_events"] == 60
        assert out["truncated"] is False

    def test_explicit_last_still_wins(self, tmp_path):
        _, out = _history(tmp_path, "--last", "10")
        assert out["returned_events"] == 10
        assert out["matched_events"] == 60


class _FakeClient:
    def __init__(self):
        self.calls: list[dict] = []

    def get(self, path, params=None):
        self.calls.append({"path": path, "params": params})
        return {"labels": ["2026-11-21"], "datasets": []}


@pytest.fixture
def fake_explorer_client(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(explorer_mod, "get_explorer_client", lambda: client)
    return client


class TestActivityTimelinePeriod:
    @pytest.mark.parametrize(
        ("period", "days"),
        [("1h", 1), ("24h", 1), ("7d", 7), ("30d", 30)],
    )
    def test_period_maps_to_days(self, fake_explorer_client, period, days):
        result = CliRunner().invoke(explorer_mod.explorer, ["activity-timeline", "--period", period])
        assert result.exit_code == 0, result.output
        call = fake_explorer_client.calls[-1]
        assert call["path"] == "/api/analytics/activity"
        assert call["params"]["days"] == days
        assert f"last {days} day" in result.output

    def test_chain_id_still_passes(self, fake_explorer_client):
        result = CliRunner().invoke(explorer_mod.explorer, ["activity-timeline", "--period", "7d", "--chain-id", "ait-2"])
        assert result.exit_code == 0, result.output
        assert fake_explorer_client.calls[-1]["params"]["chain_id"] == "ait-2"

    def test_invalid_period_rejected(self):
        result = CliRunner().invoke(explorer_mod.explorer, ["activity-timeline", "--period", "2w"])
        assert result.exit_code != 0
