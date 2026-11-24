"""#2809 AUDIT-CHAIN-GPU-ALLOC-NAN-1: finite/range gate for GPU_ALLOCATE fields (v31).

``_vt_gpu_allocate`` parse-checks ``duration_hours``/``total_cost`` but
accepts NaN/Infinity — ``float("nan")`` and ``Decimal("nan")`` parse
cleanly, then apply stores a permanently-"active" allocation with junk
fields (``total_cost`` NaN binds NULL through the Numeric column).

v31 requires both fields finite and in range: ``duration_hours`` in
[0, 876000] (100 years — stored and echoed only, never fed to
``timedelta``), ``total_cost`` a finite Decimal in the ``Numeric(20,8)``
bound (same column spec as ``GPURegistration.price_per_hour``, reusing
``_gpu_price_per_hour_in_range``). The historical ``float()``/
``Decimal(str())`` coercion is kept — only non-finite/out-of-range
values are newly refused. Below v31 nothing changes.
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from aitbc.crypto.crypto import derive_ethereum_address
from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import Account
from aitbc_chain.database import chain_metadata
from aitbc_chain.rpc.utils import sign_transaction_data
from aitbc_chain.state.gpu_resources import GPURegistration
from aitbc_chain.state.state_transition import StateTransition

CHAIN = "ait-test-2809"
KEY = "0x" + "44" * 32
SENDER = derive_ethereum_address(KEY)
START = 10**9
GPU = "gpu-live-2809"


def _sign(private_key: str, data: dict) -> str:
    return sign_transaction_data(data, private_key)


def _tx(payload: dict) -> dict:
    tx: dict[str, Any] = {
        "from": SENDER,
        "to": SENDER,
        "amount": 0,
        "fee": DEFAULT_TX_FEE_UNITS,
        "nonce": 0,
        "type": "GPU_ALLOCATE",
        "chain_id": CHAIN,
        "payload": payload,
    }
    signable = {k: v for k, v in tx.items() if k != "signature"}
    signable.pop("value", None)
    tx["signature"] = _sign(KEY, signable)
    return tx


def _payload(**over: Any) -> dict[str, Any]:
    p: dict[str, Any] = {
        "gpu_id": GPU,
        "client_id": "c-1",
        "duration_hours": 1.0,
        "total_cost": "1",
        "allocation_id": "alloc-v31-1",
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


def _validate(st: StateTransition, session: Session, payload: dict, version: int):
    return st.validate_transaction(session, CHAIN, _tx(payload), "tx_v31", block_version=version, block_height=2)


# --- v31 rejects non-finite / out-of-range fields ---


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_v31_nan_inf_duration_rejected(session, st, bad):
    ok, err = _validate(st, session, _payload(duration_hours=bad), 31)
    assert ok is False and "duration_hours out of range" in err


@pytest.mark.parametrize("bad", [-1.0, 876001.0, 1e300])
def test_v31_out_of_range_duration_rejected(session, st, bad):
    ok, err = _validate(st, session, _payload(duration_hours=bad), 31)
    assert ok is False and "duration_hours out of range" in err


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_v31_nan_inf_total_cost_rejected(session, st, bad):
    ok, err = _validate(st, session, _payload(total_cost=bad), 31)
    assert ok is False and "total_cost out of range" in err


@pytest.mark.parametrize("bad", [-5, "1e30", "nan", "abc"])
def test_v31_bad_total_cost_rejected(session, st, bad):
    ok, err = _validate(st, session, _payload(total_cost=bad), 31)
    assert ok is False


# --- v31 keeps historically-coerced shapes ---


def test_v31_string_total_cost_still_accepted(session, st):
    """``"1"`` coerced via ``Decimal(str())`` before — must still pass."""
    ok, err = _validate(st, session, _payload(total_cost="1"), 31)
    assert "total_cost" not in err and "duration_hours" not in err


def test_v31_numeric_string_duration_still_accepted(session, st):
    ok, err = _validate(st, session, _payload(duration_hours="2.5"), 31)
    assert "duration_hours" not in err


def test_v31_wellformed_payload_passes(session, st):
    ok, err = _validate(st, session, _payload(), 31)
    assert ok is True, err


# --- below v31 the rules are unchanged ---


def test_v30_nan_duration_not_gated(session, st):
    ok, err = _validate(st, session, _payload(duration_hours=math.nan), 30)
    assert "duration_hours out of range" not in err
    assert "total_cost out of range" not in err
