"""S-8 wait-for-lock gate: release/refund defer while the ESCROW_LOCK is unsealed.

``escrow_routes`` marks a row ``released_at``/``refunded_at`` at RPC acceptance,
but a settlement evaluated before its lock's block is dropped at production
("No ESCROW_LOCK found", or the v3 escrow-balance check, in
``state_transition``) — the row stays terminal and serves a dead hash forever
(15 unlanded settlements fleet-wide, 14 recorded *before* their lock block).
The gate defers with HTTP 425 while the sealed ``transaction`` table holds no
ESCROW_LOCK for the job, so the caller retries instead of minting a dead
settlement record.
"""

import asyncio
import importlib
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _reload_routes():
    """Reload escrow_routes so module-level env variables are re-read."""
    from aitbc_chain.rpc import escrow_routes

    importlib.reload(escrow_routes)
    return escrow_routes


def _env(monkeypatch):
    monkeypatch.setenv("ESCROW_RELEASE_PRIVATE_KEY", "0x2222222222222222222222222222222222222222222222222222222222222222")
    monkeypatch.setenv("GENESIS_WALLET_PRIVATE_KEY", "0x1111111111111111111111111111111111111111111111111111111111111111")
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    monkeypatch.setenv("CHAIN_ID", "test-chain")


def _record(**overrides):
    """An escrow row shaped like the locked-not-yet-settled rows the routes read."""
    fields = {
        "amount": 72_000_000,
        "status": "locked",
        "protected": False,
        "released_at": None,
        "refunded_at": None,
        "released_amount": None,
        "refunded_amount": None,
        "release_tx_hash": None,
        "refund_tx_hash": None,
        "job_tx_hash": None,
        "contract_id": "c1",
        "energy_settlement_asset": None,
        "energy_settlement_unit_scale": None,
        "energy_fee_basis_points": None,
        "energy_provider_credit_units": None,
        "energy_net_floor_units": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


class _FakeSession:
    def __init__(self, record):
        self.record = record
        self.committed = False

    def get(self, model, key):
        return self.record

    def add(self, obj):
        pass

    def commit(self):
        self.committed = True


def _session_scope(record):
    session = _FakeSession(record)

    @contextmanager
    def _scope():
        yield session

    return _scope, session


def _mgr(contract=None):
    mgr = MagicMock()
    mgr.escrow_contracts = {"c1": contract} if contract else {}
    mgr.release_lock = MagicMock(side_effect=lambda cid: asyncio.Lock())
    mgr.snapshot_release_state = MagicMock(return_value={})
    mgr.snapshot_refund_state = MagicMock(return_value={})
    mgr.release_payment = AsyncMock(return_value=(True, "released"))
    mgr.refund_contract = AsyncMock(return_value=(True, "refunded"))
    mgr.restore_after_failed_settlement = MagicMock()
    mgr.restore_after_failed_refund = MagicMock()
    return mgr


def _funded_contract(er):
    contract = MagicMock()
    contract.state = er.EscrowState.FUNDED
    contract.released_amount = Decimal("1.0")
    contract.refunded_amount = Decimal("1.0")
    contract.client_address = "0x4444444444444444444444444444444444444444"
    contract.agent_address = "0x3333333333333333333333333333333333333333"
    contract.milestones = [{"amount": "1.0", "completed": False, "verified": False}]
    contract.fee_rate = Decimal("0")
    return contract


def _patches(er, *, mgr, scope, lock_hash):
    """Everything between the route and the outside world, except the gate knob."""
    return (
        patch.object(er, "get_escrow_manager", return_value=mgr),
        patch.object(er, "session_scope", scope),
        patch.object(er, "backfill_settlement_legs"),
        patch.object(er, "_find_contract_id", new_callable=AsyncMock, return_value="c1"),
        patch.object(er, "_find_existing_lock", new_callable=AsyncMock, return_value=lock_hash),
        patch.object(er, "_find_existing_release", new_callable=AsyncMock, return_value=None),
        patch.object(er, "_find_existing_refund", new_callable=AsyncMock, return_value=None),
        patch.object(er, "_submit_payment_tx", new_callable=AsyncMock, return_value="0xreleasehash"),
        patch.object(er, "_submit_refund_tx", new_callable=AsyncMock, return_value="0xrefundhash"),
    )


@pytest.mark.asyncio
async def test_release_before_lock_seals_defers_without_marking(monkeypatch):
    """The S-8 race: release fired while the lock is still in mempool.

    Must raise 425, submit nothing, and leave the row unmarked so a later retry
    can settle. On the old source this proceeded to submit and returned a
    settled success dict — the row would have been marked released.
    """
    _env(monkeypatch)
    er = _reload_routes()
    record = _record()
    mgr = _mgr()
    scope, session = _session_scope(record)
    patches = _patches(er, mgr=mgr, scope=scope, lock_hash=None)
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4] as find_lock,
        patches[5],
        patches[6],
        patches[7] as submit_pay,
        patches[8],
    ):
        with pytest.raises(HTTPException) as excinfo:
            await er.release_escrow("job-1", {})
    assert excinfo.value.status_code == 425
    assert "not yet sealed" in excinfo.value.detail
    find_lock.assert_awaited_once_with("job-1")
    mgr.release_payment.assert_not_awaited()
    submit_pay.assert_not_awaited()
    assert record.released_at is None
    assert record.status == "locked"
    assert not session.committed


