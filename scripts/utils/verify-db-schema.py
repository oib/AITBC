#!/usr/bin/env python3
"""Verify live AITBC SQLite DB schemas match their code-defined models.

Run after migrations (e.g. from run-migrations.sh or update.sh) to catch drift
such as a stamped alembic_version that does not actually include all columns.

Covers the SQLite databases used by the production services:
  coordinator, blockchain (per-island chain.db), keystore, wallet_ledger,
  governance, trading, gpu, edge, marketplace, exchange and hermes coin requests.

Any other non-empty .db files found under the data directory are reported as
unverified warnings so they are not silently ignored.

Postgres-backed databases are NOT verified by this SQLite tool; they are checked
by run-migrations.sh with `alembic upgrade head` and an optional `alembic current`
head check.
"""

from __future__ import annotations

import argparse
import importlib
import io
import json
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


def _actual_tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'")
        return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def _actual_columns(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(f'PRAGMA table_info("{table}")')
        return {row[1] for row in cur.fetchall()}
    finally:
        conn.close()


def _resolve_metadata(metadata_attr: str) -> Any:
    parts = metadata_attr.split(".")
    mod = importlib.import_module(parts[0])
    obj = mod
    for part in parts[1:]:
        obj = getattr(obj, part)
    return obj


def _load_metadata(modules: list[str], metadata_attrs: list[str]) -> list[Any]:
    with _suppress_import_noise():
        for mod in modules:
            importlib.import_module(mod)
    return [_resolve_metadata(attr) for attr in metadata_attrs]


def _expected_schema(metadata_list: list[Any]) -> dict[str, set[str]]:
    expected: dict[str, set[str]] = {}
    for metadata in metadata_list:
        for table in metadata.tables:
            if table not in expected:
                expected[table] = set()
            expected[table] |= {c.name for c in metadata.tables[table].columns}
    return expected


def _expected_columns(metadata_list: list[Any], table: str) -> dict[str, Any] | None:
    cols: dict[str, Any] = {}
    for metadata in metadata_list:
        if table not in metadata.tables:
            continue
        for c in metadata.tables[table].columns:
            if c.name not in cols:
                cols[c.name] = c
    return cols if cols else None


def _check_sqlmodel_db(
    db_path: Path,
    metadata_list: list[Any],
    required_tables: list[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    if not db_path.exists():
        return []

    actual = _actual_tables(db_path)
    if not actual:
        # Empty/uninitialised database; its service is probably not linked for this role.
        return []

    expected = _expected_schema(metadata_list)
    for table in sorted(actual):
        exp = expected.get(table)
        if exp is None:
            continue
        missing = exp - _actual_columns(db_path, table)
        if missing:
            errors.append(f"{db_path}: table '{table}' missing columns: {sorted(missing)}")

    for table in required_tables or []:
        if table not in actual:
            exp = _expected_columns(metadata_list, table)
            if exp is not None:
                errors.append(f"{db_path}: required table '{table}' is missing")
    return errors


def _check_static_db(
    db_path: Path,
    expected: dict[str, list[str]],
    required_tables: list[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    if not db_path.exists():
        return []

    actual = _actual_tables(db_path)
    if not actual:
        return []

    required = set(required_tables or list(expected.keys()))
    for table, cols in expected.items():
        if table not in actual:
            if table in required:
                errors.append(f"{db_path}: missing table '{table}'")
            continue
        missing = set(cols) - _actual_columns(db_path, table)
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
    coltype = col.type.compile(dialect=dialect)
    default = _render_default_clause(col, dialect)
    conn = sqlite3.connect(db_path)
    try:
        if not default and col.nullable is False:
            # The table name is a known identifier from SQLModel metadata and is
            # quoted by the SQLite dialect; this is trusted DDL, not user input.
            (row_count,) = conn.execute(f"SELECT COUNT(*) FROM {quote(table)}").fetchone()  # nosec B608
            if row_count > 0:
                return f"{table}.{col.name} is NOT NULL with no default and the table has {row_count} rows; cannot safely add"
        conn.execute(f"ALTER TABLE {quote(table)} ADD COLUMN {quote(col.name)} {coltype}{default}")  # nosec B608
        conn.commit()
        return None
    finally:
        conn.close()


def _repair_sqlmodel_db(
    db_path: Path,
    metadata_list: list[Any],
    required_tables: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    repairs: list[str] = []
    errors: list[str] = []
    if not db_path.exists():
        return [], []

    actual = _actual_tables(db_path)
    if not actual:
        return [], []

    quote, dialect = _sqlite_quote_and_type()
    for table in sorted(actual):
        exp_cols = _expected_columns(metadata_list, table)
        if exp_cols is None:
            continue
        existing = _actual_columns(db_path, table)
        missing = set(exp_cols) - existing
        for col_name in sorted(missing):
            err = _add_missing_column(db_path, table, exp_cols[col_name], dialect, quote)
            if err:
                errors.append(f"{db_path}: {err}")
            else:
                repairs.append(f"{db_path}: added {table}.{col_name}")

    for table in required_tables or []:
        if table not in actual:
            exp_cols = _expected_columns(metadata_list, table)
            if exp_cols is not None:
                errors.append(f"{db_path}: required table '{table}' is missing; cannot create table")
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
        if root_db.exists() and _actual_tables(root_db):
            dbs.append(root_db)
    return dbs


# Registry of known SQLite databases and how to load their expected schema.
# Metadata is loaded in-process; apps with private metadata are listed first
# to avoid SQLModel global-metadata pollution where possible.
KNOWN_DBS: dict[str, Any] = {
    "coordinator": {
        "type": "sqlmodel",
        "path": _data_dir() / "coordinator.db",
        "modules": ["coordinator_api.main"],
        "metadata": ["sqlmodel.SQLModel.metadata"],
        "required_tables": ["job", "escrow", "miner"],
    },
    "governance": {
        "type": "sqlmodel",
        "path": _data_dir() / "governance_service.db",
        "modules": ["governance_service.domain.governance", "governance_service.domain.base"],
        "metadata": ["governance_service.domain.base.governance_metadata"],
        "required_tables": ["proposals", "votes"],
    },
    "trading": {
        "type": "sqlmodel",
        "path": _data_dir() / "trading_service.db",
        "modules": [
            "trading_service.domain.inter_chain",
            "trading_service.domain.trading",
            "trading_service.domain.base",
            "aitbc_shared.models",
        ],
        "metadata": [
            "trading_service.domain.base.trading_metadata",
            "sqlmodel.SQLModel.metadata",
        ],
        "required_tables": ["trade_requests"],
    },
    "gpu": {
        "type": "sqlmodel",
        "path": _data_dir() / "gpu_service.db",
        "modules": [
            "gpu_service.domain.gpu_marketplace",
            "gpu_service.domain.base",
            "aitbc_shared.models",
        ],
        "metadata": [
            "gpu_service.domain.base.gpu_metadata",
            "sqlmodel.SQLModel.metadata",
        ],
        "required_tables": ["gpu_registry"],
    },
    "edge": {
        "type": "sqlmodel",
        "path": _data_dir() / "aitbc_edge.db",
        "modules": [
            "aitbc_edge.schemas.database",
            "aitbc_edge.schemas.gpu",
            "aitbc_edge.schemas.island",
            "aitbc_edge.schemas.metrics",
            "aitbc_edge.schemas.serve",
            "aitbc_shared.models",
        ],
        "metadata": ["sqlmodel.SQLModel.metadata"],
        "required_tables": ["compute_requests"],
    },
    "marketplace": {
        "type": "sqlmodel",
        "path": _data_dir() / "marketplace_service.db",
        "modules": [
            "marketplace_service.domain.marketplace",
            "marketplace_service.domain.global_marketplace",
            "marketplace_service.domain.base",
        ],
        "metadata": [
            "marketplace_service.domain.base.marketplace_metadata",
            "sqlmodel.SQLModel.metadata",
        ],
        "required_tables": ["bids", "marketplaceoffer"],
    },
    "exchange": {
        "type": "static",
        "path": _data_dir() / "exchange" / "exchange.db",
        "required_tables": ["trades", "orders"],
        "tables": {
            "trades": ["id", "amount", "price", "total", "created_at"],
            "orders": [
                "id",
                "order_type",
                "amount",
                "price",
                "total",
                "filled",
                "remaining",
                "status",
                "created_at",
                "user_address",
                "tx_hash",
            ],
            "marketplace_offers": [
                "id",
                "item",
                "item_type",
                "price",
                "wallet",
                "status",
                "description",
                "created_at",
            ],
            "marketplace_orders": [
                "id",
                "order_type",
                "item",
                "price",
                "wallet",
                "status",
                "created_at",
            ],
        },
    },
    "hermes": {
        "type": "static",
        "path": _data_dir() / "hermes_coin_requests.db",
        "tables": {
            "coin_requests": [
                "id",
                "sender",
                "recipient",
                "amount",
                "wallet_address",
                "status",
                "approval_mode",
                "approved_by",
                "approved_at",
                "rejection_reason",
                "created_at",
                "expires_at",
                "signed_transaction",
                "transaction_hash",
                "audit_log",
            ],
        },
    },
    "agent_management": {
        "type": "sqlmodel",
        "path": _data_dir() / "agent_management.db",
        "modules": ["coordinator_api.main"],
        "metadata": ["sqlmodel.SQLModel.metadata"],
        "required_tables": ["agent_executions"],
    },
    "agent_coordinator": {
        "type": "static",
        "path": _data_dir() / "agent_coordinator.db",
        "tables": {
            "messages": ["message_id", "data", "sender", "receiver", "timestamp", "status"],
        },
    },
    "agent_coin_requests": {
        "type": "static",
        "path": _data_dir() / "agent_coin_requests.db",
        "tables": {
            "coin_requests": [
                "id",
                "sender",
                "recipient",
                "amount",
                "wallet_address",
                "status",
                "approval_mode",
                "approved_by",
                "approved_at",
                "rejection_reason",
                "created_at",
                "expires_at",
                "signed_transaction",
                "transaction_hash",
                "audit_log",
            ],
        },
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


def _known_db_paths() -> set[Path]:
    paths: set[Path] = set()
    for cfg in KNOWN_DBS.values():
        if "path" in cfg:
            paths.add(Path(cfg["path"]).resolve())
    return paths


def _auto_discover(checked: set[Path]) -> list[str]:
    """Return warnings for non-empty SQLite files that are not in the known set.

    Skips legacy, backup and test databases (pre-migrate*, backup*, test_*) and
    non-active chain databases so the output is not swamped by old copies.
    """
    warnings: list[str] = []
    data_dir = _data_dir()
    if not data_dir.exists():
        return warnings

    active_chain_ids = set(_active_chain_ids())

    for db_path in data_dir.rglob("*.db"):
        resolved = db_path.resolve()
        if resolved in checked:
            continue
        if not db_path.exists():
            continue

        rel = db_path.relative_to(data_dir)
        parts = rel.parts
        if any(
            part.lower().startswith("pre-migrate") or "backup" in part.lower() or part.lower().startswith("test_")
            for part in parts
        ):
            continue

        # Skip non-active island chain databases and the legacy root chain.db
        # unless _collect_chain_dbs already added it to the checked set.
        if db_path.name == "chain.db":
            if rel.parent == Path("."):
                continue  # legacy root chain.db; checked if it is the active fallback
            if rel.parent.name not in active_chain_ids:
                continue  # old / test island chain db

        if _actual_tables(db_path):
            warnings.append(f"Unverified database (not in schema registry): {db_path}")
    return warnings


def check_all(dbs: list[str] | None = None, repair: bool = False) -> tuple[list[str], list[str], list[str]]:
    _setup_pythonpath()
    errors: list[str] = []
    warnings: list[str] = []
    actions: list[str] = []
    checked_paths: set[Path] = _known_db_paths()

    selected = dbs or list(KNOWN_DBS.keys())
    for name in selected:
        if name == "blockchain" or name.endswith("-chain"):
            continue
        cfg = KNOWN_DBS.get(name)
        if not cfg:
            warnings.append(f"Unknown DB name: {name}")
            continue

        db_path = Path(cfg["path"])
        checked_paths.add(db_path.resolve())

        if cfg["type"] == "sqlmodel":
            modules = cfg["modules"]
            metadata_list = _load_metadata(modules, cfg["metadata"])
            if repair:
                rep, err = _repair_sqlmodel_db(db_path, metadata_list, cfg.get("required_tables"))
                actions.extend(rep)
                errors.extend(err)
            else:
                errors.extend(_check_sqlmodel_db(db_path, metadata_list, cfg.get("required_tables")))
        elif cfg["type"] == "static":
            errors.extend(_check_static_db(db_path, cfg["tables"], cfg.get("required_tables")))

    if dbs is None or "blockchain" in dbs or any(n.startswith("blockchain") for n in (dbs or [])):
        chain_dbs = _collect_chain_dbs()
        if not chain_dbs:
            warnings.append("No active chain database found")
        else:
            metadata_list = _load_metadata(
                ["aitbc_chain.database"],
                ["aitbc_chain.database.chain_metadata"],
            )
            for db_path in chain_dbs:
                checked_paths.add(db_path.resolve())
                if repair:
                    rep, err = _repair_sqlmodel_db(db_path, metadata_list, ["account", "block", "transaction"])
                    actions.extend(rep)
                    errors.extend(err)
                else:
                    errors.extend(_check_sqlmodel_db(db_path, metadata_list, ["account", "block", "transaction"]))

    if dbs is None:
        warnings.extend(_auto_discover(checked_paths))

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
