"""
In-memory public key registry for the Agent Coordinator.

Public keys can be registered by agents and fetched by the encryptor at
runtime without reading from the local filesystem.  The MessageEncryptor
falls back to this registry when a key is not present in its own key pairs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

# agent_id -> {"public_key": bytes, "key_id": str, "created_at": str}
PUBLIC_KEY_REGISTRY: dict[str, dict[str, Any]] = {}


def register_public_key(agent_id: str, public_key: bytes, key_id: str = "") -> bool:
    """Register a public key for an agent."""
    try:
        PUBLIC_KEY_REGISTRY[agent_id] = {
            "agent_id": agent_id,
            "public_key": public_key,
            "key_id": key_id or f"{agent_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
            "created_at": datetime.now(UTC).isoformat(),
        }
        logger.info("Registered public key for agent %s", agent_id)
        return True
    except Exception as e:
        logger.error("Error registering public key for %s: %s", agent_id, e)
        return False


def get_public_key(agent_id: str) -> bytes | None:
    """Fetch a public key for an agent from the registry."""
    entry = PUBLIC_KEY_REGISTRY.get(agent_id)
    if entry:
        # Registry values are dict[str, Any]; the "public_key" slot is only ever
        # written by register_public_key(), which takes bytes.
        public_key: bytes = entry["public_key"]
        return public_key
    return None


def get_all_public_keys() -> dict[str, dict[str, Any]]:
    """Return a shallow copy of the registry."""
    return dict(PUBLIC_KEY_REGISTRY)
