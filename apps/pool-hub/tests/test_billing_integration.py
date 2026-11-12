"""BillingIntegration tests — HTTP layer mocked, arithmetic asserted exactly.

#1400 (POOLHUB-BILL-1): ``if not unit_price`` treats an explicit Decimal("0")
as missing and substitutes the fallback price; quantity/unit_price carry no
sign or finiteness validation, so negative amounts can reach billing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from poolhub.models import Base, MatchRequest, MatchResult, Miner
from aitbc.exceptions import NetworkError

from poolhub.services.billing_integration import BillingIntegration


@pytest.fixture
def billing() -> BillingIntegration:
    return BillingIntegration(db=AsyncMock())


@pytest.fixture
def sent_events(billing, monkeypatch) -> list[dict]:
    events: list[dict] = []

    async def fake_send(event):
        events.append(event)
        return {"status": "ok", "event": event["total_amount"]}

    monkeypatch.setattr(billing, "_send_billing_event", fake_send)
    return events


class TestSendUsageArithmetic:
    async def test_total_is_unit_price_times_quantity(self, billing, sent_events):
        await billing.send_usage(
            tenant_id="t-1",
            resource_type="gpu_hours",
            quantity=Decimal("2.5"),
            unit_price=Decimal("0.50"),
        )
        event = sent_events[0]
        assert event["quantity"] == "2.5"
        assert event["unit_price"] == "0.50"
        assert event["total_amount"] == "1.250"  # Decimal arithmetic, exact
        assert event["currency"] == "USD"
        assert event["tenant_id"] == "t-1"
        assert event["event_type"] == "usage"

    async def test_fallback_price_used_when_unit_price_omitted(self, billing, sent_events):
        await billing.send_usage(tenant_id="t-1", resource_type="gpu_hours", quantity=Decimal("2"))
        event = sent_events[0]
        assert event["unit_price"] == "0.50"
        assert event["total_amount"] == "1.00"

    async def test_unknown_resource_type_prices_at_zero(self, billing, sent_events):
        await billing.send_usage(tenant_id="t-1", resource_type="mystery", quantity=Decimal("2"))
        assert sent_events[0]["total_amount"] == "0"

    async def test_job_id_included_when_given(self, billing, sent_events):
        await billing.send_usage(tenant_id="t-1", resource_type="api_calls", quantity=Decimal("1"), job_id="job-9")
        assert sent_events[0]["job_id"] == "job-9"

    async def test_timestamp_is_utc_isoformat(self, billing, sent_events):
        await billing.send_usage(tenant_id="t-1", resource_type="api_calls", quantity=Decimal("1"))
        ts = datetime.fromisoformat(sent_events[0]["timestamp"])
        assert ts.tzinfo is not None

    async def test_explicit_zero_unit_price_is_honored(self, billing, sent_events):
        await billing.send_usage(
            tenant_id="t-1",
            resource_type="gpu_hours",
            quantity=Decimal("2"),
            unit_price=Decimal("0"),
        )
        assert sent_events[0]["unit_price"] == "0"
        assert sent_events[0]["total_amount"] == "0"

    async def test_negative_quantity_is_rejected(self, billing, sent_events):
        with pytest.raises(ValueError):
            await billing.send_usage(
                tenant_id="t-1",
                resource_type="gpu_hours",
                quantity=Decimal("-5"),
                unit_price=Decimal("0.50"),
            )
        assert sent_events == []

    async def test_decimal_precision_is_preserved(self, billing, sent_events):
        """Numeric(20,8)-scale money must not go through float."""
        await billing.send_usage(
            tenant_id="t-1",
            resource_type="api_calls",
            quantity=Decimal("0.00000001"),
            unit_price=Decimal("0.0001"),
        )
        assert sent_events[0]["total_amount"] == str(Decimal("0.00000001") * Decimal("0.0001"))


class TestRecordUsageContract:
    async def test_send_failure_is_reported_not_raised(self, billing, monkeypatch):
        async def boom(event):
            raise NetworkError("coordinator down")

        monkeypatch.setattr(billing, "_send_billing_event", boom)
        result = await billing.record_usage(tenant_id="t-1", resource_type="gpu_hours", quantity=Decimal("1"))
        assert result["status"] == "failed"
        assert "coordinator down" in result["error"]

    async def test_send_usage_propagates_failure(self, billing, monkeypatch):
        async def boom(event):
            raise RuntimeError("coordinator down")

        monkeypatch.setattr(billing, "_send_billing_event", boom)
        with pytest.raises(RuntimeError):
            await billing.send_usage(tenant_id="t-1", resource_type="gpu_hours", quantity=Decimal("1"))


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _miner(miner_id: str = "m-1") -> Miner:
    return Miner(
        miner_id=miner_id,
        api_key_hash="x" * 64,
        addr="/ip4/127.0.0.1/tcp/9000",
        proto="tcp",
        gpu_vram_gb=24.0,
        gpu_name="RTX 4090",
        cpu_cores=16,
        ram_gb=64.0,
        max_parallel=4,
        base_price=Decimal("0.01"),
    )


class TestCollectMinerUsage:
    async def test_unknown_miner_raises(self, db_session):
        now = datetime.now(UTC)
        async with db_session() as s:
            with pytest.raises(ValueError, match="Miner not found"):
                await BillingIntegration(s).sync_miner_usage("ghost", now - timedelta(hours=1), now)

    async def test_compute_hours_from_eta_ms(self, db_session):
        """sum(eta_ms)/1000/3600 — 3.6M ms of eta is exactly 1 compute-hour."""
        now = datetime.now(UTC)
        async with db_session() as s:
            s.add(_miner())
            req = MatchRequest(job_id="j", requirements={})
            s.add(req)
            await s.flush()
            s.add(MatchResult(request_id=req.id, miner_id="m-1", score=0.9, eta_ms=3_600_000))
            s.add(MatchResult(request_id=req.id, miner_id="m-1", score=0.8, eta_ms=3_600_000))
            await s.commit()

        async with db_session() as s:
            usage = await BillingIntegration(s)._collect_miner_usage("m-1", now - timedelta(hours=1), now + timedelta(hours=1))

        assert usage["compute_hours"] == Decimal("2")
        assert usage["gpu_hours"] == Decimal("3.0")  # compute * 1.5
        assert usage["api_calls"] == Decimal("1")

    async def test_null_eta_rows_excluded(self, db_session):
        now = datetime.now(UTC)
        async with db_session() as s:
            s.add(_miner())
            req = MatchRequest(job_id="j", requirements={})
            s.add(req)
            await s.flush()
            s.add(MatchResult(request_id=req.id, miner_id="m-1", score=0.9, eta_ms=None))
            await s.commit()

        async with db_session() as s:
            usage = await BillingIntegration(s)._collect_miner_usage("m-1", now - timedelta(hours=1), now + timedelta(hours=1))
        assert usage["compute_hours"] == Decimal("0")
        assert usage["gpu_hours"] == Decimal("0")


class TestSyncAllMinersUsage:
    async def test_no_miners_returns_zeroed_summary(self, db_session, monkeypatch):
        send = AsyncMock()
        monkeypatch.setattr(BillingIntegration, "send_usage", send)
        async with db_session() as s:
            result = await BillingIntegration(s).sync_all_miners_usage(hours_back=24)

        assert result["miners_processed"] == 0
        assert result["miners_failed"] == 0
        send.assert_not_awaited()

    async def _seed_activity(self, s, miner_ids=("m-1", "m-2")):
        """One match request + one eta-bearing result per miner → nonzero usage."""
        req = MatchRequest(job_id="j", requirements={})
        s.add(req)
        await s.flush()
        for mid in miner_ids:
            s.add(MatchResult(request_id=req.id, miner_id=mid, score=0.9, eta_ms=3_600_000))
        await s.commit()

    async def test_failed_send_counts_miner_as_failed(self, db_session, monkeypatch):
        """send_usage raising must mark the miner failed, not processed (V23-101)."""
        async with db_session() as s:
            s.add(_miner("m-1"))
            s.add(_miner("m-2"))
            await self._seed_activity(s)

        async def boom(self, **kwargs):
            raise NetworkError("billing unreachable")

        monkeypatch.setattr(BillingIntegration, "send_usage", boom)
        async with db_session() as s:
            result = await BillingIntegration(s).sync_all_miners_usage(hours_back=24)

        assert result["miners_failed"] == 2
        assert result["miners_processed"] == 0

    async def test_per_miner_api_calls_split_is_decimal(self, db_session, monkeypatch):
        """api_calls is a global count divided across miners — Decimal, not float."""
        captured: list[dict] = []

        async def fake_send(self, **kwargs):
            captured.append(kwargs)
            return {"status": "ok"}

        monkeypatch.setattr(BillingIntegration, "send_usage", fake_send)
        async with db_session() as s:
            s.add(_miner("m-1"))
            s.add(_miner("m-2"))
            # One MatchRequest in the window → total_api_calls=1 → 0.5 per miner.
            s.add(MatchRequest(job_id="j", requirements={}))
            await s.commit()

        async with db_session() as s:
            result = await BillingIntegration(s).sync_all_miners_usage(hours_back=24)

        assert result["miners_processed"] == 2
        api_call_events = [c for c in captured if c["resource_type"] == "api_calls"]
        assert len(api_call_events) == 2
        for c in api_call_events:
            assert isinstance(c["quantity"], Decimal)
            assert c["quantity"] == Decimal("0.5")
