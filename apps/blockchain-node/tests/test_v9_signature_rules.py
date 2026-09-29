"""v9 transaction-authorization rules — shadow counting, apply enforcement,
envelope serving, and attester checks.

The shared allowlist lives in ``state/v9_policy.py`` and is consumed by the
sequential apply path, the parallel delta path, and remote attestation so
the rule cannot drift between them.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from aitbc.crypto.crypto import derive_ethereum_address
from aitbc_chain.base_models import Account, Block, ChainParameter
from aitbc_chain.config import settings
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.rpc.utils import sign_transaction_data
from aitbc_chain.state.v9_policy import V9_UNSIGNED_ALLOWED_TX_TYPES, v9_signature_verdict
from aitbc_chain.sync import ChainSync
from sqlmodel import Session, create_engine, select

CHAIN = "v9-sig-rules"
T0 = datetime(2026, 1, 1, tzinfo=UTC)

KEY_VICTIM = "0x" + "aa" * 32
KEY_ATTACKER = "0x" + "bb" * 32
KEY_BRIDGE_AUTH = "0x" + "dd" * 32
ADDR_VICTIM = derive_ethereum_address(KEY_VICTIM)
ADDR_ATTACKER = derive_ethereum_address(KEY_ATTACKER)
ADDR_BRIDGE_AUTH = derive_ethereum_address(KEY_BRIDGE_AUTH)


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


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics_registry.reset()
    yield
    metrics_registry.reset()


def _seed_genesis(session_factory, victim_balance: int = 10**9) -> None:
    from aitbc_chain.state.state_root_utils import compute_state_root_full

    with session_factory() as session:
        session.add(Account(chain_id=CHAIN, address=ADDR_VICTIM, balance=victim_balance, nonce=0))
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


def _seed_bridge_authority(session_factory) -> None:
    """On-chain bridge_release_authority (applied_height NULL → in force at
    every height), so v9 lock/credit signature checks resolve it."""
    with session_factory() as session:
        session.add(ChainParameter(chain_id=CHAIN, parameter="bridge_release_authority", value=ADDR_BRIDGE_AUTH))


def _signed_bridge_lock(tx_hash: str = "0x" + "ee" * 32) -> dict[str, Any]:
    """A BRIDGE_LOCK as the v9 bridge service issues it: no sender signature,
    the bridge authority's bridge_signature at top level."""
    from aitbc_chain.state.bridge_credit import sign_bridge_lock

    lock = _unsigned_served_tx(
        to="bridge_lock",
        type="BRIDGE_LOCK",
        tx_hash=tx_hash,
        payload={"transfer_id": "t1", "target_chain": "other", "target_recipient": ADDR_ATTACKER},
    )
    lock["bridge_signature"] = sign_bridge_lock(lock, tx_hash, KEY_BRIDGE_AUTH)
    return lock


def _content_hash(tx: dict[str, Any]) -> str:
    from aitbc_chain.mempool import compute_tx_hash

    return compute_tx_hash({k: v for k, v in tx.items() if k != "tx_hash"})


def _signed_tx(nonce: int = 0, amount: int = 999, tx_hash: str | None = None) -> dict[str, Any]:
    """A transaction exactly as a served signed envelope looks: the user's
    submitted field set plus ``tx_hash`` (the real content hash — the
    attestation binding recomputes it) and the ``value`` alias."""
    tx: dict[str, Any] = {
        "from": ADDR_VICTIM,
        "to": ADDR_ATTACKER,
        "amount": amount,
        "fee": 1,
        "nonce": nonce,
        "payload": {},
        "type": "TRANSFER",
        "chain_id": CHAIN,
    }
    tx["signature"] = sign_transaction_data(tx, KEY_VICTIM)
    # tx.content (what the proposer ships to attesters) carries no ``value``
    # alias — apply derives it from ``amount`` — and no ``tx_hash`` inside
    # the hashed body.
    tx["tx_hash"] = tx_hash or _content_hash(tx)
    return tx


def _unsigned_served_tx(**overrides: Any) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "from": ADDR_VICTIM,
        "to": ADDR_ATTACKER,
        "amount": 999,
        "fee": 1,
        "nonce": 0,
        "payload": {},
        "type": "TRANSFER",
        "signature": "",
        "tx_hash": "0x" + "cc" * 32,
        "chain_id": CHAIN,
    }
    tx.update(overrides)
    return tx


