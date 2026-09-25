"""v5 bridge-credit authorization: signature-bound BRIDGE_RELEASE/BRIDGE_REFUND.

Before v5 the pseudo-sender was the only gate — a string any proposer can
choose. v5 additionally requires a secp256k1 signature over the credit's
semantic fields (type, transfer_id, chains, recipient, amounts, proof, nonce,
tx_hash) recovering to the bridge release authority: the
``bridge_release_authority`` chain parameter, then env, then the escrow
settlement authority (the same operator key signs credits by default).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session

from aitbc.crypto.crypto import derive_ethereum_address, generate_ethereum_private_key
from aitbc_chain.base_models import ChainParameter, Transaction
from aitbc_chain.config import settings
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.state.bridge_credit import (
    bridge_credit_message,
    sign_bridge_credit,
    verify_bridge_credit_signature,
)
from aitbc_chain.state.pure_state_transition import compute_state_delta
from aitbc_chain.state.state_transition import StateTransition, _bridge_release_authority


@pytest.fixture
def engine(tmp_path):
    db_path = tmp_path / "test_bridge_credit.db"
    engine = create_engine(f"sqlite:///{db_path}")
    chain_metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def authority():
    key = generate_ethereum_private_key()
    return key, derive_ethereum_address(key)


@pytest.fixture(autouse=True)
def _clean_authority_config(monkeypatch):
    """Isolate authority resolution: no env or settings leakage between tests."""
    monkeypatch.setattr(settings, "bridge_release_authority", "")
    monkeypatch.setattr(settings, "escrow_settlement_authority", "")
    monkeypatch.delenv("BRIDGE_RELEASE_AUTHORITY", raising=False)
    monkeypatch.delenv("ESCROW_RELEASE_ADDRESS", raising=False)
    monkeypatch.delenv("ESCROW_SETTLEMENT_AUTHORITY", raising=False)


def _release_tx(recipient: str = "ait1recipient", amount: int = 100, nonce: int = 0) -> dict:
    """The sweep-rebuilt shape of a pre-registered BRIDGE_RELEASE row."""
    return {
        "from": "bridge_release",
        "to": recipient,
        "amount": 0,
        "value": 0,
        "fee": 0,
        "nonce": nonce,
        "type": "BRIDGE_RELEASE",
        "payload": {
            "type": "BRIDGE_RELEASE",
            "transfer_id": "transfer-1",
            "source_chain": "ait",
            "source_sender": "ait1source",
            "target_chain": "test",
            "amount": amount,
            "asset": "native",
            "proof": "proofhash",
        },
    }


def _refund_tx(recipient: str = "ait1sender", amount: int = 55, nonce: int = 0) -> dict:
    """The sweep-rebuilt shape of a pre-registered BRIDGE_REFUND row."""
    return {
        "from": "bridge_refund",
        "to": recipient,
        "amount": 0,
        "value": 0,
        "fee": 0,
        "nonce": nonce,
        "type": "BRIDGE_REFUND",
        "payload": {
            "type": "BRIDGE_REFUND",
            "transfer_id": "transfer-2",
            "source_chain": "test",
            "target_chain": "ait",
            "amount": amount,
            "asset": "native",
        },
    }


def _sign_payload(tx: dict, tx_hash: str, key: str) -> dict:
    """Sign as issuance does — the signature rides inside ``payload``."""
    tx["payload"]["bridge_signature"] = sign_bridge_credit(tx, tx_hash, key)
    return tx


# --------------------------------------------------------------------------
# Sequential path (validate_transaction / apply_transaction)
# --------------------------------------------------------------------------


def test_v5_signed_release_accepted(engine, authority, monkeypatch):
    _, addr = authority
    monkeypatch.setattr(settings, "bridge_release_authority", addr)
    st = StateTransition()
    with Session(engine) as session:
        tx = _sign_payload(_release_tx(), "tx-rel-1", authority[0])
        ok, msg = st.apply_transaction(session, "test", tx, "tx-rel-1", block_version=5)
        assert ok, msg


def test_v5_signed_refund_accepted(engine, authority, monkeypatch):
    _, addr = authority
    monkeypatch.setattr(settings, "bridge_release_authority", addr)
    st = StateTransition()
    with Session(engine) as session:
        tx = _sign_payload(_refund_tx(), "tx-ref-1", authority[0])
        ok, msg = st.apply_transaction(session, "test", tx, "tx-ref-1", block_version=5)
        assert ok, msg


def test_v5_unsigned_credit_rejected(engine, authority, monkeypatch):
    """The mint vector from the report: right pseudo-sender, fresh hash, no sig."""
    _, addr = authority
    monkeypatch.setattr(settings, "bridge_release_authority", addr)
    st = StateTransition()
    with Session(engine) as session:
        ok, msg = st.apply_transaction(session, "test", _release_tx(), "tx-rel-forged", block_version=5)
        assert not ok
        assert "bridge_signature" in msg


def test_v5_wrong_signer_rejected(engine, authority, monkeypatch):
    _, addr = authority
    monkeypatch.setattr(settings, "bridge_release_authority", addr)
    wrong_key = generate_ethereum_private_key()
    st = StateTransition()
    with Session(engine) as session:
        tx = _sign_payload(_release_tx(), "tx-rel-wrong", wrong_key)
        ok, msg = st.apply_transaction(session, "test", tx, "tx-rel-wrong", block_version=5)
        assert not ok
        assert "bridge_signature" in msg


def test_v5_garbage_signature_rejected(engine, authority, monkeypatch):
    _, addr = authority
    monkeypatch.setattr(settings, "bridge_release_authority", addr)
    st = StateTransition()
    with Session(engine) as session:
        tx = _release_tx()
        tx["payload"]["bridge_signature"] = "0xdeadbeef"
        ok, msg = st.apply_transaction(session, "test", tx, "tx-rel-garbage", block_version=5)
        assert not ok


def test_v5_no_authority_fails_closed(engine):
    """v5: nothing configured anywhere → signed or not, the credit is refused."""
    key = generate_ethereum_private_key()
    st = StateTransition()
    with Session(engine) as session:
        tx = _sign_payload(_release_tx(), "tx-rel-noauth", key)
        ok, msg = st.apply_transaction(session, "test", tx, "tx-rel-noauth", block_version=5)
        assert not ok
        assert "bridge release authority" in msg


def test_v5_wrong_pseudo_sender_rejected_before_signature(engine, authority, monkeypatch):
    _, addr = authority
    monkeypatch.setattr(settings, "bridge_release_authority", addr)
    st = StateTransition()
    with Session(engine) as session:
        tx = _release_tx()
        tx["from"] = "ait1attacker"
        _sign_payload(tx, "tx-rel-ps", authority[0])
        ok, msg = st.apply_transaction(session, "test", tx, "tx-rel-ps", block_version=5)
        assert not ok
        assert "pseudo-sender" in msg


def test_v4_unsigned_credit_stays_lenient(engine):
    """Replay compat: pre-v5 blocks carry unsigned credits."""
    st = StateTransition()
    with Session(engine) as session:
        ok, msg = st.apply_transaction(session, "test", _release_tx(), "tx-rel-v4", block_version=4)
        assert ok, msg


def test_v5_signature_binds_recipient(engine, authority, monkeypatch):
    _, addr = authority
    monkeypatch.setattr(settings, "bridge_release_authority", addr)
    st = StateTransition()
    with Session(engine) as session:
        tx = _sign_payload(_release_tx(), "tx-rel-rbind", authority[0])
        tx["to"] = "ait1attacker"  # tamper after signing
        ok, msg = st.apply_transaction(session, "test", tx, "tx-rel-rbind", block_version=5)
        assert not ok


def test_v5_signature_binds_credited_value(engine, authority, monkeypatch):
    """Apply credits envelope `value` — a copied signature cannot re-point it."""
    _, addr = authority
    monkeypatch.setattr(settings, "bridge_release_authority", addr)
    st = StateTransition()
    with Session(engine) as session:
        tx = _sign_payload(_release_tx(), "tx-rel-vbind", authority[0])
        tx["value"] = 10**9  # the signed row had value=0
        ok, msg = st.apply_transaction(session, "test", tx, "tx-rel-vbind", block_version=5)
        assert not ok


def test_v5_signature_binds_tx_hash(engine, authority, monkeypatch):
    """The same signed content cannot be replayed under a different hash."""
    _, addr = authority
    monkeypatch.setattr(settings, "bridge_release_authority", addr)
    st = StateTransition()
    with Session(engine) as session:
        tx = _sign_payload(_release_tx(), "tx-rel-h1", authority[0])
        ok, msg = st.apply_transaction(session, "test", tx, "tx-rel-h2", block_version=5)
        assert not ok


def test_onchain_bridge_authority_overrides_env(engine, authority, monkeypatch):
    """The chain parameter wins over per-node env — drift cannot fork the gate."""
    _, addr = authority
    env_addr = derive_ethereum_address(generate_ethereum_private_key())
    monkeypatch.setenv("BRIDGE_RELEASE_AUTHORITY", env_addr)
    st = StateTransition()
    with Session(engine) as session:
        session.add(ChainParameter(chain_id="test", parameter="bridge_release_authority", value=addr))
        session.commit()
        tx = _sign_payload(_release_tx(), "tx-rel-param", authority[0])
        ok, msg = st.apply_transaction(session, "test", tx, "tx-rel-param", block_version=5)
        assert ok, msg


def test_escrow_authority_is_the_transitional_fallback(engine, authority, monkeypatch):
    """A chain that configured only escrow still resolves — the same key signs."""
    _, addr = authority
    monkeypatch.setattr(settings, "escrow_settlement_authority", addr)
    st = StateTransition()
    with Session(engine) as session:
        tx = _sign_payload(_release_tx(), "tx-rel-escfb", authority[0])
        ok, msg = st.apply_transaction(session, "test", tx, "tx-rel-escfb", block_version=5)
        assert ok, msg


def test_bridge_param_beats_escrow_fallback(engine, authority, monkeypatch):
    """Setting a dedicated bridge authority decouples it from the escrow key."""
    _, bridge_addr = authority
    escrow_key = generate_ethereum_private_key()
    escrow_addr = derive_ethereum_address(escrow_key)
    monkeypatch.setattr(settings, "escrow_settlement_authority", escrow_addr)
    st = StateTransition()
    with Session(engine) as session:
        session.add(ChainParameter(chain_id="test", parameter="bridge_release_authority", value=bridge_addr))
        session.commit()
        # Escrow-keyed signature no longer authorises a bridge credit.
        bad = _sign_payload(_release_tx(), "tx-rel-dec1", escrow_key)
        ok, msg = st.apply_transaction(session, "test", bad, "tx-rel-dec1", block_version=5)
        assert not ok
        # The dedicated bridge authority signature does.
        good = _sign_payload(_refund_tx(), "tx-ref-dec2", authority[0])
        ok, msg = st.apply_transaction(session, "test", good, "tx-ref-dec2", block_version=5)
        assert ok, msg


# --------------------------------------------------------------------------
# Proposer sweep: the signature survives Transaction-row reconstruction
# --------------------------------------------------------------------------


def test_sweep_rebuilt_content_preserves_signature(authority):
    """poa.py rebuilds a pre-registered row into block content with
    ``signature: ""`` — the bridge signature lives in ``payload`` and the
    validator's projection of the rebuilt dict must equal the issuer's."""
    key, addr = authority
    payload = {
        "type": "BRIDGE_RELEASE",
        "transfer_id": "transfer-9",
        "source_chain": "ait",
        "source_sender": "ait1source",
        "target_chain": "test",
        "amount": 250,
        "asset": "native",
        "proof": "proofhash",
    }
    issuer_view = {
        "type": "BRIDGE_RELEASE",
        "to": "ait1recipient",
        "value": 0,
        "fee": 0,
        "nonce": 7,
        "payload": payload,
    }
    sig = sign_bridge_credit(issuer_view, "rowhash-9", key)
    payload["bridge_signature"] = sig
    # The DB row stores the payload; the sweep rebuilds the block content.
    row = Transaction(
        chain_id="test",
        tx_hash="rowhash-9",
        sender="bridge_release",
        recipient="ait1recipient",
        payload=payload,
        value=0,
        fee=0,
        nonce=7,
        type="BRIDGE_RELEASE",
    )
    rebuilt = {
        "from": row.sender or "bridge_release",
        "to": row.recipient or "",
        "amount": row.value or 0,
        "value": row.value or 0,
        "fee": row.fee or 0,
        "nonce": row.nonce or 0,
        "type": row.type or "TRANSFER",
        "payload": row.payload or {},
        "signature": "",
    }
    assert bridge_credit_message(rebuilt, row.tx_hash) == bridge_credit_message(issuer_view, "rowhash-9")
    assert verify_bridge_credit_signature(rebuilt, row.tx_hash, addr)


def test_flat_mempool_shape_signs_and_verifies(authority):
    """Block-scoped mode: the credit is a flat dict; signature at top level."""
    key, addr = authority
    tx = {
        "from": "bridge_release",
        "to": "ait1recipient",
        "amount": 300,
        "fee": 0,
        "type": "BRIDGE_RELEASE",
        "transfer_id": "transfer-10",
        "source_chain": "ait",
        "source_sender": "ait1source",
        "target_chain": "test",
        "asset": "native",
        "proof": "proofhash",
        "nonce": 0,
    }
    tx["bridge_signature"] = sign_bridge_credit(tx, "memhash-10", key)
    assert verify_bridge_credit_signature(tx, "memhash-10", addr)


# --------------------------------------------------------------------------
# Pure / parallel path (compute_state_delta)
# --------------------------------------------------------------------------


def test_pure_v5_signed_release_accepted(authority):
    _, addr = authority
    tx = _sign_payload(_release_tx(), "pure-rel-1", authority[0])
    delta = compute_state_delta({}, tx, "test", tx_hash="pure-rel-1", block_version=5, bridge_authority=addr)
    assert delta.success, delta.error


def test_pure_v5_unsigned_credit_rejected(authority):
    _, addr = authority
    delta = compute_state_delta({}, _release_tx(), "test", tx_hash="pure-rel-2", block_version=5, bridge_authority=addr)
    assert not delta.success
    assert "bridge_signature" in delta.error


def test_pure_v5_no_authority_fails_closed():
    """Key absent + env empty → fail closed even for a correctly signed credit."""
    key = generate_ethereum_private_key()
    tx = _sign_payload(_release_tx(), "pure-rel-3", key)
    delta = compute_state_delta({}, tx, "test", tx_hash="pure-rel-3", block_version=5)
    assert not delta.success
    assert "bridge release authority" in delta.error


def test_pure_v5_env_fallback_authority(authority, monkeypatch):
    _, addr = authority
    monkeypatch.setenv("BRIDGE_RELEASE_AUTHORITY", addr)
    tx = _sign_payload(_release_tx(), "pure-rel-4", authority[0])
    delta = compute_state_delta({}, tx, "test", tx_hash="pure-rel-4", block_version=5)
    assert delta.success, delta.error


def test_pure_v5_escrow_env_fallback_authority(authority, monkeypatch):
    """No bridge env → the escrow settlement env resolves the same key."""
    _, addr = authority
    monkeypatch.setattr(settings, "escrow_settlement_authority", addr)
    tx = _sign_payload(_release_tx(), "pure-rel-5", authority[0])
    delta = compute_state_delta({}, tx, "test", tx_hash="pure-rel-5", block_version=5)
    assert delta.success, delta.error


def test_pure_v5_wrong_sender_still_rejected(authority):
    _, addr = authority
    tx = _sign_payload(_release_tx(), "pure-rel-6", authority[0])
    tx["from"] = "ait1attacker"
    delta = compute_state_delta({}, tx, "test", tx_hash="pure-rel-6", block_version=5, bridge_authority=addr)
    assert not delta.success
    assert "pseudo-sender" in delta.error


def test_pure_v4_credit_stays_lenient():
    delta = compute_state_delta({}, _release_tx(), "test", tx_hash="pure-rel-v4", block_version=4)
    assert delta.success, delta.error


# --------------------------------------------------------------------------
# Authority resolution precedence
# --------------------------------------------------------------------------


def test_authority_resolution_precedence(engine, authority, monkeypatch):
    _, bridge_addr = authority
    escrow_addr = derive_ethereum_address(generate_ethereum_private_key())
    with Session(engine) as session:
        # Nothing configured → the escrow resolution (also empty) → None.
        assert _bridge_release_authority(session, "test") is None
        # Escrow env → transitional fallback.
        monkeypatch.setattr(settings, "escrow_settlement_authority", escrow_addr)
        assert _bridge_release_authority(session, "test") == escrow_addr
        # Bridge env beats the escrow fallback.
        monkeypatch.setattr(settings, "bridge_release_authority", bridge_addr)
        assert _bridge_release_authority(session, "test") == bridge_addr
        # On-chain param beats both envs.
        other = derive_ethereum_address(generate_ethereum_private_key())
        session.add(ChainParameter(chain_id="test", parameter="bridge_release_authority", value=other))
        session.commit()
        assert _bridge_release_authority(session, "test") == other
