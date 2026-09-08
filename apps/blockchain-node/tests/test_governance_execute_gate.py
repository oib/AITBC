"""GOVERNANCE_EXECUTE executor gating via the on-chain ``governance_executors``
chain parameter.

The parameter is chain state — identical on every node that applied the
parameter-setting tx — so the gate is deterministic. Unset means no
restriction (pre-gate behavior); once set, non-executor senders are rejected
at validation on every node at the same height.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import Account, ChainParameter
from aitbc_chain.database import chain_metadata
from aitbc_chain.state.state_transition import StateTransition


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


def _seed_accounts(session: Session, chain_id: str) -> str:
    from aitbc.crypto.crypto import derive_ethereum_address

    executor = derive_ethereum_address(EXECUTOR_KEY)
    stranger = derive_ethereum_address(STRANGER_KEY)
    session.add(Account(chain_id=chain_id, address=executor, balance=1_000_000, nonce=0))
    session.add(Account(chain_id=chain_id, address=stranger, balance=1_000_000, nonce=0))
    session.commit()
    return executor


def _gov_tx(key: str, chain_id: str) -> dict:
    return _make_tx(
        key,
        {
            "amount": 0,
            "value": 0,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": 0,
            "type": "GOVERNANCE_EXECUTE",
            "chain_id": chain_id,
            "payload": {
                "proposal_id": "prop-1",
                "execution_payload": {
                    "action": "parameter_change",
                    "parameter": "some_param",
                    "value": "x",
                },
            },
        },
    )


def test_governance_execute_unrestricted_when_param_unset(session):
    chain_id = "ait-test"
    _seed_accounts(session, chain_id)
    st = StateTransition()
    ok, msg = st.apply_transaction(session, chain_id, _gov_tx(STRANGER_KEY, chain_id), "tx_gov_1")
    assert ok, msg


def test_governance_execute_rejected_for_non_executor(session):
    chain_id = "ait-test"
    executor_addr = _seed_accounts(session, chain_id)
    session.add(ChainParameter(chain_id=chain_id, parameter="governance_executors", value=executor_addr))
    session.commit()

    st = StateTransition()
    ok, msg = st.apply_transaction(session, chain_id, _gov_tx(STRANGER_KEY, chain_id), "tx_gov_2")
    assert not ok
    assert "not an authorized executor" in msg


def test_governance_execute_accepted_for_executor(session):
    chain_id = "ait-test"
    executor_addr = _seed_accounts(session, chain_id)
    session.add(ChainParameter(chain_id=chain_id, parameter="governance_executors", value=executor_addr))
    session.commit()

    st = StateTransition()
    ok, msg = st.apply_transaction(session, chain_id, _gov_tx(EXECUTOR_KEY, chain_id), "tx_gov_3")
    assert ok, msg

    row = session.exec(
        select(ChainParameter).where(ChainParameter.chain_id == chain_id, ChainParameter.parameter == "some_param")
    ).first()
    assert row is not None and row.value == "x"
