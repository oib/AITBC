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
    Block,
    ChainParameter,
    ChainParameterHistory,
    GovernanceProposal,
    Transaction,
)
from aitbc_chain.database import init_db, session_scope
from aitbc_chain.config import settings
from aitbc_chain.state.state_transition import (
    StateTransition,
    _bond_slash_authority,
    _chain_parameter_value,
    _escrow_settlement_authority,
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


def _execute_tx(sender: str, parameter: str, value: str, tx_hash: str, proposal_id: str = "p-1", nonce: int = 0) -> dict:
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
    session.add(ChainParameter(chain_id=chain_id, parameter="governance_executors", value=_EXECUTOR, applied_height=None))
    session.flush()
    assert _governance_executors(session, chain_id, 0) == {_EXECUTOR}
    assert _governance_executors(session, chain_id, 999999) == {_EXECUTOR}
    assert _chain_parameter_value(session, chain_id, "governance_executors") == _EXECUTOR


def test_genesis_parameters_apply_from_height_zero(session, chain_id):
    """Genesis-seeded parameters take effect at height 0 and are recorded in
    history, so height-0 blocks resolve them like any later change."""
    session.add(ChainParameter(chain_id=chain_id, parameter="governance_executors", value=_EXECUTOR, applied_height=0))
    session.flush()
    assert _governance_executors(session, chain_id, 0) == {_EXECUTOR}


def test_no_height_context_returns_current(session, chain_id):
    session.add(ChainParameter(chain_id=chain_id, parameter="governance_executors", value=_EXECUTOR, applied_height=100))
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


def test_init_db_rebuilds_history_from_sealed_executes(chain_id):
    """The full version list is already in chain history: sealed
    GOVERNANCE_EXECUTE txs carry ``execution_payload.parameter_change``, so
    init_db rebuilds every past value — including mid-history values the
    current row no longer holds. This is what makes a parameter set at 9819
    resolvable as unset at 9818 and set at 9819 on every node."""
    init_db(chain_id)
    with session_scope(chain_id) as session:
        for tx_hash, height, parameter in (
            ("0xe9819", 9819, "governance_executors"),
            ("0xe22193", 22193, "escrow_settlement_authority"),
        ):
            session.add(
                Transaction(
                    chain_id=chain_id,
                    tx_hash=tx_hash,
                    block_height=height,
                    sender=_OTHER,
                    recipient=_OTHER,
                    type="GOVERNANCE_EXECUTE",
                    payload={
                        "proposal_id": f"prop_{height}",
                        "execution_payload": {
                            "action": "parameter_change",
                            "parameter": parameter,
                            "value": _EXECUTOR,
                        },
                    },
                    value=0,
                    fee=0,
                    nonce=0,
                    status="confirmed",
                )
            )
        # Pre-tracking current rows: proposal_id unset, applied_height unknown.
        session.add(ChainParameter(chain_id=chain_id, parameter="governance_executors", value=_EXECUTOR))
        session.add(ChainParameter(chain_id=chain_id, parameter="escrow_settlement_authority", value=_EXECUTOR))
        session.commit()

    init_db(chain_id)
    with session_scope(chain_id) as session:
        gov = session.exec(
            select(ChainParameter).where(
                ChainParameter.chain_id == chain_id,
                ChainParameter.parameter == "governance_executors",
            )
        ).first()
        esc = session.exec(
            select(ChainParameter).where(
                ChainParameter.chain_id == chain_id,
                ChainParameter.parameter == "escrow_settlement_authority",
            )
        ).first()
        assert gov.applied_height == 9819
        assert esc.applied_height == 22193
        assert _governance_executors(session, chain_id, 9818) is None
        assert _governance_executors(session, chain_id, 9819) == {_EXECUTOR}
        history = _history(session, chain_id, "governance_executors")
        assert [(h.value, h.applied_height) for h in history] == [(_EXECUTOR, 9819)]


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


def test_same_block_double_change_last_write_wins(session, chain_id):
    """Two executes in one block changing one parameter: history records the
    LAST value — the one ``chain_parameter`` ends with — so blocks at and
    above that height resolve it identically under live apply and rebuild."""
    _account(session, chain_id, _OTHER)
    st = StateTransition()
    for tx_hash, value, nonce in (("0xexec500a", _OTHER, 0), ("0xexec500b", _EXECUTOR, 1)):
        ok, err = st.apply_transaction(
            session,
            chain_id,
            _execute_tx(_OTHER, "bond_slash_authority", value, tx_hash, proposal_id=f"p-{tx_hash}", nonce=nonce),
            tx_hash,
            block_version=4,
            block_height=500,
        )
        assert ok, err
    assert _chain_parameter_value(session, chain_id, "bond_slash_authority", 500) == _EXECUTOR
    assert _chain_parameter_value(session, chain_id, "bond_slash_authority", 600) == _EXECUTOR
    history = _history(session, chain_id, "bond_slash_authority")
    assert [(h.value, h.applied_height) for h in history] == [(_EXECUTOR, 500)]


def test_rebuild_orders_same_height_executes_by_insertion(chain_id):
    """Same-height execute pairs replay in insertion (apply) order: the row
    id orders within a block identically on every node — live apply and
    bulk import both write the block's transactions in block order — so
    last-write-wins rebuild matches what live apply recorded."""
    init_db(chain_id)
    with session_scope(chain_id) as session:
        for tx_hash, value in (("0xexec700a", _OTHER), ("0xexec700b", _EXECUTOR)):
            session.add(
                Transaction(
                    chain_id=chain_id,
                    tx_hash=tx_hash,
                    block_height=700,
                    sender=_OTHER,
                    recipient=_OTHER,
                    type="GOVERNANCE_EXECUTE",
                    payload={
                        "proposal_id": f"p-{tx_hash}",
                        "execution_payload": {
                            "action": "parameter_change",
                            "parameter": "bond_slash_authority",
                            "value": value,
                        },
                    },
                    value=0,
                    fee=0,
                    nonce=0,
                    status="confirmed",
                )
            )
        session.commit()

    init_db(chain_id)
    with session_scope(chain_id) as session:
        history = _history(session, chain_id, "bond_slash_authority")
        assert [(h.value, h.applied_height) for h in history] == [(_EXECUTOR, 700)]
        row = session.exec(
            select(ChainParameter).where(
                ChainParameter.chain_id == chain_id,
                ChainParameter.parameter == "bond_slash_authority",
            )
        ).first()
        assert row.value == _EXECUTOR


def test_env_fallback_only_when_never_set(session, chain_id, monkeypatch):
    """Once the chain records an authority parameter at any height, heights
    before the first record resolve as provably unset — a per-node env value
    must not resurrect an authority the chain did not have yet."""
    from aitbc.crypto.signature_recovery import canonical_address

    monkeypatch.setenv("BOND_SLASH_AUTHORITY_ADDRESS", _OTHER)
    monkeypatch.setenv("ESCROW_RELEASE_ADDRESS", _OTHER)
    monkeypatch.setattr(settings, "escrow_settlement_authority", "")
    monkeypatch.setattr(settings, "bridge_release_authority", "")

    session.add(ChainParameter(chain_id=chain_id, parameter="bond_slash_authority", value=_EXECUTOR, applied_height=100))
    session.add(
        ChainParameterHistory(
            chain_id=chain_id,
            parameter="bond_slash_authority",
            value=_EXECUTOR,
            proposal_id="p-1",
            applied_height=100,
        )
    )
    session.flush()

    # Before the recorded height: provably unset — env must not leak in.
    assert _bond_slash_authority(session, chain_id, 50) is None
    # At/after it: the on-chain value wins.
    assert _bond_slash_authority(session, chain_id, 150) == canonical_address(_EXECUTOR)
    # No-height callers still resolve the current row.
    assert _bond_slash_authority(session, chain_id) == canonical_address(_EXECUTOR)


def test_env_never_decides_a_known_height(session, chain_id, monkeypatch):
    """For a known block height, chain history alone decides — env is never
    consulted. That makes validation a pure function of history at-or-below
    the height: a node mid-sync (records not yet applied) and a fully-synced
    node re-checking the same historical block resolve identically."""
    monkeypatch.setenv("BOND_SLASH_AUTHORITY_ADDRESS", _OTHER)
    monkeypatch.setenv("ESCROW_RELEASE_ADDRESS", _OTHER)
    monkeypatch.setattr(settings, "escrow_settlement_authority", "")
    monkeypatch.setattr(settings, "bridge_release_authority", "")

    # Node mid-sync at height 50: no records yet — env must not fill the gap.
    assert _bond_slash_authority(session, chain_id, 50) is None
    assert _escrow_settlement_authority(session, chain_id, 50) is None

    # Fully-synced node re-checking the same block after a later record
    # landed: the answer for height 50 must not change.
    session.add(ChainParameter(chain_id=chain_id, parameter="bond_slash_authority", value=_EXECUTOR, applied_height=100))
    session.add(
        ChainParameterHistory(
            chain_id=chain_id, parameter="bond_slash_authority", value=_EXECUTOR, proposal_id="p-1", applied_height=100
        )
    )
    session.flush()
    assert _bond_slash_authority(session, chain_id, 50) is None
    assert _bond_slash_authority(session, chain_id, 150) is not None


def test_env_is_bootstrap_for_height_less_callers(session, chain_id, monkeypatch):
    """``block_height=None`` callers (mempool pre-checks, non-consensus
    introspection) keep the env bootstrap for chains that never set the
    parameter — no-height callers ask for the value in force now, which is
    what env describes on a never-set chain."""
    from aitbc.crypto.signature_recovery import canonical_address

    monkeypatch.setenv("BOND_SLASH_AUTHORITY_ADDRESS", _OTHER)
    monkeypatch.setenv("ESCROW_RELEASE_ADDRESS", _OTHER)
    monkeypatch.setattr(settings, "escrow_settlement_authority", "")
    monkeypatch.setattr(settings, "bridge_release_authority", "")

    assert _bond_slash_authority(session, chain_id) == canonical_address(_OTHER)
    assert _escrow_settlement_authority(session, chain_id) == canonical_address(_OTHER)


def test_import_chain_restores_shipped_parameter_rows(chain_id, monkeypatch):
    """import-chain wipes parameter tables, but restores them from the
    export's ``chain_parameters``/``parameter_history`` sections.

    This is the regression for the genesis/peer-sync loss: parameters seeded
    by ``_seed_chain_parameters`` at genesis and rows received via peer state
    sync are not regenerable by replaying sealed executes, so the import must
    write the exporter's rows back verbatim — otherwise a chain whose genesis
    defined ``bond_slash_authority`` would silently lose it and the v5+ gates
    would fail closed (or stay lenient pre-gate where they should not).
    """
    import aitbc_chain.database as database
    from aitbc_chain.rpc.sync import _import_chain_data

    init_db(chain_id)
    # ``_import_chain_data`` opens the default-chain session — point it at
    # this test's chain DB.
    monkeypatch.setattr(database, "_default_chain_id", chain_id)
    # Old lineage: a stale parameter and a stale block that must not survive.
    with session_scope(chain_id) as session:
        session.add(ChainParameter(chain_id=chain_id, parameter="stale_param", value="old-lineage", applied_height=7))
        session.add(
            Block(
                chain_id=chain_id,
                height=3,
                hash="0xstale",
                parent_hash="0x0",
                proposer="0xp",
                timestamp=datetime.now(UTC),
            )
        )
        session.commit()

    # Genesis-seeded rows ship verbatim in the export — no executes needed.
    import_data = {
        "chain_id": chain_id,
        "blocks": [{"chain_id": chain_id, "height": 0, "hash": "0xgenesis", "parent_hash": "0x0", "proposer": "0xp"}],
        "accounts": [],
        "transactions": [],
        "chain_parameters": [
            {"parameter": "bond_slash_authority", "value": _EXECUTOR, "proposal_id": None, "applied_height": 0}
        ],
        "parameter_history": [
            {"parameter": "bond_slash_authority", "value": _EXECUTOR, "proposal_id": None, "applied_height": 0}
        ],
    }
    result = _import_chain_data(import_data)
    assert result["success"] is True

    with session_scope(chain_id) as session:
        # The genesis-seeded parameter resolves from height 0 onward.
        assert _chain_parameter_value(session, chain_id, "bond_slash_authority", 5) == _EXECUTOR
        assert _bond_slash_authority(session, chain_id, 5) is not None
        # Old-lineage rows did not bleed into the imported chain.
        assert _chain_parameter_value(session, chain_id, "stale_param", 100) is None
        assert session.exec(select(Block).where(Block.chain_id == chain_id, Block.hash == "0xstale")).first() is None


def test_import_chain_rebuilds_from_executes_without_param_sections(chain_id, monkeypatch):
    """Old-format exports (no parameter sections) still restore
    execute-derived parameters via the replay rebuild — and get the warning
    that genesis/peer-sync rows are not recoverable from such a payload."""
    import aitbc_chain.database as database
    from aitbc_chain.rpc.sync import _import_chain_data

    init_db(chain_id)
    monkeypatch.setattr(database, "_default_chain_id", chain_id)

    import_data = {
        "chain_id": chain_id,
        "blocks": [
            {"chain_id": chain_id, "height": 0, "hash": "0xg", "parent_hash": "0x0", "proposer": "0xp"},
            {"chain_id": chain_id, "height": 1, "hash": "0x1", "parent_hash": "0xg", "proposer": "0xp"},
        ],
        "accounts": [{"chain_id": chain_id, "address": _OTHER, "balance": 0, "nonce": 0}],
        "transactions": [
            {
                "id": 1,
                "tx_hash": "0xexec1",
                "block_height": 1,
                "sender": _OTHER,
                "recipient": _OTHER,
                "payload": {
                    "type": "GOVERNANCE_EXECUTE",
                    "proposal_id": "p-1",
                    "execution_payload": {
                        "action": "parameter_change",
                        "parameter": "bond_slash_authority",
                        "value": _EXECUTOR,
                    },
                },
                "value": 0,
                "fee": 0,
                "nonce": 0,
                "status": "sealed",
            }
        ],
    }
    result = _import_chain_data(import_data)
    assert result["success"] is True

    with session_scope(chain_id) as session:
        assert _chain_parameter_value(session, chain_id, "bond_slash_authority", 50) == _EXECUTOR


def test_bond_slash_authority_fails_closed_below_first_record(monkeypatch):
    """No pin: heights below the first ``bond_slash_authority`` record resolve
    ``None`` on every chain — a chain that never sealed the parameter has no
    determinable authority, and a restored lineage cannot inherit one.

    Fresh database, no env vars: every node resolves identically, so a
    restored lineage carrying a pre-record slash cannot diverge between a
    mid-sync node and a synced node re-checking the same block.
    """
    from aitbc.crypto.signature_recovery import canonical_address

    chain_id = "ait-testchain.local"
    init_db(chain_id)
    monkeypatch.delenv("BOND_SLASH_AUTHORITY_ADDRESS", raising=False)

    with session_scope(chain_id) as session:
        # No records at all: fail closed below any record, on every chain.
        assert _bond_slash_authority(session, chain_id, 5) is None
        assert _bond_slash_authority(session, "some-other-chain", 5) is None

        # A later record still wins at and above its own height.
        session.add(ChainParameter(chain_id=chain_id, parameter="bond_slash_authority", value=_OTHER, applied_height=100))
        session.add(
            ChainParameterHistory(
                chain_id=chain_id, parameter="bond_slash_authority", value=_OTHER, proposal_id="p-1", applied_height=100
            )
        )
        session.flush()
        assert _bond_slash_authority(session, chain_id, 50) is None
        assert _bond_slash_authority(session, chain_id, 150) == canonical_address(_OTHER)


def test_bond_slash_below_first_record_fails_authority_gate(monkeypatch):
    """With no ``bond_slash_authority`` record at or below the slash height the
    authority resolves ``None`` — the gate fails closed for every sender,
    identically on every node, so a pre-record slash in a restored lineage
    cannot diverge mid-sync vs synced."""
    from aitbc_chain.base_models import _to_ait_address
    from aitbc_chain.state.state_transition import _BOND_BURN_ADDRESS

    chain_id = "ait-testchain.local"
    init_db(chain_id)
    monkeypatch.delenv("BOND_SLASH_AUTHORITY_ADDRESS", raising=False)

    with session_scope(chain_id) as session:
        st = StateTransition()
        slash_tx = {
            "type": "BOND_SLASH",
            "from": _EXECUTOR,
            "to": _BOND_BURN_ADDRESS,
            "value": 0,
            "fee": 0,
            "nonce": 0,
            "payload": {"bond_id": "bond-1", "provider": _OTHER, "amount": 5},
        }
        reason = st._handle_bond_transaction(
            session,
            chain_id,
            slash_tx,
            "0xslash1",
            "BOND_SLASH",
            _to_ait_address(_EXECUTOR),
            _to_ait_address(_BOND_BURN_ADDRESS),
            0,
            50,
        )
        assert reason == "no slash authority configured (chain parameter or BOND_SLASH_AUTHORITY_ADDRESS)"

        slash_tx["from"] = _OTHER
        reason2 = st._handle_bond_transaction(
            session,
            chain_id,
            slash_tx,
            "0xslash2",
            "BOND_SLASH",
            _to_ait_address(_OTHER),
            _to_ait_address(_BOND_BURN_ADDRESS),
            0,
            50,
        )
        assert reason2 == "no slash authority configured (chain parameter or BOND_SLASH_AUTHORITY_ADDRESS)"


def test_explicit_clear_is_unset(monkeypatch):
    """A governance write of ``""`` to ``bond_slash_authority`` is a deliberate
    clear: heights at-or-after it resolve *unset* — and with no historical
    fallback, below the first record is unset too. Every node still
    agrees; an explicit clear is indistinguishable from never-set below its
    own height only in the fail-closed direction."""
    chain_id = "ait-testchain.local"
    init_db(chain_id)
    monkeypatch.delenv("BOND_SLASH_AUTHORITY_ADDRESS", raising=False)

    with session_scope(chain_id) as session:
        session.add(
            ChainParameterHistory(
                chain_id=chain_id,
                parameter="bond_slash_authority",
                value="",
                proposal_id="p-clear",
                applied_height=200,
            )
        )
        session.add(ChainParameter(chain_id=chain_id, parameter="bond_slash_authority", value="", applied_height=200))
        session.flush()

        # Below the clear: no earlier record exists — fail closed.
        assert _bond_slash_authority(session, chain_id, 50) is None
        # At/after the clear: explicitly unset.
        assert _bond_slash_authority(session, chain_id, 250) is None
        # Height-less callers see the current (cleared) row too.
        assert _bond_slash_authority(session, chain_id) is None


def test_parameter_change_null_value_is_explicit_clear(monkeypatch):
    """``value: null`` in a parameter_change records "" (a deliberate clear),
    not the literal "None" — on the pinned chain, heights at/after the clear
    resolve unset instead of resurrecting the legacy authority, and "None"
    never reaches canonical_address as a nonsense address."""
    chain_id = "ait-testchain.local"
    init_db(chain_id)
    monkeypatch.delenv("BOND_SLASH_AUTHORITY_ADDRESS", raising=False)

    with session_scope(chain_id) as session:
        _account(session, chain_id, _OTHER)
        st = StateTransition()
        ok, err = st.apply_transaction(
            session,
            chain_id,
            _execute_tx(_OTHER, "bond_slash_authority", None, "0xclear1"),
            "0xclear1",
            block_version=4,
            block_height=50,
        )
        assert ok, err

        row = session.exec(
            select(ChainParameter).where(
                ChainParameter.chain_id == chain_id,
                ChainParameter.parameter == "bond_slash_authority",
            )
        ).first()
        assert row is not None
        assert row.value == ""

        # At/after the clear: explicitly unset — not "None" as a literal.
        assert _bond_slash_authority(session, chain_id, 60) is None
        # Below it: no earlier record — fail closed.
        assert _bond_slash_authority(session, chain_id, 40) is None


def test_parameter_change_missing_value_key_rejected_at_validation():
    """A parameter_change whose execution_payload has no ``value`` key is
    malformed — rejected at payload validation (proposer-side) rather than
    sealed and stored as the string "None". ``value: null`` stays valid."""
    from aitbc_chain.consensus.poa import _validate_governance_payload

    errors = _validate_governance_payload(
        "GOVERNANCE_EXECUTE",
        {
            "proposal_id": "p-1",
            "executor": _EXECUTOR,
            "execution_payload": {"action": "parameter_change", "parameter": "bond_slash_authority"},
        },
    )
    assert any("value" in e for e in errors)

    ok_errors = _validate_governance_payload(
        "GOVERNANCE_EXECUTE",
        {
            "proposal_id": "p-1",
            "executor": _EXECUTOR,
            "execution_payload": {
                "action": "parameter_change",
                "parameter": "bond_slash_authority",
                "value": None,
            },
        },
    )
    assert not any("'value'" in e for e in ok_errors)
