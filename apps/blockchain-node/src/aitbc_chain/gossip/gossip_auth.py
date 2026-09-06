"""Validator authentication for the public gossip WebSocket.

The hub's ``/rpc/gossip/ws`` endpoint uses a signed challenge/response:

1. Server sends ``{"type": "auth_challenge", "challenge": "uuid", "timestamp": float}``.
2. Client signs the message ``{"challenge", "address", "timestamp"}`` with its
   validator private key and returns the address and signature.
3. Server verifies the signature against the public ``VALIDATOR_SET``.

This reuses the existing secp256k1 consensus signing primitives and the public
validator set. No shared secret is needed.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from aitbc.crypto.consensus_signing import sign_consensus_message, verify_consensus_message
from aitbc.crypto.signature_recovery import canonical_address

from ..config import settings

# Topics only validators may publish to. Subscribing to these is allowed from
# anyone, but publishing requires a valid validator signature.
RESTRICTED_GOSSIP_TOPICS = ("blocks", "pbft", "consensus")

# Topics anyone may publish to (still rate-limited).
PUBLIC_GOSSIP_TOPICS = ("transactions", "status", "mempool")


def is_restricted_topic(topic: str) -> bool:
    """Return True if ``topic`` requires validator authentication to publish."""
    for prefix in RESTRICTED_GOSSIP_TOPICS:
        if topic == prefix or topic.startswith(prefix + "."):
            return True
    return False


def is_public_topic(topic: str) -> bool:
    """Return True if ``topic`` is in the public allow-list."""
    return any(topic == exact or topic.startswith(exact + ".") for exact in PUBLIC_GOSSIP_TOPICS)


def _parse_validator_set() -> list[Any]:
    """Parse ``VALIDATOR_SET`` from settings into a list of validator records."""
    if not settings.validator_set:
        return []
    try:
        data: Any = json.loads(settings.validator_set)
        if isinstance(data, list):
            return list(data)
        if isinstance(data, dict) and "validators" in data:
            return list(data["validators"])
        return []
    except json.JSONDecodeError:
        return []


def get_validator_addresses() -> set[str]:
    """Return the canonical validator addresses from ``VALIDATOR_SET``."""
    validators = _parse_validator_set()
    addresses: set[str] = set()
    for entry in validators:
        if not isinstance(entry, dict):
            continue
        address = entry.get("address")
        if address:
            addresses.add(canonical_address(str(address)))
    return addresses


def is_validator(address: str) -> bool:
    """Return True if ``address`` is a known validator."""
    return canonical_address(address) in get_validator_addresses()


def create_challenge() -> tuple[str, float]:
    """Create a new auth challenge."""
    return uuid.uuid4().hex, time.time()


def build_auth_message(challenge: str, address: str, timestamp: float) -> dict[str, Any]:
    """Build the canonical message that must be signed."""
    return {
        "challenge": challenge,
        "address": canonical_address(address),
        "timestamp": timestamp,
    }


def sign_challenge(challenge: str, address: str, timestamp: float, private_key: str) -> str:
    """Sign an auth challenge with a validator private key."""
    message = build_auth_message(challenge, address, timestamp)
    return sign_consensus_message(message, private_key)


def verify_challenge(challenge: str, address: str, timestamp: float, signature: str) -> bool:
    """Verify a challenge response from a claimed validator.

    Also rejects messages that are outside the configured challenge TTL to
    protect against replay of old challenges.
    """
    if not is_validator(address):
        return False
    if abs(time.time() - timestamp) > settings.gossip_auth_challenge_ttl:
        return False
    message = build_auth_message(challenge, address, timestamp)
    return verify_consensus_message(message, signature, address)
