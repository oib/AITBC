"""Rehearsal for ``scripts/ops/governance_parameter_change.py`` (A17).

Runs the tool's own ``_build_tx`` envelope through the real state transition
against an in-memory chain — the same path a proposer takes at block
assembly — to show that what the tool builds is what the chain applies, and
that the rotation it writes actually gates the old keys off.

Cases:

(a) An executor-signed GOVERNANCE_EXECUTE built by ``_build_tx`` applies, and
    ``escrow_settlement_authority`` reads back as the new address at the
    execute's block height (the old value still resolves below it).
(b) At that height the next ESCROW_RELEASE signed by the *old* authority key
    is refused by ``validate_transaction``.
(c) At the next height ``apply_transaction`` for the same old-key release
    returns failure — inside block assembly that is exactly the
    ``continue`` path in ``consensus/poa.py`` (the failed apply is logged and
    skipped, assembly proceeds to the next tx; poa.py:2162-2178), so the
    rotation cannot wedge the chain.
(d) The chain itself does NOT protect the executor: a GOVERNANCE_EXECUTE
    writing a ``governance_executors`` list that excludes its own signer
    applies cleanly — the refusal is the tool's job, and
    ``_executor_lockout_reason`` is shown refusing the same list the chain
    just sealed.

Everything is throwaway keys and an in-memory sqlite chain; no network.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc.crypto.crypto import derive_ethereum_address
from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import Account, ChainParameter, ChainParameterHistory, Transaction
from aitbc_chain.database import chain_metadata
from aitbc_chain.state.state_transition import StateTransition, _chain_parameter_value, _escrow_settlement_authority

REPO = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "governance_parameter_change", REPO / "scripts" / "ops" / "governance_parameter_change.py"
)
assert _spec is not None and _spec.loader is not None
tool = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tool
_spec.loader.exec_module(tool)

CHAIN = "ait-test"
OLD_HEIGHT = 100  # old authority's value took effect here
EXECUTE_HEIGHT = 200  # the tool's GOVERNANCE_EXECUTE seals here
NEXT_HEIGHT = 201

EXECUTOR_KEY = "0x" + "44" * 32
OLD_AUTHORITY_KEY = "0x" + "55" * 32
NEW_AUTHORITY = derive_ethereum_address("0x" + "66" * 32)
PROVIDER = derive_ethereum_address("0x" + "77" * 32)
JOB_ID = "rehearsal-job-1"


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _seed(session: Session) -> tuple[str, str]:
    """Funded executor + old authority, the two chain parameters (with a
    history row so the old value resolves below EXECUTE_HEIGHT), and the
    job's ESCROW_LOCK."""
    executor = derive_ethereum_address(EXECUTOR_KEY)
    old_authority = derive_ethereum_address(OLD_AUTHORITY_KEY)
    session.add(Account(chain_id=CHAIN, address=executor, balance=10_000_000, nonce=0))
    session.add(Account(chain_id=CHAIN, address=old_authority, balance=10_000_000, nonce=0))
    for parameter, value in (
        ("governance_executors", executor),
        ("escrow_settlement_authority", old_authority),
    ):
        session.add(ChainParameter(chain_id=CHAIN, parameter=parameter, value=value, applied_height=OLD_HEIGHT))
        session.add(
            ChainParameterHistory(
                chain_id=CHAIN, parameter=parameter, value=value, proposal_id="genesis", applied_height=OLD_HEIGHT
            )
        )
    session.add(
        Transaction(
            chain_id=CHAIN,
            tx_hash="lock-rehearsal",
            block_height=None,
            sender=derive_ethereum_address("0x" + "88" * 32),
            recipient=old_authority,
            payload={"job_id": JOB_ID, "provider": PROVIDER},
            value=100,
            fee=0,
            nonce=0,
            type="ESCROW_LOCK",
            status="confirmed",
            timestamp=datetime.now(UTC).isoformat(),
        )
    )
    session.commit()
    return executor, old_authority


def _signed_execute(executor: str) -> dict:
    """The exact envelope the tool plans — signed with the executor key."""
    tx = tool._build_tx(executor, CHAIN, 0, "rehearsal-1", "escrow_settlement_authority", NEW_AUTHORITY)
    tx["signature"] = tool.sign_transaction_data(tx, EXECUTOR_KEY)
    return tx


