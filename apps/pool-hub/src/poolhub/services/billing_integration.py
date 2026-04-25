"""
Billing Integration Service for Pool-Hub
Integrates pool-hub usage data with coordinator-api's billing system.
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any

from aitbc import get_logger, AsyncAITBCHTTPClient, NetworkError

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from ..models import Miner, ServiceConfig, MatchRequest, MatchResult, Feedback
from ..settings import settings

logger = get_logger(__name__)


class BillingIntegration:
    """Service for integrating pool-hub with coordinator-api billing"""

    def __init__(self, db: Session):
        self.db = db
        self.coordinator_billing_url = getattr(
            settings, "coordinator_billing_url", "http://localhost:8011"
        )
        self.coordinator_api_key = getattr(
            settings, "coordinator_api_key", None
        )
        self.logger = get_logger(__name__)

        # Resource type mappings
        self.resource_type_mapping = {
            "gpu_hours": "gpu_hours",
            "storage_gb": "storage_gb",
            "api_calls": "api_calls",
            "compute_hours": "compute_hours",
        }

        # Pricing configuration (fallback if coordinator-api pricing not available)
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
        unit_price: Optional[Decimal] = None,
        job_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record usage data to coordinator-api billing system"""

        # Use fallback pricing if not provided
        if not unit_price:
            pricing_config = self.fallback_pricing.get(resource_type, {})
            unit_price = pricing_config.get("unit_price", Decimal("0"))

        # Calculate total cost
        total_cost = unit_price * quantity

        # Prepare billing event payload
        billing_event = {
            "tenant_id": tenant_id,
            "event_type": "usage",
            "resource_type": resource_type,
            "quantity": float(quantity),
            "unit_price": float(unit_price),
            "total_amount": float(total_cost),
            "currency": "USD",
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }

        if job_id:
            billing_event["job_id"] = job_id

        # Send to coordinator-api
        try:
            response = await self._send_billing_event(billing_event)
            self.logger.info(
                f"Recorded usage: tenant={tenant_id}, resource={resource_type}, "
                f"quantity={quantity}, cost={total_cost}"
            )
            return response
        except Exception as e:
            self.logger.error(f"Failed to record usage: {e}")
            # Queue for retry in production
            return {"status": "failed", "error": str(e)}

    async def sync_miner_usage(
        self, miner_id: str, start_date: datetime, end_date: datetime
    ) -> Dict[str, Any]:
        """Sync usage data for a miner to coordinator-api billing"""

        # Get miner information
        stmt = select(Miner).where(Miner.miner_id == miner_id)
        miner = self.db.execute(stmt).scalar_one_or_none()

        if not miner:
            raise ValueError(f"Miner not found: {miner_id}")

        # Map miner to tenant (simplified - in production, use proper mapping)
        tenant_id = miner_id  # For now, use miner_id as tenant_id

        # Collect usage data from pool-hub
        usage_data = await self._collect_miner_usage(miner_id, start_date, end_date)

        # Send each usage record to coordinator-api
        results = []
        for resource_type, quantity in usage_data.items():
            if quantity > 0:
                result = await self.record_usage(
                    tenant_id=tenant_id,
                    resource_type=resource_type,
                    quantity=Decimal(str(quantity)),
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

    async def sync_all_miners_usage(
        self, hours_back: int = 24
    ) -> Dict[str, Any]:
        """Sync usage data for all miners to coordinator-api billing"""

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(hours=hours_back)

        # Get all miners
        stmt = select(Miner)
        miners = self.db.execute(stmt).scalars().all()

        results = {
            "sync_period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "miners_processed": 0,
            "miners_failed": 0,
            "total_usage_records": 0,
            "details": [],
        }

        for miner in miners:
            try:
                result = await self.sync_miner_usage(miner.miner_id, start_date, end_date)
                results["details"].append(result)
                results["miners_processed"] += 1
                results["total_usage_records"] += result["usage_records"]
            except Exception as e:
                self.logger.error(f"Failed to sync usage for miner {miner.miner_id}: {e}")
                results["miners_failed"] += 1

        self.logger.info(
            f"Usage sync complete: processed={results['miners_processed']}, "
            f"failed={results['miners_failed']}, records={results['total_usage_records']}"
        )

        return results

    async def _collect_miner_usage(
        self, miner_id: str, start_date: datetime, end_date: datetime
    ) -> Dict[str, float]:
        """Collect usage data for a miner from pool-hub"""

        usage_data = {
            "gpu_hours": 0.0,
            "api_calls": 0.0,
            "compute_hours": 0.0,
        }

        # Count match requests as API calls
        stmt = select(func.count(MatchRequest.id)).where(
            and_(
                MatchRequest.created_at >= start_date,
                MatchRequest.created_at <= end_date,
            )
        )
        # Filter by miner_id if match requests have that field
        # For now, count all requests (simplified)
        api_calls = self.db.execute(stmt).scalar() or 0
        usage_data["api_calls"] = float(api_calls)

        # Calculate compute hours from match results
        stmt = (
            select(MatchResult)
            .where(
                and_(
                    MatchResult.miner_id == miner_id,
                    MatchResult.created_at >= start_date,
                    MatchResult.created_at <= end_date,
                )
            )
            .where(MatchResult.eta_ms.isnot_(None))
        )

        results = self.db.execute(stmt).scalars().all()

        # Estimate compute hours from response times (simplified)
        # In production, use actual job duration
        total_compute_time_ms = sum(r.eta_ms for r in results if r.eta_ms)
        compute_hours = (total_compute_time_ms / 1000 / 3600) if results else 0.0
        usage_data["compute_hours"] = compute_hours

        # Estimate GPU hours from miner capacity and compute hours
        # In production, use actual GPU utilization data
        gpu_hours = compute_hours * 1.5  # Estimate 1.5 GPUs per job on average
        usage_data["gpu_hours"] = gpu_hours

        return usage_data

    async def _send_billing_event(self, billing_event: Dict[str, Any]) -> Dict[str, Any]:
        """Send billing event to coordinator-api"""

        url = f"{self.coordinator_billing_url}/api/billing/usage"

        headers = {"Content-Type": "application/json"}
        if self.coordinator_api_key:
            headers["Authorization"] = f"Bearer {self.coordinator_api_key}"

        client = AsyncAITBCHTTPClient(base_url=self.coordinator_billing_url, headers=headers, timeout=30)
        response = await client.async_post("/api/billing/usage", json=billing_event)

        if response:
            return response
        else:
            raise NetworkError("Failed to send billing event")

    async def get_billing_metrics(
        self, tenant_id: Optional[str] = None, hours: int = 24
    ) -> Dict[str, Any]:
        """Get billing metrics from coordinator-api"""

        headers = {}
        if self.coordinator_api_key:
            headers["Authorization"] = f"Bearer {self.coordinator_api_key}"

        client = AsyncAITBCHTTPClient(base_url=self.coordinator_billing_url, headers=headers, timeout=30)
        params = {"hours": hours}
        if tenant_id:
            params["tenant_id"] = tenant_id

        response = await client.async_get("/api/billing/metrics", params=params)

        if response:
            return response
        else:
            raise NetworkError("Failed to get billing metrics")

    async def trigger_invoice_generation(
        self, tenant_id: str, period_start: datetime, period_end: datetime
    ) -> Dict[str, Any]:
        """Trigger invoice generation in coordinator-api"""

        payload = {
            "tenant_id": tenant_id,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
        }

        headers = {"Content-Type": "application/json"}
        if self.coordinator_api_key:
            headers["Authorization"] = f"Bearer {self.coordinator_api_key}"

        client = AsyncAITBCHTTPClient(base_url=self.coordinator_billing_url, headers=headers, timeout=30)
        response = await client.async_post("/api/billing/invoice", json=payload)

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

    async def start(self, sync_interval_hours: int = 1):
        """Start the billing synchronization scheduler"""

        if self.running:
            return

        self.running = True
        self.logger.info("Billing Integration scheduler started")

        # Start sync loop
        asyncio.create_task(self._sync_loop(sync_interval_hours))

    async def stop(self):
        """Stop the billing synchronization scheduler"""

        self.running = False
        self.logger.info("Billing Integration scheduler stopped")

    async def _sync_loop(self, interval_hours: int):
        """Background task that syncs usage data periodically"""

        while self.running:
            try:
                await self.billing_integration.sync_all_miners_usage(
                    hours_back=interval_hours
                )

                # Wait for next sync interval
                await asyncio.sleep(interval_hours * 3600)

            except Exception as e:
                self.logger.error(f"Error in billing sync loop: {e}")
                await asyncio.sleep(300)  # Retry in 5 minutes