@pytest.mark.asyncio
async def test_release_after_lock_seals_proceeds_unchanged(monkeypatch):
    """A sealed lock passes the gate and the whole path runs as before."""
    _env(monkeypatch)
    er = _reload_routes()
    record = _record()
    mgr = _mgr()
    scope, _ = _session_scope(record)
    patches = _patches(er, mgr=mgr, scope=scope, lock_hash="0xlockhash")
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7] as submit_pay,
        patches[8],
    ):
        result = await er.release_escrow("job-1", {})
    assert result["success"] is True
    assert result["tx_hash"] == "0xreleasehash"
    assert result["settlement_status"] == "settled"
    submit_pay.assert_awaited_once()
    assert record.released_at is not None
    assert record.status == "released"


@pytest.mark.asyncio
async def test_refund_before_lock_seals_defers_without_marking(monkeypatch):
    """Same race on the refund leg: defer 425, submit nothing, mark nothing."""
    _env(monkeypatch)
    er = _reload_routes()
    record = _record()
    mgr = _mgr(contract=_funded_contract(er))
    scope, session = _session_scope(record)
    patches = _patches(er, mgr=mgr, scope=scope, lock_hash=None)
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
        patches[8] as submit_refund,
    ):
        with pytest.raises(HTTPException) as excinfo:
            await er.refund_escrow("job-1", {"reason": "test"})
    assert excinfo.value.status_code == 425
    assert "not yet sealed" in excinfo.value.detail
    mgr.refund_contract.assert_not_awaited()
    submit_refund.assert_not_awaited()
    assert record.refunded_at is None
    assert record.status == "locked"
    assert not session.committed


@pytest.mark.asyncio
async def test_refund_after_lock_seals_proceeds_unchanged(monkeypatch):
    """A sealed lock passes the gate; the refund path is unchanged."""
    _env(monkeypatch)
    er = _reload_routes()
    record = _record()
    mgr = _mgr(contract=_funded_contract(er))
    scope, _ = _session_scope(record)
    patches = _patches(er, mgr=mgr, scope=scope, lock_hash="0xlockhash")
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
        patches[8] as submit_refund,
    ):
        result = await er.refund_escrow("job-1", {"reason": "test"})
    assert result["success"] is True
    assert result["refund_tx_hash"] == "0xrefundhash"
    submit_refund.assert_awaited_once()
    assert record.refunded_at is not None
    assert record.status == "refunded"


