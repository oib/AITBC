"""#1295 ATTEST-LAG-WAIT-1: bounded wait for parent import before not_at_parent.

A validator whose tip lags the requested parent by a few blocks used to
refuse attestation instantly; transient import stalls (e.g. sqlite lock
windows) turned lag into refusals. With ``attest_lag_wait_enabled`` the v9
check wrapper retries ``not_at_parent`` until ``attest_lag_wait_seconds``
elapses — but ONLY while the tip is 1..``attest_lag_wait_max_blocks``
behind the parent. Rival/ahead tips give gap <= 0 and refuse on the first
verdict: fork protection is unchanged, the wait only delays.
"""

from __future__ import annotations

import asyncio
import threading
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus.block_hash import compute_block_hash
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.base_models import Block
from aitbc_chain.metadata import chain_metadata
from sqlmodel import Session, create_engine

CHAIN = "attest-lag-wait"
T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path}/chain.db")
    chain_metadata.create_all(engine)

    @contextmanager
    def factory():
        with Session(engine) as session:
            yield session
            session.commit()

    return factory


@pytest.fixture(autouse=True)
def _lag_off(monkeypatch):
    monkeypatch.setattr(settings, "attest_lag_wait_enabled", False)
    monkeypatch.setattr(settings, "attest_lag_wait_seconds", 0.2)
    monkeypatch.setattr(settings, "attest_lag_wait_max_blocks", 2)


def _seed_block(session_factory, height: int, block_hash: str, parent_hash: str) -> None:
    with session_factory() as session:
        session.add(
            Block(
                chain_id=CHAIN,
                height=height,
                hash=block_hash,
                parent_hash=parent_hash,
                proposer="0x" + "11" * 20,
                timestamp=T0,
                tx_count=0,
            )
        )
        session.commit()


def _header(height: int, parent_hash: str) -> dict:
    header = {
        "chain_id": CHAIN,
        "height": height,
        "hash": "",
        "parent_hash": parent_hash,
        "proposer": "0x" + "11" * 20,
        "state_root": "",
        "bridge_state_root": "",
        "aux_state_root": "",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "tx_count": 0,
        "tx_hashes": [],
    }
    header["hash"] = compute_block_hash(CHAIN, height, parent_hash, header["timestamp"], [], header["proposer"], "", "", "")
    return header


def _svc(session_factory=None) -> RemoteAttestationService:
    return RemoteAttestationService(CHAIN, {}, session_factory=session_factory)


def _scripted_svc(monkeypatch, verdicts, gaps):
    """Svc whose check returns scripted verdicts and whose lag probe returns
    scripted gaps; asyncio.sleep is instant."""
    svc = _svc()
    calls: list[int] = []
    gap_calls: list[int] = []
    v = iter(verdicts)

    def fake_check(header, txs):
        calls.append(1)
        return next(v, verdicts[-1])

    def fake_gap(header):
        gap_calls.append(1)
        return gaps.pop(0) if gaps else None

    async def fake_sleep(_s):
        return None

    monkeypatch.setattr(svc, "_v9_check_transactions", fake_check)
    monkeypatch.setattr(svc, "_parent_lag_gap", fake_gap)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return svc, calls, gap_calls


@pytest.mark.asyncio
async def test_flag_off_returns_first_verdict_without_probing(monkeypatch):
    svc, calls, gap_calls = _scripted_svc(monkeypatch, ["not_at_parent"], [1])
    assert await svc._run_v9_check({}, []) == "not_at_parent"
    assert len(calls) == 1 and gap_calls == []


@pytest.mark.asyncio
async def test_flag_on_retries_until_parent_imports(monkeypatch):
    monkeypatch.setattr(settings, "attest_lag_wait_enabled", True)
    svc, calls, _ = _scripted_svc(monkeypatch, ["not_at_parent", "not_at_parent", None], [1, 1])
    assert await svc._run_v9_check({}, []) is None
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_flag_on_gives_up_after_wait_seconds(monkeypatch):
    monkeypatch.setattr(settings, "attest_lag_wait_enabled", True)
    monkeypatch.setattr(settings, "attest_lag_wait_seconds", 0.01)
    svc, calls, _ = _scripted_svc(monkeypatch, ["not_at_parent"], [1])
    assert await svc._run_v9_check({}, []) == "not_at_parent"
    assert len(calls) >= 2  # retried, then deadline hit


