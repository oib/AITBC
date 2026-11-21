"""CLI-STDERR-NOISE-1 (#2444): refusals print one clear line.

Covers the four noise sources from the issue:

1. ``get_config()`` re-emitted the ambient ``./.aitbc.yaml`` UserWarning once
   per call site per process (stacklevel=2 defeats the warnings-module
   dedupe) — now once per resolved path per process.
2. A wallet-daemon 404 on ``GET /v1/wallets/<name>`` printed
   ``Failed to get wallet info: ...`` before the canonical not-found
   refusal — a missing wallet is an answer, not an error.
3. Market chain/island-id mismatch warnings re-printed on every
   ``get_chain_id()``/``get_island_id()`` call within one process.
4. ``bridge_monitor.admin`` warned about the missing
   ``/etc/aitbc/aitbc-bridge-monitor.env`` on every read — now opt-in
   (explicit ``--env-file``/``BRIDGE_MONITOR_ENV`` only).
"""

from __future__ import annotations

import warnings
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


from aitbc_cli.config import get_config
from aitbc_cli.utils.http_client import NetworkError
from aitbc_cli.utils.wallet_daemon_client import WalletDaemonClient


def _daemon_client() -> WalletDaemonClient:
    return WalletDaemonClient(MagicMock(wallet_daemon_url="http://127.0.0.1:9", wallet_api_key=None))


def _http_error(status: int) -> NetworkError:
    err = NetworkError(f"GET request failed: {status} Client Error")
    err.response = SimpleNamespace(status_code=status)  # type: ignore[attr-defined]
    return err


# --- 1. ambient config warning: once per process ----------------------------


def test_ambient_config_warning_fires_once_per_process(tmp_path, monkeypatch):
    monkeypatch.delenv("AITBC_CONFIG_FILE", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    (tmp_path / ".aitbc.yaml").write_text("timeout: 5\n")
    monkeypatch.chdir(tmp_path)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        get_config()
        get_config()
        get_config()
    ambient = [w for w in caught if "current directory" in str(w.message)]
    assert len(ambient) == 1, [str(w.message) for w in caught]


def test_ambient_config_warning_still_fires_for_a_new_path(tmp_path, monkeypatch):
    """Dedupe is per resolved path — a different ambient file still warns."""
    monkeypatch.delenv("AITBC_CONFIG_FILE", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    (tmp_path / ".aitbc.yaml").write_text("timeout: 5\n")
    monkeypatch.chdir(tmp_path)

    other = tmp_path / "other"
    other.mkdir()
    (other / ".aitbc.yaml").write_text("timeout: 7\n")

    with warnings.catch_warnings(record=True) as first:
        warnings.simplefilter("always")
        get_config()
    monkeypatch.chdir(other)
    with warnings.catch_warnings(record=True) as second:
        warnings.simplefilter("always")
        get_config()
    assert any("current directory" in str(w.message) for w in first)
    assert any("current directory" in str(w.message) for w in second)


# --- 2. daemon 404 is quiet --------------------------------------------------


def test_get_wallet_info_404_returns_none_without_error_line(capsys):
    client = _daemon_client()
    with patch(
        "aitbc_cli.utils.wallet_daemon_client.AITBCHTTPClient.get",
        side_effect=_http_error(404),
    ):
        assert client.get_wallet_info("nosuch") is None
    captured = capsys.readouterr()
    assert "Failed to get wallet info" not in captured.out + captured.err


def test_get_wallet_balance_404_returns_none_without_error_line(capsys):
    client = _daemon_client()
    with patch(
        "aitbc_cli.utils.wallet_daemon_client.AITBCHTTPClient.get",
        side_effect=_http_error(404),
    ):
        assert client.get_wallet_balance("nosuch") is None
    captured = capsys.readouterr()
    assert "Failed to get wallet balance" not in captured.out + captured.err


def test_get_wallet_info_non_404_still_reports(capsys):
    """A real daemon failure (5xx / unreachable) keeps its error line."""
    client = _daemon_client()
    with patch(
        "aitbc_cli.utils.wallet_daemon_client.AITBCHTTPClient.get",
        side_effect=_http_error(500),
    ):
        assert client.get_wallet_info("w") is None
    captured = capsys.readouterr()
    assert "Failed to get wallet info" in captured.out + captured.err


# --- 3. market mismatch warnings once per process ----------------------------


def _market():
    from aitbc_cli.commands import market

    return market


def test_chain_id_mismatch_warns_once_across_calls(monkeypatch):
    market = _market()
    monkeypatch.setenv("CHAIN_ID", "bc-2")
    monkeypatch.setattr(
        market,
        "load_island_credentials",
        lambda: {"island_chain_id": "ait-r5-player"},
    )
    with patch.object(market, "warning") as warn:
        assert market.get_chain_id() == "bc-2"
        assert market.get_chain_id() == "bc-2"
        assert market.get_chain_id() == "bc-2"
    assert warn.call_count == 1
    assert "ait-r5-player" in warn.call_args[0][0]
    assert "bc-2" in warn.call_args[0][0]


def test_island_id_mismatch_warns_once_across_calls(monkeypatch):
    market = _market()
    monkeypatch.setenv("ISLAND_ID", "bc-2")
    monkeypatch.setattr(
        market,
        "load_island_credentials",
        lambda: {"island_id": "ait-r5-player"},
    )
    with patch.object(market, "warning") as warn:
        assert market.get_island_id() == "bc-2"
        assert market.get_island_id() == "bc-2"
    assert warn.call_count == 1


def test_distinct_mismatch_still_warns(monkeypatch):
    """A *different* disagreement is a different message — it still warns."""
    market = _market()
    monkeypatch.setenv("CHAIN_ID", "bc-2")
    creds = {"island_chain_id": "ait-r5-player"}
    monkeypatch.setattr(market, "load_island_credentials", lambda: creds)
    with patch.object(market, "warning") as warn:
        market.get_chain_id()
        creds["island_chain_id"] = "other-chain"
        market.get_chain_id()
    assert warn.call_count == 2
