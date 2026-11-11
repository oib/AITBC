"""Island IPFS access control.

Queries the on-chain IPFS subscription table and serves the private swarm key
only to paid, signature-proving island members.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aitbc.aitbc_logging import get_logger

from aitbc.crypto.signature_recovery import (  # PYTHONPATH makes this available
    canonical_address,
    verify_signature,
)

logger = get_logger(__name__)


def _to_ait_address(address: str) -> str:
    """Normalise to the EIP-55 ``0x`` spelling stored in the chain DB.

    ``ipfs_subscription.member_address`` is written verbatim from the
    transaction's ``sender_addr``, which is the canonical ``0x`` form. The
    legacy ``ait1`` spelling never matches those rows, so this helper now just
    applies ``canonical_address``; the name is kept for readability at the two
    call sites that refer to the "chain-side" spelling.
    """
    return canonical_address(address)


def _chain_db_path(chain_id: str) -> Path:
    """Return the path to the chain database for the given chain_id."""
    data_dir = Path(os.environ.get("AITBC_DATA_DIR", "/var/lib/aitbc/data"))
    path = data_dir / chain_id / "chain.db"
    if path.exists():
        return path
    fallback = data_dir / "chain.db"
    if fallback.exists():
        return fallback
    return path


def _connect_chain_db(db_path: Path) -> sqlite3.Connection:
    """Open chain.db read-only with a sane lock-wait budget.

    chain.db is owned by aitbc_chain.database (busy_timeout=60000, WAL); these
    read paths used sqlite's 5 s default in read-write mode.
    """
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA query_only=ON")
    return conn


def get_current_block_height(chain_id: str) -> int:
    """Return the current chain head height from the chain DB."""
    db_path = _chain_db_path(chain_id)
    if not db_path.exists():
        return 0
    try:
        with closing(_connect_chain_db(db_path)) as conn:
            row = conn.execute(
                "SELECT MAX(height) FROM block WHERE chain_id = ?",
                (chain_id,),
            ).fetchone()
            return row[0] or 0
    except Exception:
        logger.exception("Failed to read chain head for %s", chain_id)
        return 0


def get_ipfs_subscription(
    chain_id: str,
    island_id: str,
    member_address: str,
) -> dict[str, Any] | None:
    """Return the active on-chain IPFS subscription, or None if missing/expired."""
    db_path = _chain_db_path(chain_id)
    if not db_path.exists():
        return None
    ait_addr = _to_ait_address(member_address)
    try:
        with closing(_connect_chain_db(db_path)) as conn:
            row = conn.execute(
                """
                SELECT expires_at_block, quota_bytes, used_bytes
                FROM ipfs_subscription
                WHERE chain_id = ? AND island_id = ? AND member_address = ?
                """,
                (chain_id, island_id, ait_addr),
            ).fetchone()
            if not row:
                return None
            return {
                "expires_at_block": row[0],
                "quota_bytes": row[1],
                "used_bytes": row[2],
            }
    except Exception:
        logger.exception("Failed to read IPFS subscription for %s on %s", member_address, island_id)
        return None


def is_ipfs_subscription_active(
    chain_id: str,
    island_id: str,
    member_address: str,
) -> bool:
    """Return True if the member has a paid, unexpired IPFS subscription."""
    subscription = get_ipfs_subscription(chain_id, island_id, member_address)
    if not subscription:
        return False
    current_height = get_current_block_height(chain_id)
    if current_height >= subscription["expires_at_block"]:
        logger.info(
            "IPFS subscription expired for %s on %s (expires %s, current %s)",
            member_address,
            island_id,
            subscription["expires_at_block"],
            current_height,
        )
        return False
    # used_bytes is never written on-chain -- no path increments it, so this
    # gate is a dormant backstop. Live quota accounting happens at the
    # market layer: MarketService.get_market_job_usage sums
    # active job sizes and `aitbc market host` rejects uploads that would
    # exceed the offer's disk quota.
    if subscription["used_bytes"] >= subscription["quota_bytes"]:
        logger.info(
            "IPFS subscription quota exhausted for %s on %s (%s >= %s)",
            member_address,
            island_id,
            subscription["used_bytes"],
            subscription["quota_bytes"],
        )
        return False
    return True


# V13-RES2-IPFS-SWARM-1 (#1712): the swarm-key challenge used a
# client-chosen nonce that was never stored, so a captured
# (nonce, signature) pair replayed for the subscription's lifetime. The
# coordinator now issues the nonce: single-use, short-lived, and bound to
# (chain_id, island_id, member_address). The signed message covers
# chain_id too, so a signature cannot be moved across chains.
#
# #1771: the store must be shared across processes — coordinator-api runs
# ``uvicorn --workers 2``, so an in-process dict issued the nonce on one
# worker and consumed it on the other ~50% of the time ("Invalid or
# expired swarm-key challenge nonce"). Nonces live in a small sqlite file
# beside the swarm keys under AITBC_DATA_DIR: every worker and every
# restart sees the same single-use, expiring records. This module already
# keeps its state as files there (swarm.key, chain.db reads), so a
# dedicated nonce DB matches the local pattern without adding a dependency
# on the coordinator DB being reachable for this endpoint.
_SWARM_NONCE_TTL_SECONDS = 300
_SWARM_NONCE_MAX_PENDING = 10_000

_SWARM_NONCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS swarm_key_nonce (
    nonce TEXT PRIMARY KEY,
    chain_id TEXT NOT NULL,
    island_id TEXT NOT NULL,
    member_address TEXT NOT NULL,
    expires_at REAL NOT NULL,
    created_at REAL NOT NULL
)
"""


