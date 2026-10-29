"""Tests for the rpc-hosted shared transfer ledger (issue #696).

Covers the ``/rpc/bridge/ledger/*`` route contract (register → pending →
status → read, monotonic writeback) and the intake/relayer wiring in
``bridge_transfer.py`` — write-through register when BRIDGE_LEDGER_URL is
set, service worklist for the relayer, and byte-for-byte local-scan
fallback when it is unset.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc_chain.base_models import CrossChainTransfer
from aitbc_chain.config import settings
from aitbc_chain.cross_chain import bridge_ledger
from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account
from aitbc_chain.rpc.routers.bridge_ledger import (
    LedgerRegisterRequest,
    LedgerStatusRequest,
    ledger_pending_route,
    ledger_read_route,
    ledger_register_route,
    ledger_status_route,
)


@pytest.fixture()
def engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def bridge(engine):
    return CrossChainBridge(lambda: Session(engine))


@pytest.fixture(name="ledger_db")
def ledger_db_fixture(session, monkeypatch):
    """Point the ledger route handlers' session_scope at the in-memory test session."""

    @contextmanager
    def _fake_scope(chain_id: str = "", **kwargs):
        yield session

    monkeypatch.setattr("aitbc_chain.database.session_scope", _fake_scope)
    return session


@pytest.fixture()
def development(monkeypatch):
    for var in ("ENVIRONMENT", "APP_ENV", "NODE_ENV"):
        monkeypatch.delenv(var, raising=False)
    return True


def _register_body(tid: str = "0xabc", target: str = "island-1") -> LedgerRegisterRequest:
    return LedgerRegisterRequest(
        transfer_id=tid,
        source_chain="bc-2",
        target_chain=target,
        sender="0xSENDER",
        recipient="0xRECIPIENT",
        amount=36_000_000,
        asset="native",
        status="pending",
        source_tx_hash=tid,
        lock_time=datetime(2026, 10, 1, tzinfo=UTC),
    )


def _seed_record(engine, tid: str, status: str = "pending", source: str = "chain-a", target: str = "bc-2.test"):
    with Session(engine) as session:
        record = CrossChainTransfer(
            transfer_id=tid,
            source_chain=source,
            target_chain=target,
            sender="0xSENDER",
            recipient="0xRECIPIENT",
            amount=1000,
            asset="native",
            status=status,
            source_tx_hash=tid,
            lock_time=datetime(2026, 10, 1, tzinfo=UTC),
        )
        session.add(record)
        session.commit()
        session.expunge(record)
        return record


