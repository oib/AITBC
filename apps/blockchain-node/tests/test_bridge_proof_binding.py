"""F1/F2: a bridge proof must bind the payout fields it is confirmed with.

Before this fix ``confirm_transfer`` built the transfer record from the proof
when the target chain had none, and ``_validate_proof`` then compared the
proof with that record — i.e. with itself. The Merkle check only proved that
the proof's own ``lock_event`` string sat under ``lock_tx_hash``, never that
the string matched the claimed amount or recipient. Any real lock proof could
be replayed under a fresh ``transfer_id`` with a new amount and recipient.

These tests take a real proof from ``build_proof()`` and mutate it.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest
from eth_account import Account as EthAccount
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc.crypto.consensus_signing import sign_block_hash
from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.cross_chain.bridge_leaf import lock_leaf_value
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account, Block, CrossChainTransfer, Transaction
from aitbc_chain.rpc.router import router
from aitbc_chain.state.merkle_patricia_trie import MerklePatriciaTrie

SOURCE = "chain-a"
TARGET = "chain-b"
SENDER = "0x" + "11" * 20
RECIPIENT = "0x" + "22" * 20
ATTACKER = "0x" + "ee" * 20
HEIGHT = 7


@pytest.fixture
def engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    yield engine
    chain_metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def bridge(engine) -> CrossChainBridge:
    return CrossChainBridge(lambda: Session(engine))


@pytest.fixture
def proposer() -> EthAccount:
    return EthAccount.create()


@pytest.fixture(autouse=True)
def _settings():
    # Legacy RPC-time mutation path, so locks get a Transaction row to seal;
    # single-signer proofs (multisig off) against a registered validator set.
    with (
        patch("aitbc_chain.config.settings.supported_chains", f"{SOURCE},{TARGET}"),
        patch("aitbc_chain.config.settings.block_scoped_preregistered_transactions", False),
        patch("aitbc_chain.config.settings.bridge_release_enabled", False),
        patch("aitbc_chain.config.settings.bridge_multisig_enabled", False),
        patch("aitbc_chain.config.settings.bridge_block_signature_required", True),
        patch("aitbc_chain.config.settings.bridge_lock_leaf_v2_height", None),
    ):
        yield


def _lock(bridge: CrossChainBridge, engine: Any, amount: int, recipient: str = RECIPIENT) -> str:
    with Session(engine) as session:
        account = session.get(Account, (SOURCE, SENDER))
        if account is None:
            session.add(Account(chain_id=SOURCE, address=SENDER, balance=10_000_000, nonce=0))
            session.commit()
    return bridge.initiate_transfer(SOURCE, TARGET, SENDER, recipient, amount).transfer_id


def _seal(
    bridge: CrossChainBridge, engine: Any, proposer: EthAccount, transfer_ids: list[str], store_header: bool = True
) -> Block:
    """Seal the given locks into one signed source block, as the proposer would."""
    with Session(engine) as session:
        trie = MerklePatriciaTrie()
        locks = []
        for tid in transfer_ids:
            record = session.get(CrossChainTransfer, tid)
            assert record is not None
            leaf = lock_leaf_value(record.transfer_id, record.amount, record.target_chain, record.recipient, HEIGHT)
            trie.put(tid.encode(), leaf.encode())
            lock_tx = session.exec(select(Transaction).where(Transaction.chain_id == SOURCE, Transaction.tx_hash == tid)).one()
            locks.append(lock_tx)
        bridge_state_root = "0x" + trie.get_root().hex()
        block = Block(
            chain_id=SOURCE,
            height=HEIGHT,
            hash="0x" + hashlib.sha256(f"{SOURCE}|{HEIGHT}|{bridge_state_root}".encode()).hexdigest(),
            parent_hash="0x" + "00" * 32,
            proposer=proposer.address.lower(),
            timestamp=datetime.now(UTC),
            tx_count=len(locks),
            state_root="0x" + "00" * 32,
            bridge_state_root=bridge_state_root,
            signature="",
            block_metadata=None,
        )
        block.signature = sign_block_hash(block, proposer.key.hex())
        for tx in locks:
            tx.block_height = HEIGHT
            session.add(tx)
        session.add(block)
        session.commit()
        session.refresh(block)
    if store_header:
        bridge.store_block_header(
            {
                "chain_id": SOURCE,
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
    return block


def _forget_lock(engine: Any, transfer_id: str) -> None:
    """Drop the local record, so the confirm looks like a lock served on another node."""
    with Session(engine) as session:
        record = session.get(CrossChainTransfer, transfer_id)
        assert record is not None
        session.delete(record)
        session.commit()


def _released_to(engine: Any, recipient: str) -> list[Transaction]:
    with Session(engine) as session:
        return list(
            session.exec(
                select(Transaction).where(
                    Transaction.chain_id == TARGET,
                    Transaction.type == "BRIDGE_RELEASE",
                    Transaction.recipient == recipient,
                )
            ).all()
        )


@pytest.fixture
def sealed(bridge: CrossChainBridge, engine: Any, proposer: EthAccount) -> dict[str, Any]:
    """Two real locks sealed in one block; the proposer is chain-a's validator set."""
    bridge.register_validator(SOURCE, proposer.address.lower(), "0x", 0)
    small = _lock(bridge, engine, 1_000)
    other = _lock(bridge, engine, 2_000, recipient="0x" + "33" * 20)
    _seal(bridge, engine, proposer, [small, other])
    return {
        "small": small,
        "other": other,
        "proof": bridge.build_proof(small, source_chain=SOURCE),
        "other_proof": bridge.build_proof(other, source_chain=SOURCE),
    }


