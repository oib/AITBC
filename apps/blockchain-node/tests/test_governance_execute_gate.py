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


def _gov_tx_with_action(key: str, chain_id: str, execution_payload: dict | None) -> dict:
    tx_data = {
        "amount": 0,
        "value": 0,
        "fee": DEFAULT_TX_FEE_UNITS,
        "nonce": 0,
        "type": "GOVERNANCE_EXECUTE",
        "chain_id": chain_id,
        "payload": {"proposal_id": "prop-1"},
    }
    if execution_payload is not None:
        tx_data["payload"]["execution_payload"] = execution_payload
    return _make_tx(key, tx_data)


def test_governance_execute_rejects_set_governance_address(session):
    """The named-but-unimplemented action is refused at validation.

    The apply side logs "not implemented" and continues, so without this gate a
    passed proposal would execute a membership change that never happens.
    """
    chain_id = "ait-test"
    _seed_accounts(session, chain_id)
    tx = _gov_tx_with_action(
        EXECUTOR_KEY,
        chain_id,
        {"action": "set_governance_address", "address": "0x" + "ab" * 20, "operation": "add"},
    )
    st = StateTransition()
    ok, msg = st.apply_transaction(session, chain_id, tx, "tx_gov_sga")
    assert not ok
    assert "set_governance_address" in msg
    assert "not implemented" in msg


def test_governance_execute_rejects_set_governance_address_json_payload(session):
    """The same rejection applies when the payload arrives as a JSON string.

    Signed string-payload txs die earlier at the signature gate (the signed
    form is the dict); this unsigned variant exercises the defensive parse
    branch — unsigned txs skip signature verification entirely.
    """
    chain_id = "ait-test"
    executor_addr = _seed_accounts(session, chain_id)
    tx = {
        "amount": 0,
        "value": 0,
        "fee": DEFAULT_TX_FEE_UNITS,
        "nonce": 0,
        "type": "GOVERNANCE_EXECUTE",
        "chain_id": chain_id,
        "from": executor_addr,
        "to": executor_addr,
        "payload": json.dumps(
            {
                "proposal_id": "prop-1",
                "execution_payload": {"action": "set_governance_address", "address": "0x" + "ab" * 20},
            }
        ),
    }
    st = StateTransition()
    ok, msg = st.apply_transaction(session, chain_id, tx, "tx_gov_sga_json")
    assert not ok
    assert "set_governance_address" in msg


def test_governance_execute_v5_rejected_when_param_unset(session):
    """v5 fails closed: without the allowlist, apply would let any funded
    sender write arbitrary chain parameters."""
    chain_id = "ait-test"
    _seed_accounts(session, chain_id)
    st = StateTransition()
    ok, msg = st.apply_transaction(session, chain_id, _gov_tx(EXECUTOR_KEY, chain_id), "tx_gov_v5_unset", block_version=5)
    assert not ok
    assert "governance_executors" in msg


def test_governance_execute_v5_executor_still_accepted(session):
    chain_id = "ait-test"
    executor_addr = _seed_accounts(session, chain_id)
    session.add(ChainParameter(chain_id=chain_id, parameter="governance_executors", value=executor_addr))
    session.commit()

    st = StateTransition()
    ok, msg = st.apply_transaction(session, chain_id, _gov_tx(EXECUTOR_KEY, chain_id), "tx_gov_v5_ok", block_version=5)
    assert ok, msg


def test_governance_execute_v5_rejects_non_executor(session):
    chain_id = "ait-test"
    executor_addr = _seed_accounts(session, chain_id)
    session.add(ChainParameter(chain_id=chain_id, parameter="governance_executors", value=executor_addr))
    session.commit()

    st = StateTransition()
    ok, msg = st.apply_transaction(session, chain_id, _gov_tx(STRANGER_KEY, chain_id), "tx_gov_v5_bad", block_version=5)
    assert not ok
    assert "not an authorized executor" in msg


def test_governance_execute_missing_execution_payload_stays_lenient(session):
    """Replay compat: sealed GOVERNANCE_EXECUTEs without execution_payload must still apply.

    ait-hub blocks 8153/8165 contain exactly this shape — a rejection here would
    break historical import on every node that re-validates.
    """
    chain_id = "ait-test"
    _seed_accounts(session, chain_id)
    tx = _gov_tx_with_action(EXECUTOR_KEY, chain_id, None)
    st = StateTransition()
    ok, msg = st.apply_transaction(session, chain_id, tx, "tx_gov_noop")
    assert ok, msg


# ---------------------------------------------------------------------------
# v12 — authority-parameter value checks (A1–A6, design note
# TOPOLOGY/2026-10-06-authority-parameter-validation-design.md §2). The gate is
# a ``block_version >= 12`` branch in validate_transaction; below it every value
# stays lenient exactly as sealed history requires.
# ---------------------------------------------------------------------------