def _block(height: int, txs: list[dict[str, Any]], version: int = 9, state_root: str = "") -> dict[str, Any]:
    return {
        "chain_id": CHAIN,
        "height": height,
        "hash": f"0x{height:064x}",
        "parent_hash": "0x" + "00" * 32,
        "proposer": ADDR_ATTACKER,
        "timestamp": (T0).isoformat(),
        "tx_count": len(txs),
        "state_root": state_root,
        "block_metadata": json.dumps({"state_transition_version": version}),
        "signature": "",
        "transactions": txs,
    }


def _import(sync: ChainSync, block_data: dict[str, Any]):
    return sync.import_block(block_data, transactions=block_data["transactions"], skip_state_root_validation=True)


class TestV9ApplyGate:
    """Sequential path: unsigned non-allowlisted txs reject at v9, and shadow
    counting fires while v9 is inactive."""

    def test_v9_unsigned_transfer_rejected(self, session_factory):
        """The tx does not apply. The block itself is still imported here
        because root validation is skipped for the fixture — in production
        the proposer recorded the forged root, the follower computes state
        without the tx, and the root mismatch rejects the block."""
        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)

        _import(sync, _block(1, [_unsigned_served_tx()]))

        assert metrics_registry._counters.get("v9_would_reject_total") == 1.0
        assert metrics_registry._counters.get("v9_would_reject_missing_signature_transfer_total") == 1.0
        with session_factory() as session:
            victim = session.get(Account, (CHAIN, ADDR_VICTIM))
            assert victim is not None and victim.balance == 10**9  # untouched
            assert victim.nonce == 0

    def test_v9_signed_transfer_applied(self, session_factory):
        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)

        result = _import(sync, _block(1, [_signed_tx()]))

        assert result.accepted, f"block unexpectedly rejected: {result.reason}"
        assert metrics_registry._counters.get("v9_would_reject_total") is None
        with session_factory() as session:
            victim = session.get(Account, (CHAIN, ADDR_VICTIM))
            attacker = session.get(Account, (CHAIN, ADDR_ATTACKER))
            assert victim is not None and attacker is not None
            assert victim.balance == 10**9 - 999 - 1
            assert victim.nonce == 1
            assert attacker.balance == 999
            from aitbc_chain.models import Transaction

            stored = session.exec(select(Transaction).where(Transaction.chain_id == CHAIN)).all()
            assert stored and stored[0].envelope and stored[0].envelope.get("signature")

    def test_v9_signature_invalid_rejected(self, session_factory):
        """A served tx whose signature is forged fails the existing sig check
        (v7+), not just the missing-signature gate."""
        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)

        tx = _signed_tx()
        tx["signature"] = sign_transaction_data(tx, KEY_ATTACKER)  # signed by the wrong key
        _import(sync, _block(1, [tx]))

        with session_factory() as session:
            victim = session.get(Account, (CHAIN, ADDR_VICTIM))
            assert victim is not None and victim.balance == 10**9

    def test_v9_bridge_lock_with_authority_signature_applied(self, session_factory):
        """From v9 a BRIDGE_LOCK must carry the bridge authority's
        bridge_signature — the sender-signature exemption stands because the
        authority signature replaces it."""
        _seed_genesis(session_factory)
        _seed_bridge_authority(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)

        result = _import(sync, _block(1, [_signed_bridge_lock()]))

        assert result.accepted, f"block unexpectedly rejected: {result.reason}"
        with session_factory() as session:
            victim = session.get(Account, (CHAIN, ADDR_VICTIM))
            assert victim is not None
            assert victim.balance == 10**9 - 999 - 1  # lock debit applied

    def test_v9_unsigned_bridge_lock_rejected(self, session_factory):
        """An unsigned BRIDGE_LOCK is a forged debit — refused at v9."""
        _seed_genesis(session_factory)
        _seed_bridge_authority(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)

        lock = _unsigned_served_tx(
            to="bridge_lock",
            type="BRIDGE_LOCK",
            tx_hash="0x" + "ee" * 32,
            payload={"transfer_id": "t1", "target_chain": "other", "target_recipient": ADDR_ATTACKER},
        )
        _import(sync, _block(1, [lock]))

        with session_factory() as session:
            victim = session.get(Account, (CHAIN, ADDR_VICTIM))
            assert victim is not None and victim.balance == 10**9  # untouched

    def test_pre_v9_unsigned_bridge_lock_shadow_counts(self, session_factory):
        """Below the v9 height an unsigned lock still applies (historical
        replay is full of them) but the shadow counter fires."""
        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)

        lock = _unsigned_served_tx(
            to="bridge_lock",
            type="BRIDGE_LOCK",
            tx_hash="0x" + "ee" * 32,
            payload={"transfer_id": "t1", "target_chain": "other", "target_recipient": ADDR_ATTACKER},
        )
        result = _import(sync, _block(1, [lock], version=8))

        assert result.accepted, f"block unexpectedly rejected: {result.reason}"
        assert metrics_registry._counters.get("v9_would_reject_bridge_lock_unsigned_total") == 1.0
        with session_factory() as session:
            victim = session.get(Account, (CHAIN, ADDR_VICTIM))
            assert victim is not None and victim.balance == 10**9 - 999 - 1

    def test_v9_nested_envelope_import_keeps_signature(self, session_factory):
        """A peer serving the pre-fix nested shape (empty top-level signature,
        real signed envelope under ``envelope``) must import with the
        signature intact — otherwise the follower stores an unsigned tx and
        re-serves the hole."""
        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)

        signed = _signed_tx()
        wrapper = {
            "signature": "",
            "sender": ADDR_VICTIM,
            "recipient": ADDR_ATTACKER,
            "tx_hash": signed["tx_hash"],
            "envelope": {k: v for k, v in signed.items() if k != "tx_hash"},
        }
        result = _import(sync, _block(1, [wrapper]))

        assert result.accepted, f"block unexpectedly rejected: {result.reason}"
        assert metrics_registry._counters.get("v9_would_reject_total") is None
        with session_factory() as session:
            victim = session.get(Account, (CHAIN, ADDR_VICTIM))
            assert victim is not None and victim.balance == 10**9 - 999 - 1
            from aitbc_chain.models import Transaction

            stored = session.exec(select(Transaction).where(Transaction.chain_id == CHAIN)).all()
            assert stored and stored[0].envelope and stored[0].envelope.get("signature") == signed["signature"]
            # ... and it re-serves hoisted, not nested.
            from aitbc_chain.rpc.blocks import _served_tx_body
            from aitbc_chain.rpc.utils import verify_transaction_signature

            body = _served_tx_body(stored[0])
            assert body["signature"] == signed["signature"]
            assert verify_transaction_signature(body, body["signature"], ADDR_VICTIM)

    def test_shadow_mode_counts_but_applies(self, session_factory):
        """Pre-activation (block stamped v8): the same unsigned tx still
        applies — but the shadow counter records the would-reject."""
        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)

        result = _import(sync, _block(1, [_unsigned_served_tx()], version=8))

        assert result.accepted, f"block unexpectedly rejected: {result.reason}"
        assert metrics_registry._counters.get("v9_would_reject_total") == 1.0
        assert metrics_registry._counters.get("v9_would_reject_missing_signature_transfer_total") == 1.0
        with session_factory() as session:
            victim = session.get(Account, (CHAIN, ADDR_VICTIM))
            assert victim is not None and victim.balance == 10**9 - 999 - 1


