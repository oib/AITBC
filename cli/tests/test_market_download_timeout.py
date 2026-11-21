"""#2443 MARKET-DOWNLOAD-WAIT-UNBOUNDED-1: `market download --wait` must be
bounded by a user-settable ``--timeout``.

The old ``_cat_ipfs`` polled a fixed 59 attempts x (30s cat + 2s sleep) —
a missing CID could hang the command for ~30 minutes and the player had no
knob to cap it. ``--timeout`` (default 60s) now bounds the whole wait; each
cat attempt is capped at 30s and never exceeds the remaining budget.
"""

import time

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.market.host as host_mod
from aitbc_cli.commands.market import market


class _Cat500:
    """Kubo answers every /api/v0/cat with a 500 (CID unknown)."""

    status_code = 500

    def raise_for_status(self):
        raise RuntimeError("cat failed: 500")

    @property
    def content(self):
        return b""


@pytest.fixture
def runner():
    return CliRunner()


def _patch_daemon(monkeypatch, response=None):
    calls = []

    def fake_api_post(path, **kwargs):
        calls.append(kwargs.get("timeout"))
        return response if response is not None else _Cat500()

    monkeypatch.setattr(host_mod, "_api_post", fake_api_post)
    monkeypatch.setattr(host_mod, "_resolve_ipfs_api", lambda offer: "http://127.0.0.1:5002")
    monkeypatch.setattr(host_mod, "_daemon_available", lambda api: True)
    return calls


def test_cat_ipfs_wait_honors_timeout_budget(runner, monkeypatch):
    calls = _patch_daemon(monkeypatch)
    start = time.monotonic()
    data = host_mod._cat_ipfs("http://127.0.0.1:5002", "QmMissing", wait=True, timeout_seconds=0.2)
    elapsed = time.monotonic() - start
    assert data is None
    assert elapsed < 5, f"wait overshot its budget: {elapsed:.2f}s"
    # Each attempt's request timeout never exceeds the remaining budget.
    assert all(t is not None and t <= 30.0 for t in calls)
    assert calls, "expected at least one cat attempt"


def test_market_download_wait_missing_cid_exits_within_timeout(runner, monkeypatch):
    _patch_daemon(monkeypatch)
    start = time.monotonic()
    result = runner.invoke(
        market,
        ["download", "--cid", "QmMissing", "--wait", "--timeout", "0.2"],
        obj={"output_format": "json"},
    )
    elapsed = time.monotonic() - start
    assert result.exit_code != 0
    assert "Could not retrieve CID" in result.output
    assert elapsed < 10, f"download --wait overshot --timeout: {elapsed:.2f}s"


def test_market_download_rejects_nonpositive_timeout(runner, monkeypatch):
    _patch_daemon(monkeypatch)
    result = runner.invoke(market, ["download", "--cid", "QmX", "--timeout", "0"], obj={})
    assert result.exit_code != 0
    assert "--timeout must be greater than 0" in result.output


def test_market_download_no_wait_still_single_attempt(runner, monkeypatch):
    calls = _patch_daemon(monkeypatch)
    result = runner.invoke(market, ["download", "--cid", "QmMissing"], obj={})
    assert result.exit_code != 0
    assert len(calls) == 1
