"""Regression test: the block handed to the proposer-schedule check must be signed-header-complete.

``BlockImportMixin._append_block`` builds a ``Block`` up front and passes it to
``_validate_proposer_schedule``, which -- when multi-validator consensus is on --
calls ``MultiValidatorPoA.validate_block`` and verifies the proposer signature
over the canonical block header.

That header includes ``state_root`` and ``bridge_state_root``. The early
``Block`` used to leave both unset because the comment said roots are "filled in
after transactions have been applied", so the follower rebuilt a *different*
header than the one the proposer signed. Recovery then returned an unrelated
address and every multi-validator block was rejected with "Block signature does
not match the declared proposer", even though the signature was valid.

Observed live on 2026-09-05: block 2555 was signed correctly by the hub yet
rejected by hub2 and node1, forking the fleet until the flag was rolled back.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aitbc.crypto.consensus_signing import sign_block_hash, verify_block_signature
from aitbc_chain.sync_block_import import BlockImportMixin

# Test-only key material: a fixed, well-known throwaway scalar. It authenticates
# nothing and exists solely so the test can produce a real secp256k1 signature.
_TEST_PRIVATE_KEY = "0x" + "11" * 32
_CHAIN_ID = "test-append-chain"


def _proposer_address() -> str:
    from eth_keys import keys

    return keys.PrivateKey(bytes.fromhex(_TEST_PRIVATE_KEY[2:])).public_key.to_checksum_address()


class _Importer(BlockImportMixin):
    """Minimal concrete importer: _append_block only needs the chain id here."""

    def __init__(self, chain_id: str) -> None:
        self._chain_id = chain_id


class _Captured(Exception):
    """Stops _append_block right after the block is built, before any DB work."""


def _signed_block_data() -> dict:
    proposer = _proposer_address()
    header = {
        "chain_id": _CHAIN_ID,
        "height": 2555,
        "hash": "0x" + "ab" * 32,
        "parent_hash": "0x" + "cd" * 32,
        "proposer": proposer,
        "state_root": "0x" + "bb" * 32,
        "bridge_state_root": "0x" + "00" * 32,
    }
    block_data = dict(header)
    block_data["timestamp"] = datetime(2026, 9, 5, 16, 17, 54, tzinfo=UTC).isoformat()
    block_data["tx_count"] = 0
    block_data["signature"] = sign_block_hash(header, _TEST_PRIVATE_KEY)
    return block_data


def _capture_block(monkeypatch, importer):
    captured = {}

    def _fake(self, session, block_data, block):
        captured["block"] = block
        raise _Captured

    monkeypatch.setattr(BlockImportMixin, "_validate_proposer_schedule", _fake)
    block_data = _signed_block_data()
    with pytest.raises(_Captured):
        importer._append_block(None, block_data, [])
    return captured["block"], block_data


def test_schedule_check_sees_the_signed_state_roots(monkeypatch):
    """The roots must be on the block before the schedule check, not after."""
    block, block_data = _capture_block(monkeypatch, _Importer(_CHAIN_ID))
    assert block.state_root == block_data["state_root"]
    assert block.bridge_state_root == block_data["bridge_state_root"]


def test_proposer_signature_verifies_against_the_early_block(monkeypatch):
    """The exact check that rejected block 2555 on hub2 and node1."""
    block, block_data = _capture_block(monkeypatch, _Importer(_CHAIN_ID))
    assert verify_block_signature(block, block_data["signature"], block_data["proposer"]) is True


def test_signature_fails_when_the_roots_are_dropped(monkeypatch):
    """Pins the failure mode itself: blank roots make a valid signature look forged."""
    block, block_data = _capture_block(monkeypatch, _Importer(_CHAIN_ID))
    block.state_root = None
    block.bridge_state_root = None
    assert verify_block_signature(block, block_data["signature"], block_data["proposer"]) is False
