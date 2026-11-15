"""#1940 F5 — tx-derived bridge-root contract tests.

Covers the shared ``bridge_tx_root`` module, the history-only gate, producer
prefilter semantics, importer enforcement (actual-success tracking, carried
root, row upgrades), proof-builder locator policy and the v9 structural
check. Gate-off behavior must remain byte-identical to legacy.
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from sqlmodel import Session, create_engine, select

from aitbc_chain.base_models import Account, Block, ChainParameter, ChainParameterHistory
from aitbc_chain.cross_chain.bridge_tx_root import (
    BRIDGE_TX_ROOT_PARAMETER,
    assert_lock_debit,
    build_tx_bridge_trie,
    canonical_lock_fields,
    effective_lock_debit,
    resolve_lock_type,
    stored_lock_body,
    tx_only_root_active,
)
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Transaction
from aitbc_chain.sync import ChainSync
from aitbc.crypto.crypto import derive_ethereum_address

CHAIN = "f5-1940"
T0 = datetime(2026, 1, 1, tzinfo=UTC)
SENDER_KEY = "0x" + "77" * 32
SENDER = derive_ethereum_address(SENDER_KEY)
RECIPIENT = "0x" + "22" * 20
AUTHORITY_KEY = "0x" + "88" * 32
AUTHORITY = derive_ethereum_address(AUTHORITY_KEY)
TXHASH = "0x" + "ab" * 32


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch):
    from aitbc_chain.config import settings

    monkeypatch.setattr(settings, "bridge_lock_leaf_v2_height", 0)
    monkeypatch.setattr(settings, "parallel_tx_validation", False)
    monkeypatch.setattr(settings, "bridge_root_shadow_check", False)
    yield settings


@pytest.fixture()
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/chain.db")
    chain_metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session_factory(engine):
    @contextmanager
    def factory():
        with Session(engine) as session:
            yield session
            session.commit()

    return factory


def _genesis(session_factory) -> None:
    with session_factory() as session:
        session.add(Account(chain_id=CHAIN, address=SENDER, balance=10**9, nonce=0))
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


def _history(session, value="true", applied_height=0, chain=CHAIN, parameter=BRIDGE_TX_ROOT_PARAMETER) -> None:
    session.add(ChainParameterHistory(chain_id=chain, parameter=parameter, value=value, applied_height=applied_height))


def _authority(session) -> None:
    _history(session, AUTHORITY, 0, parameter="bridge_release_authority")


SENDER2_KEY = "0x" + "66" * 32
SENDER2 = derive_ethereum_address(SENDER2_KEY)
WRONG_KEY = "0x" + "55" * 32


def _lock_body(
    tx_hash: str = TXHASH,
    transfer_id: str | None = None,
    amount: int = 5000,
    payload_amount: int | None = None,
    top_amount: int | None = None,
    top_type: str | None = "BRIDGE_LOCK",
    value: int | None = None,
    sender: str = SENDER,
    nonce: int = 0,
    bridge_key: str = AUTHORITY_KEY,
) -> dict[str, Any]:
    payload = {
        "transfer_id": transfer_id or tx_hash,
        "amount": payload_amount if payload_amount is not None else amount,
        "target_chain": "sep",
        "target_recipient": RECIPIENT,
        "asset": "AIT",
    }
    body: dict[str, Any] = {
        "from": sender,
        "to": "bridge_lock",
        "fee": 0,
        "nonce": nonce,
        "chain_id": CHAIN,
        "tx_hash": tx_hash,
        "payload": payload,
    }
    if top_type is not None:
        body["type"] = top_type
    amt = top_amount if top_amount is not None else amount
    body["amount"] = amt
    if value is not None:
        body["value"] = value
    elif top_amount is None:
        body["value"] = amt
    from aitbc_chain.state.bridge_credit import sign_bridge_lock

    body["bridge_signature"] = sign_bridge_lock(body, tx_hash, bridge_key)
    return body


def _root(bodies: list[dict[str, Any]], height: int = 1) -> str:
    return "0x" + build_tx_bridge_trie(bodies, CHAIN, height).get_root().hex()


def _block(height: int, txs: list[dict[str, Any]], root: str | None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "chain_id": CHAIN,
        "height": height,
        "hash": "0x" + hashlib.sha256(f"{CHAIN}|{height}|{root}".encode()).hexdigest(),
        "parent_hash": "0x" + "00" * 32,
        "proposer": "0x" + "33" * 20,
        "timestamp": T0.isoformat(),
        "tx_count": len(txs),
        "block_metadata": '{"state_transition_version": 8}',
        "signature": "",
        "state_root": "0x" + "00" * 32,
    }
    if root is not None:
        data["bridge_state_root"] = root
    return data


def _sync(session_factory) -> ChainSync:
    return ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)


# ---------------------------------------------------------------- gate tests
class TestGate:
    def test_off_by_default(self, session_factory) -> None:
        _genesis(session_factory)
        with session_factory() as s:
            assert tx_only_root_active(s, CHAIN, 1) is False
            assert tx_only_root_active(s, CHAIN, 10**9) is False

    def test_history_h_affects_h_plus_1(self, session_factory) -> None:
        _genesis(session_factory)
        with session_factory() as s:
            _history(s, "true", applied_height=5)
            s.commit()
            assert tx_only_root_active(s, CHAIN, 5) is False
            assert tx_only_root_active(s, CHAIN, 6) is True
            assert tx_only_root_active(s, CHAIN, 7) is True

    def test_genesis_history_and_bad_values(self, session_factory) -> None:
        _genesis(session_factory)
        with session_factory() as s:
            _history(s, " TRUE ", applied_height=0)
            s.commit()
            assert tx_only_root_active(s, CHAIN, 1) is True
        with session_factory() as s2:
            assert tx_only_root_active(s2, "other-chain", 9) is False
        # later history rows for the SAME parameter override: invalid
        # spellings resolve inactive, and the boundary moves with them
        with session_factory() as s3:
            for i, bad in enumerate(("yes", "no", "2", "", "enabled"), start=1):
                _history(s3, bad, applied_height=i)
            s3.commit()
            assert tx_only_root_active(s3, CHAIN, 1) is True  # only applied_height<=0 counts
            assert tx_only_root_active(s3, CHAIN, 6) is False  # latest <=5 is "enabled"
            assert tx_only_root_active(s3, CHAIN, 10) is False

    def test_current_row_null_height_inert(self, session_factory) -> None:
        _genesis(session_factory)
        with session_factory() as s:
            s.add(ChainParameter(chain_id=CHAIN, parameter=BRIDGE_TX_ROOT_PARAMETER, value="true"))
            s.commit()
            assert tx_only_root_active(s, CHAIN, 1) is False
            assert tx_only_root_active(s, CHAIN, 100) is False

    def test_non_int_height_inactive(self, session_factory) -> None:
        _genesis(session_factory)
        with session_factory() as s:
            _history(s, "true", 0)
            s.commit()
            assert tx_only_root_active(s, CHAIN, 0) is False
            assert tx_only_root_active(s, CHAIN, -3) is False
            assert tx_only_root_active(s, CHAIN, True) is False  # type: ignore[arg-type]


# ------------------------------------------------------------ unit contract
class TestContract:
    def test_effective_debit_aliases(self) -> None:
        assert effective_lock_debit({"amount": 5}) == 5
        assert effective_lock_debit({"value": 7}) == 7
        assert effective_lock_debit({}) == 0
        assert effective_lock_debit({"amount": 5, "value": 5}) == 5
        with pytest.raises(ValueError):
            effective_lock_debit({"amount": 5, "value": 6})
        with pytest.raises(ValueError):
            effective_lock_debit({"amount": "5"})

    def test_canonical_fields_payload_first(self) -> None:
        body = _lock_body(payload_amount=5000, top_amount=6000)
        fields = canonical_lock_fields(body, TXHASH, CHAIN, 1)
        assert fields.amount == 5000  # signed payload-first amount
        assert fields.transfer_id == TXHASH
        assert fields.target_recipient == RECIPIENT
        assert fields.source_chain == CHAIN
        with pytest.raises(ValueError):
            assert_lock_debit(fields, effective_lock_debit(body))

    def test_canonical_rejects_bad_shapes(self) -> None:
        body = _lock_body()
        body["payload"]["target_chain"] = ""
        with pytest.raises(ValueError):
            canonical_lock_fields(body, TXHASH, CHAIN, 1)
        body2 = _lock_body()
        body2["payload"]["source_chain"] = "other"
        body2["chain_id"] = "other"
        with pytest.raises(ValueError):
            canonical_lock_fields(body2, TXHASH, CHAIN, 1)
        with pytest.raises(ValueError):
            canonical_lock_fields({"type": "TRANSFER"}, TXHASH, CHAIN, 1)

    def test_resolve_lock_type_conflicts(self) -> None:
        lock = _lock_body(top_type=None)  # payload-typed only? top_type None removes 'type'
        lock["payload"]["type"] = "BRIDGE_LOCK"
        assert resolve_lock_type(lock, None) == "BRIDGE_LOCK"
        assert resolve_lock_type(lock, "BRIDGE_LOCK") == "BRIDGE_LOCK"
        with pytest.raises(ValueError):
            resolve_lock_type(lock, "TRANSFER")
        with pytest.raises(ValueError):
            resolve_lock_type({"type": "TRANSFER"}, "BRIDGE_LOCK")
        # non-lock disagreement keeps stored-wins legacy precedence
        assert resolve_lock_type({"type": "MESSAGE"}, "TRANSFER") == "TRANSFER"

    def test_trie_empty_dup_and_v1v2(self) -> None:
        assert _root([]) == "0x" + build_tx_bridge_trie([], CHAIN, 1).get_root().hex()
        b1 = _lock_body("0x" + "01" * 32, transfer_id="t1")
        b2 = _lock_body("0x" + "02" * 32, transfer_id="t2")
        assert _root([b1, b2]) != _root([b1])
        with pytest.raises(ValueError):
            build_tx_bridge_trie([b1, dict(b1)], CHAIN, 1)
        # non-lock bodies contribute no leaf and are not an error
        assert "0x" + build_tx_bridge_trie([{"type": "TRANSFER", "tx_hash": "0x1"}, b1], CHAIN, 1).get_root().hex() == _root(
            [b1]
        )

    def test_stored_lock_body_envelope_and_columns(self) -> None:
        body = _lock_body()
        row = SimpleNamespace(
            envelope=dict(body),
            payload=dict(body["payload"]),
            sender=SENDER,
            recipient="bridge_lock",
            value=5000,
            fee=0,
            nonce=0,
            type="BRIDGE_LOCK",
            tx_hash=TXHASH,
            chain_id=CHAIN,
        )
        out = stored_lock_body(row)
        # envelope wins; the signed transfer_id lives in the payload and the
        # authoritative row hash is always injected at top level.
        assert out["tx_hash"] == TXHASH
        assert out["payload"]["transfer_id"] == TXHASH
        assert canonical_lock_fields(out, TXHASH, CHAIN, 1).transfer_id == TXHASH
        rebuilt = stored_lock_body(
            SimpleNamespace(
                envelope=None,
                payload={"transfer_id": "t", "amount": 3},
                sender=SENDER,
                recipient="r",
                value=3,
                fee=1,
                nonce=2,
                type="BRIDGE_LOCK",
                tx_hash="0x9",
                chain_id=CHAIN,
            )
        )
        assert rebuilt["payload"]["transfer_id"] == "t"
        assert rebuilt["tx_hash"] == "0x9"


# ------------------------------------------------------------- import tests
class TestImport:
    def _armed(self, session_factory) -> None:
        _genesis(session_factory)
        with session_factory() as s:
            _history(s, "true", 0)
            _authority(s)
            s.commit()

    def test_valid_lock_imports_and_debits(self, session_factory) -> None:
        self._armed(session_factory)
        body = _lock_body()
        root = _root([body])
        res = _sync(session_factory).import_block(
            _block(1, [body], root), transactions=[body], skip_state_root_validation=True
        )
        assert res.accepted, res.reason
        with session_factory() as s:
            blk = s.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 1)).one()
            assert blk.bridge_state_root == root
            tx = s.exec(select(Transaction).where(Transaction.tx_hash == TXHASH)).one()
            assert tx.type == "BRIDGE_LOCK"
            assert tx.status == "confirmed"
            assert tx.envelope["payload"]["transfer_id"] == TXHASH
            acct = s.get(Account, (CHAIN, SENDER))
            assert acct.balance == 10**9 - 5000

    def test_gate_off_trusts_carried_root(self, session_factory) -> None:
        _genesis(session_factory)
        body = _lock_body()
        forged = "0x" + "ff" * 32
        res = _sync(session_factory).import_block(
            _block(1, [body], forged), transactions=[body], skip_state_root_validation=True
        )
        assert res.accepted, res.reason  # legacy: carried root trusted, no tx-derived check
        with session_factory() as s:
            blk = s.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 1)).one()
            assert blk.bridge_state_root == forged

    def test_missing_root_rejects(self, session_factory) -> None:
        self._armed(session_factory)
        body = _lock_body()
        res = _sync(session_factory).import_block(
            _block(1, [body], None), transactions=[body], skip_state_root_validation=True
        )
        assert not res.accepted
        with session_factory() as s:
            assert s.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 1)).first() is None

    def test_mismatched_root_rejects_and_rolls_back(self, session_factory) -> None:
        self._armed(session_factory)
        body = _lock_body()
        res = _sync(session_factory).import_block(
            _block(1, [body], "0x" + "ff" * 32), transactions=[body], skip_state_root_validation=True
        )
        assert not res.accepted
        with session_factory() as s:
            assert s.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 1)).first() is None
            assert s.exec(select(Transaction).where(Transaction.tx_hash == TXHASH)).first() is None
            acct = s.get(Account, (CHAIN, SENDER))
            assert acct.balance == 10**9

    def test_failed_lock_rejects_whole_block_below_v20(self, session_factory) -> None:
        self._armed(session_factory)
        body = _lock_body(amount=10**12, payload_amount=10**12, top_amount=10**12, value=10**12)
        # insufficient balance -> apply fails; v8 would persist "confirmed"
        root = _root([body])
        res = _sync(session_factory).import_block(
            _block(1, [body], root), transactions=[body], skip_state_root_validation=True
        )
        assert not res.accepted
        with session_factory() as s:
            assert s.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 1)).first() is None
            assert s.exec(select(Transaction).where(Transaction.tx_hash == TXHASH)).first() is None

    def test_payload_typed_lock_stores_resolved_type(self, session_factory) -> None:
        self._armed(session_factory)
        body = _lock_body(top_type="TRANSFER")
        body["payload"]["type"] = "BRIDGE_LOCK"
        root = _root([body])
        res = _sync(session_factory).import_block(
            _block(1, [body], root), transactions=[body], skip_state_root_validation=True
        )
        assert res.accepted, res.reason
        with session_factory() as s:
            tx = s.exec(select(Transaction).where(Transaction.tx_hash == TXHASH)).one()
            assert tx.type == "BRIDGE_LOCK"

    def test_amount_debit_split_rejects(self, session_factory) -> None:
        self._armed(session_factory)
        body = _lock_body(payload_amount=5000, top_amount=6000, value=6000)
        res = _sync(session_factory).import_block(
            _block(1, [body], _root([body])), transactions=[body], skip_state_root_validation=True
        )
        assert not res.accepted

    def test_stored_type_conflict_rejects(self, session_factory) -> None:
        self._armed(session_factory)
        body = _lock_body(top_type=None)
        body["payload"]["type"] = "BRIDGE_LOCK"
        with session_factory() as s:
            s.add(
                Transaction(
                    chain_id=CHAIN,
                    tx_hash=TXHASH,
                    type="TRANSFER",
                    status="pending",
                    sender=SENDER,
                    recipient="bridge_lock",
                    value=0,
                    fee=0,
                    nonce=0,
                    payload={},
                    envelope={},
                )
            )
            s.commit()
        res = _sync(session_factory).import_block(
            _block(1, [body], _root([body])), transactions=[body], skip_state_root_validation=True
        )
        assert not res.accepted

    def test_duplicate_lock_hash_rejects(self, session_factory) -> None:
        self._armed(session_factory)
        b1 = _lock_body()
        b2 = dict(b1)
        res = _sync(session_factory).import_block(
            _block(1, [b1, b2], _root([b1])), transactions=[b1, b2], skip_state_root_validation=True
        )
        assert not res.accepted

    def test_row_upgrade_semantics(self, session_factory) -> None:
        self._armed(session_factory)
        body = _lock_body()
        with session_factory() as s:
            s.add(
                Transaction(
                    chain_id=CHAIN,
                    tx_hash=TXHASH,
                    type="BRIDGE_LOCK",
                    status="rejected",
                    sender="0x" + "99" * 20,
                    recipient="stale",
                    value=1,
                    fee=9,
                    nonce=9,
                    payload={"stale": True},
                    envelope={"stale": True},
                )
            )
            s.commit()
        res = _sync(session_factory).import_block(
            _block(1, [body], _root([body])), transactions=[body], skip_state_root_validation=True
        )
        assert res.accepted, res.reason
        with session_factory() as s:
            tx = s.exec(select(Transaction).where(Transaction.tx_hash == TXHASH)).one()
            assert tx.type == "BRIDGE_LOCK"
            assert tx.sender == SENDER
            assert tx.value == 5000
            assert tx.envelope["payload"]["transfer_id"] == TXHASH
            assert "stale" not in tx.envelope

    def test_header_only_with_locks_fails(self, session_factory) -> None:
        self._armed(session_factory)
        body = _lock_body()
        res = _sync(session_factory).import_block(
            _block(1, [], _root([body])), transactions=None, skip_state_root_validation=True
        )
        assert not res.accepted


# ------------------------------------------------------------- proof tests
class TestProof:
    def test_proof_without_cct(self, session_factory, engine) -> None:
        from aitbc_chain.cross_chain.bridge import CrossChainBridge

        _genesis(session_factory)
        with session_factory() as s:
            _history(s, "true", 0)
            s.commit()
        body = _lock_body()
        with Session(engine) as s:
            row = Transaction(
                chain_id=CHAIN,
                tx_hash=TXHASH,
                type="BRIDGE_LOCK",
                status="confirmed",
                sender=SENDER,
                recipient="bridge_lock",
                value=5000,
                fee=0,
                nonce=0,
                payload=dict(body["payload"]),
                envelope=dict(body),
                block_height=1,
                timestamp=T0.isoformat(),
            )
            s.add(row)
            bodies = [stored_lock_body(row)]
            root = "0x" + build_tx_bridge_trie(bodies, CHAIN, 1).get_root().hex()
            s.add(
                Block(
                    chain_id=CHAIN,
                    height=1,
                    hash="0x" + "dd" * 32,
                    parent_hash="0x" + "00" * 32,
                    proposer="0x" + "33" * 20,
                    timestamp=T0,
                    tx_count=1,
                    state_root="0x" + "00" * 32,
                    bridge_state_root=root,
                    signature="0xsig",
                )
            )
            s.commit()
        bridge = CrossChainBridge(lambda: Session(engine))
        proof = bridge.build_proof(TXHASH, source_chain=CHAIN)
        assert proof["amount"] == 5000
        assert proof["sender"] == SENDER
        assert proof["recipient"] == RECIPIENT
        assert proof["target_chain"] == "sep"
        assert proof["merkle_proof"]
        assert proof["lock_event"].startswith("lock:")

    def test_distinct_transfer_id_needs_locator(self, session_factory, engine) -> None:
        from aitbc_chain.cross_chain.bridge import CrossChainBridge

        _genesis(session_factory)
        distinct = "0x" + "ef" * 32
        body = _lock_body(transfer_id=distinct)
        with session_factory() as s:
            _history(s, "true", 0)
            s.commit()
        with Session(engine) as s:
            row = Transaction(
                chain_id=CHAIN,
                tx_hash=TXHASH,
                type="BRIDGE_LOCK",
                status="confirmed",
                sender=SENDER,
                recipient="bridge_lock",
                value=5000,
                fee=0,
                nonce=0,
                payload=dict(body["payload"]),
                envelope=dict(body),
                block_height=7,
                timestamp=T0.isoformat(),
            )
            s.add(row)
            root = "0x" + build_tx_bridge_trie([stored_lock_body(row)], CHAIN, 7).get_root().hex()
            blk = Block(
                chain_id=CHAIN,
                height=7,
                hash="0x" + "ee" * 32,
                parent_hash="0x" + "00" * 32,
                proposer="0x" + "33" * 20,
                timestamp=T0,
                tx_count=1,
                state_root="0x" + "00" * 32,
                bridge_state_root=root,
                signature="0xsig",
            )
            s.add(blk)
            s.commit()
            block_hash = blk.hash
        bridge = CrossChainBridge(lambda: Session(engine))
        with pytest.raises(ValueError):
            bridge.build_proof(distinct, source_chain=CHAIN)
        proof = bridge.build_proof(distinct, source_chain=CHAIN, block_hash=block_hash)
        assert proof["lock_tx_hash"] == TXHASH
        assert proof["amount"] == 5000
        # caller-height locator resolves the same new-era block
        proof = bridge.build_proof(distinct, source_chain=CHAIN, block_height=7)
        assert proof["lock_tx_hash"] == TXHASH
        assert proof["block_height"] == 7
        # CCT source_tx_hash as a pure block locator finds the canonical id
        from aitbc_chain.models import CrossChainTransfer

        with Session(engine) as s:
            s.add(
                CrossChainTransfer(
                    transfer_id=distinct,
                    source_chain=CHAIN,
                    target_chain="sep",
                    sender=SENDER,
                    recipient=RECIPIENT,
                    amount=5000,
                    asset="AIT",
                    status="pending",
                    source_tx_hash=TXHASH,
                )
            )
            s.commit()
        proof = bridge.build_proof(distinct, source_chain=CHAIN)
        assert proof["lock_tx_hash"] == TXHASH
        assert proof["block_height"] == 7
        assert proof["amount"] == 5000

    def test_pre_era_source_uses_legacy_path(self, session_factory, engine) -> None:
        """F4: a genuine pre-era source block (history activates at height 7)
        resolves through the legacy CCT-derived path — the tx-only resolver
        and funnel must leave it untouched."""
        from aitbc_chain.cross_chain.bridge import CrossChainBridge
        from aitbc_chain.cross_chain.bridge_leaf import unknown_lock_leaf
        from aitbc_chain.models import CrossChainTransfer
        from aitbc_chain.state.merkle_patricia_trie import MerklePatriciaTrie

        _genesis(session_factory)
        distinct = "0x" + "ef" * 32
        body = _lock_body(transfer_id=distinct)
        with session_factory() as s:
            # applied_height=6 -> era active only for height >= 7; block 3 is legacy
            _history(s, "true", 6)
            s.commit()
        with Session(engine) as s:
            s.add(
                Transaction(
                    chain_id=CHAIN,
                    tx_hash=TXHASH,
                    type="BRIDGE_LOCK",
                    status="confirmed",
                    sender=SENDER,
                    recipient="bridge_lock",
                    value=5000,
                    fee=0,
                    nonce=0,
                    payload=dict(body["payload"]),
                    envelope=dict(body),
                    block_height=3,
                    timestamp=T0.isoformat(),
                )
            )
            trie = MerklePatriciaTrie()
            trie.put(TXHASH.encode(), unknown_lock_leaf(TXHASH).encode())
            root = "0x" + trie.get_root().hex()
            s.add(
                Block(
                    chain_id=CHAIN,
                    height=3,
                    hash="0x" + "ee" * 32,
                    parent_hash="0x" + "00" * 32,
                    proposer="0x" + "33" * 20,
                    timestamp=T0,
                    tx_count=1,
                    state_root="0x" + "00" * 32,
                    bridge_state_root=root,
                    signature="0xsig",
                )
            )
            s.add(
                CrossChainTransfer(
                    transfer_id=distinct,
                    source_chain=CHAIN,
                    target_chain="sep",
                    sender=SENDER,
                    recipient=RECIPIENT,
                    amount=5000,
                    asset="AIT",
                    status="pending",
                    source_tx_hash=TXHASH,
                )
            )
            s.commit()
        bridge = CrossChainBridge(lambda: Session(engine))
        proof = bridge.build_proof(distinct, source_chain=CHAIN)
        assert proof["block_height"] == 3
        assert proof["lock_tx_hash"] == TXHASH
        assert proof["merkle_proof"]


# ----------------------------------------------------------------- v9 test
class TestV9:
    def test_structural_check_refuses_bad_root(self, session_factory) -> None:
        from aitbc_chain.consensus.remote_attestation_v9 import _V9Mixin

        _genesis(session_factory)
        with session_factory() as s:
            _history(s, "true", 0)
            s.commit()
        body = _lock_body()
        good_root = _root([body])
        header = {"bridge_state_root": "0x" + "ff" * 32, "chain_id": CHAIN}
        attester = SimpleNamespace(_chain_id=CHAIN)
        with session_factory() as s:
            r = _V9Mixin._v9_tx_root_structural_check(attester, s, header, [body], 1)
            assert r == "bridge_state_root_mismatch"
            header["bridge_state_root"] = good_root
            assert _V9Mixin._v9_tx_root_structural_check(attester, s, header, [body], 1) is None
            header["bridge_state_root"] = ""
            assert _V9Mixin._v9_tx_root_structural_check(attester, s, header, [body], 1) == "missing_bridge_state_root"

    def test_structural_check_rejects_debit_split(self, session_factory) -> None:
        from aitbc_chain.consensus.remote_attestation_v9 import _V9Mixin

        _genesis(session_factory)
        with session_factory() as s:
            _history(s, "true", 0)
            s.commit()
        body = _lock_body(payload_amount=5000, top_amount=6000, value=6000)
        attester = SimpleNamespace(_chain_id=CHAIN)
        with session_factory() as s:
            r = _V9Mixin._v9_tx_root_structural_check(attester, s, {"bridge_state_root": _root([body])}, [body], 1)
            assert r is not None and "bridge_lock_contract" in r


# ----------------------------------------------------------------- ops test
class TestOpsParam:
    def test_bridge_value_group_strict_bool(self) -> None:
        import importlib.util
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            "gpc", Path(__file__).resolve().parents[3] / "scripts/ops/governance_parameter_change.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert "bridge_state_root_tx_only_enabled" in mod.ALL_PARAMETERS
        assert mod._validated_value("bridge_state_root_tx_only_enabled", " TRUE ") == ("true", ["true"])
        assert mod._validated_value("bridge_state_root_tx_only_enabled", "1") == ("1", ["1"])
        assert mod._validated_value("bridge_state_root_tx_only_enabled", "0") == ("0", ["0"])
        for bad in ("yes", "no", "on", "2", ""):
            with pytest.raises(SystemExit):
                mod._validated_value("bridge_state_root_tx_only_enabled", bad)


# ------------------------------------------------- rework-required cases
class TestStoredBodyHashAuthority:
    def test_envelope_without_hash_gets_row_hash(self) -> None:
        body = _lock_body()
        env = dict(body)
        env.pop("tx_hash", None)
        row = SimpleNamespace(
            envelope=env,
            payload=dict(body["payload"]),
            sender=SENDER,
            recipient="bridge_lock",
            value=5000,
            fee=0,
            nonce=0,
            type="BRIDGE_LOCK",
            tx_hash=TXHASH,
            chain_id=CHAIN,
        )
        out = stored_lock_body(row)
        assert out["tx_hash"] == TXHASH
        assert "tx_hash" not in env  # stored JSON not mutated

    def test_conflicting_envelope_hash_overridden(self) -> None:
        body = _lock_body()
        env = dict(body)
        env["tx_hash"] = "0x" + "99" * 32
        row = SimpleNamespace(
            envelope=env,
            payload={},
            sender=SENDER,
            recipient="r",
            value=1,
            fee=0,
            nonce=0,
            type="BRIDGE_LOCK",
            tx_hash=TXHASH,
            chain_id=CHAIN,
        )
        assert stored_lock_body(row)["tx_hash"] == TXHASH

    def test_served_wrapper_hoist_keeps_row_hash(self) -> None:
        body = _lock_body()
        inner = dict(body)
        inner["signature"] = "0x" + "99" * 65
        wrapper = {"signature": "", "envelope": inner, "tx_hash": "0x" + "77" * 32}
        row = SimpleNamespace(
            envelope=wrapper,
            payload={},
            sender=SENDER,
            recipient="r",
            value=1,
            fee=0,
            nonce=0,
            type="BRIDGE_LOCK",
            tx_hash=TXHASH,
            chain_id=CHAIN,
        )
        out = stored_lock_body(row)
        assert out["tx_hash"] == TXHASH
        assert out["payload"]["transfer_id"] == TXHASH


class TestLeafBoundary:
    def test_v1_vs_v2_leaf(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from aitbc_chain.config import settings
        from aitbc_chain.cross_chain.bridge_leaf import lock_leaf_value

        monkeypatch.setattr(settings, "bridge_lock_leaf_v2_height", 10)
        assert lock_leaf_value("t", 5, "sep", RECIPIENT, 9) == "lock:t:5:sep"
        assert lock_leaf_value("t", 5, "sep", RECIPIENT, 10) == f"lock:t:5:sep:{RECIPIENT}"
        assert lock_leaf_value("t", 5, "sep", "", 10) == "lock:t:5:sep:"

    def test_trie_requires_recipient_at_v2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from aitbc_chain.config import settings

        monkeypatch.setattr(settings, "bridge_lock_leaf_v2_height", 0)
        body = _lock_body()
        body["payload"]["target_recipient"] = ""
        with pytest.raises(ValueError):
            build_tx_bridge_trie([body], CHAIN, 1)
        monkeypatch.setattr(settings, "bridge_lock_leaf_v2_height", 100)
        assert "0x" + build_tx_bridge_trie([body], CHAIN, 1).get_root().hex()


class TestProofLocators:
    def _seal(
        self, session_factory, engine, height: int, bodies: list[dict[str, Any]], transfer_id: str | None = None
    ) -> tuple[Any, str, str]:
        from aitbc_chain.cross_chain.bridge import CrossChainBridge

        rows = []
        with Session(engine) as s:
            for i, b in enumerate(bodies):
                h = b.get("tx_hash") or f"0x{i:064x}"
                row = Transaction(
                    chain_id=CHAIN,
                    tx_hash=h,
                    type="BRIDGE_LOCK",
                    status="confirmed",
                    sender=SENDER,
                    recipient="bridge_lock",
                    value=5000,
                    fee=0,
                    nonce=i,
                    payload=dict(b.get("payload") or {}),
                    envelope=dict(b),
                    block_height=height,
                    timestamp=T0.isoformat(),
                )
                s.add(row)
                rows.append(row)
            root = "0x" + build_tx_bridge_trie([stored_lock_body(r) for r in rows], CHAIN, height).get_root().hex()
            blk = Block(
                chain_id=CHAIN,
                height=height,
                hash="0x" + hashlib.sha256(f"{CHAIN}|{height}|{root}".encode()).hexdigest(),
                parent_hash="0x" + "00" * 32,
                proposer="0x" + "33" * 20,
                timestamp=T0,
                tx_count=len(rows),
                state_root="0x" + "00" * 32,
                bridge_state_root=root,
                signature="0xsig",
            )
            s.add(blk)
            s.commit()
            block_hash = blk.hash
        return CrossChainBridge(lambda: Session(engine)), block_hash, root

    def _arm(self, session_factory) -> None:
        _genesis(session_factory)
        with session_factory() as s:
            _history(s, "true", 0)
            s.commit()

    def test_merkle_proof_verifies(self, session_factory, engine) -> None:

        self._arm(session_factory)
        body = _lock_body()
        bridge, _, _ = self._seal(session_factory, engine, 7, [body])
        proof = bridge.build_proof(TXHASH, source_chain=CHAIN)
        # actual verifier: rebuild trie from sealed rows, verify tx_hash -> leaf bytes
        with Session(engine) as s:
            row = s.exec(select(Transaction).where(Transaction.tx_hash == TXHASH)).one()
            bodies = [stored_lock_body(row)]
        trie = build_tx_bridge_trie(bodies, CHAIN, 7)
        assert trie.verify_proof(
            TXHASH.encode(),
            proof["lock_event"].encode(),
            [bytes.fromhex(p) for p in proof["merkle_proof"]],
        )

    def test_producer_envelope_hash_shapes_proof_verifies(self, session_factory, engine) -> None:
        """Producer-shaped envelopes (no tx_hash / conflicting tx_hash) still
        prove under the authoritative row hash, verified by the real Merkle
        verifier — not merely nonempty proof bytes."""
        from aitbc_chain.cross_chain.bridge import CrossChainBridge

        self._arm(session_factory)
        b_missing = _lock_body("0x" + "31" * 32)
        env_missing = dict(b_missing)
        env_missing.pop("tx_hash", None)
        b_conflict = _lock_body("0x" + "32" * 32)
        env_conflict = dict(b_conflict)
        env_conflict["tx_hash"] = "0x" + "99" * 32
        with Session(engine) as s:
            rows = []
            for i, (b, env) in enumerate(((b_missing, env_missing), (b_conflict, env_conflict))):
                row = Transaction(
                    chain_id=CHAIN,
                    tx_hash=b["tx_hash"],
                    type="BRIDGE_LOCK",
                    status="confirmed",
                    sender=SENDER,
                    recipient="bridge_lock",
                    value=5000,
                    fee=0,
                    nonce=i,
                    payload=dict(b["payload"]),
                    envelope=env,
                    block_height=7,
                    timestamp=T0.isoformat(),
                )
                s.add(row)
                rows.append(row)
            env_missing_snapshot = dict(env_missing)
            env_conflict_snapshot = dict(env_conflict)
            sealed_bodies = [stored_lock_body(r) for r in rows]
            root = "0x" + build_tx_bridge_trie(sealed_bodies, CHAIN, 7).get_root().hex()
            s.add(
                Block(
                    chain_id=CHAIN,
                    height=7,
                    hash="0x" + hashlib.sha256(f"{CHAIN}|7|{root}".encode()).hexdigest(),
                    parent_hash="0x" + "00" * 32,
                    proposer="0x" + "33" * 20,
                    timestamp=T0,
                    tx_count=2,
                    state_root="0x" + "00" * 32,
                    bridge_state_root=root,
                    signature="0xsig",
                )
            )
            s.commit()
        assert env_missing == env_missing_snapshot
        assert env_conflict == env_conflict_snapshot
        trie = build_tx_bridge_trie(sealed_bodies, CHAIN, 7)
        bridge = CrossChainBridge(lambda: Session(engine))
        for tx_hash in ("0x" + "31" * 32, "0x" + "32" * 32):
            proof = bridge.build_proof(tx_hash, source_chain=CHAIN)
            assert proof["lock_tx_hash"] == tx_hash
            assert proof["block_height"] == 7
            assert trie.verify_proof(
                tx_hash.encode(),
                proof["lock_event"].encode(),
                [bytes.fromhex(p) for p in proof["merkle_proof"]],
            )

    def test_explicit_block_hash_authoritative(self, session_factory, engine) -> None:
        self._arm(session_factory)
        body = _lock_body()
        bridge, block_hash, _ = self._seal(session_factory, engine, 7, [body])
        proof = bridge.build_proof(TXHASH, source_chain=CHAIN, block_hash=block_hash)
        assert proof["lock_tx_hash"] == TXHASH

    def test_explicit_block_hash_conflict_reaches_funnel(self, session_factory, engine) -> None:
        """With a CCT record present the legacy path resolves its actual
        new-era block; a conflicting explicit block_hash must hit the
        funnel's conflict refusal, not a generic lookup error."""
        from aitbc_chain.models import CrossChainTransfer

        self._arm(session_factory)
        body = _lock_body()
        bridge, _, _ = self._seal(session_factory, engine, 7, [body])
        with Session(engine) as s:
            s.add(
                CrossChainTransfer(
                    transfer_id=TXHASH,
                    source_chain=CHAIN,
                    target_chain="sep",
                    sender=SENDER,
                    recipient=RECIPIENT,
                    amount=5000,
                    asset="AIT",
                    status="pending",
                    source_tx_hash=TXHASH,
                )
            )
            s.commit()
        with pytest.raises(ValueError, match="conflicts"):
            bridge.build_proof(TXHASH, source_chain=CHAIN, block_hash="0x" + "ff" * 32)

    def test_stale_cct_hint_correct_locator_wins(self, session_factory, engine) -> None:
        from aitbc_chain.models import CrossChainTransfer

        self._arm(session_factory)
        # stale CCT record pointing at an OLD-ERA block height 3
        old_body = _lock_body("0x" + "01" * 32, transfer_id="0x" + "02" * 32)
        bridge_old, _, _ = self._seal(session_factory, engine, 3, [old_body])
        # the real new-era lock at height 7
        body = _lock_body()
        bridge, block_hash, _ = self._seal(session_factory, engine, 7, [body])
        with Session(engine) as s:
            s.add(
                CrossChainTransfer(
                    transfer_id=TXHASH,
                    source_chain=CHAIN,
                    target_chain="sep",
                    sender=SENDER,
                    recipient=RECIPIENT,
                    amount=5000,
                    asset="AIT",
                    status="pending",
                    source_tx_hash=old_body["tx_hash"],
                )
            )
            s.commit()
        # explicit correct locator beats the stale CCT hint
        proof = bridge.build_proof(TXHASH, source_chain=CHAIN, block_hash=block_hash)
        assert proof["block_height"] == 7
        assert proof["amount"] == 5000

    def test_ambiguous_canonical_id_refuses(self, session_factory, engine) -> None:
        self._arm(session_factory)
        tid = "0x" + "42" * 32
        b1 = _lock_body("0x" + "11" * 32, transfer_id=tid)
        b2 = _lock_body("0x" + "22" * 32, transfer_id=tid)
        bridge, _, _ = self._seal(session_factory, engine, 7, [b1, b2])
        with pytest.raises(ValueError, match="ambiguous"):
            bridge.build_proof(tid, source_chain=CHAIN, block_height=7)

    def test_ambiguous_tx_row_locator_refuses(self, session_factory, engine) -> None:
        """F1: transfer_id == tx_hash must not bypass the block scan's
        multi-match ambiguity refusal."""
        self._arm(session_factory)
        tid = "0x" + "42" * 32
        b1 = _lock_body(tid)  # tx_hash == canonical transfer_id
        b2 = _lock_body("0x" + "22" * 32, transfer_id=tid)
        bridge, _, _ = self._seal(session_factory, engine, 7, [b1, b2])
        with pytest.raises(ValueError, match="ambiguous"):
            bridge.build_proof(tid, source_chain=CHAIN)

    def test_non_confirmed_sealed_row_refuses(self, session_factory, engine) -> None:
        """F2: a sealed row whose status is not 'confirmed' canonical-matches
        but is excluded from the proof trie — build_proof must refuse rather
        than serve a proof with an empty merkle path."""
        from aitbc_chain.cross_chain.bridge import CrossChainBridge

        self._arm(session_factory)
        body = _lock_body()
        with Session(engine) as s:
            s.add(
                Transaction(
                    chain_id=CHAIN,
                    tx_hash=TXHASH,
                    type="BRIDGE_LOCK",
                    status="failed",
                    sender=SENDER,
                    recipient="bridge_lock",
                    value=5000,
                    fee=0,
                    nonce=0,
                    payload=dict(body["payload"]),
                    envelope=dict(body),
                    block_height=7,
                    timestamp=T0.isoformat(),
                )
            )
            s.add(
                Block(
                    chain_id=CHAIN,
                    height=7,
                    hash="0x" + "ee" * 32,
                    parent_hash="0x" + "00" * 32,
                    proposer="0x" + "33" * 20,
                    timestamp=T0,
                    tx_count=1,
                    state_root="0x" + "00" * 32,
                    bridge_state_root="0x" + "00" * 32,
                    signature="0xsig",
                )
            )
            s.commit()
        bridge = CrossChainBridge(lambda: Session(engine))
        with pytest.raises(ValueError):
            bridge.build_proof(TXHASH, source_chain=CHAIN)

    def test_wrong_same_era_hint_explicit_locator_wins(self, session_factory, engine) -> None:
        from aitbc_chain.models import CrossChainTransfer

        self._arm(session_factory)
        # a DIFFERENT new-era block at height 5 (armed era starts at 0 -> all heights active)
        other = _lock_body("0x" + "51" * 32, transfer_id="0x" + "52" * 32)
        self._seal(session_factory, engine, 5, [other])
        body = _lock_body()
        bridge, block_hash, _ = self._seal(session_factory, engine, 7, [body])
        with Session(engine) as s:
            s.add(
                CrossChainTransfer(
                    transfer_id=TXHASH,
                    source_chain=CHAIN,
                    target_chain="sep",
                    sender=SENDER,
                    recipient=RECIPIENT,
                    amount=5000,
                    asset="AIT",
                    status="pending",
                    source_tx_hash=other["tx_hash"],
                )
            )
            s.commit()
        proof = bridge.build_proof(TXHASH, source_chain=CHAIN, block_hash=block_hash)
        assert proof["block_height"] == 7
        assert proof["amount"] == 5000

    def test_pending_hint_does_not_defeat_locator(self, session_factory, engine) -> None:
        from aitbc_chain.models import CrossChainTransfer

        self._arm(session_factory)
        body = _lock_body()
        bridge, block_hash, _ = self._seal(session_factory, engine, 7, [body])
        with Session(engine) as s:
            # unsealed/pending tx row: same tx_hash space, no block_height
            s.add(
                Transaction(
                    chain_id=CHAIN,
                    tx_hash="0x" + "77" * 32,
                    type="BRIDGE_LOCK",
                    status="pending",
                    sender=SENDER,
                    recipient="bridge_lock",
                    value=1,
                    fee=0,
                    nonce=0,
                    payload={},
                    envelope={},
                    block_height=None,
                    timestamp=T0.isoformat(),
                )
            )
            s.add(
                CrossChainTransfer(
                    transfer_id=TXHASH,
                    source_chain=CHAIN,
                    target_chain="sep",
                    sender=SENDER,
                    recipient=RECIPIENT,
                    amount=5000,
                    asset="AIT",
                    status="pending",
                    source_tx_hash="0x" + "77" * 32,
                )
            )
            s.commit()
        proof = bridge.build_proof(TXHASH, source_chain=CHAIN, block_hash=block_hash)
        assert proof["block_height"] == 7
        assert proof["amount"] == 5000