class TestLedgerRouteContract:
    def test_register_pending_status_read_roundtrip(self, ledger_db):
        result = asyncio.run(ledger_register_route(None, _register_body()))
        assert result["created"] is True
        assert result["transfer"]["status"] == "pending"

        pending = asyncio.run(ledger_pending_route(None, "island-1"))
        assert pending["count"] == 1
        assert pending["transfers"][0]["transfer_id"] == "0xabc"

        # Other target chains see nothing.
        assert asyncio.run(ledger_pending_route(None, "other-chain"))["count"] == 0

        confirmed = asyncio.run(
            ledger_status_route(None, "0xabc", LedgerStatusRequest(status="confirmed", target_tx_hash="0xrel"))
        )
        assert confirmed["transfer"]["status"] == "confirmed"
        assert confirmed["transfer"]["target_tx_hash"] == "0xrel"

        row = asyncio.run(ledger_read_route(None, "0xabc"))
        assert row["transfer"]["status"] == "confirmed"
        assert row["transfer"]["target_tx_hash"] == "0xrel"

        completed = asyncio.run(ledger_status_route(None, "0xabc", LedgerStatusRequest(status="completed")))
        assert completed["transfer"]["status"] == "completed"

    def test_register_is_idempotent_and_never_regresses(self, ledger_db):
        first = asyncio.run(ledger_register_route(None, _register_body()))
        assert first["created"] is True
        asyncio.run(ledger_status_route(None, "0xabc", LedgerStatusRequest(status="confirmed")))

        again = asyncio.run(ledger_register_route(None, _register_body()))
        assert again["created"] is False
        assert again["transfer"]["status"] == "confirmed"

    def test_monotonic_guard_rejects_out_of_order(self, ledger_db):
        asyncio.run(ledger_register_route(None, _register_body()))
        asyncio.run(ledger_status_route(None, "0xabc", LedgerStatusRequest(status="confirmed")))

        with pytest.raises(HTTPException) as exc:
            asyncio.run(ledger_status_route(None, "0xabc", LedgerStatusRequest(status="pending")))
        assert exc.value.status_code == 400

        asyncio.run(ledger_status_route(None, "0xabc", LedgerStatusRequest(status="completed")))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(ledger_status_route(None, "0xabc", LedgerStatusRequest(status="confirmed")))
        assert exc.value.status_code == 400
        # A terminal row cannot move sideways into another terminal state.
        with pytest.raises(HTTPException) as exc:
            asyncio.run(ledger_status_route(None, "0xabc", LedgerStatusRequest(status="failed")))
        assert exc.value.status_code == 400

    def test_same_status_writeback_is_idempotent(self, ledger_db):
        asyncio.run(ledger_register_route(None, _register_body()))
        result = asyncio.run(ledger_status_route(None, "0xabc", LedgerStatusRequest(status="pending")))
        assert result["transfer"]["status"] == "pending"

    def test_terminal_states_reachable(self, ledger_db):
        asyncio.run(ledger_register_route(None, _register_body()))
        result = asyncio.run(ledger_status_route(None, "0xabc", LedgerStatusRequest(status="refunded")))
        assert result["transfer"]["status"] == "refunded"

    def test_status_unknown_transfer_404_and_bad_status_400(self, ledger_db):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(ledger_status_route(None, "0xmissing", LedgerStatusRequest(status="confirmed")))
        assert exc.value.status_code == 404

        asyncio.run(ledger_register_route(None, _register_body()))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(ledger_status_route(None, "0xabc", LedgerStatusRequest(status="bogus")))
        assert exc.value.status_code == 400

    def test_read_unknown_transfer_404(self, ledger_db):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(ledger_read_route(None, "0xmissing"))
        assert exc.value.status_code == 404


class TestIntakeWriteThrough:
    def test_register_called_when_ledger_url_set(self, bridge, engine, development, monkeypatch):
        monkeypatch.setattr(settings, "bridge_ledger_url", "http://ledger.test")
        calls = []

        def _fake_request(method, path, **kwargs):
            calls.append((method, path, kwargs))
            return object()  # non-None = success

        monkeypatch.setattr(bridge_ledger, "_request", _fake_request)
        with Session(engine) as session:
            session.add(Account(chain_id="chain-a", address="0xsender", balance=10_000, nonce=0))
            session.commit()

        transfer = bridge.initiate_transfer("chain-a", "bc-2.test", "0xsender", "0xrecipient", 1000)

        assert len(calls) == 1
        method, path, kwargs = calls[0]
        assert method == "POST"
        assert path == "/rpc/bridge/ledger/register"
        payload = kwargs["json"]
        assert payload["transfer_id"] == transfer.transfer_id
        assert payload["source_chain"] == "chain-a"
        assert payload["target_chain"] == "bc-2.test"
        assert payload["status"] == "pending"

    def test_no_register_when_ledger_url_unset(self, bridge, engine, development, monkeypatch):
        monkeypatch.setattr(settings, "bridge_ledger_url", "")
        calls = []
        monkeypatch.setattr(bridge_ledger, "_request", lambda *a, **k: calls.append((a, k)) or object())
        with Session(engine) as session:
            session.add(Account(chain_id="chain-a", address="0xsender", balance=10_000, nonce=0))
            session.commit()

        bridge.initiate_transfer("chain-a", "bc-2.test", "0xsender", "0xrecipient", 1000)

        assert calls == []

    def test_register_failure_does_not_fail_the_lock(self, bridge, engine, development, monkeypatch):
        monkeypatch.setattr(settings, "bridge_ledger_url", "http://ledger.test")

        def _boom(method, path, **kwargs):
            raise ConnectionError("ledger down")

        monkeypatch.setattr(bridge_ledger, "_request", _boom)
        with Session(engine) as session:
            session.add(Account(chain_id="chain-a", address="0xsender", balance=10_000, nonce=0))
            session.commit()

        transfer = bridge.initiate_transfer("chain-a", "bc-2.test", "0xsender", "0xrecipient", 1000)

        assert transfer.amount == 1000
        with Session(engine) as session:
            assert len(session.exec(select(CrossChainTransfer)).all()) == 1


