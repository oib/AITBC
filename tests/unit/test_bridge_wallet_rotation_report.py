"""Fixture tests for scripts/ops/bridge_wallet_rotation_report.py (BR-6/B13).

The fixture is the real September/October rotation, static data only: four
September deposits landed on the old wallet while the ledger names the
current one, an unledgered refund left the old wallet on 29 Sep, and a
7 Oct operator sweep moved the float to the current wallet.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ops"))
import bridge_wallet_rotation_report as bwr  # noqa: E402

OLD = "0x09362894C18f7CbCdb85b124ef4c8F63DEC09B32"
CUR = "0x310dcE00270D0aC10CAccfBD636Ff07BD5648781"
REFUND_RECIPIENT = "0x5e1f5e1f5e1f5e1f5e1f5e1f5e1f5e1f5e1f5e1f"
DEPOSITOR2 = "0xF1C83cd90e4d33F35BE73Dd57CaBa21Ea52D4584"
RECEIVER = "0xCf1719140054AB3fD52ce8aa3128dec9317426E3"

SWEEP = "0x134243962cecb75f9e1cdda45c447e96044816eadbd6f77726d65a566f8bb3b4"
OOG = "0xe635238c1e1f4f31ec2daa05b33f8fc478adf0b48de70f1562d0a67f14f0fef7"
OCT_DEP = "0xe7bc66e8d463e67f9096e9f6b2b358cb3be56a7b4db3ef2291a2f134d5152acc"
REL1 = "0x7b7eaec36e2da95684b1618480c0f0e46c5019bf524af6dde3a93876f6e040ba"
REL2 = "0x38b1fa3387b073c4495da7fa788b16cde6e5db683485a2c9d0c9daa7a70d342f"

OLD_DEFICIT_WEI = 52335372406592269
OLD_RESIDUAL_WEI = 2375372406592269
SWEEP_WEI = 50664627593407731
WALLETS = {OLD.lower(): OLD, CUR.lower(): CUR}


def _tx(tx_hash, frm, to, value_wei, status=1, gas_used=None, gas_price=None):
    tx = {"tx_hash": tx_hash, "from": frm, "to": to, "value_wei": str(value_wei), "status": status}
    if gas_used is not None:
        tx["gas_used"] = gas_used
        tx["gas_price_wei"] = gas_price
    return tx


def _ledger(tmp_path: Path, with_deposit_address: bool = True) -> Path:
    db = tmp_path / "ledger.db"
    con = sqlite3.connect(db)
    dep_addr = ", deposit_address TEXT" if with_deposit_address else ""
    con.execute(
        "CREATE TABLE eth_deposits (id TEXT PRIMARY KEY, tx_hash TEXT, from_address TEXT, "
        f"amount_eth NUMERIC, status TEXT{dep_addr})"
    )
    dep_col = ", deposit_address" if with_deposit_address else ""
    rows = [
        ("dep_mig", "0x" + "11" * 32, REFUND_RECIPIENT, "0.05", "written_off"),
        ("dep_top", "0x" + "22" * 32, "0x" + "99" * 20, "0.05", "written_off"),
        ("dep_c1", "0x" + "33" * 32, "0x" + "88" * 20, "0.0015", "completed"),
        ("dep_c2", "0x" + "44" * 32, "0x" + "77" * 20, "0.0015", "completed"),
        ("dep_oct", OCT_DEP, DEPOSITOR2, "0.002", "completed"),
    ]
    for r in rows:
        if with_deposit_address:
            con.execute(
                f"INSERT INTO eth_deposits (id, tx_hash, from_address, amount_eth, status{dep_col}) VALUES (?,?,?,?,?,?)",
                (*r, CUR),
            )
        else:
            con.execute("INSERT INTO eth_deposits (id, tx_hash, from_address, amount_eth, status) VALUES (?,?,?,?,?)", r)
    con.execute(
        "CREATE TABLE eth_withdrawals (id TEXT PRIMARY KEY, ait_tx_hash TEXT, amount_eth NUMERIC, "
        "status TEXT, eth_tx_hash TEXT)"
    )
    con.execute("INSERT INTO eth_withdrawals VALUES ('w1','ait1','0.00111306005378485','completed',?)", (REL1,))
    con.execute("INSERT INTO eth_withdrawals VALUES ('w2','ait2','0.000561464253630614','completed',?)", (REL2,))
    con.commit()
    con.close()
    return db


def _txs() -> list[dict]:
    return [
        _tx("0x" + "11" * 32, REFUND_RECIPIENT, OLD, "50000000000000000"),
        _tx("0x" + "22" * 32, "0x" + "99" * 20, OLD, "50000000000000000"),
        _tx("0x" + "33" * 32, "0x" + "88" * 20, OLD, "1500000000000000"),
        _tx("0x" + "44" * 32, "0x" + "77" * 20, OLD, "1500000000000000"),
        _tx("0x" + "55" * 32, OLD, REFUND_RECIPIENT, "49960000000000000", gas_used=21000, gas_price="1000020"),
        _tx(OOG, OLD, CUR, "50664847597807731", status=0, gas_used=21000, gas_price="1000017"),
        _tx(SWEEP, OLD, CUR, str(SWEEP_WEI), gas_used=204600, gas_price="1000020"),
        _tx(OCT_DEP, DEPOSITOR2, CUR, "2000000000000000", gas_used=23688, gas_price="1000004"),
        _tx(REL1, CUR, RECEIVER, "1113060053784850", gas_used=204600, gas_price="940005"),
        _tx(REL2, CUR, RECEIVER, "561464253630614", gas_used=21000, gas_price="1000061"),
    ]


def _analyze(tmp_path: Path):
    ledger = bwr._load_ledger(_ledger(tmp_path))
    return bwr.analyze(_txs(), ledger["deposits"], ledger["depositors"], ledger["withdrawals"], set(), WALLETS, CUR.lower())


def _main(tmp_path: Path, capsys) -> tuple[int, str]:
    txs_path = tmp_path / "txs.json"
    txs_path.write_text(json.dumps(_txs()))
    rc = bwr.main(
        [
            "--ledger",
            str(_ledger(tmp_path)),
            "--txs",
            str(txs_path),
            "--wallets",
            f"{OLD},{CUR}",
            "--current-wallet",
            CUR,
        ]
    )
    return rc, capsys.readouterr().out


def test_old_deficit_decomposes_to_nothing(tmp_path):
    books, _, flags = _analyze(tmp_path)
    cur = books[CUR.lower()]
    assert cur.expected_in == 105000000000000000  # 5 deposits attributed (0.105 ETH)
    assert cur.expected_out == 1674524307415464  # the two releases
    assert cur.residual == -OLD_DEFICIT_WEI
    # 0.103 expected-never-arrived minus 0.0507 arrived-unexpected, fully
    # decomposed once rotation is modelled — no unexplained remainder.
    assert cur.residual - sum(d for d, _ in cur.components) == 0
    assert not any("unexplained" in f for f in flags if CUR.lower() in f or CUR in f)


def test_sweep_is_internal_transfer(tmp_path):
    _, transfers, flags = _analyze(tmp_path)
    assert [(t["from"], t["to"], t["value_wei"]) for t in transfers] == [(OLD.lower(), CUR.lower(), SWEEP_WEI)]
    assert not any(SWEEP in f for f in flags)


def test_four_deposits_addressed_elsewhere(tmp_path):
    books, _, _ = _analyze(tmp_path)
    cur_elsewhere = [d for d, lbl in books[CUR.lower()].components if "landed on" in lbl]
    assert len(cur_elsewhere) == 4
    assert sum(cur_elsewhere) == -103000000000000000
    old_inflows = [d for d, lbl in books[OLD.lower()].components if "inflow attributed to" in lbl]
    assert len(old_inflows) == 4
    assert sum(old_inflows) == 103000000000000000


def test_refund_is_unledgered_outflow_on_old_only(tmp_path):
    books, _, flags = _analyze(tmp_path)
    old = books[OLD.lower()]
    assert any(d == -49960000000000000 and "unledgered outflow" in lbl for d, lbl in old.components)
    assert any("unledgered outflow" in f for f in flags)
    assert not any("refund" in lbl or "unledgered" in lbl for _, lbl in books[CUR.lower()].components)


def test_old_wallet_residual_unexplained_not_gas(tmp_path):
    books, _, flags = _analyze(tmp_path)
    old = books[OLD.lower()]
    assert old.residual == OLD_RESIDUAL_WEI  # 0.103 - 0.04996 - 0.050665
    assert any("retains" in f and "unexplained" in f and OLD in f for f in flags)
    # Gas is its own term, never the unexplained label.
    assert old.gas == 21000 * 1000020 + 21000 * 1000017 + 204600 * 1000020
    assert not any("gas" in lbl.lower() for _, lbl in old.components)


def test_null_deposit_address_is_address_unknown(tmp_path, capsys):
    db = _ledger(tmp_path, with_deposit_address=False)  # pre-B13 schema: no column at all
    txs_path = tmp_path / "txs.json"
    txs_path.write_text(json.dumps(_txs()))
    rc = bwr.main(
        [
            "--ledger",
            str(db),
            "--txs",
            str(txs_path),
            "--wallets",
            f"{OLD},{CUR}",
            "--current-wallet",
            CUR,
        ]
    )
    out = capsys.readouterr().out
    assert "address unknown" in out
    assert "5 row(s) deposit_address NULL" in out
    # The math is unchanged: NULL rows are treated as the current wallet.
    assert "-52335372406592269" in out
    assert rc == 1  # the old-wallet residual still needs an operator note


def test_full_report_output(tmp_path, capsys):
    rc, out = _main(tmp_path, capsys)
    assert rc == 1
    assert "-52335372406592269" in out
    assert "+2375372406592269" in out
    assert "internal transfer" in out
    assert "needs operator note" in out
    assert "SUMMARY: 2 item(s) need an operator note" in out


def test_no_unexplained_means_exit_zero(tmp_path, capsys):
    # Single-wallet steady state: one deposit in, one release out.
    db = tmp_path / "l.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE eth_deposits (id TEXT PRIMARY KEY, tx_hash TEXT, from_address TEXT, "
        "amount_eth NUMERIC, status TEXT, deposit_address TEXT)"
    )
    con.execute(
        "INSERT INTO eth_deposits VALUES ('d','0x'||printf('%064d',1),?, '0.001', 'completed', ?)",
        (DEPOSITOR2, CUR),
    )
    con.execute(
        "CREATE TABLE eth_withdrawals (id TEXT PRIMARY KEY, ait_tx_hash TEXT, amount_eth NUMERIC, "
        "status TEXT, eth_tx_hash TEXT)"
    )
    con.execute("INSERT INTO eth_withdrawals VALUES ('w','a','0.0005','completed',?)", ("0x" + "aa" * 32,))
    con.commit()
    con.close()
    txs_path = tmp_path / "txs.json"
    txs_path.write_text(
        json.dumps(
            [
                _tx("0x" + "00" * 31 + "01", DEPOSITOR2, CUR, "1000000000000000"),
                _tx("0x" + "aa" * 32, CUR, RECEIVER, "500000000000000", gas_used=21000, gas_price="1000001"),
            ]
        )
    )
    rc = bwr.main(
        [
            "--ledger",
            str(db),
            "--txs",
            str(txs_path),
            "--current-wallet",
            CUR,
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "SUMMARY: no unexplained items" in out


def test_deposit_landing_off_list_flags(tmp_path, capsys):
    db = tmp_path / "l.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE eth_deposits (id TEXT PRIMARY KEY, tx_hash TEXT, from_address TEXT, "
        "amount_eth NUMERIC, status TEXT, deposit_address TEXT)"
    )
    con.execute(
        "INSERT INTO eth_deposits VALUES ('d',?,?, '0.001', 'completed', ?)",
        ("0x" + "12" * 32, DEPOSITOR2, CUR),
    )
    con.commit()
    con.close()
    txs_path = tmp_path / "txs.json"
    txs_path.write_text(json.dumps([_tx("0x" + "12" * 32, DEPOSITOR2, "0x" + "66" * 20, "1000000000000000")]))
    rc = bwr.main(["--ledger", str(db), "--txs", str(txs_path), "--current-wallet", CUR])
    out = capsys.readouterr().out
    assert rc == 1
    assert "off-list" in out


def test_unmatched_row_hash_is_flagged(tmp_path):
    # A ledger deposit with no chain tx in the dump is expected-never-arrived
    # and flagged — the dump may be incomplete, the operator decides.
    db = _ledger(tmp_path)
    ledger = bwr._load_ledger(db)
    books, _, flags = bwr.analyze(
        _txs()[1:],  # drop the dep_mig deposit tx
        ledger["deposits"],
        ledger["depositors"],
        ledger["withdrawals"],
        set(),
        WALLETS,
        CUR.lower(),
    )
    assert any("dep_mig" in f and "no chain tx in dump" in f for f in flags)


def test_malformed_tx_rejected(tmp_path):
    ledger = bwr._load_ledger(_ledger(tmp_path))
    with pytest.raises(SystemExit):
        bwr.analyze(
            [{"to": CUR, "value_wei": "1"}],
            ledger["deposits"],
            ledger["depositors"],
            ledger["withdrawals"],
            set(),
            WALLETS,
            CUR.lower(),
        )
