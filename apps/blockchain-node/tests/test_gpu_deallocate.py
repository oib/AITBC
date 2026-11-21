"""GPU_DEALLOCATE (v28, #2403): the allocator or client completes an allocation.

Until v28 nothing could transition a ``gpu_allocation`` row out of ``active``:
``handle_gpu_allocation`` only ever inserts ``status="active"`` rows, so
``active_allocations`` counted open rows forever and ``GPU_DEREGISTER`` left a
GPU permanently spoken-for. v28 adds a signed, value-zero ``GPU_DEALLOCATE``
naming ``payload.allocation_id``; the allocator (``allocated_by``) or the
recorded ``client_id`` may send it, and apply marks the row ``completed``.

Below v28 the name has no consensus meaning: a block carrying it must replay
exactly as it did before (a plain value transfer), because an older build
treats it that way and the fleet must agree on every block.
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
    GPUAllocation,
    gpu_deallocate_error,
)
from aitbc_chain.state.pure_state_transition import SEQUENTIAL_ONLY_TX_TYPES
from aitbc_chain.state.state_transition import StateTransition, get_block_version_for_height
from aitbc_chain.state.v9_policy import V9_METRIC_KNOWN_TX_TYPES

CHAIN = "ait-test"
OWNER_KEY = "0x" + "11" * 32
ALLOCATOR_KEY = "0x" + "22" * 32
FOREIGN_KEY = "0x" + "33" * 32
OWNER = derive_ethereum_address(OWNER_KEY)
ALLOCATOR = derive_ethereum_address(ALLOCATOR_KEY)
FOREIGN = derive_ethereum_address(FOREIGN_KEY)
START = 10_000_000
ALLOCATION_ID = "alloc_test1"


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


def _register(key: str, gpu_id: str = "gpu-1", nonce: int = 0) -> dict:
    return _tx(
        key,
        "GPU_REGISTER",
        {"gpu_id": gpu_id, "miner_id": "miner-1", "model": "RTX 4090", "memory_gb": 24, "price_per_hour": "0.1"},
        nonce,
    )


def _allocate(key: str, gpu_id: str = "gpu-1", nonce: int = 0, allocation_id: str = ALLOCATION_ID) -> dict:
    return _tx(
        key,
        "GPU_ALLOCATE",
        {
            "gpu_id": gpu_id,
            "client_id": OWNER,
            "duration_hours": 2.0,
            "total_cost": "0.2",
            "allocation_id": allocation_id,
        },
        nonce,
    )


def _deallocate(key: str, allocation_id: str = ALLOCATION_ID, nonce: int = 0, **kw: Any) -> dict:
    return _tx(key, "GPU_DEALLOCATE", {"allocation_id": allocation_id}, nonce, **kw)


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    with Session(engine) as s:
        for addr in (OWNER, ALLOCATOR, FOREIGN):
            s.add(Account(chain_id=CHAIN, address=addr, balance=START, nonce=0))
        s.commit()
        yield s


@pytest.fixture
def st():
    return StateTransition()


def _apply(st, session, tx, tx_hash, version=28):
    return st.apply_transaction(session, CHAIN, tx, tx_hash, block_version=version)


def _alloc_row(session, allocation_id=ALLOCATION_ID):
    session.commit()
    return session.exec(
        select(GPUAllocation).where(GPUAllocation.chain_id == CHAIN, GPUAllocation.allocation_id == allocation_id)
    ).first()


@pytest.fixture
def allocated(session, st):
    """gpu-1 registered by OWNER, allocated by ALLOCATOR to client OWNER at v28."""
    ok, msg = _apply(st, session, _register(OWNER_KEY), "tx_reg")
    assert ok, msg
    ok, msg = _apply(st, session, _allocate(ALLOCATOR_KEY), "tx_alloc")
    assert ok, msg
    return session


# --------------------------------------------------------------------------------------------------------------------
# v28 rules
# --------------------------------------------------------------------------------------------------------------------


def test_allocator_completes_the_allocation(allocated, st):
    ok, msg = _apply(st, allocated, _deallocate(ALLOCATOR_KEY, nonce=1), "tx_dealloc")
    assert ok, msg
    row = _alloc_row(allocated)
    assert row.status == "completed"
    assert row.completed_at is not None
    allocator = allocated.get(Account, (CHAIN, ALLOCATOR))
    assert allocator.nonce == 2  # allocate + deallocate


def test_recorded_client_may_also_complete(allocated, st):
    """client_id is OWNER here — the client signs its own release."""
    ok, msg = _apply(st, allocated, _deallocate(OWNER_KEY, nonce=1), "tx_dealloc")
    assert ok, msg
    assert _alloc_row(allocated).status == "completed"


def test_foreign_sender_is_refused_and_nothing_changes(allocated, st):
    ok, msg = _apply(st, allocated, _deallocate(FOREIGN_KEY, nonce=0), "tx_evil")
    assert not ok
    assert "must come from its allocator" in msg
    assert _alloc_row(allocated).status == "active"
    foreign = allocated.get(Account, (CHAIN, FOREIGN))
    assert (foreign.balance, foreign.nonce) == (START, 0)


def test_unknown_allocation_is_refused(session, st):
    ok, msg = _apply(st, session, _register(OWNER_KEY), "tx_reg")
    assert ok, msg
    ok, msg = _apply(st, session, _deallocate(OWNER_KEY, "alloc_missing", nonce=1), "tx_x")
    assert not ok
    assert "GPU allocation not found: alloc_missing" in msg


def test_completing_twice_is_refused(allocated, st):
    ok, msg = _apply(st, allocated, _deallocate(ALLOCATOR_KEY, nonce=1), "tx_d1")
    assert ok, msg
    ok, msg = _apply(st, allocated, _deallocate(ALLOCATOR_KEY, nonce=2), "tx_d2")
    assert not ok
    assert "already completed" in msg


def test_value_is_refused(allocated, st):
    ok, msg = _apply(st, allocated, _deallocate(ALLOCATOR_KEY, nonce=1, value=5), "tx_v")
    assert not ok
    assert "value=0" in msg
    assert _alloc_row(allocated).status == "active"


@pytest.mark.parametrize("payload", [{}, {"allocation_id": ""}, {"allocation_id": 7}, {"allocation_id": None}])
def test_payload_must_name_an_allocation(allocated, st, payload):
    tx = _tx(ALLOCATOR_KEY, "GPU_DEALLOCATE", payload, nonce=1)
    ok, msg = _apply(st, allocated, tx, "tx_p")
    assert not ok
    assert "allocation_id" in msg
    assert _alloc_row(allocated).status == "active"


def test_non_object_payload_is_refused(allocated):
    assert gpu_deallocate_error(allocated, CHAIN, "alloc_test1", ALLOCATOR) == "GPU_DEALLOCATE payload must be an object"
    assert gpu_deallocate_error(allocated, CHAIN, None, ALLOCATOR) == "GPU_DEALLOCATE payload must be an object"


def test_helper_reports_each_rule(allocated):
    assert gpu_deallocate_error(allocated, CHAIN, {"allocation_id": ALLOCATION_ID}, FOREIGN) is not None
    assert gpu_deallocate_error(allocated, CHAIN, {"allocation_id": "alloc_missing"}, ALLOCATOR) is not None
    assert gpu_deallocate_error(allocated, CHAIN, {"allocation_id": ALLOCATION_ID}, ALLOCATOR) is None
    assert gpu_deallocate_error(allocated, CHAIN, {"allocation_id": ALLOCATION_ID}, OWNER) is None


def test_completed_allocation_leaves_active_allocations(allocated, st):
    """The #2403 symptom: active_allocations must drop to 0 after release."""
    from aitbc_chain.rpc.gpu_resources import _active_allocation_counts

    assert _active_allocation_counts(allocated, CHAIN, ["gpu-1"]) == {"gpu-1": 1}
    ok, msg = _apply(st, allocated, _deallocate(ALLOCATOR_KEY, nonce=1), "tx_dealloc")
    assert ok, msg
    assert _active_allocation_counts(allocated, CHAIN, ["gpu-1"]) == {}


