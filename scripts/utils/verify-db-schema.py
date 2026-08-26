#!/usr/bin/env python3
"""Verify live AITBC SQLite DB schemas match their code-defined models.

Run after migrations (e.g. from run-migrations.sh or update.sh) to catch drift
such as a stamped alembic_version that does not actually include all columns.
"""

from __future__ import annotations

import argparse
import importlib
import io
import logging
import os
import re
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger("verify-db-schema")
logger.propagate = False
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setLevel(logging.NOTSET)
    logger.addHandler(_handler)


def _aitbc_root() -> Path:
    return Path(os.environ.get("AITBC_ROOT", "/opt/aitbc"))


def _data_dir() -> Path:
    return Path(os.environ.get("AITBC_DATA_DIR", "/var/lib/aitbc/data"))


def _setup_pythonpath() -> None:
    root = _aitbc_root()
    paths = [str(root)]
    for app in (root / "apps").glob("*"):
        if app.is_dir():
            src = app / "src"
            if src.is_dir():
                paths.append(str(src))
    pkg_src = root / "packages/py"
    if pkg_src.is_dir():
        paths.extend(str(d) for d in pkg_src.rglob("src") if d.is_dir())
    for p in paths:
        if p not in sys.path:
            sys.path.insert(0, p)


def actual_tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'")
        return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def actual_columns(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(f'PRAGMA table_info("{table}")')
        return {row[1] for row in cur.fetchall()}
    finally:
        conn.close()


def resolve_metadata(metadata_attr: str) -> Any:
    parts = metadata_attr.split(".")
    mod = importlib.import_module(parts[0])
    obj = mod
    for part in parts[1:]:
        obj = getattr(obj, part)
    return obj


@contextmanager
def _suppress_import_noise():
    old_level = logging.root.level
    logging.root.setLevel(logging.CRITICAL)
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()
    try:
        yield
    finally:
        logging.root.setLevel(old_level)
        sys.stdout = old_stdout
        sys.stderr = old_stderr


def load_metadata(module_name: str, metadata_attr: str) -> Any:
    with _suppress_import_noise():
        importlib.import_module(module_name)
    return resolve_metadata(metadata_attr)


def expected_columns(metadata: Any, table: str) -> set[str] | None:
    if table not in metadata.tables:
        return None
    return {c.name for c in metadata.tables[table].columns}


def check_sqlmodel_db(
    db_path: Path,
    metadata: Any,
    required_tables: list[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    if not db_path.exists():
        return [f"{db_path}: database file does not exist"]

    actual = actual_tables(db_path)
    for table in sorted(actual):
        exp = expected_columns(metadata, table)
        if exp is None:
            continue
        missing = exp - actual_columns(db_path, table)
        if missing:
            errors.append(f"{db_path}: table '{table}' missing columns: {sorted(missing)}")

    for table in required_tables or []:
        if table not in actual:
            exp = expected_columns(metadata, table)
            if exp is not None:
                errors.append(f"{db_path}: required table '{table}' is missing")
    return errors


def check_static_db(db_path: Path, expected: dict[str, list[str]]) -> list[str]:
    errors: list[str] = []
    if not db_path.exists():
        return [f"{db_path}: database file does not exist"]

    actual = actual_tables(db_path)
    for table, cols in expected.items():
        if table not in actual:
            errors.append(f"{db_path}: missing table '{table}'")
            continue
        missing = set(cols) - actual_columns(db_path, table)
        if missing:
            errors.append(f"{db_path}: table '{table}' missing columns: {sorted(missing)}")
    return errors


def _sqlite_quote_and_type():
    from sqlalchemy import create_engine

    engine = create_engine("sqlite://")
    return engine.dialect.identifier_preparer.quote, engine.dialect


def _render_default_clause(col, dialect) -> str:
    from sqlalchemy import ColumnDefault, literal

    default = col.default
    if not isinstance(default, ColumnDefault) or default.arg is None:
        return ""
    try:
        value = default.arg(None) if default.is_callable else default.arg
        rendered = literal(value, col.type).compile(dialect=dialect, compile_kwargs={"literal_binds": True})
    except Exception:
        return ""
    return f" DEFAULT {rendered}"


def _add_missing_column(db_path: Path, table: str, col, dialect, quote) -> str | None:
    from sqlalchemy import text

    coltype = col.type.compile(dialect=dialect)
    default = _render_default_clause(col, dialect)
    conn = sqlite3.connect(db_path)
    try:
        if not default and col.nullable is False:
            # The table name is a known identifier from SQLModel metadata and is
            # quoted by the SQLite dialect; this is trusted DDL, not user input.
            (row_count,) = conn.execute(text(f"SELECT COUNT(*) FROM {quote(table)}")).fetchone()  # nosec B608
            if row_count > 0:
                return f"{table}.{col.name} is NOT NULL with no default and the table has {row_count} rows; cannot safely add"
        conn.execute(text(f"ALTER TABLE {quote(table)} ADD COLUMN {quote(col.name)} {coltype}{default}"))  # nosec B608
        conn.commit()
        return None
    finally:
        conn.close()


def repair_sqlmodel_db(db_path: Path, metadata: Any, required_tables: list[str] | None = None) -> tuple[list[str], list[str]]:
    repairs: list[str] = []
    errors: list[str] = []
    if not db_path.exists():
        return [], [f"{db_path}: database file does not exist"]

    quote, dialect = _sqlite_quote_and_type()
    actual = actual_tables(db_path)
    for table in sorted(actual):
        if table not in metadata.tables:
            continue
        exp_cols = {c.name: c for c in metadata.tables[table].columns}
        existing = actual_columns(db_path, table)
        missing = set(exp_cols) - existing
        for col_name in sorted(missing):
            err = _add_missing_column(db_path, table, exp_cols[col_name], dialect, quote)
            if err:
                errors.append(f"{db_path}: {err}")
            else:
                repairs.append(f"{db_path}: added {table}.{col_name}")
    return repairs, errors


def _active_chain_ids() -> list[str]:
    chain_ids: list[str] = []
    for env_file in ("/etc/aitbc/blockchain.env", "/etc/aitbc/node.env"):
        p = Path(env_file)
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            m = re.match(r'^CHAIN_ID=["\']?([^"\'\s]+)', line)
            if m:
                chain_ids.append(m.group(1))
    return chain_ids


KNOWN_DBS = {
    "coordinator": {
        "type": "sqlmodel",
        "path": _data_dir() / "coordinator.db",
        "module": "coordinator_api.main",
        "metadata": "sqlmodel.SQLModel.metadata",
        "required_tables": ["job", "escrow", "miner"],
    },
    "keystore": {
        "type": "static",
        "path": _data_dir() / "keystore.db",
        "tables": {
            "wallets": [
                "wallet_id",
                "public_key",
                "salt",
                "nonce",
                "ciphertext",
                "metadata",
                "created_at",
                "updated_at",
            ],
            "wallet_access_log": [
                "id",
                "wallet_id",
                "action",
                "timestamp",
                "success",
                "ip_address",
            ],
        },
    },
    "wallet_ledger": {
        "type": "static",
        "path": _data_dir() / "wallet_ledger.db",
        "tables": {
            "wallets": ["wallet_id", "public_key", "metadata"],
            "wallet_events": ["id", "wallet_id", "event_type", "payload", "created_at"],
        },
    },
}


def _collect_chain_dbs() -> list[Path]:
    data_dir = _data_dir()
    dbs: list[Path] = []
    for chain_id in _active_chain_ids():
        db = data_dir / chain_id / "chain.db"
        if db.exists():
            dbs.append(db)
    # Fall back to legacy root chain.db only if it is actually populated.
    if not dbs:
        root_db = data_dir / "chain.db"
        if root_db.exists() and actual_tables(root_db):
            dbs.append(root_db)
    return dbs


def check_all(dbs: list[str] | None = None, repair: bool = False) -> tuple[list[str], list[str], list[str]]:
    _setup_pythonpath()
    errors: list[str] = []
    warnings: list[str] = []
    actions: list[str] = []

    selected = dbs or list(KNOWN_DBS.keys())
    for name in selected:
        if name == "blockchain" or name.endswith("-chain"):
            # handled below
            continue
        cfg = KNOWN_DBS.get(name)
        if not cfg:
            warnings.append(f"Unknown DB name: {name}")
            continue

        if cfg["type"] == "sqlmodel":
            try:
                metadata = load_metadata(cfg["module"], cfg["metadata"])
            except Exception as exc:
                errors.append(f"{name}: failed to load metadata ({exc})")
                continue
            db_path = Path(cfg["path"])
            if repair:
                rep, err = repair_sqlmodel_db(db_path, metadata, cfg.get("required_tables"))
                actions.extend(rep)
                errors.extend(err)
            else:
                errors.extend(
                    check_sqlmodel_db(
                        db_path,
                        metadata,
                        cfg.get("required_tables"),
                    )
                )
        elif cfg["type"] == "static":
            db_path = Path(cfg["path"])
            errors.extend(check_static_db(db_path, cfg["tables"]))

    if dbs is None or "blockchain" in dbs or any(n.startswith("blockchain") for n in (dbs or [])):
        chain_dbs = _collect_chain_dbs()
        if not chain_dbs:
            warnings.append("No active chain database found")
        else:
            try:
                metadata = load_metadata("aitbc_chain.database", "aitbc_chain.database.chain_metadata")
            except Exception as exc:
                errors.append(f"blockchain: failed to load metadata ({exc})")
                metadata = None

            if metadata:
                for db_path in chain_dbs:
                    if repair:
                        rep, err = repair_sqlmodel_db(db_path, metadata, ["account", "block", "transaction"])
                        actions.extend(rep)
                        errors.extend(err)
                    else:
                        errors.extend(
                            check_sqlmodel_db(
                                db_path,
                                metadata,
                                ["account", "block", "transaction"],
                            )
                        )

    return errors, warnings, actions


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify AITBC DB schemas")
    parser.add_argument("--all", action="store_true", help="Check all known databases")
    parser.add_argument("--db", action="append", help="Check specific DB by name (may be repeated)")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Add missing columns that are nullable or have a default",
    )
    parser.add_argument("--aitbc-root", default=None, help="Override AITBC_ROOT")
    parser.add_argument("--data-dir", default=None, help="Override AITBC data directory")
    args = parser.parse_args()

    if args.aitbc_root:
        os.environ["AITBC_ROOT"] = args.aitbc_root
    if args.data_dir:
        os.environ["AITBC_DATA_DIR"] = args.data_dir

    if not args.all and not args.db:
        parser.error("use --all or --db <name>")

    errors, warnings, actions = check_all(args.db, repair=args.repair)

    if args.json:
        import json

        print(json.dumps({"errors": errors, "warnings": warnings, "actions": actions}))
    else:
        for a in actions:
            logger.warning(a)
        for w in warnings:
            logger.warning(w)
        for e in errors:
            logger.error(e)
        if not errors and not (warnings or actions):
            logger.info("All checked databases match their expected schema")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
