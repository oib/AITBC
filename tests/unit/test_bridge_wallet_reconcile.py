"""Fixture tests for scripts/ops/bridge_wallet_reconcile.py."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ops"))
import bridge_wallet_reconcile as bwr  # noqa: E402

WEI = 10**18


def _db(path: Path, rows: list[tuple[str, str]]) -> None:
    """rows: (status, amount_eth)."""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE eth_deposits (id TEXT PRIMARY KEY, status TEXT NOT NULL, amount_eth NUMERIC NOT NULL)")
    con.executemany(
        "INSERT INTO eth_deposits (id,status,amount_eth) VALUES (?,?,?)",
        [(f"d{i}", s, a) for i, (s, a) in enumerate(rows)],
    )
    con.commit()
    con.close()


def _onchain(tmp_path: Path, balance_wei: int, **outbound) -> Path:
    p = tmp_path / "outbound.json"
    p.write_text(json.dumps({"wallet_balance_wei": str(balance_wei), "outbound": outbound}))
    return p


def _run(tmp_path: Path, rows: list[tuple[str, str]], balance_wei: int, **outbound) -> int:
    db = tmp_path / "ledger.db"
    _db(db, rows)
    oc = _onchain(tmp_path, balance_wei, **outbound)
    return bwr.main(["--ledger", str(db), "--onchain", str(oc)])


_ROWS = [
    ("completed", "0.5"),
    ("completed", "0.25"),
    ("pending_retry", "0.1"),
    ("funding", "1.0"),
]


def test_balanced(tmp_path, capsys):
    # inflows 1.85 ETH; outbound gas+refund 0.35 ETH; balance 1.5 ETH
    rc = _run(tmp_path, _ROWS, int(1.5 * WEI), refunds_wei=str(int(0.3 * WEI)), gas_wei=str(int(0.05 * WEI)))
    out = capsys.readouterr().out
    assert rc == 0
    assert "VERDICT: BALANCED" in out
    assert "funding" in out  # funding rows listed as their own class


def test_deficit(tmp_path, capsys):
    # balance short by 0.5 ETH vs ledger explanation
    rc = _run(tmp_path, _ROWS, int(1.35 * WEI))
    out = capsys.readouterr().out
    assert rc == 1
    assert "VERDICT: DEFICIT" in out
    assert "500000000000000000 wei" in out
    assert "0.5 ETH" in out


def test_surplus(tmp_path, capsys):
    # wallet holds more than ledger explains (e.g. unledgered inbound)
    rc = _run(tmp_path, _ROWS, int(2.0 * WEI))
    out = capsys.readouterr().out
    assert rc == 1
    assert "VERDICT: SURPLUS" in out
    assert "150000000000000000 wei" in out


def test_header_states_ledger_gap(tmp_path, capsys):
    rc = _run(tmp_path, _ROWS, int(1.85 * WEI))
    out = capsys.readouterr().out
    assert rc == 0
    assert "no ledger rows" in out
    assert "not proof" in out


def test_empty_ledger_any_balance_is_surplus(tmp_path, capsys):
    rc = _run(tmp_path, [], int(0.1 * WEI))
    out = capsys.readouterr().out
    assert rc == 1
    assert "SURPLUS" in out


def test_missing_balance_field_errors(tmp_path):
    db = tmp_path / "ledger.db"
    _db(db, _ROWS)
    oc = tmp_path / "outbound.json"
    oc.write_text(json.dumps({"outbound": {}}))
    with pytest.raises(SystemExit):
        bwr.main(["--ledger", str(db), "--onchain", str(oc)])
