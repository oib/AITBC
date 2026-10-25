"""PG-TARGET-1 stream 2: trading 002 must not alter 003's tables on the way down.

``002`` converts money columns Float -> Numeric(20, 8) with existence
guards in upgrade(). Its downgrade() had none: it issued ``ALTER
COLUMN`` on ``trade_agreements``, ``trade_settlements`` and
``trading_analytics`` — tables that belong to ``003`` and are therefore
already dropped by the time 002 steps back. On PostgreSQL that aborts
the downgrade with "relation does not exist".

Two pins, both offline:

- A temp-SQLite ``upgrade head`` -> ``downgrade base`` sweep.
- A stubbed-bind unit test that runs 002's downgrade() under a fake
  postgresql dialect with only the 001/002-era tables present and
  asserts no alter touches a 003-owned table. No PostgreSQL needed.
"""

from __future__ import annotations

import importlib.util
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa

TRADING_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TRADING_ROOT.parent.parent

_REV002 = TRADING_ROOT / "alembic" / "versions" / "002_v0180_decimal_money_fields.py"
# Tables that exist at 002's point in the chain; the rest of _MONEY_COLUMNS
# belongs to 003.
_AT_002 = {"inter_chain_trades": ["trade_id", "price"], "island_registry": ["chain_id"]}
_003_OWNED = {"trade_agreements", "trade_settlements", "trading_analytics"}


def _run_alembic(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{tmp_path}/trading_migrations.db"
    env["PYTHONPATH"] = f"{TRADING_ROOT / 'src'}:{REPO_ROOT}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=TRADING_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"alembic {' '.join(args)} failed (exit {result.returncode}):\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def test_upgrade_head_downgrade_base(tmp_path: Path) -> None:
    _run_alembic(tmp_path, "upgrade", "head")
    _run_alembic(tmp_path, "downgrade", "base")
    con = sqlite3.connect(f"file:{tmp_path / 'trading_migrations.db'}?mode=ro", uri=True)
    try:
        assert con.execute("SELECT version_num FROM alembic_version").fetchall() == []
    finally:
        con.close()


def _load_rev002() -> Any:
    spec = importlib.util.spec_from_file_location("rev002", _REV002)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_002_downgrade_alters_only_tables_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Under a postgresql dialect bind, 002's downgrade skips absent tables."""
    module = _load_rev002()
    altered: list[tuple[str, str]] = []

    fake_bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    fake_op = SimpleNamespace(
        get_bind=lambda: fake_bind,
        alter_column=lambda table, col, **kw: altered.append((table, col)),
    )
    fake_inspector = SimpleNamespace(
        get_table_names=lambda: list(_AT_002),
        get_columns=lambda table: [{"name": c} for c in _AT_002.get(table, [])],
    )

    monkeypatch.setattr(module, "op", fake_op)
    monkeypatch.setattr(sa, "inspect", lambda bind: fake_inspector)

    module.downgrade()

    assert altered == [("inter_chain_trades", "price")]
    assert not ({t for t, _ in altered} & _003_OWNED)