# --------------------------------------------------------------------------------------------------------------------
# below v28: the name means nothing and replays as the plain transfer it always was
# --------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("version", [10, 20, 27])
def test_below_v28_it_is_a_plain_transfer_and_the_row_is_untouched(allocated, st, version):
    ok, msg = _apply(st, allocated, _deallocate(ALLOCATOR_KEY, nonce=1), "tx_dealloc", version=version)
    assert ok, msg
    assert _alloc_row(allocated).status == "active"


def test_below_v28_a_foreign_sender_replays_too(allocated, st):
    """No ownership gate below the activation height — same as every pre-rung name."""
    ok, msg = _apply(st, allocated, _deallocate(FOREIGN_KEY, nonce=0), "tx_foreign", version=27)
    assert ok, msg
    assert _alloc_row(allocated).status == "active"


# --------------------------------------------------------------------------------------------------------------------
# activation height and registration in the shared sets
# --------------------------------------------------------------------------------------------------------------------


def test_v28_is_unarmed_by_default():
    """Like every post-v26 rung the default is None — the operator pins it fleet-wide."""
    assert ChainSettings(_env_file=None).state_transition_v28_height is None


def test_v28_activates_at_its_height(monkeypatch, pin_heights_above):
    monkeypatch.setattr(settings, "state_transition_v28_height", 40_000)
    pin_heights_above(28)
    assert get_block_version_for_height(39_999) < 28
    assert get_block_version_for_height(40_000) == 28
    assert get_block_version_for_height(40_001) == 28


