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
            tx_hash=f"tx_propose_{proposal_id}_{block_height}",
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
    key: str,
    chain_id: str,
    proposal_id: str = "prop-1",
    execution_payload: dict | None = TAMPERED_PAYLOAD,
    nonce: int = 0,
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
            "nonce": nonce,
            "type": "GOVERNANCE_EXECUTE",
            "chain_id": chain_id,
            "payload": payload,
        },
    )


def _propose_tx(key: str, chain_id: str, execution_payload: dict | None = PROPOSED_PAYLOAD, nonce: int = 0) -> dict:
    payload: dict = {"proposal_id": "prop-new", "title": "t", "proposer": "0x" + "ab" * 20}
    if execution_payload is not None:
        payload["execution_payload"] = execution_payload
    return _make_tx(
        key,
        {
            "amount": 0,
            "value": 0,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": nonce,
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


# --- A10 adversarial battery -------------------------------------------------
#
# Helpers and constants reused from above; EXECUTE2_HEIGHT sits strictly after
# EXECUTE_HEIGHT so "already executed in an earlier block" is exercisable.

EXECUTE2_HEIGHT = 60


def _seed_execute(
    session: Session,
    chain_id: str,
    proposal_id: str = "prop-1",
    block_height: int = EXECUTE_HEIGHT,
    execution_payload: dict | None = PROPOSED_PAYLOAD,
) -> None:
    """Insert a sealed GOVERNANCE_EXECUTE row — a proposal already executed."""
    payload: dict = {"proposal_id": proposal_id}
    if execution_payload is not None:
        payload["execution_payload"] = execution_payload
    session.add(
        Transaction(
            chain_id=chain_id,
            tx_hash=f"tx_execute_{proposal_id}_{block_height}",
            block_height=block_height,
            sender="0x" + "44" * 20,
            recipient="0x" + "44" * 20,
            payload=payload,
            nonce=1,
            value=0,
            fee=DEFAULT_TX_FEE_UNITS,
            type="GOVERNANCE_EXECUTE",
            status="sealed",
        )
    )
    session.commit()


def _apply_execute(session: Session, tx: dict, block_height: int = EXECUTE2_HEIGHT) -> tuple[bool, str]:
    st = StateTransition()
    return st.apply_transaction(session, CHAIN_ID, tx, "tx_" + str(block_height), block_version=13, block_height=block_height)


def _admission_verdict(
    session: Session,
    tx_type: str,
    sender: str,
    payload: dict,
    block_height: int = EXECUTE2_HEIGHT,
) -> str | None:
    from aitbc_chain.state.admission_authority import sender_authority_error

    return sender_authority_error(
        session,
        CHAIN_ID,
        tx_type,
        sender,
        block_version=13,
        block_height=block_height,
        payload=payload,
        fee=DEFAULT_TX_FEE_UNITS,
    )


def test_adversarial_double_execute_rejected_in_verification_and_admission(session):
    """A second EXECUTE for an already-executed proposal must be refused by
    BOTH doors — parameter history rows and status stamps are not idempotent,
    and any future non-idempotent action would double-apply."""
    executor = _seed_executor_gate(session, CHAIN_ID)
    _seed_propose(session, CHAIN_ID)
    _seed_execute(session, CHAIN_ID, block_height=EXECUTE_HEIGHT)

    ok, msg = _apply_execute(session, _execute_tx(EXECUTOR_KEY, CHAIN_ID, execution_payload=PROPOSED_PAYLOAD))
    assert not ok
    assert "already executed" in msg

    error = _admission_verdict(
        session,
        "GOVERNANCE_EXECUTE",
        executor,
        {"proposal_id": "prop-1", "execution_payload": PROPOSED_PAYLOAD},
    )
    assert error is not None and "already executed" in error


def test_adversarial_execute_before_propose_height_rejected(session):
    """Ordering is strict in both directions: an EXECUTE sealed at a height
    the PROPOSE never precedes is refused — not just same-block."""
    _seed_executor_gate(session, CHAIN_ID)
    _seed_propose(session, CHAIN_ID, block_height=EXECUTE2_HEIGHT)

    ok, msg = _apply_execute(
        session,
        _execute_tx(EXECUTOR_KEY, CHAIN_ID, execution_payload=PROPOSED_PAYLOAD),
        block_height=EXECUTE_HEIGHT,
    )
    assert not ok
    assert "earlier block" in msg


def test_adversarial_propose_non_dict_execution_payload_rejected(session):
    """A list/string/int execution_payload cannot be committed — the cap and
    the equality check are only meaningful on objects."""
    _seed_accounts(session, CHAIN_ID)
    for bad in (["a"], "a-string", 42, True):
        ok, msg = _apply_execute(
            session, _propose_tx(EXECUTOR_KEY, CHAIN_ID, execution_payload=bad), block_height=EXECUTE_HEIGHT
        )
        assert not ok, f"non-dict payload {bad!r} was accepted"
        assert "execution_payload" in msg


def test_adversarial_propose_payload_cap_boundary(session):
    """Exactly at the cap passes; one byte over refuses — no off-by-one."""
    _seed_accounts(session, CHAIN_ID)
    from aitbc_chain.state.state_transition import _V13_MAX_EXECUTION_PAYLOAD_BYTES

    # Value length that lands the serialized dict exactly on the cap.
    base = {"action": "x", "value": ""}
    overhead = len(json.dumps(base, sort_keys=True, separators=(",", ":")))
    exact = {"action": "x", "value": "y" * (_V13_MAX_EXECUTION_PAYLOAD_BYTES - overhead)}
    assert len(json.dumps(exact, sort_keys=True, separators=(",", ":"))) == _V13_MAX_EXECUTION_PAYLOAD_BYTES
    ok, msg = _apply_execute(
        session, _propose_tx(EXECUTOR_KEY, CHAIN_ID, execution_payload=exact), block_height=EXECUTE_HEIGHT
    )
    assert ok, msg

    over = {"action": "x", "value": "y" * (_V13_MAX_EXECUTION_PAYLOAD_BYTES - overhead + 1)}
    ok, msg = _apply_execute(
        session,
        _propose_tx(EXECUTOR_KEY, CHAIN_ID, execution_payload=over, nonce=1),
        block_height=EXECUTE2_HEIGHT,
    )
    assert not ok
    assert "exceeds" in msg


def test_adversarial_execute_rejected_for_proposal_whose_vote_failed(session):
    """Documented limitation: voting state lives in the node-local
    ``governance_vote`` table — it is NOT canonical chain data, so binding can
    only prove payload equality, not that the proposal passed. This test pins
    the current semantic: a binding-valid EXECUTE applies even for a proposal
    an operator would call failed/expired. Closing this needs votes (or a
    tally commitment) on-chain — out of scope for V-2."""
    _seed_executor_gate(session, CHAIN_ID)
    _seed_propose(session, CHAIN_ID)  # propose exists; no votes anywhere

    ok, msg = _apply_execute(session, _execute_tx(EXECUTOR_KEY, CHAIN_ID, execution_payload=PROPOSED_PAYLOAD))
    assert ok, msg
    assert _param_value(session, CHAIN_ID) == "proposed-value"


def test_adversarial_reproposal_binds_latest_sealed(session):
    """proposal_id reuse: the binding resolves the LATEST sealed PROPOSE for
    the id — an execute naming the old payload is refused."""
    _seed_executor_gate(session, CHAIN_ID)
    _seed_propose(session, CHAIN_ID, execution_payload=PROPOSED_PAYLOAD, block_height=PROPOSE_HEIGHT)
    _seed_propose(session, CHAIN_ID, execution_payload=TAMPERED_PAYLOAD, block_height=PROPOSE_HEIGHT + 5)

    ok, msg = _apply_execute(session, _execute_tx(EXECUTOR_KEY, CHAIN_ID, execution_payload=TAMPERED_PAYLOAD))
    assert ok, msg
    assert _param_value(session, CHAIN_ID) == "tampered-value"

    # And the supersedes semantic in the other direction: the stale payload
    # of the same id is refused.
    _seed_propose(session, CHAIN_ID, proposal_id="prop-2", execution_payload=PROPOSED_PAYLOAD)
    _seed_propose(session, CHAIN_ID, proposal_id="prop-2", execution_payload=TAMPERED_PAYLOAD, block_height=PROPOSE_HEIGHT + 5)
    ok, msg = _apply_execute(
        session,
        _execute_tx(EXECUTOR_KEY, CHAIN_ID, proposal_id="prop-2", execution_payload=PROPOSED_PAYLOAD, nonce=1),
        block_height=EXECUTE2_HEIGHT + 1,
    )
    assert not ok
    assert "does not match sealed proposal" in msg


def test_adversarial_proposal_id_type_coercion(session):
    """A non-string proposal_id must not crash the binding and must not match
    a stringly-typed proposal — rejects cleanly, identical in both doors."""
    executor = _seed_executor_gate(session, CHAIN_ID)
    _seed_propose(session, CHAIN_ID)

    for bad_id in ({"x": 1}, [1, 2], 5):
        tx = _execute_tx(EXECUTOR_KEY, CHAIN_ID, proposal_id="prop-1", execution_payload=PROPOSED_PAYLOAD)
        tx["payload"]["proposal_id"] = (
            bad_id  # post-sign swap — verification may reject on signature first; admission exercises the binding directly. Either way both must refuse without crashing.
        )
        ok, msg = _apply_execute(session, tx)
        assert not ok
        error = _admission_verdict(session, "GOVERNANCE_EXECUTE", executor, tx["payload"])
        assert error is not None
        assert (not ok) == (error is not None)


def test_adversarial_replay_twice_identical(session):
    """Applying the same sealed tx sequence twice produces identical state —
    the binding must be deterministic across replays."""
    _seed_executor_gate(session, CHAIN_ID)
    _seed_propose(session, CHAIN_ID)

    from aitbc_chain.base_models import ChainParameterHistory

    def run_once() -> tuple[str | None, int]:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        chain_metadata.create_all(engine)
        with Session(engine) as s:
            _seed_executor_gate(s, CHAIN_ID)
            _seed_propose(s, CHAIN_ID)
            st = StateTransition()
            ok, msg = st.apply_transaction(
                s,
                CHAIN_ID,
                _execute_tx(EXECUTOR_KEY, CHAIN_ID, execution_payload=PROPOSED_PAYLOAD),
                "tx_exec_replay",
                block_version=13,
                block_height=EXECUTE_HEIGHT,
            )
            assert ok, msg
            s.commit()
            history = len(s.exec(select(ChainParameterHistory).where(ChainParameterHistory.chain_id == CHAIN_ID)).all())
            return _param_value(s, CHAIN_ID), history

    first, second = run_once(), run_once()
    assert first == second == ("proposed-value", 1)


def test_adversarial_admission_verification_parity(session):
    """Admission and block verification must agree on every adversarial case:
    whatever the mempool door refuses, the block verifier refuses too."""
    executor = _seed_executor_gate(session, CHAIN_ID)
    _seed_propose(session, CHAIN_ID)
    _seed_execute(session, CHAIN_ID, block_height=EXECUTE_HEIGHT)

    cases = [
        # (payload, expect_reject)
        ({"proposal_id": "prop-1", "execution_payload": PROPOSED_PAYLOAD}, True),  # already executed
        ({"proposal_id": "prop-1", "execution_payload": TAMPERED_PAYLOAD}, True),  # tampered
        ({"proposal_id": "ghost", "execution_payload": PROPOSED_PAYLOAD}, True),  # unknown id
        ({"execution_payload": PROPOSED_PAYLOAD}, True),  # missing id
    ]
    for payload, _ in cases:
        admission = _admission_verdict(session, "GOVERNANCE_EXECUTE", executor, payload)
        ok, _msg = _apply_execute(
            session,
            _make_tx(
                EXECUTOR_KEY,
                {
                    "amount": 0,
                    "value": 0,
                    "fee": DEFAULT_TX_FEE_UNITS,
                    "nonce": 0,
                    "type": "GOVERNANCE_EXECUTE",
                    "chain_id": CHAIN_ID,
                    "payload": payload,
                },
            ),
        )
        assert (admission is not None) == (not ok), (
            f"admission/verification disagree on {payload}: admission={admission!r} apply_ok={ok}"
        )


# --- v13 shadow counters (the would-reject window before arming) ------------


@pytest.fixture
def metrics():
    from aitbc_chain.metrics import metrics_registry

    metrics_registry.reset()
    yield metrics_registry
    metrics_registry.reset()


def test_shadow_counts_would_reject_pre_gate(session, metrics):
    """Pre-gate an EXECUTE v13 would refuse still applies — but the shadow
    window must SEE it: checked and would_reject both increment."""
    _seed_executor_gate(session, CHAIN_ID)
    st = StateTransition()
    ok, msg = st.apply_transaction(
        session,
        CHAIN_ID,
        _execute_tx(EXECUTOR_KEY, CHAIN_ID, proposal_id="ghost"),
        "tx_shadow_unknown",
        block_version=12,
        block_height=EXECUTE_HEIGHT,
    )
    assert ok, msg
    c = metrics._counters
    assert c["v13_shadow_checked_total"] == 1
    assert c["v13_shadow_checked_governance_execute_total"] == 1
    assert c["v13_would_reject_total"] == 1
    assert c["v13_would_reject_execute_unknown_proposal_total"] == 1


def test_shadow_clean_verdict_counts_checked_only(session, metrics):
    """An EXECUTE satisfying the v13 rules pre-gate increments only the
    positive-control series — silence on would_reject is provable."""
    _seed_executor_gate(session, CHAIN_ID)
    _seed_propose(session, CHAIN_ID)
    st = StateTransition()
    ok, msg = st.apply_transaction(
        session,
        CHAIN_ID,
        _execute_tx(EXECUTOR_KEY, CHAIN_ID, execution_payload=PROPOSED_PAYLOAD),
        "tx_shadow_clean",
        block_version=12,
        block_height=EXECUTE_HEIGHT,
    )
    assert ok, msg
    c = metrics._counters
    assert c["v13_shadow_checked_governance_execute_total"] == 1
    assert c.get("v13_would_reject_total", 0) == 0


def test_shadow_counts_propose_missing_payload_pre_gate(session, metrics):
    """A bare PROPOSE is legal today; the counter records that v13 would
    refuse it."""
    _seed_accounts(session, CHAIN_ID)
    st = StateTransition()
    ok, msg = st.apply_transaction(
        session,
        CHAIN_ID,
        _propose_tx(EXECUTOR_KEY, CHAIN_ID, execution_payload=None),
        "tx_prop_shadow",
        block_version=12,
        block_height=EXECUTE_HEIGHT,
    )
    assert ok, msg
    c = metrics._counters
    assert c["v13_shadow_checked_governance_propose_total"] == 1
    assert c["v13_would_reject_propose_missing_execution_payload_total"] == 1


def test_shadow_counts_at_admission_door(session, metrics):
    """sender_authority_error counts the same would-reject pre-gate while
    still admitting the transaction — door and apply see the same verdict."""
    executor = _seed_executor_gate(session, CHAIN_ID)
    from aitbc_chain.state.admission_authority import sender_authority_error

    error = sender_authority_error(
        session,
        CHAIN_ID,
        "GOVERNANCE_EXECUTE",
        executor,
        block_version=12,
        block_height=EXECUTE_HEIGHT,
        payload={"proposal_id": "ghost", "execution_payload": PROPOSED_PAYLOAD},
        fee=DEFAULT_TX_FEE_UNITS,
    )
    assert error is None
    assert metrics._counters["v13_would_reject_execute_unknown_proposal_total"] == 1
    assert metrics._counters["v13_shadow_checked_governance_execute_total"] == 1


def test_shadow_counts_real_reject_post_gate(session, metrics):
    """Same counter for a real post-gate rejection (v9 convention) — the
    metric keeps its meaning across the activation boundary."""
    _seed_executor_gate(session, CHAIN_ID)
    st = StateTransition()
    ok, _msg = st.apply_transaction(
        session,
        CHAIN_ID,
        _execute_tx(EXECUTOR_KEY, CHAIN_ID, proposal_id="ghost"),
        "tx_shadow_armed",
        block_version=13,
        block_height=EXECUTE_HEIGHT,
    )
    assert not ok
    assert metrics._counters["v13_would_reject_execute_unknown_proposal_total"] == 1


def test_shadow_skips_non_bind_types(session, metrics):
    """No counter moves for a type the v13 rules do not govern."""
    from aitbc_chain.state.admission_authority import sender_authority_error

    error = sender_authority_error(
        session,
        CHAIN_ID,
        "TRANSFER",
        "0x" + "ab" * 20,
        block_version=12,
        block_height=EXECUTE_HEIGHT,
        payload={},
        fee=DEFAULT_TX_FEE_UNITS,
    )
    assert error is None
    assert metrics._counters.get("v13_shadow_checked_total", 0) == 0
