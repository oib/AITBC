"""Issued peer keys for self-serve island joining (POST /rpc/join).

Each issued key is bound to exactly one ``node_id``: it can register,
heartbeat, and revoke only that node's subscription lease. That binding is
what makes self-serve issuance safe — a leaked issued key can disturb only
its own lease, never another node's. Keys configured through
``BLOCKCHAIN_RPC_API_KEY_PEERS`` are fleet-internal and remain unbound.

Only the SHA-256 hash of a key is stored; the plaintext is returned once at
issuance and cannot be recovered. Re-issuing a node_id requires an operator
revocation first (``scripts/ops/manage-peer-keys.sh``).
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from aitbc.constants import DATA_DIR

_NODE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{2,63}$")

# Issuance caps: enough for a real island, tight enough that a scripted client
# cannot flood the store or squat every plausible node_id.
MAX_KEYS_PER_IP_PER_DAY = 10
MAX_TOTAL_KEYS = 5000


def _db_path() -> Path:
    return Path(os.getenv("PEER_KEYS_DB", str(DATA_DIR / "data" / "peer_keys.db")))


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS peer_keys ("
        " key_hash TEXT PRIMARY KEY,"
        " node_id TEXT NOT NULL,"
        " issued_ip TEXT NOT NULL,"
        " contact TEXT,"
        " created_at REAL NOT NULL,"
        " revoked_at REAL"
        ")"
    )
    # Active node_ids are unique; revoked rows keep their node_id so a node can
    # re-join after an operator revocation.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_peer_keys_active_node"
        " ON peer_keys(node_id) WHERE revoked_at IS NULL"
    )
    return conn


def valid_node_id(node_id: str) -> bool:
    return bool(_NODE_ID_RE.match(node_id or ""))


@dataclass
class PeerKey:
    node_id: str
    issued_ip: str
    created_at: float
    revoked_at: float | None


def _row_to_key(row: sqlite3.Row | tuple) -> PeerKey:
    return PeerKey(node_id=row[1], issued_ip=row[2], created_at=row[3], revoked_at=row[4])


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def lookup(key: str) -> PeerKey | None:
    """Return the issued-key record for ``key`` (hash match), or None."""
    if not key:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT key_hash, node_id, issued_ip, created_at, revoked_at FROM peer_keys WHERE key_hash = ?",
            (_hash(key),),
        ).fetchone()
    return _row_to_key(row) if row else None


def peer_key_node_scope(key: str) -> str | None:
    """The node_id an issued key is bound to, or None.

    None means either "not an issued key" or "unbound" (env-configured fleet
    keys) — callers must distinguish via ``lookup`` where it matters.
    """
    record = lookup(key)
    if record is None or record.revoked_at is not None:
        return None
    return record.node_id


def is_issued_key(key: str) -> bool:
    record = lookup(key)
    return record is not None and record.revoked_at is None


def recent_count_for_ip(ip: str, window_seconds: float = 86400) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM peer_keys WHERE issued_ip = ? AND created_at > ?",
            (ip, time.time() - window_seconds),
        ).fetchone()
    return int(row[0])


def total_count() -> int:
    with _connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM peer_keys").fetchone()[0])


def node_id_taken(node_id: str) -> bool:
    """True when an active (non-revoked) issued key already holds ``node_id``."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM peer_keys WHERE node_id = ? AND revoked_at IS NULL",
            (node_id,),
        ).fetchone()
    return row is not None


def issue(node_id: str, issued_ip: str, contact: str | None = None) -> str:
    """Issue a new peer key bound to ``node_id``. Returns the plaintext once."""
    key = f"aitbc-peer-{secrets.token_hex(24)}"
    with _connect() as conn:
        conn.execute(
            "INSERT INTO peer_keys (key_hash, node_id, issued_ip, contact, created_at) VALUES (?, ?, ?, ?, ?)",
            (_hash(key), node_id, issued_ip, contact, time.time()),
        )
    return key


def revoke(node_id: str) -> bool:
    """Revoke the active key bound to ``node_id``. Returns True if one was revoked."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE peer_keys SET revoked_at = ? WHERE node_id = ? AND revoked_at IS NULL",
            (time.time(), node_id),
        )
    return cur.rowcount > 0


def list_keys(include_revoked: bool = False) -> list[PeerKey]:
    sql = "SELECT key_hash, node_id, issued_ip, created_at, revoked_at FROM peer_keys"
    if not include_revoked:
        sql += " WHERE revoked_at IS NULL"
    sql += " ORDER BY created_at"
    with _connect() as conn:
        return [_row_to_key(r) for r in conn.execute(sql).fetchall()]