class TestV9ParallelGate:
    def test_v9_unsigned_transfer_rejected_parallel(self, session_factory, monkeypatch):
        """The parallel delta path enforces the same rule."""
        monkeypatch.setattr(settings, "parallel_tx_validation", True)
        monkeypatch.setattr(settings, "conflict_threshold", 1.0)

        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)

        _import(sync, _block(1, [_unsigned_served_tx()]))

        assert metrics_registry._counters.get("v9_would_reject_total") == 1.0
        with session_factory() as session:
            victim = session.get(Account, (CHAIN, ADDR_VICTIM))
            assert victim is not None and victim.balance == 10**9

    def test_v9_signed_bridge_lock_parallel_applied(self, session_factory, monkeypatch):
        """A v9 block whose only bridge tx is a correctly signed BRIDGE_LOCK
        must apply on the parallel path too — the caller resolves the bridge
        authority for locks as well as credits (incident: a LOCK-only block
        reached the pure path with bridge_authority=None and the shadow
        counter fired; at v9 that would have been a follower rejection the
        proposer's sequential path accepted)."""
        monkeypatch.setattr(settings, "parallel_tx_validation", True)
        monkeypatch.setattr(settings, "conflict_threshold", 1.0)

        _seed_genesis(session_factory)
        _seed_bridge_authority(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)

        result = _import(sync, _block(1, [_signed_bridge_lock()]))

        assert result.accepted, f"block unexpectedly rejected: {result.reason}"
        assert metrics_registry._counters.get("v9_would_reject_total") is None
        with session_factory() as session:
            victim = session.get(Account, (CHAIN, ADDR_VICTIM))
            assert victim is not None and victim.balance == 10**9 - 999 - 1

    def test_v9_unsigned_bridge_lock_parallel_rejected(self, session_factory, monkeypatch):
        """Same block minus the bridge_signature: the parallel path agrees
        with the sequential one and does not debit."""
        monkeypatch.setattr(settings, "parallel_tx_validation", True)
        monkeypatch.setattr(settings, "conflict_threshold", 1.0)

        _seed_genesis(session_factory)
        _seed_bridge_authority(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)

        lock = _unsigned_served_tx(
            to="bridge_lock",
            type="BRIDGE_LOCK",
            tx_hash="0x" + "ee" * 32,
            payload={"transfer_id": "t1", "target_chain": "other", "target_recipient": ADDR_ATTACKER},
        )
        _import(sync, _block(1, [lock]))

        with session_factory() as session:
            victim = session.get(Account, (CHAIN, ADDR_VICTIM))
            assert victim is not None and victim.balance == 10**9

    def test_pre_v9_signed_bridge_lock_parallel_no_counter(self, session_factory, monkeypatch):
        """v8 shadow: a correctly signed lock applies on the parallel path
        and does NOT fire the shadow counter — the authority is resolved
        rather than compared against ""."""
        monkeypatch.setattr(settings, "parallel_tx_validation", True)
        monkeypatch.setattr(settings, "conflict_threshold", 1.0)

        _seed_genesis(session_factory)
        _seed_bridge_authority(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)

        result = _import(sync, _block(1, [_signed_bridge_lock()], version=8))

        assert result.accepted, f"block unexpectedly rejected: {result.reason}"
        assert metrics_registry._counters.get("v9_would_reject_bridge_lock_unsigned_total") is None
        with session_factory() as session:
            victim = session.get(Account, (CHAIN, ADDR_VICTIM))
            assert victim is not None and victim.balance == 10**9 - 999 - 1

    def test_pre_v9_unsigned_bridge_lock_parallel_shadow_counts(self, session_factory, monkeypatch):
        """v8 shadow: an unsigned lock still applies on the parallel path but
        counts exactly like the sequential path."""
        monkeypatch.setattr(settings, "parallel_tx_validation", True)
        monkeypatch.setattr(settings, "conflict_threshold", 1.0)

        _seed_genesis(session_factory)
        sync = ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)

        lock = _unsigned_served_tx(
            to="bridge_lock",
            type="BRIDGE_LOCK",
            tx_hash="0x" + "ee" * 32,
            payload={"transfer_id": "t1", "target_chain": "other", "target_recipient": ADDR_ATTACKER},
        )
        result = _import(sync, _block(1, [lock], version=8))

        assert result.accepted, f"block unexpectedly rejected: {result.reason}"
        assert metrics_registry._counters.get("v9_would_reject_bridge_lock_unsigned_total") == 1.0
        with session_factory() as session:
            victim = session.get(Account, (CHAIN, ADDR_VICTIM))
            assert victim is not None and victim.balance == 10**9 - 999 - 1