def _old_key_release() -> dict:
    tx = {
        "from": derive_ethereum_address(OLD_AUTHORITY_KEY),
        "to": PROVIDER,
        "amount": 0,
        "fee": DEFAULT_TX_FEE_UNITS,
        "nonce": 0,
        "type": "ESCROW_RELEASE",
        "chain_id": CHAIN,
        "payload": {"job_id": JOB_ID},
    }
    tx["signature"] = tool.sign_transaction_data(tx, OLD_AUTHORITY_KEY)
    return tx


def test_execute_applies_and_reads_back_at_height(session: Session) -> None:
    executor, old_authority = _seed(session)
    assert _escrow_settlement_authority(session, CHAIN, block_height=OLD_HEIGHT) == old_authority

    tx = _signed_execute(executor)
    ok, msg = StateTransition().apply_transaction(
        session, CHAIN, tx, "rehearsal-execute", block_version=11, block_height=EXECUTE_HEIGHT
    )
    assert ok, msg

    # (a) the parameter reads back at the execute's height — and the old
    # value still answers below it.
    assert _chain_parameter_value(session, CHAIN, "escrow_settlement_authority", EXECUTE_HEIGHT) == NEW_AUTHORITY
    assert _chain_parameter_value(session, CHAIN, "escrow_settlement_authority", EXECUTE_HEIGHT - 1) == old_authority
    assert _escrow_settlement_authority(session, CHAIN, block_height=EXECUTE_HEIGHT) == NEW_AUTHORITY


def test_old_authority_release_refused_at_execute_height(session: Session) -> None:
    executor, old_authority = _seed(session)
    ok, msg = StateTransition().apply_transaction(
        session, CHAIN, _signed_execute(executor), "rehearsal-execute", block_version=11, block_height=EXECUTE_HEIGHT
    )
    assert ok, msg

    # (b) at the execute's height the rotation is already in force — the
    # old key's release never reaches the beneficiary.
    ok, msg = StateTransition().validate_transaction(
        session, CHAIN, _old_key_release(), "rehearsal-release", block_version=11, block_height=EXECUTE_HEIGHT
    )
    assert not ok
    assert "must be signed by settlement authority" in msg
    assert old_authority not in msg or NEW_AUTHORITY in msg


def test_old_authority_release_fails_apply_at_next_height(session: Session) -> None:
    """Same refusal one block later, through apply: returns (False, msg), so
    under poa.py:2162-2178 the proposer logs it and continues — a failed
    old-key release cannot stall block assembly."""
    executor, _ = _seed(session)
    ok, msg = StateTransition().apply_transaction(
        session, CHAIN, _signed_execute(executor), "rehearsal-execute", block_version=11, block_height=EXECUTE_HEIGHT
    )
    assert ok, msg

    ok, msg = StateTransition().apply_transaction(
        session, CHAIN, _old_key_release(), "rehearsal-release", block_version=11, block_height=NEXT_HEIGHT
    )
    assert not ok
    assert "must be signed by settlement authority" in msg


def test_chain_seals_executor_lockout_but_tool_refuses(session: Session) -> None:
    """The chain has no lock-out protection: an execute writing a
    governance_executors list that excludes its own signer applies cleanly.
    The tool is the guard — it refuses the same list."""
    executor, _ = _seed(session)
    survivors = derive_ethereum_address("0x" + "99" * 32)
    new_list = f"{survivors},{derive_ethereum_address('0x' + 'aa' * 32)}"  # executor absent

    tx = tool._build_tx(executor, CHAIN, 0, "rehearsal-lockout", "governance_executors", new_list)
    tx["signature"] = tool.sign_transaction_data(tx, EXECUTOR_KEY)
    ok, msg = StateTransition().apply_transaction(
        session, CHAIN, tx, "rehearsal-lockout-tx", block_version=11, block_height=EXECUTE_HEIGHT
    )
    assert ok, f"chain sealed the lock-out: {msg}"
    locked = session.exec(
        select(ChainParameter).where(ChainParameter.chain_id == CHAIN, ChainParameter.parameter == "governance_executors")
    ).first()
    assert locked is not None and executor not in locked.value

    elements = [e.strip() for e in new_list.split(",")]
    assert tool._executor_lockout_reason(executor, elements, proof_address=None) is not None
    assert tool._executor_lockout_reason(executor, elements, proof_address=survivors) is None