@pytest.mark.asyncio
async def test_refund_refused_on_keyless_node(monkeypatch):
    """A node that cannot sign settlement must refuse the refund op entirely —
    same gate as release/create, before any row read, state change or
    submission."""
    monkeypatch.delenv("ESCROW_RELEASE_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("GENESIS_WALLET_PRIVATE_KEY", raising=False)
    er = _reload_routes()
    record = _record()
    mgr = _mgr(contract=_funded_contract(er))
    scope, session = _session_scope(record)
    patches = _patches(er, mgr=mgr, scope=scope, lock_hash="0xlockhash")
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
        patches[8] as submit_refund,
    ):
        with pytest.raises(HTTPException) as excinfo:
            await er.refund_escrow("job-1", {"reason": "test"})
    assert excinfo.value.status_code == 503
    mgr.refund_contract.assert_not_awaited()
    submit_refund.assert_not_awaited()
    assert record.refunded_at is None
    assert record.status == "locked"
    assert not session.committed


@pytest.mark.asyncio
async def test_refund_refusal_increments_settlement_refused_counter(monkeypatch):
    """op="refund" counts once per refusal; a keyed refund does not count."""
    from aitbc_chain.metrics import escrow_settlement_refused_total

    monkeypatch.delenv("ESCROW_RELEASE_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("GENESIS_WALLET_PRIVATE_KEY", raising=False)
    er = _reload_routes()
    record = _record()
    mgr = _mgr(contract=_funded_contract(er))
    scope, _session = _session_scope(record)
    patches = _patches(er, mgr=mgr, scope=scope, lock_hash="0xlockhash")
    child = escrow_settlement_refused_total.labels(op="refund")
    before = child._value.get()
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
        patches[8],
    ):
        with pytest.raises(HTTPException) as excinfo:
            await er.refund_escrow("job-1", {"reason": "test"})
    assert excinfo.value.status_code == 503
    assert child._value.get() == before + 1

    _env(monkeypatch)
    er = _reload_routes()
    record = _record()
    mgr = _mgr(contract=_funded_contract(er))
    scope, _session = _session_scope(record)
    patches = _patches(er, mgr=mgr, scope=scope, lock_hash="0xlockhash")
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
        patches[8],
    ):
        result = await er.refund_escrow("job-1", {"reason": "test"})
    assert result["success"] is True
    assert child._value.get() == before + 1


@pytest.mark.asyncio
async def test_release_refusal_increments_settlement_refused_counter(monkeypatch):
    """op="release" counts once per refusal; a keyed release does not count."""
    from aitbc_chain.metrics import escrow_settlement_refused_total

    monkeypatch.delenv("ESCROW_RELEASE_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("GENESIS_WALLET_PRIVATE_KEY", raising=False)
    er = _reload_routes()
    record = _record()
    mgr = _mgr()
    scope, _session = _session_scope(record)
    patches = _patches(er, mgr=mgr, scope=scope, lock_hash="0xlockhash")
    child = escrow_settlement_refused_total.labels(op="release")
    before = child._value.get()
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
        patches[8],
    ):
        with pytest.raises(HTTPException) as excinfo:
            await er.release_escrow("job-1", {})
    assert excinfo.value.status_code == 503
    assert child._value.get() == before + 1

    _env(monkeypatch)
    er = _reload_routes()
    record = _record()
    mgr = _mgr()
    scope, _session = _session_scope(record)
    patches = _patches(er, mgr=mgr, scope=scope, lock_hash="0xlockhash")
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
        patches[8],
    ):
        result = await er.release_escrow("job-1", {})
    assert result["success"] is True
    assert child._value.get() == before + 1


def test_settlement_refused_children_exist_at_zero_on_import():
    """All three op children must exist at 0 straight after metrics import.

    increase() cannot see a counter child that first appears at value 1 —
    Prometheus needs a prior sample to diff against — so a lazily created
    child hides the FIRST refusal from the EscrowSettlementRefusedOn* alerts
    entirely. metrics.py pre-creates the children at import; verify that in
    a fresh interpreter so increments by earlier tests in this session
    cannot mask a regression.
    """
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    import aitbc_chain

    # pytest resolves aitbc_chain via the ini `pythonpath` option, which
    # mutates this process's sys.path only — export the same src dir to the
    # child via PYTHONPATH so it can import the module at all.
    src_dir = Path(aitbc_chain.__file__).resolve().parent.parent
    env = {**os.environ, "PYTHONPATH": f"{src_dir}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"}
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json; "
            "from aitbc_chain.metrics import escrow_settlement_refused_total as c; "
            "print(json.dumps({s.labels['op']: s.value for m in c.collect() "
            "for s in m.samples if s.name == 'blockchain_escrow_settlement_refused_total'}))",
        ],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    assert json.loads(out.stdout) == {"create": 0.0, "refund": 0.0, "release": 0.0}