class TestV9Authority:
    """v9+ enforces the bridge-authority signature on BRIDGE_LOCK."""

    def _block9(self, txs: list[dict[str, Any]], root: str | None) -> dict[str, Any]:
        data = _block(1, txs, root)
        data["block_metadata"] = '{"state_transition_version": 9}'
        return data

    def test_v9_valid_authority_sig_accepts(self, session_factory) -> None:
        _genesis(session_factory)
        with session_factory() as s:
            _history(s, "true", 0)
            _authority(s)
            s.commit()
        body = _lock_body()
        res = _sync(session_factory).import_block(
            self._block9([body], _root([body])), transactions=[body], skip_state_root_validation=True
        )
        assert res.accepted, res.reason

    def test_v9_invalid_authority_sig_rejects(self, session_factory, caplog) -> None:
        import logging

        _genesis(session_factory)
        with session_factory() as s:
            _history(s, "true", 0)
            _authority(s)
            s.commit()
        # every other field identical; only the bridge signature is by the wrong key
        body = _lock_body(bridge_key=WRONG_KEY)
        with caplog.at_level(logging.WARNING):
            res = _sync(session_factory).import_block(
                self._block9([body], _root([body])), transactions=[body], skip_state_root_validation=True
            )
        assert not res.accepted
        # the refusal must be the authority bridge_signature check itself —
        # the apply log carries the validator's exact error text
        assert "bridge_lock_apply_failed" in (res.reason or "")
        assert TXHASH in (res.reason or "")
        assert any("bridge_signature" in r.getMessage() for r in caplog.records)
        with session_factory() as s:
            assert s.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 1)).first() is None


