"""Unsigned-transaction acceptance — the consensus hole this file confirms.

Transactions are served to followers by ``/rpc/blocks-range`` (and the gossip
block-push / ``/rpc/sync`` export paths) as ``Transaction.model_dump()``. The
row has no top-level ``signature`` column — the signed envelope lives nested
in the ``envelope`` column. ``_append_block`` builds ``tx_data`` from that
served dict, so no top-level ``signature`` is ever present, and both apply
paths (``apply_transaction`` / ``compute_state_delta``) verify a signature
only "when a signature field is present". Unsigned means skipped, at every
version. The v7+ nonce check is likewise bypassed: ``use_account_nonce_override``
returns True for unsigned transactions, so the recorded nonce is rewritten to
the live account nonce before any nonce comparison runs.

Consequence: a single compromised validator key can propose a block carrying
an unsigned TRANSFER out of any account. Attesters sign only header fields
(``remote_attestation._handle_request`` signs chain_id/height/hash/
parent_hash/proposer/state_root/bridge_state_root — it never executes a
transaction), so the block collects quorum; every follower then applies the
unsigned tx because nothing served a signature to check.

These tests assert the CURRENT (vulnerable) behaviour so the hole is pinned
in CI. At the v9 fix they flip: unsigned user-type transactions must be
rejected on every path, and a nested signed envelope must be hoisted and
verified rather than ignored.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from aitbc.crypto.crypto import derive_ethereum_address
from aitbc_chain.base_models import Account, Block
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc.utils import sign_transaction_data
from aitbc_chain.sync import ChainSync
from sqlmodel import Session, create_engine, select

CHAIN = "unsigned-import"
T0 = datetime(2026, 1, 1, tzinfo=UTC)

KEY_VICTIM = "0x" + "aa" * 32  # the proposer does NOT hold this key
KEY_ATTACKER = "0x" + "bb" * 32  # proposer-controlled recipient

ADDR_VICTIM = derive_ethereum_address(KEY_VICTIM)
ADDR_ATTACKER = derive_ethereum_address(KEY_ATTACKER)


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path}/chain.db")
    chain_metadata.create_all(engine)

    @contextmanager
    def factory():
        with Session(engine) as session:
            yield session
            session.commit()

    return factory


def _seed_genesis(session_factory) -> None:
    """Block 0 + the victim account — recorded root must equal the real one."""
    from aitbc_chain.state.state_root_utils import compute_state_root_full

    with session_factory() as session:
        session.add(Account(chain_id=CHAIN, address=ADDR_VICTIM, balance=10**9, nonce=0))
        session.add(
            Block(
                chain_id=CHAIN,
                height=0,
                hash="0x" + "00" * 32,
                parent_hash="0x00",
                proposer="genesis",
                timestamp=T0,
                tx_count=0,
            )
        )
        session.commit()
        genesis = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 0)).one()
        genesis.state_root = compute_state_root_full(session, CHAIN)
        session.commit()


def _served_tx(**overrides: Any) -> dict[str, Any]:
    """A transaction row exactly as ``/rpc/blocks-range`` serves it:
    ``Transaction.model_dump()`` plus the ``from``/``to`` aliases — signature,
    if any, exists only inside ``envelope``; there is no top-level
    ``signature`` key."""
    tx: dict[str, Any] = {
        "sender": ADDR_VICTIM,
        "recipient": ADDR_ATTACKER,
        "from": ADDR_VICTIM,
        "to": ADDR_ATTACKER,
        "value": 999,  # served rows carry ``value``, not ``amount``
        "fee": 1,
        "nonce": 0,
        "payload": {},
        "type": "TRANSFER",
        "status": "confirmed",
        "tx_hash": "0x" + "cc" * 32,
        "chain_id": CHAIN,
        "envelope": None,
    }
    tx.update(overrides)
    return tx


def _block(height: int, txs: list[dict[str, Any]], state_root: str = "") -> dict[str, Any]:
    return {
        "chain_id": CHAIN,
        "height": height,
        "hash": f"0x{height:064x}",
        "parent_hash": "0x" + "00" * 32,
        "proposer": ADDR_ATTACKER,
        "timestamp": (T0).isoformat(),
        "tx_count": len(txs),
        "state_root": state_root,
        "block_metadata": '{"state_transition_version": 8}',
        "signature": "",  # block header sig — a real validator would sign
        "transactions": txs,
    }


def _import(sync: ChainSync, block_data: dict[str, Any]):
    # Root check skipped for the fixture: it changes nothing about the finding.
    # A malicious proposer applies its own unsigned txs when building the block
    # and records the resulting (correct) state_root — followers recompute the
    # same root, so the check passes for them too. The hole is the tx check,
    # not the root arithmetic.
    return sync.import_block(block_data, transactions=block_data["transactions"], skip_state_root_validation=True)


class TestUnsignedServedTransactions:
    """The hole: import applies served transactions without ever checking a
    signature, at every version, because served rows never carry one."""

    def test_unsigned_transfer_from_foreign_account_is_applied(self, session_factory, monkeypatch):
        """A validator proposes an unsigned TRANSFER draining an account it
        holds no key for. The follower applies it. Also demonstrate the nonce
        rewrite bypass: the recorded nonce (777) never matched the account's
        and is silently overwritten before the nonce check."""
        from aitbc_chain.config import settings

        monkeypatch.setattr(settings, "parallel_tx_validation", True)
        monkeypatch.setattr(settings, "conflict_threshold", 1.0)

        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)

        tx = _served_tx(nonce=777)  # bogus nonce — rewritten, never checked
        result = _import(sync, _block(1, [tx]))

        assert result.accepted, f"block unexpectedly rejected: {result.reason}"
        with session_factory() as session:
            victim = session.get(Account, (CHAIN, ADDR_VICTIM))
            attacker = session.get(Account, (CHAIN, ADDR_ATTACKER))
            assert victim is not None and attacker is not None
            assert victim.balance == 10**9 - 999 - 1  # drained, no signature needed
            assert victim.nonce == 1  # applied despite recorded nonce 777
            assert attacker.balance == 999

    def test_nested_signed_envelope_is_never_checked(self, session_factory, monkeypatch):
        """Even when the served row DOES carry a signed envelope, import never
        hoists or verifies it: here the envelope is genuinely signed by the
        victim's key — over amount=10 — while the served row moves 999. The
        follower applies 999. The signature on the wire is decorative."""
        from aitbc_chain.config import settings

        monkeypatch.setattr(settings, "parallel_tx_validation", True)
        monkeypatch.setattr(settings, "conflict_threshold", 1.0)

        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)

        # A real signed envelope — but for a different transfer than the one
        # the served row executes.
        envelope: dict[str, Any] = {
            "from": ADDR_VICTIM,
            "to": ADDR_ATTACKER,
            "amount": 10,
            "fee": 1,
            "nonce": 0,
            "payload": {},
            "type": "TRANSFER",
            "chain_id": CHAIN,
        }
        envelope["signature"] = sign_transaction_data(envelope, KEY_VICTIM)

        tx = _served_tx(value=999, envelope=envelope, tx_hash="0x" + "dd" * 32)
        result = _import(sync, _block(1, [tx]))

        assert result.accepted, f"block unexpectedly rejected: {result.reason}"
        with session_factory() as session:
            victim = session.get(Account, (CHAIN, ADDR_VICTIM))
            assert victim is not None
            # Served value applied (999), not the signed envelope value (10).
            assert victim.balance == 10**9 - 999 - 1
