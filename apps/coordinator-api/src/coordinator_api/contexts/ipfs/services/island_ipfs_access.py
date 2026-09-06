"""Island IPFS access control.

Queries the on-chain IPFS subscription table and serves the private swarm key
only to paid, signature-proving island members.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aitbc.aitbc_logging import get_logger
from eth_utils import keccak

from aitbc.crypto.signature_recovery import (  # PYTHONPATH makes this available
    canonical_address,
    verify_signature,
)

logger = get_logger(__name__)


def _to_ait_address(address: str) -> str:
    """Normalise to the `ait1` spelling used in the chain DB."""
    canonical = canonical_address(address)
    body = canonical.removeprefix("0x")
    if canonical.startswith("0x") and len(body) == 40:
        return f"ait1{body}"
    return canonical


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


def get_current_block_height(chain_id: str) -> int:
    """Return the current chain head height from the chain DB."""
    db_path = _chain_db_path(chain_id)
    if not db_path.exists():
        return 0
    try:
        with closing(sqlite3.connect(str(db_path))) as conn:
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
        with closing(sqlite3.connect(str(db_path))) as conn:
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


def _swarm_key_dir(island_id: str) -> Path:
    """Directory where island IPFS swarm keys are stored."""
    data_dir = Path(os.environ.get("AITBC_DATA_DIR", "/var/lib/aitbc/data"))
    return data_dir / "ipfs-island" / island_id


def _generate_swarm_key() -> str:
    """Generate a new 32-byte private swarm key in Kubo base16 format."""
    return f"/key/swarm/psk/1.0.0/\n/base16/\n{secrets.token_hex(32)}\n"


def get_island_swarm_key(island_id: str) -> str:
    """Return the island swarm key, creating it if necessary.

    The key is stored on disk and must be kept readable only by the hub.
    """
    key_dir = _swarm_key_dir(island_id)
    key_dir.mkdir(parents=True, exist_ok=True)
    key_file = key_dir / "swarm.key"
    if key_file.exists():
        return key_file.read_text()
    key = _generate_swarm_key()
    key_file.write_text(key)
    key_file.chmod(0o600)
    logger.info("Generated new private IPFS swarm key for island %s at %s", island_id, key_file)
    return key


def verify_member_signature(
    island_id: str,
    member_address: str,
    nonce: str,
    signature: str,
) -> bool:
    """Verify that member_address signed the swarm-key challenge message."""
    if not signature or not member_address:
        return False
    message = f"{island_id}:{member_address}:{nonce}".encode()
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
    if not verify_member_signature(island_id, member_address, nonce, signature):
        raise PermissionError("Invalid signature")
    if not is_ipfs_subscription_active(chain_id, island_id, member_address):
        raise PermissionError("No active IPFS subscription for this island")
    key = get_island_swarm_key(island_id)
    hub_host = os.environ.get("ISLAND_IPFS_HUB_HOST", "hub2.aitbc.bubuit.net")
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
