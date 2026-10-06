"""GPU_DEREGISTER (v10): a registrant takes its own GPU out of service.

Until v10 an on-chain GPU registration could not be removed: ``handle_gpu_registration`` only ever sets ``active``, so
the ten test and canary rows stay in the registry for good. v10 adds a signed ``GPU_DEREGISTER`` that only the recorded
registrant may send; it sets ``status = "deactivated"`` and keeps the row, so ``registered_by`` keeps guarding the id
and the registrant can reactivate it by re-registering.

Below v10 the name has no consensus meaning at all: a block carrying it must replay exactly as it did before (a plain
value transfer), because an older build treats it that way and the fleet must agree on every block.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

import pytest
from eth_utils import keccak
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc.crypto.crypto import derive_ethereum_address, sign_transaction_hash
from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import Account
from aitbc_chain.config import ChainSettings, settings
from aitbc_chain.database import chain_metadata
from aitbc_chain.rpc.transactions import _validate_transaction_admission
from aitbc_chain.state.gpu_resources import (
    GPU_STATUS_DEACTIVATED,
    GPUAllocation,
    GPURegistration,
    gpu_allocate_deactivated_error,
    gpu_deregister_error,
)
from aitbc_chain.state.pure_state_transition import SEQUENTIAL_ONLY_TX_TYPES
from aitbc_chain.state.state_transition import StateTransition, get_block_version_for_height
from aitbc_chain.state.v9_policy import V9_METRIC_KNOWN_TX_TYPES

CHAIN = "ait-test"
OWNER_KEY = "0x" + "11" * 32
OTHER_KEY = "0x" + "22" * 32
OWNER = derive_ethereum_address(OWNER_KEY)
OTHER = derive_ethereum_address(OTHER_KEY)
START = 10_000_000


def _sign(private_key: str, data: dict) -> str:
    message = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return sign_transaction_hash("0x" + keccak(message).hex(), private_key)


def _tx(private_key: str, tx_type: str, payload: dict, nonce: int = 0, value: int = 0) -> dict:
    sender = derive_ethereum_address(private_key)
    tx: dict[str, Any] = {
        "from": sender,
        "to": sender,
        "amount": value,
        "value": value,
        "fee": DEFAULT_TX_FEE_UNITS,
        "nonce": nonce,
        "type": tx_type,
        "chain_id": CHAIN,
        "payload": payload,
    }
    signable = {k: v for k, v in tx.items() if k != "signature"}
    signable.pop("value", None)
    tx["signature"] = _sign(private_key, signable)
    return tx


def _register(key: str, gpu_id: str = "gpu-1", nonce: int = 0, price: str = "0.1") -> dict:
    return _tx(
        key,
        "GPU_REGISTER",
        {"gpu_id": gpu_id, "miner_id": "miner-1", "model": "RTX 4090", "memory_gb": 24, "price_per_hour": price},
        nonce,
    )


def _deregister(key: str, gpu_id: str = "gpu-1", nonce: int = 1, **kw: Any) -> dict:
    return _tx(key, "GPU_DEREGISTER", {"gpu_id": gpu_id}, nonce, **kw)


def _allocate(key: str, gpu_id: str = "gpu-1", nonce: int = 0) -> dict:
    return _tx(
        key,
        "GPU_ALLOCATE",
        {"gpu_id": gpu_id, "client_id": "client-1", "duration_hours": 2.0, "total_cost": "0.2"},
        nonce,
    )


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    with Session(engine) as s:
        for addr in (OWNER, OTHER):
            s.add(Account(chain_id=CHAIN, address=addr, balance=START, nonce=0))
        s.commit()
        yield s


@pytest.fixture
def st():
    return StateTransition()


def _apply(st, session, tx, tx_hash, version=10):
    return st.apply_transaction(session, CHAIN, tx, tx_hash, block_version=version)


def _row(session, gpu_id="gpu-1"):
    session.commit()  # the caller of apply_transaction commits; commit flushes and expires, so reads see the DB
    return session.exec(
        select(GPURegistration).where(GPURegistration.chain_id == CHAIN, GPURegistration.gpu_id == gpu_id)
    ).first()


def _account(session, address):
    session.commit()
    return session.get(Account, (CHAIN, address))


@pytest.fixture
def registered(session, st):
    ok, msg = _apply(st, session, _register(OWNER_KEY), "tx_reg")
    assert ok, msg
    return session


# --------------------------------------------------------------------------------------------------------------------
# v10 rules
# --------------------------------------------------------------------------------------------------------------------


def test_registrant_deregisters_and_the_row_stays(registered, st):
    before = _row(registered)
    assert before.status == "active"

    ok, msg = _apply(st, registered, _deregister(OWNER_KEY), "tx_dereg")
    assert ok, msg

    row = _row(registered)
    assert row is not None, "the row must stay: registered_by keeps guarding the id"
    assert row.status == GPU_STATUS_DEACTIVATED == "deactivated"
    assert row.registered_by == OWNER
    assert (row.model, row.memory_gb, str(row.price_per_hour)) == (before.model, before.memory_gb, str(before.price_per_hour))
    owner = _account(registered, OWNER)
    assert owner.balance == START - 2 * DEFAULT_TX_FEE_UNITS  # register fee + deregister fee, no value moved
    assert owner.nonce == 2


def test_foreign_sender_is_refused_and_nothing_changes(registered, st):
    ok, msg = _apply(st, registered, _deregister(OTHER_KEY, nonce=0), "tx_evil")
    assert not ok
    assert "must come from its registrant" in msg
    assert _row(registered).status == "active"
    other = _account(registered, OTHER)
    assert (other.balance, other.nonce) == (START, 0)


def test_unknown_gpu_is_refused(session, st):
    ok, msg = _apply(st, session, _deregister(OWNER_KEY, "no-such-gpu", nonce=0), "tx_x")
    assert not ok
    assert "GPU not found: no-such-gpu" in msg


def test_row_without_a_registrant_fails_closed(session, st):
    session.add(GPURegistration(chain_id=CHAIN, gpu_id="orphan", miner_id="m", model="x", registered_by=""))
    session.commit()
    ok, msg = _apply(st, session, _deregister(OWNER_KEY, "orphan", nonce=0), "tx_o")
    assert not ok
    assert "no registrant on record" in msg
    assert _row(session, "orphan").status == "active"


def test_deregistering_twice_is_refused(registered, st):
    ok, msg = _apply(st, registered, _deregister(OWNER_KEY), "tx_d1")
    assert ok, msg
    ok, msg = _apply(st, registered, _deregister(OWNER_KEY, nonce=2), "tx_d2")
    assert not ok
    assert "already deactivated" in msg


def test_value_is_refused(registered, st):
    ok, msg = _apply(st, registered, _deregister(OWNER_KEY, value=5), "tx_v")
    assert not ok
    assert "value=0" in msg
    assert _row(registered).status == "active"


@pytest.mark.parametrize("payload", [{}, {"gpu_id": ""}, {"gpu_id": 7}, {"gpu_id": None}, {"gpu_id": ["gpu-1"]}])
def test_payload_must_name_a_gpu(registered, st, payload):
    tx = _tx(OWNER_KEY, "GPU_DEREGISTER", payload, nonce=1)
    ok, msg = _apply(st, registered, tx, "tx_p")
    assert not ok
    assert "gpu_id" in msg
    assert _row(registered).status == "active"


def test_non_object_payload_is_refused(registered):
    assert gpu_deregister_error(registered, CHAIN, "gpu-1", OWNER) == "GPU_DEREGISTER payload must be an object"
    assert gpu_deregister_error(registered, CHAIN, None, OWNER) == "GPU_DEREGISTER payload must be an object"


def test_registrant_match_ignores_address_case(registered):
    assert gpu_deregister_error(registered, CHAIN, {"gpu_id": "gpu-1"}, OWNER.lower()) is None
    assert gpu_deregister_error(registered, CHAIN, {"gpu_id": "gpu-1"}, OTHER) is not None


def test_allocations_are_neither_a_precondition_nor_touched(registered, st):
    registered.add(
        GPUAllocation(
            chain_id=CHAIN, allocation_id="alloc-1", gpu_id="gpu-1", client_id="c", status="active", allocated_by=OTHER
        )
    )
    registered.commit()
    ok, msg = _apply(st, registered, _deregister(OWNER_KEY), "tx_dereg")
    assert ok, msg
    registered.commit()
    allocation = registered.exec(select(GPUAllocation).where(GPUAllocation.allocation_id == "alloc-1")).one()
    assert allocation.status == "active"


def test_deactivated_gpu_takes_no_new_allocation_at_v10(registered, st):
    ok, msg = _apply(st, registered, _deregister(OWNER_KEY), "tx_dereg")
    assert ok, msg
    ok, msg = _apply(st, registered, _allocate(OTHER_KEY), "tx_alloc")
    assert not ok
    assert "deactivated" in msg
    assert _account(registered, OTHER).nonce == 0


def test_active_gpu_still_takes_allocations_at_v10(registered, st):
    ok, msg = _apply(st, registered, _allocate(OTHER_KEY), "tx_alloc")
    assert ok, msg


def test_registrant_can_reactivate_by_registering_again(registered, st):
    ok, msg = _apply(st, registered, _deregister(OWNER_KEY), "tx_dereg")
    assert ok, msg
    ok, msg = _apply(st, registered, _register(OWNER_KEY, nonce=2, price="0.5"), "tx_re")
    assert ok, msg
    row = _row(registered)
    assert row.status == "active"
    assert str(row.price_per_hour) == "0.50000000"


def test_nobody_else_can_take_over_a_deactivated_id(registered, st):
    ok, msg = _apply(st, registered, _deregister(OWNER_KEY), "tx_dereg")
    assert ok, msg
    ok, msg = _apply(st, registered, _register(OTHER_KEY, nonce=0, price="999"), "tx_evil")
    assert not ok
    assert "registrant" in msg
    row = _row(registered)
    assert row.status == "deactivated"
    assert row.registered_by == OWNER


# --------------------------------------------------------------------------------------------------------------------
# below v10: the name means nothing and replays as the plain transfer it always was
# --------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("version", [7, 8, 9])
def test_below_v10_it_is_a_plain_transfer_and_the_row_is_untouched(registered, st, version):
    ok, msg = _apply(st, registered, _deregister(OWNER_KEY), "tx_dereg", version=version)
    assert ok, msg
    assert _row(registered).status == "active"
    owner = _account(registered, OWNER)
    assert owner.balance == START - 2 * DEFAULT_TX_FEE_UNITS
    assert owner.nonce == 2


@pytest.mark.parametrize("version", [7, 8, 9])
def test_below_v10_a_foreign_sender_replays_too(registered, st, version):
    """No ownership gate, no value rule: whatever an older build accepted, this build accepts."""
    ok, msg = _apply(st, registered, _deregister(OTHER_KEY, nonce=0), "tx_foreign", version=version)
    assert ok, msg
    assert _row(registered).status == "active"


def test_below_v10_value_moves_like_a_transfer(registered, st):
    tx = _tx(OWNER_KEY, "GPU_DEREGISTER", {"gpu_id": "gpu-1"}, nonce=1, value=0)
    tx["to"] = OTHER
    tx["amount"] = tx["value"] = 1000
    tx.pop("signature")
    signable = dict(tx.items())
    signable.pop("value", None)
    tx["signature"] = _sign(OWNER_KEY, signable)
    ok, msg = _apply(st, registered, tx, "tx_t", version=9)
    assert ok, msg
    assert _account(registered, OTHER).balance == START + 1000
    assert _row(registered).status == "active"


def test_allocation_on_a_deactivated_row_is_accepted_below_v10(registered, st):
    """The v10 allocation rule must not reach back: a v9 block that allocates such a row replays."""
    row = _row(registered)
    row.status = GPU_STATUS_DEACTIVATED
    registered.add(row)
    registered.commit()
    ok, msg = _apply(st, registered, _allocate(OTHER_KEY), "tx_alloc", version=9)
    assert ok, msg


# --------------------------------------------------------------------------------------------------------------------
# activation height and registration in the shared sets
# --------------------------------------------------------------------------------------------------------------------


def test_v10_height_is_baked_at_32100(monkeypatch):
    """The baked default is consensus: a fresh settings object (no env, no env file) activates v10 at 32100."""
    monkeypatch.delenv("STATE_TRANSITION_V10_HEIGHT", raising=False)
    assert ChainSettings(_env_file=None).state_transition_v10_height == 32_100
    monkeypatch.setattr(settings, "state_transition_v10_height", 32_100)
    assert get_block_version_for_height(32_099) == 9
    assert get_block_version_for_height(32_100) == 10


def test_v10_env_still_overrides_the_baked_default(monkeypatch):
    """STATE_TRANSITION_V10_HEIGHT still wins over the baked default for a process that sets it."""
    monkeypatch.setenv("STATE_TRANSITION_V10_HEIGHT", "40000")
    assert ChainSettings(_env_file=None).state_transition_v10_height == 40_000


def test_v10_activates_at_its_height(monkeypatch):
    monkeypatch.setattr(settings, "state_transition_v10_height", 40_000)
    # Pin v11/v12 off so the v10-era assertions keep their literals regardless
    # of which later heights are baked into config.py.
    monkeypatch.setattr(settings, "state_transition_v11_height", None)
    monkeypatch.setattr(settings, "state_transition_v12_height", None)
    assert get_block_version_for_height(39_999) == 9
    assert get_block_version_for_height(40_000) == 10
    assert get_block_version_for_height(40_001) == 10


def test_the_type_runs_the_sequential_path_and_has_its_own_metric_series():
    assert "GPU_DEREGISTER" in SEQUENTIAL_ONLY_TX_TYPES
    assert "GPU_DEREGISTER" in V9_METRIC_KNOWN_TX_TYPES


# --------------------------------------------------------------------------------------------------------------------
# mempool admission refuses what apply would
# --------------------------------------------------------------------------------------------------------------------


@pytest.fixture
def door(session, monkeypatch):
    @contextmanager
    def _scope():
        yield session

    monkeypatch.setattr("aitbc_chain.rpc.transactions.session_scope", _scope)
    monkeypatch.setattr("aitbc_chain.rpc.utils.get_supported_chains", lambda: [CHAIN])
    monkeypatch.setattr(settings, "state_transition_v10_height", 1)

    def submit(sender: str, gpu_id: str = "gpu-1", nonce: int = 0, **overrides: Any) -> None:
        tx: dict[str, Any] = {
            "from": sender,
            "to": sender,
            "amount": 0,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": nonce,
            "type": "GPU_DEREGISTER",
            "chain_id": CHAIN,
            "payload": {"gpu_id": gpu_id},
        }
        tx.update(overrides)
        _validate_transaction_admission(tx, None)

    return submit


def test_admission_refuses_the_type_before_v10(door, registered, monkeypatch):
    monkeypatch.setattr(settings, "state_transition_v10_height", None)
    with pytest.raises(ValueError, match="not active on this chain yet"):
        door(OWNER, nonce=1)


def test_admission_admits_the_registrant(door, registered):
    door(OWNER, nonce=1)


def test_admission_refuses_a_foreign_sender(door, registered):
    with pytest.raises(ValueError, match="must come from its registrant"):
        door(OTHER)


def test_admission_refuses_an_unknown_gpu(door, registered):
    with pytest.raises(ValueError, match="GPU not found"):
        door(OWNER, gpu_id="no-such-gpu", nonce=1)


def test_admission_refuses_a_repeat(door, registered, st):
    ok, msg = _apply(st, registered, _deregister(OWNER_KEY), "tx_dereg")
    assert ok, msg
    with pytest.raises(ValueError, match="already deactivated"):
        door(OWNER, nonce=2)


def test_admission_and_apply_give_the_same_verdict(door, session, st):
    """The two doors share gpu_deregister_error; this fails if either ever grows a private check."""
    ok, msg = _apply(st, session, _register(OWNER_KEY), "tx_reg")
    assert ok, msg
    cases = [
        (OWNER_KEY, "gpu-1", 1, True),
        (OTHER_KEY, "gpu-1", 0, False),
        (OWNER_KEY, "missing", 1, False),
    ]
    for key, gpu_id, nonce, expect in cases:
        sender = derive_ethereum_address(key)
        try:
            door(sender, gpu_id=gpu_id, nonce=nonce)
            admitted = True
        except ValueError:
            admitted = False
        valid, _ = st.validate_transaction(
            session, CHAIN, _deregister(key, gpu_id, nonce), f"probe-{key[-4:]}-{gpu_id}", block_version=10
        )
        assert admitted == valid == expect, (key, gpu_id)


# --------------------------------------------------------------------------------------------------------------------
# GPU_ALLOCATE: the deactivated-row door
# --------------------------------------------------------------------------------------------------------------------


@pytest.fixture
def door_allocate(session, monkeypatch):
    @contextmanager
    def _scope():
        yield session

    monkeypatch.setattr("aitbc_chain.rpc.transactions.session_scope", _scope)
    monkeypatch.setattr("aitbc_chain.rpc.utils.get_supported_chains", lambda: [CHAIN])
    monkeypatch.setattr(settings, "state_transition_v10_height", 1)

    def submit(sender: str, gpu_id: str = "gpu-1", nonce: int = 0, **overrides: Any) -> None:
        tx: dict[str, Any] = {
            "from": sender,
            "to": sender,
            "amount": 0,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": nonce,
            "type": "GPU_ALLOCATE",
            "chain_id": CHAIN,
            "payload": {"gpu_id": gpu_id, "client_id": "client-1", "duration_hours": 2.0, "total_cost": "0.2"},
        }
        tx.update(overrides)
        _validate_transaction_admission(tx, None)

    return submit


def test_allocate_helper_only_reports_the_one_rule(registered):
    assert gpu_allocate_deactivated_error(registered, CHAIN, "gpu-1") is None
    assert gpu_allocate_deactivated_error(registered, CHAIN, None) is None
    assert gpu_allocate_deactivated_error(registered, CHAIN, {}) is None
    assert gpu_allocate_deactivated_error(registered, CHAIN, {"gpu_id": "gpu-1"}) is None
    assert gpu_allocate_deactivated_error(registered, CHAIN, {"gpu_id": "no-such-gpu"}) is None


def test_allocate_helper_reports_the_deactivated_row(registered):
    row = _row(registered)
    row.status = GPU_STATUS_DEACTIVATED
    registered.add(row)
    registered.commit()
    assert (
        gpu_allocate_deactivated_error(registered, CHAIN, {"gpu_id": "gpu-1"})
        == "GPU gpu-1 is deactivated; it takes no new allocations"
    )


def test_allocate_admission_admits_an_active_row(door_allocate, registered):
    door_allocate(OTHER)


def test_allocate_admission_refuses_a_deactivated_row(door_allocate, registered, st):
    ok, msg = _apply(st, registered, _deregister(OWNER_KEY), "tx_dereg")
    assert ok, msg
    with pytest.raises(ValueError, match="is deactivated; it takes no new allocations"):
        door_allocate(OTHER)


def test_allocate_admission_admits_a_deactivated_row_below_v10(door_allocate, registered, st, monkeypatch):
    """Below the activation height the door stays as it was: the type predates v10, unlike GPU_DEREGISTER."""
    ok, msg = _apply(st, registered, _deregister(OWNER_KEY), "tx_dereg")
    assert ok, msg
    monkeypatch.setattr(settings, "state_transition_v10_height", None)
    door_allocate(OTHER)


def test_allocate_admission_admits_an_unknown_row(door_allocate, registered):
    door_allocate(OTHER, gpu_id="no-such-gpu")


def test_allocate_admission_and_apply_give_the_same_verdict(door_allocate, session, registered, st):
    """The two doors share gpu_allocate_deactivated_error; this fails if either ever grows a private check."""
    ok, msg = _apply(st, session, _register(OTHER_KEY, "gpu-9", nonce=0), "tx_reg9")
    assert ok, msg
    ok, msg = _apply(st, session, _deregister(OTHER_KEY, "gpu-9", nonce=1), "tx_dereg9")
    assert ok, msg
    cases = [
        (OTHER_KEY, "gpu-9", 2, False),
        (OTHER_KEY, "gpu-1", 2, True),
        (OTHER_KEY, "missing", 2, True),
    ]
    for key, gpu_id, nonce, expect in cases:
        sender = derive_ethereum_address(key)
        try:
            door_allocate(sender, gpu_id=gpu_id, nonce=nonce)
            admitted = True
        except ValueError:
            admitted = False
        valid, _ = st.validate_transaction(session, CHAIN, _allocate(key, gpu_id, nonce), f"probe-{gpu_id}", block_version=10)
        assert admitted == valid == expect, (key, gpu_id)