def test_the_type_runs_the_sequential_path_and_has_its_own_metric_series():
    assert "GPU_DEALLOCATE" in SEQUENTIAL_ONLY_TX_TYPES
    assert "GPU_DEALLOCATE" in V9_METRIC_KNOWN_TX_TYPES


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
    monkeypatch.setattr(settings, "state_transition_v28_height", 1)

    def submit(sender: str, allocation_id: str = ALLOCATION_ID, nonce: int = 0, **overrides: Any) -> None:
        tx: dict[str, Any] = {
            "from": sender,
            "to": sender,
            "amount": 0,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": nonce,
            "type": "GPU_DEALLOCATE",
            "chain_id": CHAIN,
            "payload": {"allocation_id": allocation_id},
        }
        tx.update(overrides)
        _validate_transaction_admission(tx, None)

    return submit


def test_admission_refuses_the_type_before_v28(door, allocated, monkeypatch):
    monkeypatch.setattr(settings, "state_transition_v28_height", None)
    with pytest.raises(ValueError, match="not active on this chain yet"):
        door(ALLOCATOR, nonce=1)


def test_admission_admits_the_allocator(door, allocated):
    door(ALLOCATOR, nonce=1)


def test_admission_admits_the_client(door, allocated):
    door(OWNER, nonce=1)


def test_admission_refuses_a_foreign_sender(door, allocated):
    with pytest.raises(ValueError, match="must come from its allocator"):
        door(FOREIGN)


def test_admission_refuses_an_unknown_allocation(door, allocated):
    with pytest.raises(ValueError, match="GPU allocation not found"):
        door(ALLOCATOR, allocation_id="alloc_missing", nonce=1)


def test_admission_refuses_a_repeat(door, allocated, st):
    ok, msg = _apply(st, allocated, _deallocate(ALLOCATOR_KEY, nonce=1), "tx_d1")
    assert ok, msg
    with pytest.raises(ValueError, match="already completed"):
        door(ALLOCATOR, nonce=2)


def test_admission_and_apply_give_the_same_verdict(door, session, st):
    """The two doors share gpu_deallocate_error; this fails if either ever grows a private check."""
    ok, msg = _apply(st, session, _register(OWNER_KEY), "tx_reg")
    assert ok, msg
    ok, msg = _apply(st, session, _allocate(ALLOCATOR_KEY, nonce=0), "tx_alloc")
    assert ok, msg
    cases = [
        (ALLOCATOR_KEY, ALLOCATION_ID, 1, True),
        (OWNER_KEY, ALLOCATION_ID, 1, True),
        (FOREIGN_KEY, ALLOCATION_ID, 0, False),
        (ALLOCATOR_KEY, "alloc_missing", 1, False),
    ]
    for key, allocation_id, nonce, expect in cases:
        sender = derive_ethereum_address(key)
        try:
            door(sender, allocation_id=allocation_id, nonce=nonce)
            admitted = True
        except ValueError:
            admitted = False
        valid, _ = st.validate_transaction(
            session,
            CHAIN,
            _deallocate(key, allocation_id, nonce),
            f"probe-{key[-4:]}-{allocation_id}",
            block_version=28,
        )
        assert admitted == valid == expect, (key, allocation_id)