HUB = "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B"  # 0x02B8…4c5B — hub validator, executor 9819–30551
FE04 = "0x04fE87ac0E6a9bcbe7554eb29ea86312BF817cCC"  # executor from 30551
D9CC = "0xD9CC189c19eF96F6f536E0ea92BEc218d829c694"  # executor from 37259
BOND_AUTH = "0xab0797Ae8cfF09B313c71cAb2f894B342b6e1d76"
BRIDGE_AUTH = "0x2b0F2399680E2f3BdbBBC06bDc8D9a6b301D2DDe"
SETTLE_AUTH = "0x03DF9Ed3788E5BA3991e6788036f9D171f027716"
FEE_RECIP = "0x716a56468DD4A11A91116920F9E8892BbDD7b1B8"

# Every GOVERNANCE_EXECUTE sealed on ait-hub through 2026-10-06, verbatim from
# the chain.db ``transaction`` rows / ``chain_parameter_history`` (height, fee,
# parameter, value). The two oldest carries no execution_payload at all — the
# forward-compat case.
SEALED_EXECUTES = [
    (8153, 360000, None, None),
    (8165, 360000, None, None),
    (9819, 0, "governance_executors", HUB),
    (22193, 0, "escrow_settlement_authority", HUB),
    (22218, 0, "bond_slash_authority", BOND_AUTH),
    (22469, 0, "bridge_release_authority", HUB),
    (30551, 360000, "governance_executors", f"{HUB},{FE04}"),
    (30552, 360000, "governance_executors", FE04),
    (30563, 360000, "bridge_release_authority", BRIDGE_AUTH),
    (30564, 360000, "escrow_settlement_authority", SETTLE_AUTH),
    (35411, 360000, "escrow_fee_recipient", FEE_RECIP),
    (37259, 360000, "governance_executors", f"{FE04},{D9CC}"),
]


def _gov_param_tx(key: str, chain_id: str, execution_payload: dict | None, *, fee: int = DEFAULT_TX_FEE_UNITS) -> dict:
    tx_data = {
        "amount": 0,
        "value": 0,
        "fee": fee,
        "nonce": 0,
        "type": "GOVERNANCE_EXECUTE",
        "chain_id": chain_id,
        "payload": {"proposal_id": "prop-1"},
    }
    if execution_payload is not None:
        tx_data["payload"]["execution_payload"] = execution_payload
    return _make_tx(key, tx_data)


def _seed_v12_gate(session: Session, chain_id: str) -> str:
    """Executor allowlist = the fixture executor, plus funded rows for every
    member the sealed executor lists name (the A5 floor needs a funded member)."""
    executor_addr = _seed_accounts(session, chain_id)
    session.add(ChainParameter(chain_id=chain_id, parameter="governance_executors", value=executor_addr))
    for addr in (HUB, FE04, D9CC):
        session.add(Account(chain_id=chain_id, address=addr, balance=1_000_000, nonce=0))
    session.commit()
    return executor_addr


@pytest.mark.parametrize("block_height,fee,parameter,value", SEALED_EXECUTES)
def test_v12_accepts_every_sealed_authority_execute(session, block_height, fee, parameter, value):
    """Replay table: all twelve sealed GOVERNANCE_EXECUTEs — the ones that name
    an authority parameter — pass A1–A6 under v12 with their verbatim values."""
    chain_id = "ait-test"
    _seed_v12_gate(session, chain_id)
    ep = None if parameter is None else {"action": "parameter_change", "parameter": parameter, "value": value}
    tx = _gov_param_tx(EXECUTOR_KEY, chain_id, ep, fee=fee)
    st = StateTransition()
    ok, msg = st.validate_transaction(session, chain_id, tx, f"tx_v12_replay_{block_height}", block_version=12)
    assert ok, f"sealed execute at {block_height} rejected: {msg}"