def _swarm_nonce_db_path() -> Path:
    """Shared nonce store, next to the island swarm keys."""
    data_dir = Path(os.environ.get("AITBC_DATA_DIR", "/var/lib/aitbc/data"))
    return data_dir / "ipfs-island" / "swarm-nonces.db"


def _connect_swarm_nonce_db() -> sqlite3.Connection:
    """Open the shared nonce DB, creating schema on first use.

    ``isolation_level=None`` gives explicit transaction control so the
    issue path can hold a write lock (``BEGIN IMMEDIATE``) across the
    expiry sweep, the pending cap and the insert — two workers cannot
    both pass the cap check or lose each other's rows.
    """
    path = _swarm_nonce_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute(_SWARM_NONCE_SCHEMA)
    return conn


def issue_swarm_key_nonce(chain_id: str, island_id: str, member_address: str) -> dict[str, Any]:
    """Issue a single-use swarm-key challenge nonce bound to the requester."""
    now = time.time()
    expires_at = now + _SWARM_NONCE_TTL_SECONDS
    nonce = secrets.token_urlsafe(24)
    with closing(_connect_swarm_nonce_db()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("DELETE FROM swarm_key_nonce WHERE expires_at <= ?", (now,))
            pending = conn.execute("SELECT COUNT(*) FROM swarm_key_nonce").fetchone()
            if pending is not None and int(pending[0]) >= _SWARM_NONCE_MAX_PENDING:
                conn.execute("ROLLBACK")
                raise PermissionError("Too many pending swarm-key challenges")
            conn.execute(
                "INSERT INTO swarm_key_nonce"
                " (nonce, chain_id, island_id, member_address, expires_at, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (nonce, chain_id, island_id, _to_ait_address(member_address), expires_at, now),
            )
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
    return {"nonce": nonce, "expires_at": int(expires_at)}


def _consume_swarm_nonce(chain_id: str, island_id: str, member_address: str, nonce: str) -> bool:
    """Atomically validate and burn a swarm-key nonce (single-use).

    The DELETE...RETURNING runs under BEGIN IMMEDIATE, so exactly one
    worker/process can burn a given nonce — the row is gone before the
    binding/expiry checks run, preserving the original burn-on-present
    semantics (a nonce presented with the wrong binding is still spent).
    """
    if not nonce:
        return False
    now = time.time()
    with closing(_connect_swarm_nonce_db()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "DELETE FROM swarm_key_nonce WHERE nonce = ? RETURNING chain_id, island_id, member_address, expires_at",
                (nonce,),
            ).fetchone()
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
    if row is None:
        return False
    rec_chain_id, rec_island_id, rec_member, expires_at = row
    if float(expires_at) <= now:
        return False
    return bool(rec_chain_id == chain_id and rec_island_id == island_id and rec_member == _to_ait_address(member_address))


def _swarm_key_dir(island_id: str) -> Path:
    """Directory where island IPFS swarm keys are stored.

    `island_id` arrives from the request body, so it is checked before it is
    used as a path segment.
    """
    if not island_id or "/" in island_id or "\\" in island_id or island_id in (".", ".."):
        raise PermissionError("Invalid island id")
    data_dir = Path(os.environ.get("AITBC_DATA_DIR", "/var/lib/aitbc/data"))
    return data_dir / "ipfs-island" / island_id


def get_island_swarm_key(island_id: str) -> str:
    """Return the island swarm key. Never creates one.

    This used to generate and persist a key when the directory was empty, using
    the island id from the request. An id naming no island therefore did not
    fail -- it minted a second island whose key nobody else holds, and handed it
    to the caller as if it were the real one. Provisioning belongs to
    `aitbc-island-ipfs.service`, which writes the key once under
    `ISLAND_IPFS_HUB=true`; a read must stay a read.

    The key is stored on disk and must be kept readable only by the hub.
    """
    key_file = _swarm_key_dir(island_id) / "swarm.key"
    if not key_file.exists():
        logger.warning("No swarm key on disk for island %s (%s)", island_id, key_file)
        raise PermissionError("Unknown island")
    return key_file.read_text()


def verify_member_signature(
    chain_id: str,
    island_id: str,
    member_address: str,
    nonce: str,
    signature: str,
) -> bool:
    """Verify that member_address signed the swarm-key challenge message.

    The challenge binds chain_id, island_id, member address and the
    server-issued nonce (#1712) — a signature captured for one chain or one
    nonce cannot be replayed elsewhere.
    """
    if not signature or not member_address:
        return False
    from eth_utils import keccak

    message = f"{chain_id}:{island_id}:{member_address}:{nonce}".encode()
    msg_hash = keccak(message)
    try:
        return verify_signature(msg_hash, signature, member_address)
    except Exception:
        logger.warning("Swarm-key signature verification failed for %s", member_address)
        return False


def get_member_swarm_key(
    chain_id: str,
    island_id: str,
    member_address: str,
    nonce: str,
    signature: str,
) -> dict[str, Any]:
    """Return the swarm key and hub multiaddr for a paid, verified member."""
    if not verify_member_signature(chain_id, island_id, member_address, nonce, signature):
        raise PermissionError("Invalid signature")
    if not _consume_swarm_nonce(chain_id, island_id, member_address, nonce):
        raise PermissionError("Invalid or expired swarm-key challenge nonce")
    if not is_ipfs_subscription_active(chain_id, island_id, member_address):
        raise PermissionError("No active IPFS subscription for this island")
    key = get_island_swarm_key(island_id)
    hub_host = os.environ.get("ISLAND_IPFS_HUB_HOST", "hub.aitbc.invalid")
    hub_port = os.environ.get("ISLAND_IPFS_HUB_SWARM_PORT", "4002")
    hub_peer_id = os.environ.get("ISLAND_IPFS_HUB_PEER_ID", "<hub_peer_id>")
    multiaddr = f"/dns4/{hub_host}/tcp/{hub_port}/p2p/{hub_peer_id}"
    return {
        "island_id": island_id,
        "chain_id": chain_id,
        "member_address": _to_ait_address(member_address),
        "swarm_key": key,
        "hub_multiaddr_template": multiaddr,
        "issued_at": datetime.now(UTC).isoformat(),
    }