@pytest.mark.asyncio
async def test_flag_on_zero_gap_refuses_immediately(monkeypatch):
    """Tip at parent height on a rival hash → gap 0 → no wait (fork protection)."""
    monkeypatch.setattr(settings, "attest_lag_wait_enabled", True)
    svc, calls, _ = _scripted_svc(monkeypatch, ["not_at_parent"], [0])
    assert await svc._run_v9_check({}, []) == "not_at_parent"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_flag_on_gap_beyond_window_refuses_immediately(monkeypatch):
    monkeypatch.setattr(settings, "attest_lag_wait_enabled", True)
    svc, calls, _ = _scripted_svc(monkeypatch, ["not_at_parent"], [3])
    assert await svc._run_v9_check({}, []) == "not_at_parent"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_flag_on_probe_failure_refuses_immediately(monkeypatch):
    monkeypatch.setattr(settings, "attest_lag_wait_enabled", True)
    svc, calls, _ = _scripted_svc(monkeypatch, ["not_at_parent"], [None])
    assert await svc._run_v9_check({}, []) == "not_at_parent"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_flag_on_other_verdicts_never_wait(monkeypatch):
    monkeypatch.setattr(settings, "attest_lag_wait_enabled", True)
    svc, calls, gap_calls = _scripted_svc(monkeypatch, ["nonce_order"], [1])
    assert await svc._run_v9_check({}, []) == "nonce_order"
    assert len(calls) == 1 and gap_calls == []


@pytest.mark.asyncio
async def test_lag_wait_enabled_alone_offloads_the_check(monkeypatch):
    """The bounded wait sleeps — enabling it must not freeze the event loop."""
    monkeypatch.setattr(settings, "attest_v9_check_offload_enabled", False)
    monkeypatch.setattr(settings, "attest_lag_wait_enabled", True)
    svc = _svc()
    seen: list[int] = []

    def fake(header, txs):
        seen.append(threading.get_ident())
        return "check_error"  # non-not_at_parent → no lag loop

    monkeypatch.setattr(svc, "_v9_check_transactions", fake)
    assert await svc._run_v9_check({}, []) == "check_error"
    assert seen and seen[0] != threading.get_ident()


@pytest.mark.asyncio
async def test_real_check_parent_arriving_mid_wait_is_attestable(session_factory, monkeypatch):
    """End-to-end: real _v9_check_transactions + real session. Tip at height
    1, request for height 3 needs the height-2 parent; the 'import' lands
    during the first lag sleep."""
    monkeypatch.setattr(settings, "attest_lag_wait_enabled", True)
    _seed_block(session_factory, 1, "0x" + "aa" * 32, "0x" + "00" * 32)
    parent_hash = "0x" + "bb" * 32
    imported = {"done": False}

    async def fake_sleep(_s):
        if not imported["done"]:
            imported["done"] = True
            _seed_block(session_factory, 2, parent_hash, "0x" + "aa" * 32)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    svc = _svc(session_factory)
    assert await svc._run_v9_check(_header(3, parent_hash), []) is None


@pytest.mark.asyncio
async def test_real_check_lag_past_deadline_still_refuses(session_factory, monkeypatch):
    monkeypatch.setattr(settings, "attest_lag_wait_enabled", True)
    monkeypatch.setattr(settings, "attest_lag_wait_seconds", 0.01)
    _seed_block(session_factory, 1, "0x" + "aa" * 32, "0x" + "00" * 32)

    async def fake_sleep(_s):
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    svc = _svc(session_factory)
    assert await svc._run_v9_check(_header(3, "0x" + "bb" * 32), []) == "not_at_parent"
