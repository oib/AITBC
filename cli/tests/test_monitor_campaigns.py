"""TOOL-1: ``aitbc monitor campaigns`` / ``campaign-stats`` must not write.

Both commands are read-only listings: they must not create the campaigns
file when it is absent, and must not rewrite it when expired campaigns are
folded to ``ended`` — that computation happens in memory only.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner

from aitbc_cli.commands import monitor as monitor_mod


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def campaigns_dir(tmp_path, monkeypatch):
    """Point the campaigns store at a private tmp dir."""
    d = tmp_path / "campaigns"
    monkeypatch.setattr(monitor_mod, "CAMPAIGNS_DIR", d)
    return d


def _invoke(runner, *args):
    return runner.invoke(monitor_mod.campaigns, list(args), obj={"output_format": "json"})


def _invoke_stats(runner, *args):
    return runner.invoke(monitor_mod.campaign_stats, list(args), obj={"output_format": "json"})


class TestAbsentFile:
    def test_absent_file_stays_absent(self, runner, campaigns_dir):
        result = _invoke(runner)
        assert result.exit_code == 0, result.output
        assert not (campaigns_dir / "campaigns.json").exists()
        assert not campaigns_dir.exists()  # directory must not be created either

    def test_absent_file_lists_defaults(self, runner, campaigns_dir):
        result = _invoke(runner)
        assert result.exit_code == 0, result.output
        campaigns = json.loads(result.output)
        assert any(c["id"] == "staking_launch" for c in campaigns)

    def test_campaign_stats_absent_file(self, runner, campaigns_dir):
        result = _invoke_stats(runner)
        assert result.exit_code == 0, result.output
        assert not campaigns_dir.exists()


class TestExistingFile:
    def _write_campaigns(self, campaigns_dir, campaigns):
        campaigns_dir.mkdir(parents=True)
        f = campaigns_dir / "campaigns.json"
        f.write_text(json.dumps({"campaigns": campaigns}, indent=2))
        return f

    def test_existing_file_byte_identical(self, runner, campaigns_dir):
        past = (datetime.now() - timedelta(days=10)).isoformat()
        older = (datetime.now() - timedelta(days=40)).isoformat()
        f = self._write_campaigns(
            campaigns_dir,
            [
                {
                    "id": "expired_one",
                    "name": "Expired",
                    "type": "staking",
                    "apy_boost": 1.0,
                    "start_date": older,
                    "end_date": past,
                    "status": "active",
                    "total_staked": 0,
                    "participants": 0,
                    "rewards_distributed": 0,
                }
            ],
        )
        before = f.read_bytes()

        result = _invoke(runner, "--status", "all")
        assert result.exit_code == 0, result.output
        # expired campaign still shows as ended in output
        assert json.loads(result.output)[0]["status"] == "ended"
        # but the file is untouched
        assert f.read_bytes() == before

    def test_campaign_stats_existing_file_unchanged(self, runner, campaigns_dir):
        past = (datetime.now() - timedelta(days=10)).isoformat()
        older = (datetime.now() - timedelta(days=40)).isoformat()
        f = self._write_campaigns(
            campaigns_dir,
            [
                {
                    "id": "expired_one",
                    "name": "Expired",
                    "type": "staking",
                    "apy_boost": 1.0,
                    "start_date": older,
                    "end_date": past,
                    "status": "active",
                    "total_staked": 5,
                    "participants": 3,
                    "rewards_distributed": 0,
                }
            ],
        )
        before = f.read_bytes()
        result = _invoke_stats(runner, "expired_one")
        assert result.exit_code == 0, result.output
        assert f.read_bytes() == before
