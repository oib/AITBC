"""Unit tests for gossip topic classification.

These tests do not require Redis or an active node; they guard the topic
matching logic that the public websocket handler uses to decide whether a
topic requires validator authentication.
"""

from __future__ import annotations

import pytest

from aitbc_chain.gossip.gossip_auth import is_public_topic, is_restricted_topic


@pytest.mark.parametrize(
    ("topic", "expected"),
    [
        ("blocks", True),
        ("blocks.ait-testchain.local", True),
        ("pbft.prepare.ait-testchain.local", True),
        ("pbft.pre_prepare.ait-testchain.local", True),
        ("pbft.commit.ait-testchain.local", True),
        ("pbft", True),
        ("consensus.attest_request.ait-testchain.local", True),
        ("consensus.attest_response.ait-testchain.local", True),
        ("consensus", True),
        ("transactions", False),
        ("transactions.ait-testchain.local", False),
        ("status", False),
        ("mempool", False),
        ("mempool.pending", False),
        ("random", False),
    ],
)
def test_is_restricted_topic(topic: str, expected: bool) -> None:
    assert is_restricted_topic(topic) is expected


@pytest.mark.parametrize(
    ("topic", "expected"),
    [
        ("transactions", True),
        ("transactions.ait-testchain.local", True),
        ("status", True),
        ("status.health", True),
        ("mempool", True),
        ("mempool.pending", True),
        ("blocks", False),
        ("blocks.ait-testchain.local", False),
        ("pbft.prepare", False),
        ("pbft.pre_prepare", False),
        ("consensus.attest", False),
        ("random", False),
    ],
)
def test_is_public_topic(topic: str, expected: bool) -> None:
    assert is_public_topic(topic) is expected


# ---------------------------------------------------------------------------
# #1128: scoped signatures, single-use challenges, mint rate limit
# ---------------------------------------------------------------------------

from aitbc_chain.config import settings
from aitbc_chain.gossip import gossip_auth

_VALIDATOR_KEY = "22" * 32


def _validator_address() -> str:
    from eth_keys import keys

    return keys.PrivateKey(bytes.fromhex(_VALIDATOR_KEY)).public_key.to_checksum_address()


@pytest.fixture(autouse=True)
def _clean_challenge_state(monkeypatch: pytest.MonkeyPatch):
    gossip_auth._PENDING_CHALLENGES.clear()
    monkeypatch.setattr(settings, "validator_set", f'[{{"address": "{_validator_address()}"}}]')
    yield
    gossip_auth._PENDING_CHALLENGES.clear()


def _sign(challenge: str, ts: float, scope: str = "") -> tuple[str, str]:
    address = _validator_address()
    return address, gossip_auth.sign_challenge(challenge, address, ts, _VALIDATOR_KEY, scope)


def test_scope_binding_rejects_tampered_message() -> None:
    issued = gossip_auth.create_challenge("10.0.0.1")
    assert issued is not None
    challenge, ts = issued
    scope = gossip_auth.publish_scope("blocks.bc-2", {"a": 1})
    address, sig = _sign(challenge, ts, scope)
    # signature for {"a": 1} must not authorize {"a": 2}
    tampered = gossip_auth.publish_scope("blocks.bc-2", {"a": 2})
    assert not gossip_auth.verify_challenge(challenge, address, ts, sig, tampered)
    # and a different channel likewise
    other = gossip_auth.publish_scope("pbft.prepare", {"a": 1})
    assert not gossip_auth.verify_challenge(challenge, address, ts, sig, other)


def test_challenge_is_single_use() -> None:
    issued = gossip_auth.create_challenge("10.0.0.1")
    assert issued is not None
    challenge, ts = issued
    scope = gossip_auth.channel_scope("blocks.bc-2")
    address, sig = _sign(challenge, ts, scope)
    assert gossip_auth.verify_challenge(challenge, address, ts, sig, scope)
    # replay of the exact same response fails — the mint was consumed
    assert not gossip_auth.verify_challenge(challenge, address, ts, sig, scope)


def test_unminted_challenge_rejected() -> None:
    assert not gossip_auth.verify_challenge("deadbeef", _validator_address(), 1.0, "ab" * 65, "x")


def test_unscoped_signature_flag_off_and_on(monkeypatch: pytest.MonkeyPatch) -> None:
    issued = gossip_auth.create_challenge("10.0.0.1")
    assert issued is not None
    challenge, ts = issued
    address, sig = _sign(challenge, ts)  # legacy unscoped signature
    scope = gossip_auth.channel_scope("blocks.bc-2")
    monkeypatch.setattr(settings, "gossip_auth_require_scope", False)
    assert gossip_auth.verify_challenge(challenge, address, ts, sig, scope)

    issued2 = gossip_auth.create_challenge("10.0.0.1")
    assert issued2 is not None
    challenge2, ts2 = issued2
    address2, sig2 = _sign(challenge2, ts2)
    monkeypatch.setattr(settings, "gossip_auth_require_scope", True)
    assert not gossip_auth.verify_challenge(challenge2, address2, ts2, sig2, scope)


def test_canonical_scope_crosscheck() -> None:
    # Signer and verifier must serialize identically — unicode and nested
    # keys through the shared canonical_json (#1128 amendment 3).
    from eth_utils import keccak
    import json

    message = {"nested": {"z": 1, "a": [2, 3]}, "uni": "héllo—"}
    # Independent literal form — sorted keys, compact separators, UTF-8 —
    # so a canonical-form drift in the helper FAILS here, not self-agrees.
    canonical = json.dumps(message, sort_keys=True, separators=(",", ":")).encode()
    expected = "0x" + keccak(b"blocks.bc-2" + b":" + canonical).hex()
    assert gossip_auth.publish_scope("blocks.bc-2", message) == expected


def test_mint_rate_limit_is_per_ip() -> None:
    for _ in range(20):
        assert gossip_auth.create_challenge("10.0.0.9") is not None
    assert gossip_auth.create_challenge("10.0.0.9") is None
    assert gossip_auth.create_challenge("10.0.0.10") is not None


def test_flood_cannot_evict_fresh_challenge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gossip_auth, "_MAX_PENDING_CHALLENGES", 8)
    for i in range(7):
        assert gossip_auth.create_challenge(f"10.1.{i}.1") is not None
    # a fresh legitimate challenge still mints — oldest flood entry is evicted
    legit = gossip_auth.create_challenge("10.9.9.9")
    assert legit is not None
    assert legit[0] in gossip_auth._PENDING_CHALLENGES