class TestParallelImport:
    def _armed2(self, session_factory) -> None:
        _genesis(session_factory)
        with session_factory() as s:
            _history(s, "true", 0)
            _authority(s)
            s.add(Account(chain_id=CHAIN, address=SENDER2, balance=10**9, nonce=0))
            s.commit()

    def test_failed_lock_parallel_branch_rejects(self, session_factory, monkeypatch) -> None:
        import aitbc_chain.sync_block_import as sbi

        self._armed2(session_factory)
        monkeypatch.setattr(sbi, "_PARALLEL_V2V8_ENABLED", True)
        from aitbc_chain.config import settings

        monkeypatch.setattr(settings, "parallel_tx_validation", True)
        calls = {"graph": 0}
        real_graph = sbi.DependencyGraph

        class _SpyGraph(real_graph):
            def __init__(self, *a: Any, **k: Any) -> None:
                calls["graph"] += 1
                super().__init__(*a, **k)

        monkeypatch.setattr(sbi, "DependencyGraph", _SpyGraph)
        good = _lock_body("0x" + "aa" * 32, sender=SENDER, nonce=0)
        bad = _lock_body(
            "0x" + "bb" * 32, sender=SENDER2, nonce=0, amount=10**12, payload_amount=10**12, top_amount=10**12, value=10**12
        )
        bodies = [good, bad]
        res = _sync(session_factory).import_block(
            _block(1, bodies, _root(bodies)), transactions=bodies, skip_state_root_validation=True
        )
        assert calls["graph"] >= 1, "parallel branch never ran"
        assert not res.accepted
        with session_factory() as s:
            assert s.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 1)).first() is None

    def test_parallel_happy_path_two_locks(self, session_factory, monkeypatch) -> None:
        import aitbc_chain.sync_block_import as sbi

        self._armed2(session_factory)
        monkeypatch.setattr(sbi, "_PARALLEL_V2V8_ENABLED", True)
        from aitbc_chain.config import settings

        monkeypatch.setattr(settings, "parallel_tx_validation", True)
        calls = {"graph": 0}
        real_graph = sbi.DependencyGraph

        class _SpyGraph(real_graph):
            def __init__(self, *a: Any, **k: Any) -> None:
                calls["graph"] += 1
                super().__init__(*a, **k)

        monkeypatch.setattr(sbi, "DependencyGraph", _SpyGraph)
        b1 = _lock_body("0x" + "aa" * 32, sender=SENDER, nonce=0)
        b2 = _lock_body("0x" + "bb" * 32, sender=SENDER2, nonce=0)
        bodies = [b1, b2]
        res = _sync(session_factory).import_block(
            _block(1, bodies, _root(bodies)), transactions=bodies, skip_state_root_validation=True
        )
        assert calls["graph"] >= 1, "parallel branch never ran"
        assert res.accepted, res.reason


