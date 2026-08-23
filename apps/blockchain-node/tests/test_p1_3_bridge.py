"""P1.3 cross-chain bridge integration tests.

Exercises the new bridge proof path:
- initiate a transfer on the source chain
- manually build and sign a source block with a bridge_state_root
- build a Merkle proof anchored to that block
- confirm the transfer on the target chain
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest
from eth_account import Account as EthAccount
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc.crypto.consensus_signing import sign_block_hash
from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.cross_chain.bridge_types import BridgeStatus, BridgeTransfer
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account, Block, CrossChainTransfer, Transaction
from aitbc_chain.state.merkle_patricia_trie import MerklePatriciaTrie


@pytest.fixture
def bridge() -> CrossChainBridge:
    """A CrossChainBridge backed by an in-memory SQLite database."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    chain_metadata.create_all(engine)
    try:
        yield CrossChainBridge(lambda: Session(engine))
    finally:
        chain_metadata.drop_all(engine)
        engine.dispose()


def _compute_bridge_state_root(record: CrossChainTransfer) -> str:
    """Recompute the bridge event trie root for the lock transfer."""
    trie = MerklePatriciaTrie()
    value = f"lock:{record.transfer_id}:{record.amount}:{record.target_chain}".encode()
    trie.put(record.transfer_id.encode(), value)
    return "0x" + trie.get_root().hex()


def _build_and_sign_block(
    bridge: CrossChainBridge,
    source_chain: str,
    proposer: EthAccount,
    height: int,
    transfer: BridgeTransfer,
) -> tuple[Block, str]:
    """Create a block containing the lock tx, sign it, and persist it."""
    with bridge._session_factory() as session:
        record = session.get(CrossChainTransfer, transfer.transfer_id)
        assert record is not None
        lock_tx = session.exec(
            select(Transaction).where(
                Transaction.chain_id == source_chain,
                Transaction.tx_hash == (record.source_tx_hash or transfer.transfer_id),
            )
        ).first()
        assert lock_tx is not None

        bridge_state_root = _compute_bridge_state_root(record)
        state_root = "0x" + "00" * 32
        parent_hash = "0x" + "00" * 32

        payload = (
            f"{source_chain}|{height}|{parent_hash}|{datetime.now(UTC).isoformat()}"
            f"|{lock_tx.tx_hash}"
            f"|{proposer.address.lower()}"
            f"|{state_root}"
            f"|{bridge_state_root}"
        ).encode()
        block_hash = "0x" + hashlib.sha256(payload).hexdigest()

        block = Block(
            chain_id=source_chain,
            height=height,
            hash=block_hash,
            parent_hash=parent_hash,
            proposer=proposer.address.lower(),
            timestamp=datetime.now(UTC),
            tx_count=1,
            state_root=state_root,
            bridge_state_root=bridge_state_root,
            signature="",
            block_metadata=None,
        )
        block.signature = sign_block_hash(block, proposer.key.hex())

        lock_tx.block_height = height
        session.add(block)
        session.add(lock_tx)
        session.commit()

        return block, block.signature


class TestP1_3Bridge:
    """End-to-end bridge proof flow for P1.3."""

    def test_initiate_build_proof_and_confirm(self, bridge: CrossChainBridge) -> None:
        """A transfer can be locked on the source chain and released on the target."""
        source_chain = "chain-a"
        target_chain = "chain-b"
        proposer = EthAccount.create()
        sender = "0x" + "11" * 20
        recipient = "0x" + "22" * 20

        # Seed the source and target chain accounts.
        with bridge._session_factory() as session:
            session.add(Account(chain_id=source_chain, address=sender, balance=1_000_000, nonce=0))
            session.add(Account(chain_id=target_chain, address=recipient, balance=0, nonce=0))
            session.commit()

        # Disable release-only fences so the test can pass without a full validator set.
        with (
            patch("aitbc_chain.config.settings.bridge_release_enabled", False),
            patch("aitbc_chain.config.settings.bridge_multisig_enabled", False),
            patch("aitbc_chain.config.settings.bridge_block_signature_required", True),
        ):
            transfer = bridge.initiate_transfer(
                source_chain, target_chain, sender, recipient, 10_000
            )
            assert transfer.status == BridgeStatus.locked

            # Build and persist the signed source block with bridge_state_root.
            block, _signature = _build_and_sign_block(
                bridge, source_chain, proposer, 1, transfer
            )

            # Store the corresponding bridge block header for proof verification.
            bridge.store_block_header(
                {
                    "chain_id": source_chain,
                    "height": block.height,
                    "hash": block.hash,
                    "parent_hash": block.parent_hash,
                    "proposer": block.proposer,
                    "state_root": block.state_root or "",
                    "bridge_state_root": block.bridge_state_root or "",
                    "signature": block.signature,
                    "confirmation_count": 10,
                    "finality_confirmed": True,
                }
            )

            # Build the proof from the source block.
            proof = bridge.build_proof(transfer.transfer_id, source_chain=source_chain)
            assert proof["source_chain"] == source_chain
            assert proof["target_chain"] == target_chain
            assert proof["block_hash"] == block.hash
            assert proof["proposer"] == block.proposer
            assert proof["parent_hash"] == block.parent_hash
            assert proof["proposer_signature"] == block.signature
            assert proof["state_root"] == block.state_root
            assert proof["bridge_state_root"] == block.bridge_state_root

            # Confirm on the target chain.
            completed = bridge.confirm_transfer(transfer.transfer_id, proof)
            assert completed.status == BridgeStatus.completed

        # The recipient should now hold the transferred amount on the target chain.
        with bridge._session_factory() as session:
            recipient_account = session.get(Account, (target_chain, recipient))
            assert recipient_account is not None
            assert recipient_account.balance == 10_000

            record = session.get(CrossChainTransfer, transfer.transfer_id)
            assert record is not None
            assert record.status == "completed"

    def test_build_proof_rejects_mismatched_bridge_state_root(self, bridge: CrossChainBridge) -> None:
        """build_proof raises when the block's bridge_state_root does not match recomputed."""
        source_chain = "chain-a"
        target_chain = "chain-b"
        proposer = EthAccount.create()
        sender = "0x" + "11" * 20
        recipient = "0x" + "22" * 20

        with bridge._session_factory() as session:
            session.add(Account(chain_id=source_chain, address=sender, balance=1_000_000, nonce=0))
            session.add(Account(chain_id=target_chain, address=recipient, balance=0, nonce=0))
            session.commit()

        with patch("aitbc_chain.config.settings.bridge_release_enabled", False):
            transfer = bridge.initiate_transfer(
                source_chain, target_chain, sender, recipient, 5_000
            )

            block, _signature = _build_and_sign_block(
                bridge, source_chain, proposer, 1, transfer
            )

        # Tamper with the bridge state root on the stored block.
        with bridge._session_factory() as session:
            stored = session.exec(
                select(Block).where(Block.chain_id == source_chain, Block.height == block.height)
            ).first()
            assert stored is not None
            stored.bridge_state_root = "0x" + "ff" * 32
            session.add(stored)
            session.commit()

        with pytest.raises(ValueError, match="bridge state root"):
            bridge.build_proof(transfer.transfer_id, source_chain=source_chain)
