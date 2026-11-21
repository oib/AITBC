"""#2221: monitor alerts/webhooks files must not accumulate same-name rows.

``alerts add`` / ``webhooks add`` used to append unconditionally, so
re-adding a name produced duplicate rows that ``list`` showed side by
side. Names are now the identity: add upserts (replaces every same-name
row) and reports "updated" when it did.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from aitbc_cli.commands import monitor as monitor_mod


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def alerts_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path / ".aitbc" / "alerts" / "alerts.json"


@pytest.fixture
def webhooks_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path / ".aitbc" / "webhooks" / "webhooks.json"


def _add_alert(runner, name="miner-watch"):
    return runner.invoke(
        monitor_mod.monitor,
        obj={"output_format": "table"},
        args=["alerts", "add", "--name", name, "--type", "miner_offline", "--threshold", "1"],
    )


def test_alerts_add_dedupes_by_name(runner, alerts_home):
    assert _add_alert(runner).exit_code == 0
    second = _add_alert(runner)
    assert second.exit_code == 0
    assert "updated" in second.output

    rows = json.loads(alerts_home.read_text())
    assert [a["name"] for a in rows] == ["miner-watch"]


def test_alerts_add_collapses_legacy_duplicates(runner, alerts_home):
    alerts_home.parent.mkdir(parents=True)
    alerts_home.write_text(
        json.dumps(
            [
                {"name": "miner-watch", "type": "miner_offline"},
                {"name": "other", "type": "job_failed"},
                {"name": "miner-watch", "type": "miner_offline"},
            ]
        )
    )

    result = _add_alert(runner)
    assert result.exit_code == 0

    rows = json.loads(alerts_home.read_text())
    assert [a["name"] for a in rows] == ["other", "miner-watch"]


def test_alerts_remove_drops_every_same_name_row(runner, alerts_home):
    alerts_home.parent.mkdir(parents=True)
    alerts_home.write_text(
        json.dumps(
            [
                {"name": "miner-watch", "type": "miner_offline"},
                {"name": "other", "type": "job_failed"},
                {"name": "miner-watch", "type": "coordinator_down"},
            ]
        )
    )

    result = runner.invoke(
        monitor_mod.monitor, obj={"output_format": "table"}, args=["alerts", "remove", "--name", "miner-watch"]
    )
    assert result.exit_code == 0

    rows = json.loads(alerts_home.read_text())
    assert [a["name"] for a in rows] == ["other"]


def test_webhooks_add_dedupes_by_name(runner, webhooks_home):
    args = ["webhooks", "add", "--name", "hook-1", "--url", "https://example.com/hook"]
    assert runner.invoke(monitor_mod.monitor, obj={"output_format": "table"}, args=args).exit_code == 0
    second = runner.invoke(
        monitor_mod.monitor,
        obj={"output_format": "table"},
        args=["webhooks", "add", "--name", "hook-1", "--url", "https://example.com/hook2"],
    )
    assert second.exit_code == 0
    assert "updated" in second.output

    rows = json.loads(webhooks_home.read_text())
    assert len(rows) == 1
    assert rows[0]["url"] == "https://example.com/hook2"


def test_alerts_list_collapses_legacy_duplicate_names(runner, alerts_home):
    """#2409: legacy alerts.json rows with duplicate names are collapsed on
    any action — names are the identity, last (newest) row wins."""
    alerts_home.parent.mkdir(parents=True, exist_ok=True)
    alerts_home.write_text(
        json.dumps(
            [
                {"name": "probe", "type": "miner_offline", "created_at": "2026-10-25"},
                {"name": "probe", "type": "job_failed", "created_at": "2026-10-26"},
                {"name": "other", "type": "low_balance"},
            ]
        )
    )

    result = runner.invoke(monitor_mod.monitor, obj={"output_format": "table"}, args=["alerts", "list"])
    assert result.exit_code == 0

    rows = json.loads(alerts_home.read_text())
    assert [a["name"] for a in rows] == ["probe", "other"]
    # last duplicate wins — the newest row survives
    assert rows[0]["type"] == "job_failed"
