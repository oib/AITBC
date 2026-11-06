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

from aitbc.crypto.consensus_signing import canonical_json, sign_consensus_message, verify_consensus_message
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.security import RateLimiter

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


# Pending single-use challenges: {challenge: (expiry, client_ip)}.
# In-memory and per-process BY DESIGN (#1128): only the process that minted
# a challenge can verify it, and a restart drops the set — clients simply
# re-handshake. There is deliberately no shared store.
_PENDING_CHALLENGES: dict[str, tuple[float, str]] = {}

# Bound on pending challenges. When full, the OLDEST-UNUSED entry is evicted
# so a fresh legitimate challenge always gets in; combined with the per-IP
# mint limit below, a single flooding source can neither fill the table nor
# evict anyone else's fresh challenge.
_MAX_PENDING_CHALLENGES = 4096

# Per-client-IP mint limiter for challenge issuers (GET /gossip/challenge
# and the ws auth_challenge frame). Unauthenticated endpoints would
# otherwise let an attacker churn the pending set.
_challenge_mint_rate = RateLimiter(rate=20, per=60)


def create_challenge(client_ip: str = "") -> tuple[str, float] | None:
    """Mint a single-use challenge, or None when the issuer is rate-limited.

    The challenge is bound to this process and expires after
    ``gossip_auth_challenge_ttl`` seconds; it is consumed on first
    successful verify (#1128).
    """
    if client_ip and not _challenge_mint_rate.is_allowed(f"challenge:{client_ip}"):
        return None
    now = time.time()
    if len(_PENDING_CHALLENGES) >= _MAX_PENDING_CHALLENGES:
        oldest = min(_PENDING_CHALLENGES, key=lambda c: _PENDING_CHALLENGES[c][0])
        _PENDING_CHALLENGES.pop(oldest, None)
    challenge = uuid.uuid4().hex
    _PENDING_CHALLENGES[challenge] = (now + settings.gossip_auth_challenge_ttl, client_ip)
    return challenge, now


def _scope_payload(channel: str, message: Any) -> bytes:
    """Canonical bytes for a publish scope: channel + canonical message."""
    payload = message if isinstance(message, dict) else {"message": message}
    return channel.encode("utf-8") + b":" + canonical_json(payload)


def publish_scope(channel: str, message: Any) -> str:
    """Scope for a publish authorization: keccak256(channel:canonical(message))."""
    from eth_utils import keccak

    return "0x" + keccak(_scope_payload(channel, message)).hex()


def channel_scope(channel: str, chain_id: str = "") -> str:
    """Scope for a websocket connection authorization.

    With ``chain_id`` the scope is ``keccak256("channel:"+chain+":"+channel)``
    — a validator signature minted for one chain can never satisfy another
    chain's scope (#1159). The ordering and separator are the wire contract:
    dialers MUST use this exact format. An empty ``chain_id`` reproduces the
    legacy ``keccak256("channel:"+channel)`` scope, kept for rollout
    compatibility while ``gossip_auth_require_chain_scope`` is off.
    """
    from eth_utils import keccak

    scoped = f"channel:{chain_id}:{channel}" if chain_id else f"channel:{channel}"
    return "0x" + keccak(scoped.encode("utf-8")).hex()


def build_auth_message(challenge: str, address: str, timestamp: float, scope: str = "") -> dict[str, Any]:
    """Build the canonical message that must be signed.

    ``scope`` binds the signature to exactly one payload/topic (#1128):
    ``publish_scope(channel, message)`` for relay publishes and
    ``channel_scope(channel)`` for websocket connections. An empty scope
    reproduces the legacy unbound signature — only accepted while
    ``gossip_auth_require_scope`` is off.
    """
    message: dict[str, Any] = {
        "challenge": challenge,
        "address": canonical_address(address),
        "timestamp": timestamp,
    }
    if scope:
        message["scope"] = scope
    return message


def sign_challenge(challenge: str, address: str, timestamp: float, private_key: str, scope: str = "") -> str:
    """Sign an auth challenge with a validator private key."""
    message = build_auth_message(challenge, address, timestamp, scope)
    return sign_consensus_message(message, private_key)


def verify_challenge(
    challenge: str,
    address: str,
    timestamp: float,
    signature: str,
    scope: str = "",
    legacy_scope: str = "",
) -> bool:
    """Verify a challenge response from a claimed validator.

    The challenge must have been minted by THIS process and is consumed on
    first successful verify — a second use, even inside the TTL window,
    fails (#1128). ``scope`` is the caller-derived binding for what is
    being authorized; when ``gossip_auth_require_scope`` is off (rolling
    rollout), a signature made without scope is still accepted, while a
    scoped signature is always checked strictly.

    ``legacy_scope`` (#1159): when the primary scope fails and
    ``gossip_auth_require_chain_scope`` is off, the signature is retried
    against the pre-chain-binding scope so old and new dialers keep
    gossiping mid-rollout. Once the flag flips, only the chain-bound scope
    is accepted.
    """
    if settings.gossip_auth_require_scope and not scope:
        return False  # scoped era: unbound signatures are not accepted
    pending = _PENDING_CHALLENGES.get(challenge)
    if pending is None:
        return False  # unknown or already consumed
    if pending[0] < time.time():
        _PENDING_CHALLENGES.pop(challenge, None)
        return False
    if not is_validator(address):
        return False
    if abs(time.time() - timestamp) > settings.gossip_auth_challenge_ttl:
        return False
    ok = verify_consensus_message(build_auth_message(challenge, address, timestamp, scope), signature, address)
    if not ok and legacy_scope and legacy_scope != scope and not settings.gossip_auth_require_chain_scope:
        # Chain-binding rollout compat (#1159): accept a signature made
        # against the legacy chain-less scope while the flag is off.
        ok = verify_consensus_message(build_auth_message(challenge, address, timestamp, legacy_scope), signature, address)
    if not ok and scope and not settings.gossip_auth_require_scope:
        # Rollout compat: accept a legacy unscoped signature while the flag
        # is off so old and new nodes keep gossiping mid-restart (#1128).
        ok = verify_consensus_message(build_auth_message(challenge, address, timestamp), signature, address)
    if ok:
        _PENDING_CHALLENGES.pop(challenge, None)
    return ok