class TestServedTxBody:
    def test_envelope_is_served_verbatim(self):
        """Signature digests cover the exact submitted field set — the served
        body must add only digest-excluded fields (tx_hash, value)."""
        from aitbc_chain.rpc.blocks import _served_tx_body

        env = {
            "from": ADDR_VICTIM,
            "to": ADDR_ATTACKER,
            "amount": 999,
            "fee": 1,
            "nonce": 0,
            "payload": {},
            "type": "TRANSFER",
            "chain_id": CHAIN,
        }
        env["signature"] = sign_transaction_data(env, KEY_VICTIM)

        class _Row:
            envelope = env
            tx_hash = "0x" + "cc" * 32
            value = 999

        body = _served_tx_body(_Row())  # type: ignore[arg-type]

        assert body["signature"] == env["signature"]
        assert body["tx_hash"] == "0x" + "cc" * 32
        assert body["value"] == 999
        # No row-column leakage into the signed field set.
        for leaked in ("status", "block_height", "id", "sender", "recipient", "created_at"):
            assert leaked not in body
        # And the signature still verifies over the served body.
        from aitbc_chain.rpc.utils import verify_transaction_signature

        assert verify_transaction_signature(body, body["signature"], ADDR_VICTIM)

    def test_nested_envelope_is_hoisted_on_serve(self):
        """A row stored in the pre-fix shape — column dump with an empty
        top-level signature and the real signed envelope nested under
        ``envelope`` — must serve the signed body, not the unsigned wrapper."""
        from aitbc_chain.rpc.blocks import _served_tx_body

        env = {
            "from": ADDR_VICTIM,
            "to": ADDR_ATTACKER,
            "amount": 999,
            "fee": 1,
            "nonce": 0,
            "payload": {},
            "type": "TRANSFER",
            "chain_id": CHAIN,
        }
        env["signature"] = sign_transaction_data(env, KEY_VICTIM)

        class _Row:
            envelope = {"signature": "", "sender": ADDR_VICTIM, "envelope": dict(env)}
            tx_hash = "0x" + "cc" * 32
            value = 999

        body = _served_tx_body(_Row())  # type: ignore[arg-type]

        assert body["signature"] == env["signature"]
        assert body["tx_hash"] == "0x" + "cc" * 32
        from aitbc_chain.rpc.utils import verify_transaction_signature

        assert verify_transaction_signature(body, body["signature"], ADDR_VICTIM)

    def test_row_without_envelope_falls_back_to_columns(self):
        from aitbc_chain.rpc.blocks import _served_tx_body

        class _Row:
            envelope = None
            tx_hash = "0x" + "cc" * 32
            value = 999

            def model_dump(self):
                return {"sender": ADDR_VICTIM, "recipient": ADDR_ATTACKER, "value": 999, "envelope": None}

        body = _served_tx_body(_Row())  # type: ignore[arg-type]
        assert body["from"] == ADDR_VICTIM
        assert body["to"] == ADDR_ATTACKER