class TestNonLockRetention:
    def test_transfer_row_envelope_unchanged(self, session_factory) -> None:
        _genesis(session_factory)
        with session_factory() as s:
            _history(s, "true", 0)
            s.commit()
        tx_body = {
            "from": SENDER,
            "to": RECIPIENT,
            "amount": 100,
            "value": 100,
            "fee": 0,
            "nonce": 0,
            "chain_id": CHAIN,
            "tx_hash": "0x" + "cc" * 32,
            "type": "TRANSFER",
            "payload": {"note": "keep-me"},
        }
        empty_root = _root([])
        res = _sync(session_factory).import_block(
            _block(1, [tx_body], empty_root), transactions=[tx_body], skip_state_root_validation=True
        )
        assert res.accepted, res.reason
        with session_factory() as s:
            tx = s.exec(select(Transaction).where(Transaction.tx_hash == "0x" + "cc" * 32)).one()
            assert tx.type == "TRANSFER"
            assert tx.envelope["payload"]["note"] == "keep-me"

    def test_preregistered_non_lock_retains_semantics(self, session_factory) -> None:
        """A pre-registered non-lock row keeps its stored semantics under
        the armed flag — only BRIDGE_LOCK rows get the semantic/envelope
        refresh."""
        _genesis(session_factory)
        with session_factory() as s:
            _history(s, "true", 0)
            s.commit()
        h = "0x" + "dd" * 32
        tx_body = {
            "from": SENDER,
            "to": RECIPIENT,
            "amount": 0,
            "value": 0,
            "fee": 0,
            "nonce": 0,
            "chain_id": CHAIN,
            "tx_hash": h,
            "type": "MESSAGE",
            "payload": {"note": "new"},
        }
        with session_factory() as s:
            s.add(
                Transaction(
                    chain_id=CHAIN,
                    tx_hash=h,
                    type="MESSAGE",
                    status="pending",
                    block_height=None,
                    sender="0x" + "99" * 20,
                    recipient="stale",
                    value=1,
                    fee=9,
                    nonce=9,
                    payload={"stale": True},
                    envelope={"stale": True},
                )
            )
            s.commit()
        empty_root = _root([])
        res = _sync(session_factory).import_block(
            _block(1, [tx_body], empty_root), transactions=[tx_body], skip_state_root_validation=True
        )
        assert res.accepted, res.reason
        with session_factory() as s:
            tx = s.exec(select(Transaction).where(Transaction.tx_hash == h)).one()
            assert tx.type == "MESSAGE"
            assert tx.block_height == 1
            # stored semantics/envelope untouched — no lock refresh ran
            assert tx.envelope == {"stale": True}
            assert tx.payload == {"stale": True}
            assert tx.sender == "0x" + "99" * 20
            assert tx.value == 1