class TestRelayerWorklist:
    """_pending_worklist: service-driven when armed, local scan otherwise."""

    def test_unset_url_uses_local_scan(self, bridge, engine, monkeypatch):
        monkeypatch.setattr(settings, "bridge_ledger_url", "")
        monkeypatch.setattr(
            bridge_ledger, "fetch_pending", lambda *a, **k: pytest.fail("fetch_pending called with ledger unset")
        )
        _seed_record(engine, "0xours", source="chain-a", target="bc-2.test")
        _seed_record(engine, "0xother_source", source="chain-b", target="bc-2.test")
        _seed_record(engine, "0xother_target", source="chain-a", target="island-9")

        worklist = bridge._pending_worklist("chain-a", "bc-2.test")

        assert [t.transfer_id for t in worklist] == ["0xours"]

    def test_service_worklist_materialises_local_row(self, bridge, engine, monkeypatch):
        monkeypatch.setattr(settings, "bridge_ledger_url", "http://ledger.test")
        service_rows = [
            {
                "transfer_id": "0xremote",
                "source_chain": "chain-a",
                "target_chain": "bc-2.test",
                "sender": "0xS",
                "recipient": "0xR",
                "amount": 500,
                "asset": "native",
                "status": "pending",
                "source_tx_hash": "0xremote",
                "lock_time": "2026-10-01T00:00:00+00:00",
                "release_amount": None,
            },
            {
                "transfer_id": "0xother",
                "source_chain": "chain-b",
                "target_chain": "bc-2.test",
                "sender": "0xS",
                "recipient": "0xR",
                "amount": 1,
                "asset": "native",
            },
        ]
        monkeypatch.setattr(bridge_ledger, "fetch_pending", lambda target: service_rows)

        worklist = bridge._pending_worklist("chain-a", "bc-2.test")

        assert [t.transfer_id for t in worklist] == ["0xremote"]
        # The remote row was materialised locally so build_proof can read it.
        with Session(engine) as session:
            record = session.get(CrossChainTransfer, "0xremote")
            assert record is not None
            assert record.status == "pending"
            assert record.amount == 500
            # The chain-b row was filtered out and not materialised.
            assert session.get(CrossChainTransfer, "0xother") is None

    def test_service_outage_skips_the_pass(self, bridge, engine, monkeypatch):
        monkeypatch.setattr(settings, "bridge_ledger_url", "http://ledger.test")
        monkeypatch.setattr(bridge_ledger, "fetch_pending", lambda target: None)
        _seed_record(engine, "0xlocal", source="chain-a", target="bc-2.test")

        assert bridge._pending_worklist("chain-a", "bc-2.test") == []

    def test_local_row_wins_over_service_copy(self, bridge, engine, monkeypatch):
        """An existing local record is never overwritten by the service row."""
        monkeypatch.setattr(settings, "bridge_ledger_url", "http://ledger.test")
        _seed_record(engine, "0xdup", status="confirmed", source="chain-a", target="bc-2.test")
        monkeypatch.setattr(
            bridge_ledger,
            "fetch_pending",
            lambda target: [{"transfer_id": "0xdup", "source_chain": "chain-a", "target_chain": "bc-2.test", "amount": 999}],
        )

        worklist = bridge._pending_worklist("chain-a", "bc-2.test")

        with Session(engine) as session:
            assert session.get(CrossChainTransfer, "0xdup").status == "confirmed"
        assert worklist == []