class TestV9Policy:
    def test_verdict(self):
        assert v9_signature_verdict({"type": "TRANSFER"}, "TRANSFER") == "missing_signature"
        assert v9_signature_verdict({"type": "TRANSFER", "signature": "0xabc"}, "TRANSFER") is None
        assert v9_signature_verdict({"type": "TRANSFER", "sig": "0xabc"}, "TRANSFER") is None
        for internal in V9_UNSIGNED_ALLOWED_TX_TYPES:
            assert v9_signature_verdict({"type": internal}, internal) is None

    def test_allowlist_contents(self):
        # The unsigned set is exactly the internal producers discovered in
        # inventory: the bridge rows only — each carries its own authority
        # check (bridge_signature). MESSAGE was removed: it increments the
        # sender nonce at apply, so an unsigned forged MESSAGE is a nonce-DoS.
        # User-originated types are not in it — a shadow run that reports
        # v9_would_reject for one of these means the allowlist needs
        # revisiting BEFORE the height is pinned.
        assert V9_UNSIGNED_ALLOWED_TX_TYPES == {"BRIDGE_LOCK", "BRIDGE_RELEASE", "BRIDGE_REFUND"}
        assert v9_signature_verdict({"type": "MESSAGE"}, "MESSAGE") == "missing_signature"

    def test_shadow_checked_positive_control(self):
        """The window pass condition needs presence, not absence: every
        verdict evaluation counts into v9_shadow_checked_*, so a clean
        window is provably `checked > 0 AND would_reject == 0` — silence
        could otherwise mean the check never ran."""
        v9_signature_verdict({"type": "TRANSFER", "signature": "0xabc"}, "TRANSFER")
        v9_signature_verdict({}, "BRIDGE_LOCK")
        c = metrics_registry._counters
        assert c["v9_shadow_checked_total"] == 2.0
        assert c["v9_shadow_checked_transfer_total"] == 1.0
        assert c["v9_shadow_checked_bridge_lock_total"] == 1.0


class _StubBroker:
    def __init__(self) -> None:
        self.published: list[tuple[str, Any]] = []

    async def publish(self, topic: str, message: Any) -> None:
        self.published.append((topic, message))