@pytest.mark.asyncio
async def test_already_released_row_short_circuits_before_the_gate(monkeypatch):
    """The stored-hash short-circuit still runs first — the gate is never reached.

    This is what keeps the 14+1 existing unlanded rows served as before: the
    remediation of those rows is remedy 2's job, not this gate's.
    """
    from datetime import UTC, datetime

    _env(monkeypatch)
    er = _reload_routes()
    record = _record(released_at=datetime.now(UTC))
    mgr = _mgr()
    scope, _ = _session_scope(record)
    patches = _patches(er, mgr=mgr, scope=scope, lock_hash=None)
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch.object(er, "_find_existing_lock", new_callable=AsyncMock, return_value=None) as find_lock,
        patch.object(er, "_find_existing_release", new_callable=AsyncMock, return_value="0xdead"),
        patches[6],
        patches[7],
        patches[8],
    ):
        result = await er.release_escrow("job-1", {})
    assert result["success"] is True
    assert result["tx_hash"] == "0xdead"
    find_lock.assert_not_awaited()
    mgr.release_payment.assert_not_awaited()


@pytest.mark.asyncio
async def test_gate_fails_closed_when_the_lock_probe_errors(monkeypatch):
    """An unreachable transactions lookup must defer, never mint a settlement.

    ``_find_existing_lock`` swallows its own errors to ``None``; the gate reads
    that as "not sealed" and defers — the safe direction for a custody call.
    """
    _env(monkeypatch)
    er = _reload_routes()
    record = _record()
    mgr = _mgr()
    scope, _ = _session_scope(record)
    with (
        patch.object(er, "get_escrow_manager", return_value=mgr),
        patch.object(er, "session_scope", scope),
        patch.object(er, "backfill_settlement_legs"),
        patch.object(er, "_find_contract_id", new_callable=AsyncMock, return_value="c1"),
        patch.object(er.SharedHttpClient, "get", new_callable=AsyncMock, side_effect=RuntimeError("RPC down")),
        patch.object(er, "_submit_payment_tx", new_callable=AsyncMock, return_value="0xreleasehash") as submit_pay,
    ):
        with pytest.raises(HTTPException) as excinfo:
            await er.release_escrow("job-1", {})
    assert excinfo.value.status_code == 425
    submit_pay.assert_not_awaited()
    assert record.released_at is None


@pytest.mark.asyncio
async def test_refund_gate_fails_closed_when_the_lock_probe_errors(monkeypatch):
    """The refund leg fails closed the same way: probe error -> 425, no refund."""
    _env(monkeypatch)
    er = _reload_routes()
    record = _record()
    mgr = _mgr(contract=_funded_contract(er))
    scope, _ = _session_scope(record)
    with (
        patch.object(er, "get_escrow_manager", return_value=mgr),
        patch.object(er, "session_scope", scope),
        patch.object(er, "backfill_settlement_legs"),
        patch.object(er, "_find_contract_id", new_callable=AsyncMock, return_value="c1"),
        patch.object(er.SharedHttpClient, "get", new_callable=AsyncMock, side_effect=RuntimeError("RPC down")),
        patch.object(er, "_submit_refund_tx", new_callable=AsyncMock, return_value="0xrefundhash") as submit_refund,
    ):
        with pytest.raises(HTTPException) as excinfo:
            await er.refund_escrow("job-1", {"reason": "test"})
    assert excinfo.value.status_code == 425
    submit_refund.assert_not_awaited()
    assert record.refunded_at is None
