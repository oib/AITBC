"""Height-aware chain-parameter resolution: the replay regression.

Chain parameters are consensus state, and the gates that read them —
``governance_executors`` at every block version, the settlement/slash/bridge
authorities from their gate heights — must see the value in force at the
block being validated, not the latest value. Before ``applied_height`` and
``chain_parameter_history`` existed, a parameter set at height H wrongly
governed blocks below H: a node replaying history would reject a sealed
GOVERNANCE_EXECUTE whose sender predates the executor list, and could
diverge from a node that held different env at startup. These tests pin the
semantics: a parameter takes effect from the height its GOVERNANCE_EXECUTE
sealed at, history rows preserve superseded values, rows with no recorded
height keep the pre-tracking status quo, and genesis values apply from
height 0.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlmodel import select

from aitbc_chain.base_models import (
    Account,
    ChainParameter,
    ChainParameterHistory,
    GovernanceProposal,
    Transaction,
)
from aitbc_chain.database import init_db, session_scope
from aitbc_chain.state.state_transition import (
    StateTransition,
    _chain_parameter_value,
    _governance_executors,
)

# Checksummed — resolver outputs go through _to_ait_address.
_EXECUTOR = "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B"
_OTHER = "0xab0797Ae8cfF09B313c71cAb2f894B342b6e1d76"


@pytest.fixture
def chain_id(request):
    """A fresh chain DB per test — parameter rows are consensus state and
    must not leak between scenarios."""
    return f"param-height-{request.node.name[:40]}"


@pytest.fixture
def session(chain_id):
    init_db(chain_id)
    with session_scope(chain_id) as s:
        yield s


def _account(session, chain_id: str, address: str) -> None:
    session.add(Account(chain_id=chain_id, address=address, balance=0, nonce=0))
    session.flush()


def _execute_tx(
    sender: str, parameter: str, value: str, tx_hash: str, proposal_id: str = "p-1", nonce: int = 0
) -> dict:
    return {
        "type": "GOVERNANCE_EXECUTE",
        "from": sender,
        "to": sender,
        "value": 0,
        "fee": 0,
        "nonce": nonce,
        "payload": {
            "proposal_id": proposal_id,
            "execution_payload": {"action": "parameter_change", "parameter": parameter, "value": value},
        },
    }


def _history(session, chain_id: str, parameter: str) -> list[ChainParameterHistory]:
    return session.exec(
        select(ChainParameterHistory)
        .where(
            ChainParameterHistory.chain_id == chain_id,
            ChainParameterHistory.parameter == parameter,
        )
        .order_by(ChainParameterHistory.applied_height)
    ).all()


def test_apply_records_height_and_history(session, chain_id):
    _account(session, chain_id, _OTHER)
    st = StateTransition()
    # Unset executors fail closed from v5, so the first parameter_change in a
    # chain's life applies under the pre-v5 lenient rule — as real chains did.
    ok, err = st.apply_transaction(
        session,
        chain_id,
        _execute_tx(_OTHER, "governance_executors", _EXECUTOR, "0xexec100"),
        "0xexec100",
        block_version=4,
        block_height=100,
    )
    assert ok, err
    row = session.exec(
        select(ChainParameter).where(
            ChainParameter.chain_id == chain_id,
            ChainParameter.parameter == "governance_executors",
        )
    ).first()
    assert row is not None
    assert row.applied_height == 100
    history = _history(session, chain_id, "governance_executors")
    assert [(h.value, h.applied_height) for h in history] == [(_EXECUTOR, 100)]


def test_parameter_not_retroactive(session, chain_id):
    """A parameter set at height 100 is unset for blocks below 100 and in
    force at and above it — replaying an earlier block can never fail
    because the value was set later in the chain."""
    _account(session, chain_id, _OTHER)
    st = StateTransition()
    ok, err = st.apply_transaction(
        session,
        chain_id,
        _execute_tx(_OTHER, "governance_executors", _EXECUTOR, "0xexec100"),
        "0xexec100",
        block_version=4,
        block_height=100,
    )
    assert ok, err

    assert _chain_parameter_value(session, chain_id, "governance_executors", 99) is None
    assert _governance_executors(session, chain_id, 99) is None
    for height in (100, 101, 1000):
        assert _governance_executors(session, chain_id, height) == {_EXECUTOR}


def test_late_change_keeps_earlier_value(session, chain_id):
    """Two parameter changes: each replayed height resolves the value that
    was in force when its block sealed."""
    _account(session, chain_id, _OTHER)
    _account(session, chain_id, _EXECUTOR)
    st = StateTransition()
    ok, err = st.apply_transaction(
        session,
        chain_id,
        _execute_tx(_OTHER, "governance_executors", _EXECUTOR, "0xexec100"),
        "0xexec100",
        block_version=4,
        block_height=100,
    )
    assert ok, err
    # The second change must come from the executor — the gate is live by
    # height 200.
    ok, err = st.apply_transaction(
        session,
        chain_id,
        _execute_tx(_EXECUTOR, "governance_executors", _OTHER, "0xexec200", proposal_id="p-2"),
        "0xexec200",
        block_version=5,
        block_height=200,
    )
    assert ok, err

    assert _governance_executors(session, chain_id, 99) is None
    assert _governance_executors(session, chain_id, 150) == {_EXECUTOR}
    assert _governance_executors(session, chain_id, 250) == {_OTHER}
    # The current row holds the latest value.
    assert _governance_executors(session, chain_id) == {_OTHER}
    history = _history(session, chain_id, "governance_executors")
    assert [(h.value, h.applied_height) for h in history] == [(_EXECUTOR, 100), (_OTHER, 200)]


def test_replay_governance_execute_from_before_executors_set(session, chain_id):
    """The core regression: seed executors at height 100, then validate a
    GOVERNANCE_EXECUTE as it stood at height 50 — before the parameter
    existed. The pre-gate lenient rule applies (block_version < 5), so the
    replayed transaction succeeds instead of failing on a sender list that
    did not exist when its block sealed."""
    _account(session, chain_id, _OTHER)
    _account(session, chain_id, _EXECUTOR)
    st = StateTransition()

    # Seed the executor list at height 100 (as an applied parameter_change).
    ok, err = st.apply_transaction(
        session,
        chain_id,
        _execute_tx(_OTHER, "governance_executors", _EXECUTOR, "0xexec100"),
        "0xexec100",
        block_version=4,
        block_height=100,
    )
    assert ok, err

    # A GOVERNANCE_EXECUTE replayed at height 50 — before the list existed.
    old_tx = _execute_tx(_OTHER, "bond_slash_authority", _OTHER, "0xold50", proposal_id="p-old", nonce=1)
    ok, err = st.validate_transaction(session, chain_id, old_tx, "0xold50", block_version=4, block_height=50)
    assert ok, err

    # The same sender at height 150 — after the list took effect — is gated.
    new_tx = _execute_tx(_OTHER, "bond_slash_authority", _OTHER, "0xnew150", proposal_id="p-new", nonce=1)
    ok, err = st.validate_transaction(session, chain_id, new_tx, "0xnew150", block_version=5, block_height=150)
    assert not ok
    assert "executor" in err.lower()

    # The listed executor passes at the same height.
    ok, err = st.validate_transaction(
        session,
        chain_id,
        _execute_tx(_EXECUTOR, "bond_slash_authority", _OTHER, "0xok150", proposal_id="p-ok"),
        "0xok150",
        block_version=5,
        block_height=150,
    )
    assert ok, err


def test_null_height_row_applies_at_all_heights(session, chain_id):
    """Rows with no recorded height — written before tracking, or
    operator-seeded outside the apply path — keep the pre-tracking status
    quo: the value applies at every height. This is the documented safe
    semantic for rows whose true set-height is unknowable."""
    session.add(
        ChainParameter(chain_id=chain_id, parameter="governance_executors", value=_EXECUTOR, applied_height=None)
    )
    session.flush()
    assert _governance_executors(session, chain_id, 0) == {_EXECUTOR}
    assert _governance_executors(session, chain_id, 999999) == {_EXECUTOR}
    assert _chain_parameter_value(session, chain_id, "governance_executors") == _EXECUTOR


def test_genesis_parameters_apply_from_height_zero(session, chain_id):
    """Genesis-seeded parameters take effect at height 0 and are recorded in
    history, so height-0 blocks resolve them like any later change."""
    session.add(
        ChainParameter(chain_id=chain_id, parameter="governance_executors", value=_EXECUTOR, applied_height=0)
    )
    session.flush()
    assert _governance_executors(session, chain_id, 0) == {_EXECUTOR}


def test_no_height_context_returns_current(session, chain_id):
    session.add(
        ChainParameter(chain_id=chain_id, parameter="governance_executors", value=_EXECUTOR, applied_height=100)
    )
    session.flush()
    # block_height=None callers (mempool pre-checks) see the current value.
    assert _governance_executors(session, chain_id) == {_EXECUTOR}


def test_init_db_backfills_height_from_chain_history(chain_id):
    """init_db resolves applied_height for pre-tracking rows from sealed
    history: parameter → proposal → execution tx → its block height. Every
    node replaying the same chain derives the same height — unlike the
    parameter value, the height is already in chain history."""
    init_db(chain_id)
    with session_scope(chain_id) as session:
        session.add(
            Transaction(
                chain_id=chain_id,
                tx_hash="0xexec8153",
                block_height=8153,
                sender=_OTHER,
                recipient=_OTHER,
                type="GOVERNANCE_EXECUTE",
                value=0,
                fee=0,
                nonce=0,
                status="confirmed",
            )
        )
        session.add(
            GovernanceProposal(
                chain_id=chain_id,
                proposal_id="gap58",
                proposer_address=_OTHER,
                title="governance executors",
                description="set the executor list",
                status="executed",
                execution_tx_hash="0xexec8153",
                voting_starts=datetime(2026, 9, 20, tzinfo=UTC),
                voting_ends=datetime(2026, 9, 21, tzinfo=UTC),
            )
        )
        # A pre-tracking row: proposal_id set, applied_height unknown.
        session.add(
            ChainParameter(
                chain_id=chain_id,
                parameter="governance_executors",
                value=_EXECUTOR,
                proposal_id="gap58",
            )
        )
        session.commit()

    # init_db again — the backfill pass resolves the height.
    init_db(chain_id)
    with session_scope(chain_id) as session:
        row = session.exec(
            select(ChainParameter).where(
                ChainParameter.chain_id == chain_id,
                ChainParameter.parameter == "governance_executors",
            )
        ).first()
        assert row.applied_height == 8153
        history = _history(session, chain_id, "governance_executors")
        assert [(h.value, h.applied_height) for h in history] == [(_EXECUTOR, 8153)]
        # Below the real height the parameter resolves unset — replay safety.
        assert _governance_executors(session, chain_id, 8152) is None
        assert _governance_executors(session, chain_id, 8153) == {_EXECUTOR}


def test_backfill_leaves_unresolvable_rows_null(chain_id):
    """Rows with no resolvable proposal keep NULL applied_height — the
    status-quo semantic — rather than inventing a height."""
    init_db(chain_id)
    with session_scope(chain_id) as session:
        session.add(
            ChainParameter(
                chain_id=chain_id,
                parameter="governance_executors",
                value=_EXECUTOR,
                proposal_id="bootstrap-seed-2026-09-25",
            )
        )
        session.commit()
    init_db(chain_id)
    with session_scope(chain_id) as session:
        row = session.exec(
            select(ChainParameter).where(
                ChainParameter.chain_id == chain_id,
                ChainParameter.parameter == "governance_executors",
            )
        ).first()
        assert row.applied_height is None
