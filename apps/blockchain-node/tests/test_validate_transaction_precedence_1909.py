"""Validator-order precedence pins for ``StateTransition.validate_transaction`` (#1909).

``validate_transaction`` runs a fixed ordered tuple of ~40 ``_vt_*`` checks;
first failure wins and that order is consensus-observable (which error a
block producer sees, and therefore what it can be made to emit). #1861
verification showed a swap of two validators goes uncaught — these tests pin
the contract: a tx failing gate A *and* gate B must surface gate A's error
when A precedes B, and each later gate's trigger is proven live by a
companion call that fails only that gate.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session

from aitbc_chain.base_models import Account, Bond, ChainParameter
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.state.gpu_resources import GPURegistration
from aitbc_chain.state.state_transition import StateTransition

CHAIN = "test"


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test_precedence.db")
    chain_metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_authority_config(monkeypatch):
    """No authority/fee-recipient leakage from env or settings between tests."""
    from aitbc_chain.config import settings

    for attr in ("bridge_release_authority", "escrow_settlement_authority", "escrow_fee_recipient"):
        if hasattr(settings, attr):
            monkeypatch.setattr(settings, attr, "")
    for var in (
        "BRIDGE_RELEASE_AUTHORITY",
        "ESCROW_RELEASE_ADDRESS",
        "ESCROW_SETTLEMENT_AUTHORITY",
        "ESCROW_FEE_RECIPIENT",
    ):
        monkeypatch.delenv(var, raising=False)


def _session(engine) -> Session:
    return Session(engine)


def _account(session: Session, address: str, balance: int = 10**9, nonce: int = 0) -> None:
    session.add(Account(chain_id=CHAIN, address=address, balance=balance, nonce=nonce))
    session.commit()


def _validate(st: StateTransition, session: Session, tx: dict[str, Any], tx_hash: str, bv: int = 8) -> str:
    ok, msg = st.validate_transaction(session, CHAIN, tx, tx_hash, block_version=bv)
    assert not ok, f"expected rejection, got success: {tx_hash}"
    return msg


def _tx(frm: str = "ait1sender", **over: Any) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "from": frm,
        "to": "ait1recipient",
        "value": 0,
        "fee": 0,
        "nonce": 0,
        "type": "TRANSFER",
        "payload": {},
    }
    tx.update(over)
    return tx


def _signed_tx(key: str, frm: str, **over: Any) -> dict[str, Any]:
    from aitbc_chain.rpc.utils import sign_transaction_data

    tx = _tx(frm, **over)
    tx["signature"] = sign_transaction_data(tx, key)
    return tx


def _keypair() -> tuple[str, str]:
    from aitbc.crypto.crypto import derive_ethereum_address, generate_ethereum_private_key
    from aitbc.crypto.signature_recovery import canonical_address

    key = generate_ethereum_private_key()
    return key, canonical_address(derive_ethereum_address(key))


# ---------------------------------------------------------------------------
# Gates 1-3: chain_id, dedup, prepare — all type-agnostic, no fixtures needed.
# ---------------------------------------------------------------------------


class TestEarlyGatePrecedence:
    def test_chain_id_beats_dedup(self, engine) -> None:
        st = StateTransition()
        with _session(engine) as session:
            st._processed_tx_hashes.add("tx-c1")
            both = _tx(chain_id="other-chain")
            msg = _validate(st, session, both, "tx-c1")
            assert "Chain isolation violation" in msg
            # Companion: same replayed hash, correct chain_id -> dedup fires.
            only_dedup = _tx(chain_id=CHAIN)
            msg2 = _validate(st, session, only_dedup, "tx-c1")
            assert "already processed" in msg2

    def test_dedup_beats_prepare_v20_amount(self, engine) -> None:
        st = StateTransition()
        with _session(engine) as session:
            st._processed_tx_hashes.add("tx-c2")
            bad_amount = _tx(value=100, amount=200)
            msg = _validate(st, session, bad_amount, "tx-c2", bv=20)
            assert "already processed" in msg
            # Companion: fresh hash, v20 value/amount divergence -> prepare fires.
            msg2 = _validate(st, session, bad_amount, "tx-c2-fresh", bv=20)
            assert "value must equal signed amount" in msg2

    def test_prepare_beats_signature(self, engine) -> None:
        st = StateTransition()
        with _session(engine) as session:
            # Fails prepare (v20 amount divergence) AND signature (garbage sig).
            msg = _validate(st, session, _tx(value=100, amount=200, signature="0xdead"), "tx-c3", bv=20)
            assert "value must equal signed amount" in msg
            # Companion: consistent amounts, garbage signature -> signature gate.
            msg2 = _validate(st, session, _tx(value=100, amount=100, signature="0xdead"), "tx-c3b", bv=20)
            assert "Invalid signature" in msg2


# ---------------------------------------------------------------------------
# Gates 4-14: liquidity, bridge_*, escrow_lock_v3, signature, nonce, sender_account.
# ---------------------------------------------------------------------------


class TestMidGatePrecedence:
    def test_liquidity_beats_signature(self, engine) -> None:
        st = StateTransition()
        with _session(engine) as session:
            msg = _validate(
                st,
                session,
                _tx(type="LIQUIDITY_DEPOSIT", payload={"lock_days": 30}, signature="0xdead"),
                "tx-m1",
            )
            assert "must include pool_id" in msg
            msg2 = _validate(
                st,
                session,
                _tx(
                    type="LIQUIDITY_DEPOSIT",
                    payload={"pool_id": "p1", "lock_days": 30},
                    signature="0xdead",
                ),
                "tx-m1b",
            )
            assert "Invalid signature" in msg2

    def test_bridge_withdraw_beats_signature(self, engine) -> None:
        st = StateTransition()
        with _session(engine) as session:
            msg = _validate(
                st,
                session,
                _tx(
                    type="BRIDGE_WITHDRAW",
                    value=100,
                    payload={"eth_address": "not-an-address"},
                    signature="0xdead",
                ),
                "tx-m2",
            )
            assert "valid 0x eth_address" in msg
            msg2 = _validate(
                st,
                session,
                _tx(
                    type="BRIDGE_WITHDRAW",
                    value=100,
                    payload={"eth_address": "0x" + "ab" * 20},
                    signature="0xdead",
                ),
                "tx-m2b",
            )
            assert "Invalid signature" in msg2

    def test_escrow_lock_v3_beats_signature(self, engine) -> None:
        st = StateTransition()
        with _session(engine) as session:
            msg = _validate(
                st,
                session,
                _tx(type="ESCROW_LOCK", payload={}, signature="0xdead"),
                "tx-m3",
                bv=8,
            )
            assert "must include job_id" in msg
            msg2 = _validate(
                st,
                session,
                _tx(type="ESCROW_LOCK", payload={"job_id": "j1", "provider": "p1"}, signature="0xdead"),
                "tx-m3b",
                bv=8,
            )
            assert "Invalid signature" in msg2

    def test_signature_beats_nonce(self, engine) -> None:
        st = StateTransition()
        with _session(engine) as session:
            _account(session, "ait1sender", nonce=0)
            # Bad signature AND wrong nonce -> signature (gate 10) wins over nonce (14).
            msg = _validate(st, session, _tx(nonce=5, signature="0xdead"), "tx-m4")
            assert "Invalid signature" in msg
            # Companion: no signature, wrong nonce -> nonce gate fires.
            msg2 = _validate(st, session, _tx(nonce=5), "tx-m4b")
            assert "Invalid nonce" in msg2

    def test_nonce_beats_sender_balance(self, engine) -> None:
        st = StateTransition()
        with _session(engine) as session:
            _account(session, "ait1sender", balance=0, nonce=0)
            msg = _validate(st, session, _tx(nonce=5, value=100), "tx-m5")
            assert "Invalid nonce" in msg
            msg2 = _validate(st, session, _tx(nonce=0, value=100), "tx-m5b")
            assert "Insufficient balance" in msg2

    def test_stake_payload_auth_beats_sender_account(self, engine) -> None:
        st = StateTransition()
        with _session(engine) as session:
            bad_auth = {"signer": "ait1x", "message": {}, "signature": "0xbad"}
            msg = _validate(
                st,
                session,
                _tx(frm="ait1staker", type="STAKE_LOCK", payload={"auth": bad_auth}),
                "tx-m6",
            )
            assert "Invalid payload auth signature" in msg
            # Companion: no auth, missing sender account -> sender_account gate.
            msg2 = _validate(st, session, _tx(frm="ait1staker", type="STAKE_LOCK", payload={}), "tx-m6b")
            assert "Sender account not found" in msg2

    def test_nonce_beats_governance_execute(self, engine) -> None:
        st = StateTransition()
        with _session(engine) as session:
            _account(session, "ait1gov", nonce=0)
            msg = _validate(st, session, _tx(frm="ait1gov", type="GOVERNANCE_EXECUTE", nonce=5), "tx-m7")
            assert "Invalid nonce" in msg
            # Companion: nonce ok, no governance_executors param, bv>=5 -> gov gate.
            msg2 = _validate(st, session, _tx(frm="ait1gov", type="GOVERNANCE_EXECUTE", nonce=0), "tx-m7b")
            assert "governance_executors" in msg2


# ---------------------------------------------------------------------------
# Gates 18-33: zero_value_cost, sender_balance, ipfs, gpu_register_*.
# ---------------------------------------------------------------------------


class TestLateGatePrecedence:
    def test_zero_value_cost_beats_sender_balance(self, engine) -> None:
        st = StateTransition()
        with _session(engine) as session:
            _account(session, "ait1sender", balance=0, nonce=0)
            # MESSAGE is zero-value: value=5 violates gate 18; companion
            # (value=0, fee=100) shows the balance gate live at gate 29.
            msg = _validate(st, session, _tx(type="MESSAGE", value=5), "tx-l1")
            assert "must have value=0" in msg
            msg2 = _validate(st, session, _tx(type="MESSAGE", value=0, fee=100), "tx-l1b")
            assert "Insufficient balance" in msg2

    def test_sender_balance_beats_ipfs_subscription(self, engine) -> None:
        st = StateTransition()
        with _session(engine) as session:
            _account(session, "ait1sender", balance=0, nonce=0)
            msg = _validate(
                st,
                session,
                _tx(to="ait1island", type="IPFS_SUBSCRIPTION", value=100, payload={}),
                "tx-l2",
            )
            assert "Insufficient balance" in msg
            _account(session, "ait1rich", balance=10**9, nonce=0)
            msg2 = _validate(
                st,
                session,
                _tx(frm="ait1rich", to="ait1island", type="IPFS_SUBSCRIPTION", value=100, payload={}),
                "tx-l2b",
            )
            assert "must include island_id" in msg2

    def test_gpu_register_fields_beats_ownership(self, engine) -> None:
        st = StateTransition()
        with _session(engine) as session:
            _account(session, "ait1miner", balance=0, nonce=0)
            session.add(
                GPURegistration(
                    chain_id=CHAIN,
                    gpu_id="gpu-1",
                    miner_id="m1",
                    model="x",
                    registered_by="ait1other",
                    status="active",
                )
            )
            session.commit()
            # Missing miner_id/model (gate 32) AND foreign registrant (gate 33).
            msg = _validate(
                st,
                session,
                _tx(frm="ait1miner", type="GPU_REGISTER", payload={"gpu_id": "gpu-1"}),
                "tx-l3",
            )
            assert "must include miner_id" in msg
            # Companion: complete payload, foreign gpu_id -> ownership gate.
            msg2 = _validate(
                st,
                session,
                _tx(
                    frm="ait1miner",
                    type="GPU_REGISTER",
                    payload={
                        "gpu_id": "gpu-1",
                        "miner_id": "m1",
                        "model": "x",
                        "memory_gb": 8,
                        "price_per_hour": "1.0",
                    },
                ),
                "tx-l3b",
            )
            assert "must come from its registrant" in msg2


# ---------------------------------------------------------------------------
# Gates 6-7, 24-25, 37-38: bridge_lock_sig/account, sweep_params/fee_recipient,
# bond_lock_v20/v19 — need authority params or signed txs.
# ---------------------------------------------------------------------------


class TestAuthorityChainPrecedence:
    def test_bridge_lock_sig_beats_bridge_lock_account(self, engine) -> None:
        st = StateTransition()
        with _session(engine) as session:
            tx = _tx(
                frm="ait1sender",
                type="BRIDGE_LOCK",
                value=10,
                payload={"transfer_id": "t1", "amount": 10, "target_chain": "ait"},
            )
            # bv=9: no bridge authority configured -> sig gate fails closed;
            # the missing sender account would also fail gate 7.
            msg = _validate(st, session, tx, "tx-a1", bv=9)
            assert "requires a bridge release authority" in msg
            # Companion at bv=8 (sig check is shadow-only): account gate fires.
            msg2 = _validate(st, session, tx, "tx-a1b", bv=8)
            assert "Sender account not found" in msg2

    def test_sweep_params_beats_fee_recipient(self, engine) -> None:
        st = StateTransition()
        auth_key, auth_addr = _keypair()
        wrong_key, wrong_addr = _keypair()
        with _session(engine) as session:
            # escrow_settlement_authority set; escrow_fee_recipient deliberately unset.
            session.add(ChainParameter(chain_id=CHAIN, parameter="escrow_settlement_authority", value=auth_addr))
            _account(session, auth_addr, nonce=0)
            _account(session, wrong_addr, nonce=0)
            session.commit()
            payload = {"job_id": "job-1"}
            # Wrong signer fails gate 24; the unset fee recipient would fail gate 25.
            msg = _validate(
                st,
                session,
                _signed_tx(wrong_key, wrong_addr, type="ESCROW_FEE_SWEEP", payload=payload),
                "tx-a2",
                bv=11,
            )
            assert "must be signed by settlement authority" in msg
            # Companion: correct authority signer -> fee_recipient gate fires.
            msg2 = _validate(
                st,
                session,
                _signed_tx(auth_key, auth_addr, type="ESCROW_FEE_SWEEP", payload=payload),
                "tx-a2b",
                bv=11,
            )
            assert "fee recipient" in msg2

    def test_bond_lock_v20_beats_v19(self, engine) -> None:
        st = StateTransition()
        key, signer = _keypair()
        _, other = _keypair()
        with _session(engine) as session:
            session.add(Bond(chain_id=CHAIN, bond_id="bond-1", provider="ait1prov", amount=100, status="slashed"))
            session.commit()
            # provider != signer fails gate 37; the slashed bond would fail gate 38.
            msg = _validate(
                st,
                session,
                _signed_tx(
                    key,
                    signer,
                    type="BOND_LOCK",
                    payload={"provider": other, "bond_id": "bond-1", "lock_days": 30},
                ),
                "tx-a3",
                bv=22,
            )
            assert "signer is not the bond provider" in msg
            # Companion: provider == signer -> v19 top-up-on-terminal gate fires.
            msg2 = _validate(
                st,
                session,
                _signed_tx(
                    key,
                    signer,
                    type="BOND_LOCK",
                    payload={"provider": signer, "bond_id": "bond-1", "lock_days": 30},
                ),
                "tx-a3b",
                bv=22,
            )
            assert "not active" in msg2
