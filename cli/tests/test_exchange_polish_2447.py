"""EXCHANGE-CLI-POLISH-1 (#2447): monitor --real-time actually loops,
set-payout reports a clean invalid-address error (no web3 internals), and
add-liquidity states the unit each side is denominated in.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Scratch HOME with a registered fixture exchange + AIT/ETH pair."""
    aitbc_dir = tmp_path / ".aitbc"
    aitbc_dir.mkdir()
    (aitbc_dir / "exchanges.json").write_text(
        json.dumps(
            {
                "fixturex": {
                    "name": "fixturex",
                    "status": "registered",
                    "sandbox": True,
                    "created_at": "2026-11-21T00:00:00+00:00",
                    "trading_pairs": [
                        {
                            "symbol": "AIT/ETH",
                            "trading_enabled": True,
                            "created_at": "2026-11-21T00:00:00+00:00",
                            "started_at": "2026-11-21T00:01:00+00:00",
                            "initial_price": "0.0001",
                            "base_liquidity": "5000",
                            "quote_liquidity": "0.5",
                        }
                    ],
                }
            }
        )
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _exchanges(home: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((home / ".aitbc" / "exchanges.json").read_text()))


# --- monitor --real-time -----------------------------------------------------


def test_monitor_real_time_loops_and_rereads(runner, home, monkeypatch):
    from aitbc_cli.commands.exchange import main as ex_main
    from aitbc_cli.commands.exchange.main import exchange

    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise KeyboardInterrupt
        # Between ticks the file changes — the loop must re-read it.
        doc = _exchanges(home)
        doc["fixturex"]["trading_pairs"][0]["quote_liquidity"] = "9.9"
        (home / ".aitbc" / "exchanges.json").write_text(json.dumps(doc))

    monkeypatch.setattr(ex_main.time, "sleep", fake_sleep)
    result = runner.invoke(exchange, ["monitor", "--real-time", "--interval", "30"])
    assert result.exit_code == 0, result.output
    out = result.output
    # Two snapshots printed; the second reflects the rewritten file.
    assert out.count('"monitoring_active": true') == 2
    assert '"quote_liquidity": "9.9"' in out
    assert "Re-scanning every 30 seconds" in out
    assert "Monitoring stopped." in out


def test_monitor_real_time_ctrl_c_on_first_sleep(runner, home, monkeypatch):
    from aitbc_cli.commands.exchange import main as ex_main
    from aitbc_cli.commands.exchange.main import exchange

    monkeypatch.setattr(ex_main.time, "sleep", lambda s: (_ for _ in ()).throw(KeyboardInterrupt))
    result = runner.invoke(exchange, ["monitor", "--real-time", "--interval", "5"])
    assert result.exit_code == 0, result.output
    assert "Monitoring stopped." in result.output


def test_monitor_without_real_time_prints_once(runner, home, monkeypatch):
    from aitbc_cli.commands.exchange import main as ex_main
    from aitbc_cli.commands.exchange.main import exchange

    def fail_sleep(s):
        raise AssertionError("sleep must not run without --real-time")

    monkeypatch.setattr(ex_main.time, "sleep", fail_sleep)
    result = runner.invoke(exchange, ["monitor"])
    assert result.exit_code == 0, result.output
    assert result.output.count('"monitoring_active"') == 1


def test_monitor_rejects_zero_interval(runner, home):
    from aitbc_cli.commands.exchange.main import exchange

    result = runner.invoke(exchange, ["monitor", "--real-time", "--interval", "0"])
    assert result.exit_code != 0
    assert "--interval must be at least 1" in result.output


# --- add-liquidity units ------------------------------------------------------


def test_add_liquidity_buy_reports_quote_units(runner, home):
    from aitbc_cli.commands.exchange.main import exchange

    result = runner.invoke(
        exchange,
        ["add-liquidity", "--pair", "AIT/ETH", "--amount", "100", "--side", "buy", "--exchange", "fixturex"],
    )
    assert result.exit_code == 0, result.output
    assert "(buy side): 100 ETH" in result.output
    pair = _exchanges(home)["fixturex"]["trading_pairs"][0]
    assert pair["quote_liquidity"] == "100.5"
    assert pair["base_liquidity"] == "5000"


def test_add_liquidity_sell_reports_base_units(runner, home):
    from aitbc_cli.commands.exchange.main import exchange

    result = runner.invoke(
        exchange,
        ["add-liquidity", "--pair", "AIT/ETH", "--amount", "25", "--side", "sell", "--exchange", "fixturex"],
    )
    assert result.exit_code == 0, result.output
    assert "(sell side): 25 AIT" in result.output
    pair = _exchanges(home)["fixturex"]["trading_pairs"][0]
    assert pair["base_liquidity"] == "5025"
    assert pair["quote_liquidity"] == "0.5"


def test_add_liquidity_both_is_a_valid_side_and_reports_both_units(runner, home):
    from aitbc_cli.commands.exchange.main import exchange

    result = runner.invoke(
        exchange,
        ["add-liquidity", "--pair", "AIT/ETH", "--amount", "10", "--side", "both", "--exchange", "fixturex"],
    )
    assert result.exit_code == 0, result.output
    assert "10 AIT + 10 ETH" in result.output
    pair = _exchanges(home)["fixturex"]["trading_pairs"][0]
    assert pair["base_liquidity"] == "5010"
    assert pair["quote_liquidity"] == "10.5"


def test_add_liquidity_json_output_carries_unit(runner, home):
    from aitbc_cli.commands.exchange.main import exchange

    result = runner.invoke(
        exchange,
        ["add-liquidity", "--pair", "AIT/ETH", "--amount", "5", "--side", "buy", "--exchange", "fixturex"],
        obj={"output_format": "json"},
    )
    assert result.exit_code == 0, result.output
    # success() status lines share the mixed stream; the JSON doc starts at
    # the first '{'.
    data = json.loads(result.output[result.output.index("{") :])
    assert data["unit"] == "ETH"
    assert data["amount"] == "5"


# --- set-payout invalid address ----------------------------------------------


def test_set_payout_invalid_address_is_clean(runner):
    from aitbc_cli.commands.exchange.hub_orders import node

    result = runner.invoke(
        node,
        ["set-payout", "--eth-address", "notanaddress"],
        obj={"output_format": "json"},
    )
    # Invoking the group directly surfaces the CLIError (exit_code lives in
    # the payload; the real entrypoint maps it to process exit 4).
    assert result.exit_code == 1
    payload = json.loads(result.output[result.output.index("{") :])
    assert payload["error"] == "ValidationError"
    assert payload["exit_code"] == 4
    assert "Invalid --eth-address" in payload["message"]
    # The web3/eth-utils internal must not leak into the error detail.
    assert "hex string" not in result.output
    assert payload["detail"] == "invalid hex address"
