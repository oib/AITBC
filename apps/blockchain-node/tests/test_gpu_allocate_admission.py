"""GPU-ADMISSION-1 (#384): v16-gated admission for GPU_ALLOCATE.

Today GPU_ALLOCATE is AUTHORITY_OPEN: a missing ``allocation_id`` is minted
per-host at apply (``alloc_<uuid4>``, nondeterministic — ``allocation_id`` is in
CANONICAL_EXCLUDED_COLUMNS) and an unknown ``gpu_id`` dies only at apply after
reaching the mempool. At ``STATE_TRANSITION_V16_HEIGHT`` (operator ruling
24 Oct; multisig-accounts takes v17 if it lands second) both become admission
requirements via the shared helper ``gpu_allocate_admission_error`` — same rule
at the consensus door and the mempool door. Below the height nothing changes;
bc-2 holds zero GPU_ALLOCATE txs so no recorded block is reachable.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from aitbc.crypto.crypto import derive_ethereum_address
from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import Account
from aitbc_chain.config import ChainSettings, settings
from aitbc_chain.database import chain_metadata
from aitbc_chain.rpc.transactions import _validate_transaction_admission
from aitbc_chain.rpc.utils import sign_transaction_data
from aitbc_chain.state.gpu_resources import GPURegistration, gpu_allocate_admission_error
from aitbc_chain.state.state_transition import StateTransition, get_block_version_for_height

CHAIN = "ait-test"
KEY = "0x" + "33" * 32
SENDER = derive_ethereum_address(KEY)
START = 10_000_000
GPU = "gpu-live-1"


def _sign(private_key: str, data: dict) -> str:
    return sign_transaction_data(data, private_key)


def _tx(private_key: str, tx_type: str, payload: dict, nonce: int = 0) -> dict:
    tx: dict[str, Any] = {
        "from": derive_ethereum_address(private_key),
        "to": derive_ethereum_address(private_key),
        "amount": 0,
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


def _allocate_payload(**over: Any) -> dict[str, Any]:
    p: dict[str, Any] = {
        "gpu_id": GPU,
        "client_id": "c-1",
        "duration_hours": 1.0,
        "total_cost": "1",
        "allocation_id": "alloc-fixed-1",
    }
    p.update(over)
    return p


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Account(chain_id=CHAIN, address=SENDER, balance=START, nonce=0))
        s.add(
            GPURegistration(
                chain_id=CHAIN,
                gpu_id=GPU,
                miner_id="m-1",
                model="RTX 4090",
                memory_gb=24,
                price_per_hour="0.1",
                registered_by=SENDER,
            )
        )
        s.commit()
        yield s


@pytest.fixture
def st():
    return StateTransition()


class TestPureRule:
    def test_missing_allocation_id(self, session):
        assert gpu_allocate_admission_error(session, CHAIN, _allocate_payload(allocation_id=None)) is not None

    def test_unknown_gpu(self, session):
        err = gpu_allocate_admission_error(session, CHAIN, _allocate_payload(gpu_id="gpu-nope"))
        assert err and "not found" in err.lower()

    def test_valid_passes(self, session):
        assert gpu_allocate_admission_error(session, CHAIN, _allocate_payload()) is None

    def test_non_dict_left_alone(self, session):
        assert gpu_allocate_admission_error(session, CHAIN, "junk") is None


class TestConsensusGate:
    def test_missing_id_refused_at_v16(self, session, st):
        tx = _tx(KEY, "GPU_ALLOCATE", _allocate_payload(allocation_id=None))
        ok, _ = st.validate_transaction(session, CHAIN, tx, "tx_t", block_version=16)
        assert not ok

    def test_unknown_gpu_refused_at_v16(self, session, st):
        tx = _tx(KEY, "GPU_ALLOCATE", _allocate_payload(gpu_id="gpu-nope"))
        ok, _ = st.validate_transaction(session, CHAIN, tx, "tx_t", block_version=16)
        assert not ok

    @pytest.mark.parametrize("version", [10, 15])
    def test_below_gate_accepts_minted_id(self, session, st, version):
        """Pre-height txs may still omit allocation_id (apply mints alloc_<uuid4>)."""
        tx = _tx(KEY, "GPU_ALLOCATE", _allocate_payload(allocation_id=None, gpu_id="gpu-nope"))
        ok, _ = st.validate_transaction(session, CHAIN, tx, "tx_t", block_version=version)
        assert ok


@pytest.fixture
def door(session, monkeypatch):
    @contextmanager
    def _scope():
        yield session

    monkeypatch.setattr("aitbc_chain.rpc.transactions.session_scope", _scope)
    monkeypatch.setattr("aitbc_chain.rpc.utils.get_supported_chains", lambda: [CHAIN])
    monkeypatch.setattr(settings, "state_transition_v16_height", 1)

    def submit(**over: Any) -> None:
        _validate_transaction_admission(_tx(KEY, "GPU_ALLOCATE", _allocate_payload(**over)), None)

    return submit


class TestDoor:
    def test_missing_id_refused_when_armed(self, door):
        with pytest.raises((HTTPException, ValueError)):
            door(allocation_id=None)

    def test_unknown_gpu_refused_when_armed(self, door):
        with pytest.raises((HTTPException, ValueError)):
            door(gpu_id="gpu-nope")

    def test_unarmed_passes_door(self, session, monkeypatch):
        @contextmanager
        def _scope():
            yield session

        monkeypatch.setattr("aitbc_chain.rpc.transactions.session_scope", _scope)
        monkeypatch.setattr("aitbc_chain.rpc.utils.get_supported_chains", lambda: [CHAIN])
        monkeypatch.setattr(settings, "state_transition_v16_height", None)
        try:
            _validate_transaction_admission(
                _tx(KEY, "GPU_ALLOCATE", _allocate_payload(allocation_id=None, gpu_id="gpu-nope")), None
            )
        except (HTTPException, ValueError) as e:
            pytest.fail(f"unarmed gate must not change admission: {e}")


def test_v16_setting_defaults_unarmed():
    assert ChainSettings(_env_file=None).state_transition_v16_height is None


def test_v16_env_overrides(monkeypatch):
    monkeypatch.setenv("STATE_TRANSITION_V16_HEIGHT", "7")
    assert ChainSettings(_env_file=None).state_transition_v16_height == 7


def test_v16_version_resolution_boundary(monkeypatch):
    monkeypatch.setattr(settings, "state_transition_v16_height", 100)
    monkeypatch.setattr(settings, "state_transition_v15_height", None)
    assert get_block_version_for_height(99) != 16
    assert get_block_version_for_height(100) == 16
