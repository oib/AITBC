"""
Billing Integration Service for Pool-Hub
Integrates pool-hub usage data with coordinator-api's billing system.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aitbc.aitbc_logging import get_logger
from aitbc.async_tasks import create_task_with_logging
from aitbc.exceptions import NetworkError
from aitbc.network import AsyncAITBCHTTPClient

from ..models import MatchRequest, MatchResult, Miner
from ..settings import settings

logger = get_logger(__name__)


class BillingIntegration:
    """Service for integrating pool-hub with coordinator-api billing"""

    # V23-46: annotated AsyncSession, not Session. Every call site passes one
    # (app/routers/sla.py, tests/conftest.py) and every use here is `await`ed --
    # the sync annotation is what forced the `# type: ignore[misc]` on each of them.
    def __init__(self, db: AsyncSession):
        self.db = db
        self.coordinator_billing_url = getattr(settings, "coordinator_billing_url", "http://localhost:8203")
        self.coordinator_api_key = getattr(settings, "coordinator_api_key", None)
        self.logger = get_logger(__name__)
        self.resource_type_mapping = {
            "gpu_hours": "gpu_hours",
            "storage_gb": "storage_gb",
            "api_calls": "api_calls",
            "compute_hours": "compute_hours",
        }
        self.fallback_pricing = {
            "gpu_hours": {"unit_price": Decimal("0.50")},
            "storage_gb": {"unit_price": Decimal("0.02")},
            "api_calls": {"unit_price": Decimal("0.0001")},
            "compute_hours": {"unit_price": Decimal("0.30")},
        }

    async def record_usage(
        self,
        tenant_id: str,
        resource_type: str,
        quantity: Decimal,
        unit_price: Decimal | None = None,
        job_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record usage data to coordinator-api billing system"""
        if not unit_price:
            pricing_config = self.fallback_pricing.get(resource_type, {})
            unit_price = pricing_config.get("unit_price", Decimal("0"))
        total_cost = unit_price * quantity
        billing_event = {
            "tenant_id": tenant_id,
            "event_type": "usage",
            "resource_type": resource_type,
            "quantity": str(quantity),
            "unit_price": str(unit_price),
            "total_amount": str(total_cost),
            "currency": "USD",
            "timestamp": datetime.now(UTC).isoformat(),
            "metadata": metadata or {},
        }
        if job_id:
            billing_event["job_id"] = job_id
        try:
            response = await self._send_billing_event(billing_event)
            self.logger.info(
                "Recorded usage: tenant=%s, resource=%s, quantity=%s, cost=%s", tenant_id, resource_type, quantity, total_cost
            )
            return response
        except Exception as e:
            self.logger.error("Failed to record usage: %s", e)
            return {"status": "failed", "error": str(e)}

    async def sync_miner_usage(self, miner_id: str, start_date: datetime, end_date: datetime) -> dict[str, Any]:
        """Sync usage data for a miner to coordinator-api billing"""
        stmt = select(Miner).where(Miner.miner_id == miner_id)
        miner = (await self.db.execute(stmt)).scalar_one_or_none()
        if not miner:
            raise ValueError(f"Miner not found: {miner_id}")
        tenant_id = miner_id
        usage_data = await self._collect_miner_usage(miner_id, start_date, end_date)
        results = []
        for resource_type, quantity in usage_data.items():
            if quantity > 0:
                result = await self.record_usage(
                    tenant_id=tenant_id,
                    resource_type=resource_type,
                    quantity=quantity,
                    metadata={"miner_id": miner_id, "sync_type": "miner_usage"},
                )
                results.append(result)
        return {
            "miner_id": miner_id,
            "tenant_id": tenant_id,
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "usage_records": len(results),
            "results": results,
        }

    async def sync_all_miners_usage(self, hours_back: int = 24) -> dict[str, Any]:
        """Sync usage data for all miners to coordinator-api billing.

        Uses batched queries to collect all miner usage in O(1) round trips
        instead of O(N) per-miner queries. All DB reads are done in one
        transaction for consistency.
        """
        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(hours=hours_back)
        # Read all data in one transaction for a consistent snapshot
        async with self.db.begin():
            stmt = select(Miner)
            miners = (await self.db.execute(stmt)).scalars().all()
            miner_ids = [m.miner_id for m in miners]
            if not miner_ids:
                return {
                    "sync_period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
                    "miners_processed": 0,
                    "miners_failed": 0,
                    "total_usage_records": 0,
                    "details": [],
                }

            # Batch 1: API call counts (global, not per-miner — MatchRequest has no miner_id)
            count_stmt = select(func.count(MatchRequest.id)).where(
                and_(MatchRequest.created_at >= start_date, MatchRequest.created_at <= end_date)
            )
            total_api_calls = (await self.db.execute(count_stmt)).scalar() or 0

            # Batch 2: Match results for all miners in one query
            result_stmt = (
                select(MatchResult)
                .where(
                    and_(
                        MatchResult.miner_id.in_(miner_ids),
                        MatchResult.created_at >= start_date,
                        MatchResult.created_at <= end_date,
                    )
                )
                # is_not, not isnot_ (V23-97) — see _collect_miner_usage below.
                .where(MatchResult.eta_ms.is_not(None))
            )
            all_results = (await self.db.execute(result_stmt)).scalars().all()

        # Group by miner_id and aggregate (outside the transaction — pure computation)
        compute_ms_by_miner: dict[str, int] = {}
        for r in all_results:
            compute_ms_by_miner[r.miner_id] = compute_ms_by_miner.get(r.miner_id, 0) + (r.eta_ms or 0)
        api_calls_per_miner = Decimal(str(total_api_calls)) / Decimal(str(len(miner_ids)))

        results: dict[str, Any] = {
            "sync_period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "miners_processed": 0,
            "miners_failed": 0,
            "total_usage_records": 0,
            "details": [],
        }

        for miner_id in miner_ids:
            try:
                total_compute_time_ms = compute_ms_by_miner.get(miner_id, 0)
                compute_hours = Decimal(str(total_compute_time_ms)) / Decimal("1000") / Decimal("3600")
                gpu_hours = compute_hours * Decimal("1.5")
                usage_data = {
                    "gpu_hours": gpu_hours,
                    "api_calls": api_calls_per_miner,
                    "compute_hours": compute_hours,
                }
                sync_details = []
                for resource_type, quantity in usage_data.items():
                    if quantity > 0:
                        record_result = await self.record_usage(
                            tenant_id=miner_id,
                            resource_type=resource_type,
                            quantity=quantity,
                            metadata={"miner_id": miner_id, "sync_type": "batch_usage"},
                        )
                        sync_details.append(record_result)
                results["details"].append(
                    {
                        "miner_id": miner_id,
                        "tenant_id": miner_id,
                        "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
                        "usage_records": len(sync_details),
                        "results": sync_details,
                    }
                )
                results["miners_processed"] += 1
                results["total_usage_records"] += len(sync_details)
            except Exception as e:
                self.logger.error("Failed to sync usage for miner %s: %s", miner_id, e)
                results["miners_failed"] += 1
        self.logger.info(
            "Usage sync complete: processed=%s, failed=%s, records=%s",
            results["miners_processed"],
            results["miners_failed"],
            results["total_usage_records"],
        )
        return results

    async def _collect_miner_usage(self, miner_id: str, start_date: datetime, end_date: datetime) -> dict[str, Decimal]:
        """Collect usage data for a miner from pool-hub"""
        usage_data: dict[str, Decimal] = {"gpu_hours": Decimal("0"), "api_calls": Decimal("0"), "compute_hours": Decimal("0")}
        count_stmt = select(func.count(MatchRequest.id)).where(
            and_(MatchRequest.created_at >= start_date, MatchRequest.created_at <= end_date)
        )
        api_calls = (await self.db.execute(count_stmt)).scalar() or 0
        usage_data["api_calls"] = Decimal(str(api_calls))
        result_stmt = (
            select(MatchResult)
            .where(
                and_(
                    MatchResult.miner_id == miner_id, MatchResult.created_at >= start_date, MatchResult.created_at <= end_date
                )
            )
            # is_not, not isnot_ (V23-97).  `isnot_` is not a SQLAlchemy operator, so
            # every billing sync raised AttributeError here before touching the database.
            .where(MatchResult.eta_ms.is_not(None))
        )
        results = (await self.db.execute(result_stmt)).scalars().all()
        total_compute_time_ms = sum(r.eta_ms for r in results if r.eta_ms)
        compute_hours = Decimal(str(total_compute_time_ms)) / Decimal("1000") / Decimal("3600") if results else Decimal("0")
        usage_data["compute_hours"] = compute_hours
        gpu_hours = compute_hours * Decimal("1.5")
        usage_data["gpu_hours"] = gpu_hours
        return usage_data

    async def _send_billing_event(self, billing_event: dict[str, Any]) -> dict[str, Any]:
        """Send billing event to coordinator-api"""
        headers = {"Content-Type": "application/json"}
        if self.coordinator_api_key:
            headers["Authorization"] = f"Bearer {self.coordinator_api_key}"
        client = AsyncAITBCHTTPClient(base_url=self.coordinator_billing_url, headers=headers, timeout=30)
        response = await client.post("/api/billing/usage", json=billing_event)
        if response:
            return response
        else:
            raise NetworkError("Failed to send billing event")

    async def get_billing_metrics(self, tenant_id: str | None = None, hours: int = 24) -> dict[str, Any]:
        """Get billing metrics from coordinator-api"""
        headers = {}
        if self.coordinator_api_key:
            headers["Authorization"] = f"Bearer {self.coordinator_api_key}"
        client = AsyncAITBCHTTPClient(base_url=self.coordinator_billing_url, headers=headers, timeout=30)
        params: dict[str, Any] = {"hours": hours}
        if tenant_id:
            params["tenant_id"] = tenant_id
        response = await client.get("/api/billing/metrics", params=params)
        if response:
            return response
        else:
            raise NetworkError("Failed to get billing metrics")

    async def trigger_invoice_generation(self, tenant_id: str, period_start: datetime, period_end: datetime) -> dict[str, Any]:
        """Trigger invoice generation in coordinator-api"""
        payload = {"tenant_id": tenant_id, "period_start": period_start.isoformat(), "period_end": period_end.isoformat()}
        headers = {"Content-Type": "application/json"}
        if self.coordinator_api_key:
            headers["Authorization"] = f"Bearer {self.coordinator_api_key}"
        client = AsyncAITBCHTTPClient(base_url=self.coordinator_billing_url, headers=headers, timeout=30)
        response = await client.post("/api/billing/invoice", json=payload)
        if response:
            return response
        else:
            raise NetworkError("Failed to trigger invoice generation")


class BillingIntegrationScheduler:
    """Scheduler for automated billing synchronization"""

    def __init__(self, billing_integration: BillingIntegration):
        self.billing_integration = billing_integration
        self.logger = get_logger(__name__)
        self.running = False

    async def start(self, sync_interval_hours: int = 1) -> None:
        """Start the billing synchronization scheduler"""
        if self.running:
            return
        self.running = True
        self.logger.info("Billing Integration scheduler started")
        create_task_with_logging(self._sync_loop(sync_interval_hours), name="billing_sync_loop")

    async def stop(self) -> None:
        """Stop the billing synchronization scheduler"""
        self.running = False
        self.logger.info("Billing Integration scheduler stopped")

    async def _sync_loop(self, interval_hours: int) -> None:
        """Background task that syncs usage data periodically"""
        while self.running:
            try:
                await self.billing_integration.sync_all_miners_usage(hours_back=interval_hours)
                await asyncio.sleep(interval_hours * 3600)
            except Exception as e:
                self.logger.error("Error in billing sync loop: %s", e)
                await asyncio.sleep(300)