class TestProbeGuards:
    def test_probe_rejection_skips_tracker_and_metrics(self, session_factory, monkeypatch) -> None:
        import aitbc_chain.sync_block_import as sbi

        _genesis(session_factory)
        with session_factory() as s:
            _history(s, "true", 0)
            s.commit()
        body = _lock_body()
        sync = _sync(session_factory)
        tracked = {"n": 0}
        rejected_counters = []
        real_increment = sbi.metrics_registry.increment

        def _spy_increment(name, *a, **k):
            if name == "sync_blocks_rejected_total":
                rejected_counters.append(name)
            return real_increment(name, *a, **k)

        monkeypatch.setattr(sync, "_track_rejection", lambda *a, **k: tracked.__setitem__("n", tracked["n"] + 1))
        monkeypatch.setattr(sbi.metrics_registry, "increment", _spy_increment)
        block_data = _block(1, [body], "0x" + "ff" * 32)  # mismatched carried root
        with session_factory() as s:
            res = sync._append_block(s, block_data, [body], skip_state_root_validation=True, _probe=True)
        assert not res.accepted
        assert tracked["n"] == 0
        assert rejected_counters == []


class TestProducer:
    """Real producer pipeline: _process_proposal_txs + _compute_bridge_state_root."""

    def _proposer(self):
        import logging

        from aitbc_chain.consensus.poa import PoAProposer

        p = PoAProposer.__new__(PoAProposer)
        p._config = SimpleNamespace(chain_id=CHAIN)
        p._logger = logging.getLogger("f5-producer-test")
        return p

    @staticmethod
    def _force_v8(monkeypatch: pytest.MonkeyPatch) -> None:
        from aitbc_chain.config import settings

        for v in range(9, 26):
            monkeypatch.setattr(settings, f"state_transition_v{v}_height", 10**9)
        for v in range(3, 9):
            monkeypatch.setattr(settings, f"state_transition_v{v}_height", 1)

    @staticmethod
    def _armed(session_factory, second: bool = False) -> None:
        _genesis(session_factory)
        with session_factory() as s:
            _history(s, "true", 0)
            _authority(s)
            if second:
                s.add(Account(chain_id=CHAIN, address=SENDER2, balance=10**9, nonce=0))
            s.commit()

    @staticmethod
    def _tx(body: dict[str, Any]) -> Any:
        return SimpleNamespace(tx_hash=body["tx_hash"], content=body)

    @staticmethod
    def _account_map(s) -> dict:
        return {a.address: a for a in s.exec(select(Account).where(Account.chain_id == CHAIN)).all()}

    def test_sequential_native_lock_root_and_proof(self, session_factory, engine, monkeypatch) -> None:
        from aitbc_chain.cross_chain.bridge import CrossChainBridge

        self._armed(session_factory)
        self._force_v8(monkeypatch)
        h = "0x" + "d1" * 32
        body = _lock_body(tx_hash=h)
        p = self._proposer()
        with Session(engine) as s:
            amap = self._account_map(s)
            processed, _changed, ok = p._process_proposal_txs(s, [self._tx(body)], amap, {}, 1, T0, [])
            assert ok and len(processed) == 1
            prod_root = p._compute_bridge_state_root(s, processed, CHAIN, 1)
            s.rollback()  # producer work is inspect-only here; import phase needs clean state
        assert prod_root == _root([body], 1)
        # identical block through the real importer — carried root must match exactly
        res = _sync(session_factory).import_block(
            _block(1, [body], prod_root), transactions=[body], skip_state_root_validation=True
        )
        assert res.accepted, res.reason
        # proof from sealed rows agrees — zero CCT rows exist anywhere
        bridge = CrossChainBridge(lambda: Session(engine))
        proof = bridge.build_proof(h, source_chain=CHAIN, block_height=1)
        assert proof["amount"] == 5000
        assert proof["block_height"] == 1

    def test_payload_typed_lock_producer(self, session_factory, engine, monkeypatch) -> None:
        self._armed(session_factory)
        self._force_v8(monkeypatch)
        body = _lock_body(tx_hash="0x" + "d2" * 32, top_type="TRANSFER")
        body["payload"]["type"] = "BRIDGE_LOCK"
        p = self._proposer()
        with Session(engine) as s:
            amap = self._account_map(s)
            processed, _changed, ok = p._process_proposal_txs(s, [self._tx(body)], amap, {}, 1, T0, [])
            assert ok and len(processed) == 1
            prod_root = p._compute_bridge_state_root(s, processed, CHAIN, 1)
            s.rollback()
        assert prod_root == _root([body], 1)
        res = _sync(session_factory).import_block(
            _block(1, [body], prod_root), transactions=[body], skip_state_root_validation=True
        )
        assert res.accepted, res.reason
        with session_factory() as s:
            tx = s.exec(select(Transaction).where(Transaction.tx_hash == "0x" + "d2" * 32)).one()
            assert tx.type == "BRIDGE_LOCK"

    def test_amount_shaped_lock_no_payload_amount(self, session_factory, engine, monkeypatch) -> None:
        self._armed(session_factory)
        self._force_v8(monkeypatch)
        body = _lock_body(tx_hash="0x" + "d3" * 32)
        del body["payload"]["amount"]  # signed amount falls back to top-level amount
        body["bridge_signature"] = __import__(
            "aitbc_chain.state.bridge_credit", fromlist=["sign_bridge_lock"]
        ).sign_bridge_lock(body, body["tx_hash"], AUTHORITY_KEY)
        p = self._proposer()
        rejected: list = []
        with Session(engine) as s:
            amap = self._account_map(s)
            processed, _changed, ok = p._process_proposal_txs(s, [self._tx(body)], amap, {}, 1, T0, rejected)
            s.rollback()
        # contract: signed amount (top-level) == effective debit -> accepted
        assert ok and len(processed) == 1 and not rejected

    def test_preregistered_lock_semantics_refreshed(self, session_factory, engine, monkeypatch) -> None:
        self._armed(session_factory)
        self._force_v8(monkeypatch)
        body = _lock_body(tx_hash="0x" + "d4" * 32)
        with session_factory() as s:
            s.add(
                Transaction(
                    chain_id=CHAIN,
                    tx_hash="0x" + "d4" * 32,
                    type="BRIDGE_LOCK",
                    status="confirmed",
                    block_height=None,
                    sender="0x" + "99" * 20,
                    recipient="stale",
                    value=1,
                    fee=9,
                    nonce=9,
                    payload={"stale": True},
                    envelope={"stale": True},
                )
            )
            s.commit()
        p = self._proposer()
        with Session(engine) as s:
            amap = self._account_map(s)
            processed, _changed, ok = p._process_proposal_txs(s, [self._tx(body)], amap, {}, 1, T0, [])
            assert ok and len(processed) == 1
            prod_root = p._compute_bridge_state_root(s, processed, CHAIN, 1)
            row = s.exec(select(Transaction).where(Transaction.tx_hash == "0x" + "d4" * 32)).one()
            assert row.sender == SENDER
            assert row.value == 5000
            assert row.envelope["payload"]["transfer_id"] == "0x" + "d4" * 32
            assert "stale" not in row.envelope
            s.rollback()
        assert prod_root == _root([body], 1)

    def test_parallel_producer_two_locks(self, session_factory, engine, monkeypatch) -> None:
        import aitbc_chain.consensus.poa as poa_mod
        from aitbc_chain.config import settings

        self._armed(session_factory, second=True)
        self._force_v8(monkeypatch)
        monkeypatch.setattr(settings, "parallel_tx_validation", True)
        monkeypatch.setattr(settings, "conflict_threshold", 1.0)
        calls = {"exec": 0}
        real_exec = poa_mod.ParallelExecutor

        class _SpyExecutor(real_exec):
            def __init__(self, *a: Any, **k: Any) -> None:
                calls["exec"] += 1
                super().__init__(*a, **k)

        monkeypatch.setattr(poa_mod, "ParallelExecutor", _SpyExecutor)
        b1 = _lock_body("0x" + "d5" * 32, sender=SENDER, nonce=0)
        b2 = _lock_body("0x" + "d6" * 32, sender=SENDER2, nonce=0)
        p = self._proposer()
        with Session(engine) as s:
            amap = self._account_map(s)
            processed, _changed, ok = p._process_proposal_txs(s, [self._tx(b1), self._tx(b2)], amap, {}, 1, T0, [])
            assert ok and len(processed) == 2
            prod_root = p._compute_bridge_state_root(s, processed, CHAIN, 1)
            s.rollback()
        assert calls["exec"] >= 1, "parallel producer branch never ran"
        assert prod_root == _root([b1, b2], 1)
        # order independence of the trie
        assert _root([b1, b2], 1) == _root([b2, b1], 1)