class TestAttesterTxChecks:
    """remote_attestation: the attester checks tx signatures and nonce order
    against its own state at the block's parent — and refuses once v9 is
    active. While v9 is inactive the same failure is shadow-only."""

    @pytest.fixture()
    def attester(self, session_factory, monkeypatch):
        from aitbc_chain.consensus.remote_attestation import RemoteAttestationService

        key_attester = "0x" + "cd" * 32
        addr_attester = derive_ethereum_address(key_attester)
        monkeypatch.setattr(
            settings,
            "validator_set",
            json.dumps([{"address": ADDR_ATTACKER}, {"address": addr_attester}]),
        )
        monkeypatch.setattr(settings, "attestation_lock_enabled", False)
        broker = _StubBroker()
        monkeypatch.setattr("aitbc_chain.consensus.remote_attestation.gossip_broker", broker)
        svc = RemoteAttestationService(CHAIN, {addr_attester: key_attester}, session_factory=session_factory)
        return svc, broker

    def _request(
        self,
        txs: list[dict[str, Any]] | None,
        parent_hash: str = "0x" + "00" * 32,
        **header_overrides: Any,
    ) -> dict[str, Any]:
        """An attestation request in the v9 shape: the header declares the
        tx-hash set, count and timestamp, and ``hash`` is the real block
        hash over those fields so the binding check recomputes it."""
        from aitbc_chain.consensus.block_hash import compute_block_hash

        header: dict[str, Any] = {
            "chain_id": CHAIN,
            "height": 1,
            "parent_hash": parent_hash,
            "proposer": ADDR_ATTACKER,
            "state_root": "0xroot",
            "bridge_state_root": "0xbridge",
        }
        header.update(header_overrides)
        if txs is not None and "tx_hashes" not in header:
            header["tx_hashes"] = sorted(str(t.get("tx_hash") or "") for t in txs)
            header["tx_count"] = len(txs)
            header["timestamp"] = T0.isoformat()
        header["hash"] = header_overrides.get("hash") or compute_block_hash(
            header["chain_id"],
            header["height"],
            header["parent_hash"],
            str(header.get("timestamp") or ""),
            header.get("tx_hashes") or [],
            header["proposer"],
            header.get("state_root") or "",
            header.get("bridge_state_root") or "",
        )
        req: dict[str, Any] = {"header": header, "timestamp": 0.0}
        if txs is not None:
            req["transactions"] = txs
        return req

    def _unsigned_bound_tx(self) -> dict[str, Any]:
        """Unsigned TRANSFER with a consistent content hash so the request
        binding passes and the verdict reaches the signature check."""
        tx = _unsigned_served_tx()
        tx["tx_hash"] = _content_hash(tx)
        return tx

    def test_shadow_mode_signs_despite_unsigned_tx(self, session_factory, attester):
        svc, broker = attester
        _seed_genesis(session_factory)
        # v9 unset → would-refuse only; the attestation still goes out.
        asyncio.run(svc._handle_request(self._request([self._unsigned_bound_tx()])))
        assert broker.published, "shadow mode must still attest"
        assert metrics_registry._counters.get("v9_would_reject_total") == 1.0
        assert metrics_registry._counters.get("v9_would_reject_attest_missing_signature_total") == 1.0

    def test_v9_active_refuses_unsigned_tx(self, session_factory, attester, monkeypatch):
        svc, broker = attester
        monkeypatch.setattr(settings, "state_transition_v9_height", 1)
        _seed_genesis(session_factory)
        asyncio.run(svc._handle_request(self._request([self._unsigned_bound_tx()])))
        assert not broker.published, "v9 must refuse an unsigned user tx"
        assert metrics_registry._counters.get("v9_would_reject_attest_missing_signature_total") == 1.0

    def test_v9_active_refuses_when_not_at_parent(self, session_factory, attester, monkeypatch):
        svc, broker = attester
        monkeypatch.setattr(settings, "state_transition_v9_height", 1)
        _seed_genesis(session_factory)
        asyncio.run(svc._handle_request(self._request([_signed_tx()], parent_hash="0x" + "ff" * 32)))
        assert not broker.published
        assert metrics_registry._counters.get("v9_would_reject_attest_not_at_parent_total") == 1.0

    def test_v9_active_refuses_nonce_skip(self, session_factory, attester, monkeypatch):
        svc, broker = attester
        monkeypatch.setattr(settings, "state_transition_v9_height", 1)
        _seed_genesis(session_factory)
        asyncio.run(svc._handle_request(self._request([_signed_tx(nonce=5)])))
        assert not broker.published
        assert metrics_registry._counters.get("v9_would_reject_attest_nonce_order_total") == 1.0

    def test_v9_active_refuses_invalid_signature(self, session_factory, attester, monkeypatch):
        svc, broker = attester
        monkeypatch.setattr(settings, "state_transition_v9_height", 1)
        _seed_genesis(session_factory)
        tx = _signed_tx()
        tx["signature"] = sign_transaction_data(tx, KEY_ATTACKER)
        # The forged signature changes the content hash — declare the real
        # (forged) hash so the binding passes and the verdict reaches the
        # signature check itself.
        tx["tx_hash"] = _content_hash(tx)
        asyncio.run(svc._handle_request(self._request([tx])))
        assert not broker.published
        assert metrics_registry._counters.get("v9_would_reject_attest_invalid_signature_total") == 1.0

    def test_v9_active_refuses_missing_transactions_key(self, session_factory, attester, monkeypatch):
        svc, broker = attester
        monkeypatch.setattr(settings, "state_transition_v9_height", 1)
        _seed_genesis(session_factory)
        asyncio.run(svc._handle_request(self._request(None)))
        assert not broker.published
        assert metrics_registry._counters.get("v9_would_reject_attest_transactions_absent_total") == 1.0

    def test_v9_active_signs_valid_block(self, session_factory, attester, monkeypatch):
        svc, broker = attester
        monkeypatch.setattr(settings, "state_transition_v9_height", 1)
        _seed_genesis(session_factory)
        asyncio.run(svc._handle_request(self._request([_signed_tx()])))
        assert broker.published
        assert metrics_registry._counters.get("v9_would_reject_total") is None

    def test_v9_active_allows_signed_bridge_lock(self, session_factory, attester, monkeypatch):
        """A BRIDGE_LOCK carrying the bridge authority signature attests."""
        svc, broker = attester
        monkeypatch.setattr(settings, "state_transition_v9_height", 1)
        _seed_genesis(session_factory)
        _seed_bridge_authority(session_factory)
        asyncio.run(svc._handle_request(self._request([_signed_bridge_lock()])))
        assert broker.published

    def test_v9_active_refuses_unsigned_bridge_lock(self, session_factory, attester, monkeypatch):
        """A lock with no bridge_signature is refused — the sender-signature
        exemption exists only because the authority signature replaces it."""
        svc, broker = attester
        monkeypatch.setattr(settings, "state_transition_v9_height", 1)
        _seed_genesis(session_factory)
        _seed_bridge_authority(session_factory)
        lock = _unsigned_served_tx(to="bridge_lock", type="BRIDGE_LOCK", tx_hash="0x" + "ee" * 32)
        asyncio.run(svc._handle_request(self._request([lock])))
        assert not broker.published
        assert metrics_registry._counters.get("v9_would_reject_attest_bridge_signature_missing_total") == 1.0

    def test_nonce_advances_past_unsigned_internal(self, session_factory, attester, monkeypatch):
        """BRIDGE_LOCK bumps the sender nonce at apply — a same-sender signed
        tx after it must carry nonce 1, and the attester must not flag it."""
        svc, broker = attester
        monkeypatch.setattr(settings, "state_transition_v9_height", 1)
        _seed_genesis(session_factory)
        _seed_bridge_authority(session_factory)
        asyncio.run(svc._handle_request(self._request([_signed_bridge_lock(), _signed_tx(nonce=1)])))
        assert broker.published

    def test_same_sender_pair_must_be_ordered(self, session_factory, attester, monkeypatch):
        svc, broker = attester
        monkeypatch.setattr(settings, "state_transition_v9_height", 1)
        _seed_genesis(session_factory)
        pair = [
            _signed_tx(nonce=1),
            _signed_tx(nonce=0),
        ]
        asyncio.run(svc._handle_request(self._request(pair)))
        assert not broker.published
        assert metrics_registry._counters.get("v9_would_reject_attest_nonce_order_total") == 1.0

    def test_v9_active_refuses_undeclared_tx(self, session_factory, attester, monkeypatch):
        """A tx body whose content hash is not in the declared set must be
        refused — otherwise the proposer could attest one list and seal a
        block carrying another."""
        svc, broker = attester
        monkeypatch.setattr(settings, "state_transition_v9_height", 1)
        _seed_genesis(session_factory)
        tx = _signed_tx()
        request = self._request([tx])
        # Declare a different hash set while the header hash is recomputed
        # consistently — the request then commits to a set that does NOT
        # contain the delivered tx.
        request["header"]["tx_hashes"] = ["0x" + "99" * 32]
        asyncio.run(svc._handle_request(request))
        assert not broker.published
        assert metrics_registry._counters.get("v9_would_reject_attest_tx_set_mismatch_total") == 1.0

    def test_v9_active_refuses_truncated_tx_list(self, session_factory, attester, monkeypatch):
        svc, broker = attester
        monkeypatch.setattr(settings, "state_transition_v9_height", 1)
        _seed_genesis(session_factory)
        txs = [_signed_tx(), _signed_tx(nonce=1)]
        request = self._request(txs)
        request["transactions"] = txs[:1]  # header still declares 2
        asyncio.run(svc._handle_request(request))
        assert not broker.published
        assert metrics_registry._counters.get("v9_would_reject_attest_tx_count_mismatch_total") == 1.0

    def test_v9_active_refuses_forged_envelope_body(self, session_factory, attester, monkeypatch):
        """An envelope whose body doesn't hash to its declared tx_hash is a
        substituted tx — refuse."""
        svc, broker = attester
        monkeypatch.setattr(settings, "state_transition_v9_height", 1)
        _seed_genesis(session_factory)
        tx = _signed_tx()
        tx["amount"] = 5000  # tamper after hashing
        asyncio.run(svc._handle_request(self._request([tx])))
        assert not broker.published
        assert metrics_registry._counters.get("v9_would_reject_attest_tx_not_in_block_total") == 1.0

    def test_attester_without_state_access_refuses_at_v9(self, session_factory, monkeypatch):
        """A listener with no session factory cannot run the checks — at v9
        that fails closed rather than attesting blind."""
        from aitbc_chain.consensus.remote_attestation import RemoteAttestationService

        key_attester = "0x" + "cd" * 32
        addr_attester = derive_ethereum_address(key_attester)
        monkeypatch.setattr(
            settings,
            "validator_set",
            json.dumps([{"address": ADDR_ATTACKER}, {"address": addr_attester}]),
        )
        monkeypatch.setattr(settings, "attestation_lock_enabled", False)
        monkeypatch.setattr(settings, "state_transition_v9_height", 1)
        broker = _StubBroker()
        monkeypatch.setattr("aitbc_chain.consensus.remote_attestation.gossip_broker", broker)
        svc = RemoteAttestationService(CHAIN, {addr_attester: key_attester})  # no session_factory
        asyncio.run(svc._handle_request(self._request([_signed_tx()])))
        assert not broker.published
        assert metrics_registry._counters.get("v9_would_reject_attest_no_state_access_total") == 1.0

    def _make_head(self, session_factory, height: int, block_hash: str, parent_hash: str) -> None:
        """Record a Block row as the local head — what a completed import leaves."""
        with session_factory() as session:
            session.add(
                Block(
                    chain_id=CHAIN,
                    height=height,
                    hash=block_hash,
                    parent_hash=parent_hash,
                    proposer=ADDR_ATTACKER,
                    timestamp=T0,
                    tx_count=1,
                )
            )
            session.commit()

    def test_v9_resigns_already_imported_head(self, session_factory, attester, monkeypatch):
        """The request arrived AFTER the block imported: the local head IS the
        requested block (same height, same hash), so its parent no longer
        equals the tip. Import already ran every check — the attester signs
        again without counting a would-reject (live incident: not_at_parent
        fired on the attester's own head)."""
        svc, broker = attester
        monkeypatch.setattr(settings, "state_transition_v9_height", 1)
        _seed_genesis(session_factory)
        request = self._request([_signed_tx()])
        header = request["header"]
        self._make_head(session_factory, 1, header["hash"], header["parent_hash"])
        asyncio.run(svc._handle_request(request))
        assert broker.published, "re-attesting the already-imported head must sign"
        assert metrics_registry._counters.get("v9_would_reject_total") is None
        assert metrics_registry._counters.get("v9_would_reject_attest_not_at_parent_total") is None

    def test_v9_rival_at_head_height_still_refused(self, session_factory, attester, monkeypatch):
        """Same height, different hash: the requested block is NOT the local
        head, so the imported-head shortcut must not fire — the refusal and
        the shadow counter are the fork protection working."""
        svc, broker = attester
        monkeypatch.setattr(settings, "state_transition_v9_height", 1)
        _seed_genesis(session_factory)
        # Local head at height 1 is a different block than the request's.
        self._make_head(session_factory, 1, "0x" + "11" * 32, "0x" + "00" * 32)
        asyncio.run(svc._handle_request(self._request([_signed_tx()])))
        assert not broker.published
        assert metrics_registry._counters.get("v9_would_reject_attest_not_at_parent_total") == 1.0

    def test_v9_block_ahead_of_head_still_checked(self, session_factory, attester, monkeypatch):
        """A not-yet-imported block (the head is still its parent) runs the
        full tx checks — an unsigned tx in it refuses exactly as before."""
        svc, broker = attester
        monkeypatch.setattr(settings, "state_transition_v9_height", 1)
        _seed_genesis(session_factory)  # head = genesis = the request's parent
        asyncio.run(svc._handle_request(self._request([self._unsigned_bound_tx()])))
        assert not broker.published
        assert metrics_registry._counters.get("v9_would_reject_attest_missing_signature_total") == 1.0
