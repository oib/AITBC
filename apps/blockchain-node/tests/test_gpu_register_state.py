"""Tests for GPU_REGISTER and GPU_ALLOCATE state transitions."""

from __future__ import annotations

import json

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc.crypto.crypto import derive_ethereum_address, sign_transaction_hash
from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import Account
from aitbc_chain.database import chain_metadata
from aitbc_chain.state.gpu_resources import GPUAllocation, GPURegistration
from aitbc_chain.state.state_transition import StateTransition


def _sign_data(private_key: str, data: dict) -> str:
    from eth_utils import keccak

    message = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return sign_transaction_hash("0x" + keccak(message).hex(), private_key)


def _make_tx(private_key: str, tx_data: dict) -> dict:
    tx = dict(tx_data)
    from_address = derive_ethereum_address(private_key)
    tx["from"] = from_address
    tx["to"] = tx.get("to", from_address)

    signable = {k: v for k, v in tx.items() if k not in ("signature",)}
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


@pytest.fixture
def st():
    return StateTransition()


def test_gpu_register_creates_record_and_takes_fee(session, st):
    chain_id = "ait-test"
    private_key = "0x" + "11" * 32
    sender = derive_ethereum_address(private_key)

    session.add(Account(chain_id=chain_id, address=sender, balance=1_000_000, nonce=0))
    session.commit()

    tx_data = _make_tx(
        private_key,
        {
            "from": sender,
            "to": sender,
            "amount": 0,
            "value": 0,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": 0,
            "type": "GPU_REGISTER",
            "chain_id": chain_id,
            "payload": {
                "gpu_id": "gpu-1",
                "miner_id": "miner-1",
                "model": "RTX 4090",
                "memory_gb": 24,
                "price_per_hour": "0.1",
            },
        },
    )

    success, msg = st.apply_transaction(session, chain_id, tx_data, "tx_hash_1")
    assert success, msg

    sender_account = session.get(Account, (chain_id, sender))
    assert sender_account.balance == 1_000_000 - DEFAULT_TX_FEE_UNITS
    assert sender_account.nonce == 1

    gpu = session.exec(
        select(GPURegistration).where(GPURegistration.chain_id == chain_id, GPURegistration.gpu_id == "gpu-1")
    ).first()
    assert gpu is not None
    assert gpu.model == "RTX 4090"
    assert gpu.memory_gb == 24
    assert str(gpu.price_per_hour) == "0.10000000"
    assert gpu.registered_by == sender


def test_gpu_register_rejects_invalid_price(session, st):
    chain_id = "ait-test"
    private_key = "0x" + "11" * 32
    sender = derive_ethereum_address(private_key)

    session.add(Account(chain_id=chain_id, address=sender, balance=1_000_000, nonce=0))
    session.commit()

    tx_data = _make_tx(
        private_key,
        {
            "from": sender,
            "to": sender,
            "amount": 0,
            "value": 0,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": 0,
            "type": "GPU_REGISTER",
            "chain_id": chain_id,
            "payload": {
                "gpu_id": "gpu-1",
                "miner_id": "miner-1",
                "model": "RTX 4090",
                "memory_gb": 24,
                "price_per_hour": "not-a-number",
            },
        },
    )

    success, msg = st.apply_transaction(session, chain_id, tx_data, "tx_hash_1")
    assert not success
    assert "price_per_hour" in msg


def test_gpu_allocate_creates_record_and_takes_fee(session, st):
    chain_id = "ait-test"
    private_key = "0x" + "11" * 32
    sender = derive_ethereum_address(private_key)
    client = "0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2"

    session.add(Account(chain_id=chain_id, address=sender, balance=1_000_000, nonce=0))
    session.add(
        GPURegistration(
            chain_id=chain_id,
            gpu_id="gpu-1",
            miner_id="miner-1",
            model="RTX 4090",
            memory_gb=24,
            price_per_hour="0.1",
            registered_by=sender,
            status="active",
        )
    )
    session.commit()

    tx_data = _make_tx(
        private_key,
        {
            "from": sender,
            "to": sender,
            "amount": 0,
            "value": 0,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": 0,
            "type": "GPU_ALLOCATE",
            "chain_id": chain_id,
            "payload": {
                "gpu_id": "gpu-1",
                "client_id": client,
                "duration_hours": 2.0,
                "total_cost": "0.2",
            },
        },
    )

    success, msg = st.apply_transaction(session, chain_id, tx_data, "tx_hash_2")
    assert success, msg

    sender_account = session.get(Account, (chain_id, sender))
    assert sender_account.balance == 1_000_000 - DEFAULT_TX_FEE_UNITS
    assert sender_account.nonce == 1

    allocation = session.exec(
        select(GPUAllocation).where(GPUAllocation.chain_id == chain_id, GPUAllocation.gpu_id == "gpu-1")
    ).first()
    assert allocation is not None
    assert allocation.client_id == client
    assert allocation.duration_hours == 2.0
    assert str(allocation.total_cost) == "0.20000000"
    assert allocation.allocated_by == sender


def test_gpu_register_requires_sequential_delta():
    """The pure/parallel delta map cannot model the gpu_registration side effect,
    so it must force a sequential fallback through the full state transition."""
    from aitbc_chain.state.pure_state_transition import compute_state_delta

    tx_data = {
        "from": "0x" + "aa" * 20,
        "to": "0x" + "aa" * 20,
        "amount": 0,
        "fee": 36,
        "nonce": 0,
        "type": "GPU_REGISTER",
        "chain_id": "ait-test",
        "payload": {
            "gpu_id": "gpu-parallel",
            "miner_id": "miner-1",
            "model": "RTX 4090",
            "memory_gb": 24,
            "price_per_hour": "0.1",
        },
    }
    delta = compute_state_delta(
        {},
        tx_data,
        "ait-test",
        tx_hash="tx-gpu-parallel",
        existing_tx_hashes=set(),
        block_version=2,
    )
    assert not delta.success
    assert delta.requires_sequential
    assert "GPU_REGISTER" in delta.error
    assert "sequentially" in delta.error


def test_gpu_allocate_requires_sequential_delta():
    """GPU_ALLOCATE must also force sequential processing in the parallel delta path."""
    from aitbc_chain.state.pure_state_transition import compute_state_delta

    tx_data = {
        "from": "0x" + "aa" * 20,
        "to": "0x" + "aa" * 20,
        "amount": 0,
        "fee": 36,
        "nonce": 0,
        "type": "GPU_ALLOCATE",
        "chain_id": "ait-test",
        "payload": {
            "gpu_id": "gpu-1",
            "client_id": "0x" + "bb" * 20,
            "duration_hours": 2.0,
            "total_cost": "0.2",
        },
    }
    delta = compute_state_delta(
        {},
        tx_data,
        "ait-test",
        tx_hash="tx-gpu-allocate",
        existing_tx_hashes=set(),
        block_version=2,
    )
    assert not delta.success
    assert delta.requires_sequential
    assert "GPU_ALLOCATE" in delta.error
