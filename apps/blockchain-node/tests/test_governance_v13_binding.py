"""v13 governance binding: GOVERNANCE_EXECUTE applies the sealed PROPOSE's
stored ``execution_payload`` (V-2).

The gate is ``settings.state_transition_v13_height``, which defaults to
``V13_HEIGHT_NOT_ARMED`` — an unreachable sentinel, so every v13 rule is dead
code on the live chain until the operator arms a real activation height.
Pre-gate behaviour is byte-identical: an EXECUTE keeps applying the payload
the transaction carries, whatever any proposal says.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import Account, ChainParameter
from aitbc_chain.config import V13_HEIGHT_NOT_ARMED, settings
from aitbc_chain.database import chain_metadata
from aitbc_chain.models import Transaction
from aitbc_chain.state.state_transition import StateTransition, get_block_version_for_height


def _sign_data(private_key: str, data: dict) -> str:
    from eth_utils import keccak
    from aitbc.crypto.crypto import sign_transaction_hash

    message = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return sign_transaction_hash("0x" + keccak(message).hex(), private_key)


def _make_tx(private_key: str, tx_data: dict) -> dict:
    from aitbc.crypto.crypto import derive_ethereum_address

    tx = dict(tx_data)
    tx["from"] = derive_ethereum_address(private_key)
    tx.setdefault("to", tx["from"])
    signable = {k: v for k, v in tx.items() if k != "signature"}
    if "amount" in signable:
        signable.pop("value", None)
    tx["signature"] = _sign_data(private_key, signable)
    return tx


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    with Session(engine) as session:
        yield session


EXECUTOR_KEY = "0x" + "44" * 32
STRANGER_KEY = "0x" + "55" * 32
CHAIN_ID = "ait-test"
PROPOSE_HEIGHT = 10
EXECUTE_HEIGHT = 50

PROPOSED_PAYLOAD = {
    "action": "parameter_change",
    "parameter": "some_param",
    "value": "proposed-value",
}
TAMPERED_PAYLOAD = {
    "action": "parameter_change",
    "parameter": "some_param",
    "value": "tampered-value",
}


def _seed_accounts(session: Session, chain_id: str) -> str:
    from aitbc.crypto.crypto import derive_ethereum_address

    executor = derive_ethereum_address(EXECUTOR_KEY)
    stranger = derive_ethereum_address(STRANGER_KEY)
    session.add(Account(chain_id=chain_id, address=executor, balance=1_000_000, nonce=0))
    session.add(Account(chain_id=chain_id, address=stranger, balance=1_000_000, nonce=0))
    session.commit()
    return executor


def _seed_executor_gate(session: Session, chain_id: str) -> str:
    executor = _seed_accounts(session, chain_id)
    session.add(ChainParameter(chain_id=chain_id, parameter="governance_executors", value=executor))
    session.commit()
    return executor


def _seed_propose(
    session: Session,
    chain_id: str,
    proposal_id: str = "prop-1",
    execution_payload: dict | None = PROPOSED_PAYLOAD,
    block_height: int = PROPOSE_HEIGHT,
) -> None:
    """Insert a sealed GOVERNANCE_PROPOSE row — the canonical proposal record."""
    payload: dict = {"proposal_id": proposal_id, "title": "t", "proposer": "0x" + "ab" * 20}
    if execution_payload is not None:
        payload["execution_payload"] = execution_payload
    session.add(
        Transaction(
            chain_id=chain_id,
            tx_hash=f"tx_propose_{proposal_id}",
            block_height=block_height,
            sender="0x" + "ab" * 20,
            recipient="0x" + "ab" * 20,
            payload=payload,
            nonce=0,
            value=0,
            fee=DEFAULT_TX_FEE_UNITS,
            type="GOVERNANCE_PROPOSE",
            status="sealed",
        )
    )
    session.commit()


def _execute_tx(
    key: str, chain_id: str, proposal_id: str = "prop-1", execution_payload: dict | None = TAMPERED_PAYLOAD
) -> dict:
    payload: dict = {"proposal_id": proposal_id}
    if execution_payload is not None:
        payload["execution_payload"] = execution_payload
    return _make_tx(
        key,
        {
            "amount": 0,
            "value": 0,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": 0,
            "type": "GOVERNANCE_EXECUTE",
            "chain_id": chain_id,
            "payload": payload,
        },
    )


def _propose_tx(key: str, chain_id: str, execution_payload: dict | None = PROPOSED_PAYLOAD) -> dict:
    payload: dict = {"proposal_id": "prop-new", "title": "t", "proposer": "0x" + "ab" * 20}
    if execution_payload is not None:
        payload["execution_payload"] = execution_payload
    return _make_tx(
        key,
        {
            "amount": 0,
            "value": 0,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": 0,
            "type": "GOVERNANCE_PROPOSE",
            "chain_id": chain_id,
            "payload": payload,
        },
    )


def _param_value(session: Session, chain_id: str, parameter: str = "some_param") -> str | None:
    row = session.exec(
        select(ChainParameter).where(ChainParameter.chain_id == chain_id, ChainParameter.parameter == parameter)
    ).first()
    return row.value if row is not None else None


# --- The gate itself: inert by default, functional when armed ----------------


def test_v13_height_defaults_to_unreachable_sentinel():
    """The default can never activate: no real chain produces block 2**62."""
    assert settings.state_transition_v13_height == V13_HEIGHT_NOT_ARMED
    # Far past every armed height, the derived version stays 12, never 13.
    assert get_block_version_for_height(10**12) == 12


def test_v13_ladder_works_when_armed():
    """The version rung itself is functional — height-derived like v8+."""
    assert get_block_version_for_height(V13_HEIGHT_NOT_ARMED) == 13
    assert get_block_version_for_height(V13_HEIGHT_NOT_ARMED - 1) == 12


# --- Pre-gate: byte-identical current behaviour -------------------------------


def test_pre_gate_execute_applies_tx_payload_regardless_of_proposal(session):
    """Below v13 the stored proposal is ignored even when it exists and
    disagrees — the tx-carried payload applies, exactly as today."""
    _seed_executor_gate(session, CHAIN_ID)
    _seed_propose(session, CHAIN_ID)  # stored payload says "proposed-value"

    st = StateTransition()
    ok, msg = st.apply_transaction(
        session,
        CHAIN_ID,
        _execute_tx(EXECUTOR_KEY, CHAIN_ID),
        "tx_exec_pre",
        block_version=12,
        block_height=EXECUTE_HEIGHT,
    )
    assert ok, msg
    assert _param_value(session, CHAIN_ID) == "tampered-value"


def test_pre_gate_execute_without_any_proposal_still_applies(session):
    """Below v13 an EXECUTE needs no sealed proposal at all (18 sealed
    mainnet executes reference no propose)."""
    _seed_executor_gate(session, CHAIN_ID)

    st = StateTransition()
    ok, msg = st.apply_transaction(
        session,
        CHAIN_ID,
        _execute_tx(EXECUTOR_KEY, CHAIN_ID),
        "tx_exec_pre2",
        block_version=12,
        block_height=EXECUTE_HEIGHT,
    )
    assert ok, msg
    assert _param_value(session, CHAIN_ID) == "tampered-value"


def test_pre_gate_propose_needs_no_execution_payload(session):
    """All three sealed mainnet proposes carry no execution_payload — they
    must stay replayable."""
    _seed_accounts(session, CHAIN_ID)

    st = StateTransition()
    ok, msg = st.apply_transaction(
        session,
        CHAIN_ID,
        _propose_tx(EXECUTOR_KEY, CHAIN_ID, execution_payload=None),
        "tx_prop_pre",
        block_version=12,
        block_height=EXECUTE_HEIGHT,
    )
    assert ok, msg


# --- Post-gate: the binding ----------------------------------------------------


def test_post_gate_matching_payload_applies(session):
    """An EXECUTE carrying exactly the stored payload is admitted and applied."""
    _seed_executor_gate(session, CHAIN_ID)
    _seed_propose(session, CHAIN_ID)

    st = StateTransition()
    ok, msg = st.apply_transaction(
        session,
        CHAIN_ID,
        _execute_tx(EXECUTOR_KEY, CHAIN_ID, execution_payload=PROPOSED_PAYLOAD),
        "tx_exec_match",
        block_version=13,
        block_height=EXECUTE_HEIGHT,
    )
    assert ok, msg
    assert _param_value(session, CHAIN_ID) == "proposed-value"


def test_post_gate_tampered_payload_rejected_in_verification(session):
    """A swapped payload is refused at block verification and writes nothing."""
    _seed_executor_gate(session, CHAIN_ID)
    _seed_propose(session, CHAIN_ID)

    st = StateTransition()
    ok, msg = st.apply_transaction(
        session,
        CHAIN_ID,
        _execute_tx(EXECUTOR_KEY, CHAIN_ID),
        "tx_exec_tampered",
        block_version=13,
        block_height=EXECUTE_HEIGHT,
    )
    assert not ok
    assert "does not match sealed proposal" in msg
    assert _param_value(session, CHAIN_ID) is None


def test_post_gate_tampered_payload_rejected_in_admission(session):
    """The mempool door refuses the same swap with the same message."""
    executor = _seed_executor_gate(session, CHAIN_ID)
    _seed_propose(session, CHAIN_ID)

    from aitbc_chain.state.admission_authority import sender_authority_error

    error = sender_authority_error(
        session,
        CHAIN_ID,
        "GOVERNANCE_EXECUTE",
        executor,
        block_version=13,
        block_height=EXECUTE_HEIGHT,
        payload={"proposal_id": "prop-1", "execution_payload": TAMPERED_PAYLOAD},
        fee=DEFAULT_TX_FEE_UNITS,
    )
    assert error is not None and "does not match sealed proposal" in error


def test_post_gate_matching_payload_admitted(session):
    """Admission twin of the happy path: the door opens for the stored payload."""
    executor = _seed_executor_gate(session, CHAIN_ID)
    _seed_propose(session, CHAIN_ID)

    from aitbc_chain.state.admission_authority import sender_authority_error

    assert (
        sender_authority_error(
            session,
            CHAIN_ID,
            "GOVERNANCE_EXECUTE",
            executor,
            block_version=13,
            block_height=EXECUTE_HEIGHT,
            payload={"proposal_id": "prop-1", "execution_payload": PROPOSED_PAYLOAD},
            fee=DEFAULT_TX_FEE_UNITS,
        )
        is None
    )


def test_post_gate_missing_proposal_rejected(session):
    """No sealed PROPOSE for the id — refused in verification and admission."""
    executor = _seed_executor_gate(session, CHAIN_ID)

    st = StateTransition()
    ok, msg = st.apply_transaction(
        session,
        CHAIN_ID,
        _execute_tx(EXECUTOR_KEY, CHAIN_ID, proposal_id="ghost"),
        "tx_exec_ghost",
        block_version=13,
        block_height=EXECUTE_HEIGHT,
    )
    assert not ok
    assert "no GOVERNANCE_PROPOSE" in msg

    from aitbc_chain.state.admission_authority import sender_authority_error

    error = sender_authority_error(
        session,
        CHAIN_ID,
        "GOVERNANCE_EXECUTE",
        executor,
        block_version=13,
        block_height=EXECUTE_HEIGHT,
        payload={"proposal_id": "ghost", "execution_payload": PROPOSED_PAYLOAD},
        fee=DEFAULT_TX_FEE_UNITS,
    )
    assert error is not None and "no GOVERNANCE_PROPOSE" in error


def test_post_gate_same_block_propose_not_bindable(session):
    """The PROPOSE must seal in an *earlier* block — a same-block pair rejects."""
    _seed_executor_gate(session, CHAIN_ID)
    _seed_propose(session, CHAIN_ID, block_height=EXECUTE_HEIGHT)

    st = StateTransition()
    ok, msg = st.apply_transaction(
        session,
        CHAIN_ID,
        _execute_tx(EXECUTOR_KEY, CHAIN_ID, execution_payload=PROPOSED_PAYLOAD),
        "tx_exec_sameblock",
        block_version=13,
        block_height=EXECUTE_HEIGHT,
    )
    assert not ok
    assert "earlier block" in msg


def test_post_gate_execute_requires_proposal_id(session):
    """At v13 an EXECUTE with no proposal_id is refused outright."""
    _seed_executor_gate(session, CHAIN_ID)
    tx = _make_tx(
        EXECUTOR_KEY,
        {
            "amount": 0,
            "value": 0,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": 0,
            "type": "GOVERNANCE_EXECUTE",
            "chain_id": CHAIN_ID,
            "payload": {"execution_payload": PROPOSED_PAYLOAD},
        },
    )

    st = StateTransition()
    ok, msg = st.apply_transaction(
        session,
        CHAIN_ID,
        tx,
        "tx_exec_noid",
        block_version=13,
        block_height=EXECUTE_HEIGHT,
    )
    assert not ok
    assert "proposal_id is required" in msg


def test_post_gate_propose_requires_execution_payload(session):
    """A v13 PROPOSE without the committed payload is refused."""
    _seed_accounts(session, CHAIN_ID)

    st = StateTransition()
    ok, msg = st.apply_transaction(
        session,
        CHAIN_ID,
        _propose_tx(EXECUTOR_KEY, CHAIN_ID, execution_payload=None),
        "tx_prop_bare",
        block_version=13,
        block_height=EXECUTE_HEIGHT,
    )
    assert not ok
    assert "execution_payload" in msg


def test_post_gate_propose_accepts_dict_payload(session):
    _seed_accounts(session, CHAIN_ID)

    st = StateTransition()
    ok, msg = st.apply_transaction(
        session,
        CHAIN_ID,
        _propose_tx(EXECUTOR_KEY, CHAIN_ID),
        "tx_prop_ok",
        block_version=13,
        block_height=EXECUTE_HEIGHT,
    )
    assert ok, msg


def test_post_gate_propose_payload_size_cap(session):
    """The committed payload is bounded — no unbounded blobs in the tx table."""
    _seed_accounts(session, CHAIN_ID)
    huge = {"action": "parameter_change", "parameter": "p", "value": "x" * (20 * 1024)}

    st = StateTransition()
    ok, msg = st.apply_transaction(
        session,
        CHAIN_ID,
        _propose_tx(EXECUTOR_KEY, CHAIN_ID, execution_payload=huge),
        "tx_prop_huge",
        block_version=13,
        block_height=EXECUTE_HEIGHT,
    )
    assert not ok
    assert "exceeds" in msg


def test_post_gate_apply_uses_stored_payload(session):
    """Even past validation, apply resolves and uses the STORED payload — the
    literal V-2 semantic, not 'apply what the tx carried'."""
    _seed_executor_gate(session, CHAIN_ID)
    _seed_propose(session, CHAIN_ID)

    st = StateTransition()
    tx = _execute_tx(EXECUTOR_KEY, CHAIN_ID, execution_payload=PROPOSED_PAYLOAD)
    # Simulate a tx whose payload were swapped after validation: the handler
    # re-resolves the sealed proposal and applies its payload regardless.
    tx["payload"]["execution_payload"] = TAMPERED_PAYLOAD
    st._handle_governance_execute(session, CHAIN_ID, tx, "tx_exec_direct", EXECUTE_HEIGHT, block_version=13)
    assert _param_value(session, CHAIN_ID) == "proposed-value"
