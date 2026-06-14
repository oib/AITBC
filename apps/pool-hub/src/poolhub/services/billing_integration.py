"""
Billing Integration Service for Pool-Hub
Integrates pool-hub usage data with coordinator-api's billing system.
"""
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session
from aitbc import AsyncAITBCHTTPClient, NetworkError, get_logger
from ..models import MatchRequest, MatchResult, Miner
from ..settings import settings
logger = get_logger(__name__)

class BillingIntegration:
    """Service for integrating pool-hub with coordinator-api billing"""

    def __init__(self, db: Session):
        self.db = db
        self.coordinator_billing_url = getattr(settings, 'coordinator_billing_url', 'http://localhost:8011')
        self.coordinator_api_key = getattr(settings, 'coordinator_api_key', None)
        self.logger = get_logger(__name__)
        self.resource_type_mapping = {'gpu_hours': 'gpu_hours', 'storage_gb': 'storage_gb', 'api_calls': 'api_calls', 'compute_hours': 'compute_hours'}
        self.fallback_pricing = {'gpu_hours': {'unit_price': Decimal('0.50')}, 'storage_gb': {'unit_price': Decimal('0.02')}, 'api_calls': {'unit_price': Decimal('0.0001')}, 'compute_hours': {'unit_price': Decimal('0.30')}}

    async def record_usage(self, tenant_id: str, resource_type: str, quantity: Decimal, unit_price: Decimal | None=None, job_id: str | None=None, metadata: dict[str, Any] | None=None) -> dict[str, Any]:
        """Record usage data to coordinator-api billing system"""
        if not unit_price:
            pricing_config = self.fallback_pricing.get(resource_type, {})
            unit_price = pricing_config.get('unit_price', Decimal('0'))
        total_cost = unit_price * quantity
        billing_event = {'tenant_id': tenant_id, 'event_type': 'usage', 'resource_type': resource_type, 'quantity': float(quantity), 'unit_price': float(unit_price), 'total_amount': float(total_cost), 'currency': 'USD', 'timestamp': datetime.now(UTC).isoformat(), 'metadata': metadata or {}}
        if job_id:
            billing_event['job_id'] = job_id
        try:
            response = await self._send_billing_event(billing_event)
            self.logger.info('Recorded usage: tenant=%s, resource=%s, quantity=%s, cost=%s', tenant_id, resource_type, quantity, total_cost)
            return response
        except Exception as e:
            self.logger.error('Failed to record usage: %s', e)
            return {'status': 'failed', 'error': str(e)}

    async def sync_miner_usage(self, miner_id: str, start_date: datetime, end_date: datetime) -> dict[str, Any]:
        """Sync usage data for a miner to coordinator-api billing"""
        stmt = select(Miner).where(Miner.miner_id == miner_id)
        miner = self.db.execute(stmt).scalar_one_or_none()
        if not miner:
            raise ValueError(f'Miner not found: {miner_id}')
        tenant_id = miner_id
        usage_data = await self._collect_miner_usage(miner_id, start_date, end_date)
        results = []
        for resource_type, quantity in usage_data.items():
            if quantity > 0:
                result = await self.record_usage(tenant_id=tenant_id, resource_type=resource_type, quantity=Decimal(str(quantity)), metadata={'miner_id': miner_id, 'sync_type': 'miner_usage'})
                results.append(result)
        return {'miner_id': miner_id, 'tenant_id': tenant_id, 'period': {'start': start_date.isoformat(), 'end': end_date.isoformat()}, 'usage_records': len(results), 'results': results}

    async def sync_all_miners_usage(self, hours_back: int=24) -> dict[str, Any]:
        """Sync usage data for all miners to coordinator-api billing"""
        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(hours=hours_back)
        stmt = select(Miner)
        miners = self.db.execute(stmt).scalars().all()
        results: dict[str, Any] = {'sync_period': {'start': start_date.isoformat(), 'end': end_date.isoformat()}, 'miners_processed': 0, 'miners_failed': 0, 'total_usage_records': 0, 'details': []}
        for miner in miners:
            try:
                result = await self.sync_miner_usage(miner.miner_id, start_date, end_date)
                results['details'].append(result)
                results['miners_processed'] += 1
                results['total_usage_records'] += result['usage_records']
            except Exception as e:
                self.logger.error('Failed to sync usage for miner %s: %s', miner.miner_id, e)
                results['miners_failed'] += 1
        self.logger.info('Usage sync complete: processed=%s, failed=%s, records=%s', results['miners_processed'], results['miners_failed'], results['total_usage_records'])
        return results

    async def _collect_miner_usage(self, miner_id: str, start_date: datetime, end_date: datetime) -> dict[str, float]:
        """Collect usage data for a miner from pool-hub"""
        usage_data = {'gpu_hours': 0.0, 'api_calls': 0.0, 'compute_hours': 0.0}
        count_stmt = select(func.count(MatchRequest.id)).where(and_(MatchRequest.created_at >= start_date, MatchRequest.created_at <= end_date))
        api_calls = self.db.execute(count_stmt).scalar() or 0
        usage_data['api_calls'] = float(api_calls)
        result_stmt = select(MatchResult).where(and_(MatchResult.miner_id == miner_id, MatchResult.created_at >= start_date, MatchResult.created_at <= end_date)).where(MatchResult.eta_ms.isnot_(None))
        results = self.db.execute(result_stmt).scalars().all()
        total_compute_time_ms = sum((r.eta_ms for r in results if r.eta_ms))
        compute_hours = total_compute_time_ms / 1000 / 3600 if results else 0.0
        usage_data['compute_hours'] = compute_hours
        gpu_hours = compute_hours * 1.5
        usage_data['gpu_hours'] = gpu_hours
        return usage_data

    async def _send_billing_event(self, billing_event: dict[str, Any]) -> dict[str, Any]:
        """Send billing event to coordinator-api"""
        url = f'{self.coordinator_billing_url}/api/billing/usage'
        headers = {'Content-Type': 'application/json'}
        if self.coordinator_api_key:
            headers['Authorization'] = f'Bearer {self.coordinator_api_key}'
        client = AsyncAITBCHTTPClient(base_url=self.coordinator_billing_url, headers=headers, timeout=30)
        response = await client.async_post('/api/billing/usage', json=billing_event)
        if response:
            return response  # type: ignore[no-any-return]
        else:
            raise NetworkError('Failed to send billing event')

    async def get_billing_metrics(self, tenant_id: str | None=None, hours: int=24) -> dict[str, Any]:
        """Get billing metrics from coordinator-api"""
        headers = {}
        if self.coordinator_api_key:
            headers['Authorization'] = f'Bearer {self.coordinator_api_key}'
        client = AsyncAITBCHTTPClient(base_url=self.coordinator_billing_url, headers=headers, timeout=30)
        params: dict[str, Any] = {'hours': hours}
        if tenant_id:
            params['tenant_id'] = tenant_id
        response = await client.async_get('/api/billing/metrics', params=params)
        if response:
            return response  # type: ignore[no-any-return]
        else:
            raise NetworkError('Failed to get billing metrics')

    async def trigger_invoice_generation(self, tenant_id: str, period_start: datetime, period_end: datetime) -> dict[str, Any]:
        """Trigger invoice generation in coordinator-api"""
        payload = {'tenant_id': tenant_id, 'period_start': period_start.isoformat(), 'period_end': period_end.isoformat()}
        headers = {'Content-Type': 'application/json'}
        if self.coordinator_api_key:
            headers['Authorization'] = f'Bearer {self.coordinator_api_key}'
        client = AsyncAITBCHTTPClient(base_url=self.coordinator_billing_url, headers=headers, timeout=30)
        response = await client.async_post('/api/billing/invoice', json=payload)
        if response:
            return response  # type: ignore[no-any-return]
        else:
            raise NetworkError('Failed to trigger invoice generation')

class BillingIntegrationScheduler:
    """Scheduler for automated billing synchronization"""

    def __init__(self, billing_integration: BillingIntegration):
        self.billing_integration = billing_integration
        self.logger = get_logger(__name__)
        self.running = False

    async def start(self, sync_interval_hours: int=1) -> None:
        """Start the billing synchronization scheduler"""
        if self.running:
            return
        self.running = True
        self.logger.info('Billing Integration scheduler started')
        asyncio.create_task(self._sync_loop(sync_interval_hours))

    async def stop(self) -> None:
        """Stop the billing synchronization scheduler"""
        self.running = False
        self.logger.info('Billing Integration scheduler stopped')

    async def _sync_loop(self, interval_hours: int) -> None:
        """Background task that syncs usage data periodically"""
        while self.running:
            try:
                await self.billing_integration.sync_all_miners_usage(hours_back=interval_hours)
                await asyncio.sleep(interval_hours * 3600)
            except Exception as e:
                self.logger.error('Error in billing sync loop: %s', e)
                await asyncio.sleep(300)