@pytest.mark.parametrize(
    "parameter,value,why",
    [
        ("governance_executors", None, "must not be empty"),  # A1 null
        ("governance_executors", "", "must not be empty"),  # A1 empty
        ("escrow_settlement_authority", "   ", "must not be empty"),  # A1 whitespace
        ("governance_executors", ",,", "at least one address"),  # A1 commas only
        ("bond_slash_authority", "0x" + "gg" * 20, "0x + 40-hex"),  # A2 non-hex, 42 chars
        ("escrow_fee_recipient", "0x" + "ab" * 21, "0x + 40-hex"),  # A2 too long
        ("bridge_release_authority", "0x" + "00" * 20, "zero address"),  # A3
        ("escrow_fee_recipient", "0x" + "ab" * 20 + ",0x" + "cd" * 20, "exactly one address"),  # A4
        ("governance_executors", "0x" + "de" * 20 + ",0x" + "ad" * 20, "executor minimum"),  # A5
        ("governance_executors", "0x" + "ab" * 20 + ",0x" + "AB" * 20, "repeats"),  # A6 case-insensitive dup
    ],
)
def test_v12_rejects_bad_authority_values(session, parameter, value, why):
    """Each A1–A6 violation refuses at v12 with the parameter-named message."""
    chain_id = "ait-test"
    _seed_v12_gate(session, chain_id)
    tx = _gov_param_tx(EXECUTOR_KEY, chain_id, {"action": "parameter_change", "parameter": parameter, "value": value})
    st = StateTransition()
    ok, msg = st.validate_transaction(session, chain_id, tx, f"tx_v12_bad_{parameter}_{str(value)[:8]}", block_version=12)
    assert not ok, "v12 must refuse this authority-parameter value"
    assert f"GOVERNANCE_EXECUTE rejected: {parameter} value" in msg
    assert why in msg


def test_v11_still_accepts_garbage_authority_values(session):
    """Boundary: below v12 the same value the v12 test rejects stays lenient —
    sealed history's rule. Pin the exact garbage A2 would refuse."""
    chain_id = "ait-test"
    _seed_v12_gate(session, chain_id)
    tx = _gov_param_tx(
        EXECUTOR_KEY, chain_id, {"action": "parameter_change", "parameter": "bond_slash_authority", "value": "0x" + "gg" * 20}
    )
    st = StateTransition()
    ok, msg = st.validate_transaction(session, chain_id, tx, "tx_v11_lenient", block_version=11)
    assert ok, msg


def test_v12_executor_list_accepts_one_funded_member(session):
    """A5 is the anti-freeze floor: a list with at least one member holding the
    executor minimum passes — an unfunded member is dead weight, not a freeze."""
    chain_id = "ait-test"
    executor_addr = _seed_v12_gate(session, chain_id)
    unfunded = "0x" + "de" * 20
    tx = _gov_param_tx(
        EXECUTOR_KEY,
        chain_id,
        {"action": "parameter_change", "parameter": "governance_executors", "value": f"{executor_addr},{unfunded}"},
    )
    st = StateTransition()
    ok, msg = st.validate_transaction(session, chain_id, tx, "tx_v12_mixed_funding", block_version=12)
    assert ok, msg


def test_v12_other_parameters_and_actions_stay_lenient(session):
    """Forward-compat escape hatch: non-authority parameters and unknown
    actions are outside the gate — same behaviour as before v12."""
    chain_id = "ait-test"
    _seed_v12_gate(session, chain_id)
    st = StateTransition()
    tx = _gov_param_tx(EXECUTOR_KEY, chain_id, {"action": "parameter_change", "parameter": "some_param", "value": ""})
    ok, msg = st.validate_transaction(session, chain_id, tx, "tx_v12_other_param", block_version=12)
    assert ok, msg
    tx = _gov_param_tx(
        EXECUTOR_KEY,
        chain_id,
        {"action": "not_a_real_action", "parameter": "governance_executors", "value": ""},
    )
    ok, msg = st.validate_transaction(session, chain_id, tx, "tx_v12_other_action", block_version=12)
    assert ok, msg


def test_v12_absent_action_treated_as_parameter_change(session):
    """Apply defaults a missing action to ``parameter_change`` (:1867) — the
    validate trigger must match, so a five-name parameter with no action key
    is checked rather than waved through."""
    chain_id = "ait-test"
    _seed_v12_gate(session, chain_id)
    tx = _gov_param_tx(EXECUTOR_KEY, chain_id, {"parameter": "governance_executors", "value": ""})
    st = StateTransition()
    ok, msg = st.validate_transaction(session, chain_id, tx, "tx_v12_no_action", block_version=12)
    assert not ok
    assert "must not be empty" in msg


def test_v12_env_still_overrides_the_baked_default(monkeypatch):
    """STATE_TRANSITION_V12_HEIGHT wins over the baked 37500 for a process
    that sets it — the height-derived ladder resolves the env value. The
    baked default itself is pinned in test_escrow_fee_sweep.py next to the
    v11 pair."""
    from aitbc_chain.config import ChainSettings, settings
    from aitbc_chain.state.state_transition import get_block_version_for_height

    monkeypatch.setenv("STATE_TRANSITION_V12_HEIGHT", "40000")
    assert ChainSettings(_env_file=None).state_transition_v12_height == 40_000
    monkeypatch.setattr(settings, "state_transition_v12_height", 40_000)
    assert get_block_version_for_height(39_999) == 11
    assert get_block_version_for_height(40_000) == 12