class TestForgedConfirmRejected:
    """F1: mutate a real proof; confirm_transfer must raise and release nothing."""

    def test_genuine_proof_still_confirms(self, bridge: CrossChainBridge, sealed: dict[str, Any], engine: Any) -> None:
        transfer = bridge.confirm_transfer(sealed["small"], sealed["proof"])
        assert transfer.amount == 1_000
        assert len(_released_to(engine, RECIPIENT)) == 1

    def test_replay_under_new_transfer_id_rejected(
        self, bridge: CrossChainBridge, sealed: dict[str, Any], engine: Any
    ) -> None:
        """The proof is untouched; only a fresh transfer_id makes the proof hash new."""
        forged_id = "0x" + "ab" * 32
        with pytest.raises(ValueError):
            bridge.confirm_transfer(forged_id, dict(sealed["proof"]))
        assert _released_to(engine, RECIPIENT) == []

    def test_changed_amount_rejected(self, bridge: CrossChainBridge, sealed: dict[str, Any], engine: Any) -> None:
        forged = dict(sealed["proof"], amount=9_000_000)
        with pytest.raises(ValueError):
            bridge.confirm_transfer("0x" + "ac" * 32, forged)
        with pytest.raises(ValueError):
            bridge.confirm_transfer(sealed["small"], forged)
        assert _released_to(engine, RECIPIENT) == []

    def test_changed_recipient_rejected(self, bridge: CrossChainBridge, sealed: dict[str, Any], engine: Any) -> None:
        forged = dict(sealed["proof"], recipient=ATTACKER)
        with pytest.raises(ValueError):
            bridge.confirm_transfer("0x" + "ad" * 32, forged)
        with pytest.raises(ValueError):
            bridge.confirm_transfer(sealed["small"], forged)
        assert _released_to(engine, ATTACKER) == []

    def test_changed_amount_and_recipient_rejected(
        self, bridge: CrossChainBridge, sealed: dict[str, Any], engine: Any
    ) -> None:
        """The review's scenario: new transfer_id, amount and recipient over a real lock."""
        forged = dict(sealed["proof"], amount=9_000_000, recipient=ATTACKER)
        with pytest.raises(ValueError):
            bridge.confirm_transfer("0x" + "ae" * 32, forged)
        assert _released_to(engine, ATTACKER) == []

    def test_lock_event_swapped_for_another_real_leaf_rejected(
        self, bridge: CrossChainBridge, sealed: dict[str, Any], engine: Any
    ) -> None:
        """The other lock's key, leaf and path verify in the trie, but are not this transfer's."""
        other = sealed["other_proof"]
        forged = dict(
            sealed["proof"],
            lock_tx_hash=other["lock_tx_hash"],
            lock_event=other["lock_event"],
            merkle_proof=other["merkle_proof"],
        )
        with pytest.raises(ValueError):
            bridge.confirm_transfer(sealed["small"], forged)
        forged_amount = dict(forged, amount=2_000)
        with pytest.raises(ValueError):
            bridge.confirm_transfer("0x" + "af" * 32, forged_amount)
        assert _released_to(engine, RECIPIENT) == []

    def test_lock_event_rewritten_rejected(self, bridge: CrossChainBridge, sealed: dict[str, Any]) -> None:
        forged = dict(sealed["proof"], lock_event=f"lock:{sealed['small']}:9000000:{TARGET}")
        with pytest.raises(ValueError):
            bridge.confirm_transfer(sealed["small"], forged)


class TestLockOnAnotherNode:
    """F1: with no local record, only a recipient-bound leaf can stand on its own."""

    def test_rejected_while_leaf_v2_unarmed(self, bridge: CrossChainBridge, sealed: dict[str, Any], engine: Any) -> None:
        _forget_lock(engine, sealed["small"])
        with pytest.raises(ValueError):
            bridge.confirm_transfer(sealed["small"], sealed["proof"])

    def test_recipient_bound_leaf_confirms_and_binds(
        self, bridge: CrossChainBridge, engine: Any, proposer: EthAccount
    ) -> None:
        with patch("aitbc_chain.config.settings.bridge_lock_leaf_v2_height", HEIGHT):
            bridge.register_validator(SOURCE, proposer.address.lower(), "0x", 0)
            tid = _lock(bridge, engine, 5_000)
            _seal(bridge, engine, proposer, [tid])
            proof = bridge.build_proof(tid, source_chain=SOURCE)
            assert proof["lock_event"] == f"lock:{tid}:5000:{TARGET}:{RECIPIENT}"
            _forget_lock(engine, tid)

            for forged in (
                dict(proof, amount=9_000_000),
                dict(proof, recipient=ATTACKER),
                dict(proof, lock_event=f"lock:{tid}:9000000:{TARGET}:{ATTACKER}", amount=9_000_000, recipient=ATTACKER),
            ):
                with pytest.raises(ValueError):
                    bridge.confirm_transfer(tid, forged)
            with pytest.raises(ValueError):
                bridge.confirm_transfer("0x" + "ba" * 32, proof)

            transfer = bridge.confirm_transfer(tid, proof)
            assert (transfer.amount, transfer.recipient) == (5_000, RECIPIENT)
        assert _released_to(engine, ATTACKER) == []


class TestUnverifiableHeadersRejected:
    """F2: the proof may not supply its own header or vouch for its own signer."""

    def test_header_not_stored_rejected(self, bridge: CrossChainBridge, engine: Any, proposer: EthAccount) -> None:
        bridge.register_validator(SOURCE, proposer.address.lower(), "0x", 0)
        tid = _lock(bridge, engine, 1_000)
        _seal(bridge, engine, proposer, [tid], store_header=False)
        proof = dict(bridge.build_proof(tid, source_chain=SOURCE), confirmation_count=99, finality_confirmed=True)
        with pytest.raises(ValueError):
            bridge.confirm_transfer(tid, proof)

    def test_no_validator_set_rejected(self, bridge: CrossChainBridge, engine: Any, proposer: EthAccount) -> None:
        tid = _lock(bridge, engine, 1_000)
        _seal(bridge, engine, proposer, [tid])
        with pytest.raises(ValueError):
            bridge.confirm_transfer(tid, bridge.build_proof(tid, source_chain=SOURCE))

    def test_freshness_without_validators_is_false(self, bridge: CrossChainBridge) -> None:
        assert bridge._check_validator_set_freshness(SOURCE) is False


class TestConfirmRouteFence:
    """F2: escrow_enabled alone no longer opens /bridge/confirm."""

    @pytest.mark.parametrize("path", ["/bridge/confirm", "/bridge/batch/confirm"])
    def test_escrow_only_returns_503(self, bridge: CrossChainBridge, path: str) -> None:
        app = FastAPI()
        app.include_router(router)
        body: dict[str, Any] = {
            "transfer_id": "t1",
            "proof": {"target_chain": TARGET},
            "confirmer": ATTACKER,
            "signature": "0x" + "00" * 65,
        }
        if path.endswith("batch/confirm"):
            body = {"confirmations": [body]}
        with (
            patch("aitbc_chain.config.settings.escrow_enabled", True),
            patch("aitbc_chain.cross_chain.bridge.get_cross_chain_bridge", return_value=bridge),
        ):
            resp = TestClient(app).post(path, json=body)
        assert resp.status_code == 503
