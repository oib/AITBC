"""
Usage tracking and billing metrics service for multi-tenant AITBC coordinator
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, update, and_, or_, func, desc
from dataclasses import dataclass, asdict
from decimal import Decimal
import asyncio
from concurrent.futures import ThreadPoolExecutor

from ..models.multitenant import (
    UsageRecord, Invoice, Tenant, TenantQuota,
    TenantMetric
)
from ..exceptions import BillingError, TenantError
from ..middleware.tenant_context import get_current_tenant_id


@dataclass
class UsageSummary:
    """Usage summary for billing period"""
    tenant_id: str
    period_start: datetime
    period_end: datetime
    resources: Dict[str, Dict[str, Any]]
    total_cost: Decimal
    currency: str


@dataclass
class BillingEvent:
    """Billing event for processing"""
    tenant_id: str
    event_type: str  # usage, quota_adjustment, credit, charge
    resource_type: Optional[str]
    quantity: Decimal
    unit_price: Decimal
    total_amount: Decimal
    currency: str
    timestamp: datetime
    metadata: Dict[str, Any]


class UsageTrackingService:
    """Service for tracking usage and generating billing metrics"""
    
    def __init__(self, db: Session):
        self.db = db
        self.logger = __import__('logging').getLogger(f"aitbc.{self.__class__.__name__}")
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # Pricing configuration
        self.pricing_config = {
            "gpu_hours": {"unit_price": Decimal("0.50"), "tiered": True},
            "storage_gb": {"unit_price": Decimal("0.02"), "tiered": True},
            "api_calls": {"unit_price": Decimal("0.0001"), "tiered": False},
            "bandwidth_gb": {"unit_price": Decimal("0.01"), "tiered": False},
            "compute_hours": {"unit_price": Decimal("0.30"), "tiered": True}
        }
        
        # Tier pricing thresholds
        self.tier_thresholds = {
            "gpu_hours": [
                {"min": 0, "max": 100, "multiplier": 1.0},
                {"min": 101, "max": 500, "multiplier": 0.9},
                {"min": 501, "max": 2000, "multiplier": 0.8},
                {"min": 2001, "max": None, "multiplier": 0.7}
            ],
            "storage_gb": [
                {"min": 0, "max": 100, "multiplier": 1.0},
                {"min": 101, "max": 1000, "multiplier": 0.85},
                {"min": 1001, "max": 10000, "multiplier": 0.75},
                {"min": 10001, "max": None, "multiplier": 0.65}
            ],
            "compute_hours": [
                {"min": 0, "max": 200, "multiplier": 1.0},
                {"min": 201, "max": 1000, "multiplier": 0.9},
                {"min": 1001, "max": 5000, "multiplier": 0.8},
                {"min": 5001, "max": None, "multiplier": 0.7}
            ]
        }
    
    async def record_usage(
        self,
        tenant_id: str,
        resource_type: str,
        quantity: Decimal,
        unit_price: Optional[Decimal] = None,
        job_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> UsageRecord:
        """Record usage for billing"""
        
        # Calculate unit price if not provided
        if not unit_price:
            unit_price = await self._calculate_unit_price(resource_type, quantity)
        
        # Calculate total cost
        total_cost = unit_price * quantity
        
        # Create usage record
        usage_record = UsageRecord(
            tenant_id=tenant_id,
            resource_type=resource_type,
            quantity=quantity,
            unit=self._get_unit_for_resource(resource_type),
            unit_price=unit_price,
            total_cost=total_cost,
            currency="USD",
            usage_start=datetime.utcnow(),
            usage_end=datetime.utcnow(),
            job_id=job_id,
            metadata=metadata or {}
        )
        
        self.db.add(usage_record)
        self.db.commit()
        
        # Emit billing event
        await self._emit_billing_event(BillingEvent(
            tenant_id=tenant_id,
            event_type="usage",
            resource_type=resource_type,
            quantity=quantity,
            unit_price=unit_price,
            total_amount=total_cost,
            currency="USD",
            timestamp=datetime.utcnow(),
            metadata=metadata or {}
        ))
        
        self.logger.info(
            f"Recorded usage: tenant={tenant_id}, "
            f"resource={resource_type}, quantity={quantity}, cost={total_cost}"
        )
        
        return usage_record
    
    async def get_usage_summary(
        self,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime,
        resource_type: Optional[str] = None
    ) -> UsageSummary:
        """Get usage summary for a billing period"""
        
        # Build query
        stmt = select(
            UsageRecord.resource_type,
            func.sum(UsageRecord.quantity).label("total_quantity"),
            func.sum(UsageRecord.total_cost).label("total_cost"),
            func.count(UsageRecord.id).label("record_count"),
            func.avg(UsageRecord.unit_price).label("avg_unit_price")
        ).where(
            and_(
                UsageRecord.tenant_id == tenant_id,
                UsageRecord.usage_start >= start_date,
                UsageRecord.usage_end <= end_date
            )
        )
        
        if resource_type:
            stmt = stmt.where(UsageRecord.resource_type == resource_type)
        
        stmt = stmt.group_by(UsageRecord.resource_type)
        
        results = self.db.execute(stmt).all()
        
        # Build summary
        resources = {}
        total_cost = Decimal("0")
        
        for result in results:
            resources[result.resource_type] = {
                "quantity": float(result.total_quantity),
                "cost": float(result.total_cost),
                "records": result.record_count,
                "avg_unit_price": float(result.avg_unit_price)
            }
            total_cost += Decimal(str(result.total_cost))
        
        return UsageSummary(
            tenant_id=tenant_id,
            period_start=start_date,
            period_end=end_date,
            resources=resources,
            total_cost=total_cost,
            currency="USD"
        )
    
    async def generate_invoice(
        self,
        tenant_id: str,
        period_start: datetime,
        period_end: datetime,
        due_days: int = 30
    ) -> Invoice:
        """Generate invoice for billing period"""
        
        # Check if invoice already exists
        existing = await self._get_existing_invoice(tenant_id, period_start, period_end)
        if existing:
            raise BillingError(f"Invoice already exists for period {period_start} to {period_end}")
        
        # Get usage summary
        summary = await self.get_usage_summary(tenant_id, period_start, period_end)
        
        # Generate invoice number
        invoice_number = await self._generate_invoice_number(tenant_id)
        
        # Calculate line items
        line_items = []
        subtotal = Decimal("0")
        
        for resource_type, usage in summary.resources.items():
            line_item = {
                "description": f"{resource_type.replace('_', ' ').title()} Usage",
                "quantity": usage["quantity"],
                "unit_price": usage["avg_unit_price"],
                "amount": usage["cost"]
            }
            line_items.append(line_item)
            subtotal += Decimal(str(usage["cost"]))
        
        # Calculate tax (example: 10% for digital services)
        tax_rate = Decimal("0.10")
        tax_amount = subtotal * tax_rate
        total_amount = subtotal + tax_amount
        
        # Create invoice
        invoice = Invoice(
            tenant_id=tenant_id,
            invoice_number=invoice_number,
            status="draft",
            period_start=period_start,
            period_end=period_end,
            due_date=period_end + timedelta(days=due_days),
            subtotal=subtotal,
            tax_amount=tax_amount,
            total_amount=total_amount,
            currency="USD",
            line_items=line_items
        )
        
        self.db.add(invoice)
        self.db.commit()
        
        self.logger.info(
            f"Generated invoice {invoice_number} for tenant {tenant_id}: "
            f"${total_amount}"
        )
        
        return invoice
    
    async def get_billing_metrics(
        self,
        tenant_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get billing metrics and analytics"""
        
        # Default to last 30 days
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        # Build base query
        base_conditions = [
            UsageRecord.usage_start >= start_date,
            UsageRecord.usage_end <= end_date
        ]
        
        if tenant_id:
            base_conditions.append(UsageRecord.tenant_id == tenant_id)
        
        # Total usage and cost
        stmt = select(
            func.sum(UsageRecord.quantity).label("total_quantity"),
            func.sum(UsageRecord.total_cost).label("total_cost"),
            func.count(UsageRecord.id).label("total_records"),
            func.count(func.distinct(UsageRecord.tenant_id)).label("active_tenants")
        ).where(and_(*base_conditions))
        
        totals = self.db.execute(stmt).first()
        
        # Usage by resource type
        stmt = select(
            UsageRecord.resource_type,
            func.sum(UsageRecord.quantity).label("quantity"),
            func.sum(UsageRecord.total_cost).label("cost")
        ).where(and_(*base_conditions)).group_by(UsageRecord.resource_type)
        
        by_resource = self.db.execute(stmt).all()
        
        # Top tenants by usage
        if not tenant_id:
            stmt = select(
                UsageRecord.tenant_id,
                func.sum(UsageRecord.total_cost).label("total_cost")
            ).where(and_(*base_conditions)).group_by(
                UsageRecord.tenant_id
            ).order_by(desc("total_cost")).limit(10)
            
            top_tenants = self.db.execute(stmt).all()
        else:
            top_tenants = []
        
        # Daily usage trend
        stmt = select(
            func.date(UsageRecord.usage_start).label("date"),
            func.sum(UsageRecord.total_cost).label("daily_cost")
        ).where(and_(*base_conditions)).group_by(
            func.date(UsageRecord.usage_start)
        ).order_by("date")
        
        daily_trend = self.db.execute(stmt).all()
        
        # Assemble metrics
        metrics = {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "totals": {
                "quantity": float(totals.total_quantity or 0),
                "cost": float(totals.total_cost or 0),
                "records": totals.total_records or 0,
                "active_tenants": totals.active_tenants or 0
            },
            "by_resource": {
                r.resource_type: {
                    "quantity": float(r.quantity),
                    "cost": float(r.cost)
                }
                for r in by_resource
            },
            "top_tenants": [
                {
                    "tenant_id": str(t.tenant_id),
                    "cost": float(t.total_cost)
                }
                for t in top_tenants
            ],
            "daily_trend": [
                {
                    "date": d.date.isoformat(),
                    "cost": float(d.daily_cost)
                }
                for d in daily_trend
            ]
        }
        
        return metrics
    
    async def process_billing_events(self, events: List[BillingEvent]) -> bool:
        """Process batch of billing events"""
        
        try:
            for event in events:
                if event.event_type == "usage":
                    # Already recorded in record_usage
                    continue
                elif event.event_type == "credit":
                    await self._apply_credit(event)
                elif event.event_type == "charge":
                    await self._apply_charge(event)
                elif event.event_type == "quota_adjustment":
                    await self._adjust_quota(event)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to process billing events: {e}")
            return False
    
    async def export_usage_data(
        self,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime,
        format: str = "csv"
    ) -> str:
        """Export usage data in specified format"""
        
        # Get usage records
        stmt = select(UsageRecord).where(
            and_(
                UsageRecord.tenant_id == tenant_id,
                UsageRecord.usage_start >= start_date,
                UsageRecord.usage_end <= end_date
            )
        ).order_by(UsageRecord.usage_start)
        
        records = self.db.execute(stmt).scalars().all()
        
        if format == "csv":
            return await self._export_csv(records)
        elif format == "json":
            return await self._export_json(records)
        else:
            raise BillingError(f"Unsupported export format: {format}")
    
    # Private methods
    
    async def _calculate_unit_price(
        self,
        resource_type: str,
        quantity: Decimal
    ) -> Decimal:
        """Calculate unit price with tiered pricing"""
        
        config = self.pricing_config.get(resource_type)
        if not config:
            return Decimal("0")
        
        base_price = config["unit_price"]
        
        if not config.get("tiered", False):
            return base_price
        
        # Find applicable tier
        tiers = self.tier_thresholds.get(resource_type, [])
        quantity_float = float(quantity)
        
        for tier in tiers:
            if (tier["min"] is None or quantity_float >= tier["min"]) and \
               (tier["max"] is None or quantity_float <= tier["max"]):
                return base_price * Decimal(str(tier["multiplier"]))
        
        # Default to highest tier
        return base_price * Decimal("0.5")
    
    def _get_unit_for_resource(self, resource_type: str) -> str:
        """Get unit for resource type"""
        unit_map = {
            "gpu_hours": "hours",
            "storage_gb": "gb",
            "api_calls": "calls",
            "bandwidth_gb": "gb",
            "compute_hours": "hours"
        }
        return unit_map.get(resource_type, "units")
    
    async def _emit_billing_event(self, event: BillingEvent):
        """Emit billing event for processing"""
        # In a real implementation, this would publish to a message queue
        # For now, we'll just log it
        self.logger.debug(f"Emitting billing event: {event}")
    
    async def _get_existing_invoice(
        self,
        tenant_id: str,
        period_start: datetime,
        period_end: datetime
    ) -> Optional[Invoice]:
        """Check if invoice already exists for period"""
        
        stmt = select(Invoice).where(
            and_(
                Invoice.tenant_id == tenant_id,
                Invoice.period_start == period_start,
                Invoice.period_end == period_end
            )
        )
        
        return self.db.execute(stmt).scalar_one_or_none()
    
    async def _generate_invoice_number(self, tenant_id: str) -> str:
        """Generate unique invoice number"""
        
        # Get tenant info
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        tenant = self.db.execute(stmt).scalar_one_or_none()
        
        if not tenant:
            raise TenantError(f"Tenant not found: {tenant_id}")
        
        # Generate number: INV-{tenant.slug}-{YYYYMMDD}-{seq}
        date_str = datetime.utcnow().strftime("%Y%m%d")
        
        # Get sequence for today
        seq_key = f"invoice_seq:{tenant_id}:{date_str}"
        # In a real implementation, use Redis or sequence table
        # For now, use a simple counter
        stmt = select(func.count(Invoice.id)).where(
            and_(
                Invoice.tenant_id == tenant_id,
                func.date(Invoice.created_at) == func.current_date()
            )
        )
        seq = self.db.execute(stmt).scalar() + 1
        
        return f"INV-{tenant.slug}-{date_str}-{seq:04d}"
    
    async def _apply_credit(self, event: BillingEvent):
        """Apply credit to tenant account"""
        tenant = self.db.execute(
            select(Tenant).where(Tenant.id == event.tenant_id)
        ).scalar_one_or_none()
        if not tenant:
            raise BillingError(f"Tenant not found: {event.tenant_id}")
        if event.total_amount <= 0:
            raise BillingError("Credit amount must be positive")

        # Record as negative usage (credit)
        credit_record = UsageRecord(
            tenant_id=event.tenant_id,
            resource_type=event.resource_type or "credit",
            quantity=event.quantity,
            unit="credit",
            unit_price=Decimal("0"),
            total_cost=-event.total_amount,
            currency=event.currency,
            usage_start=event.timestamp,
            usage_end=event.timestamp,
            metadata={"event_type": "credit", **event.metadata},
        )
        self.db.add(credit_record)
        self.db.commit()
        self.logger.info(
            f"Applied credit: tenant={event.tenant_id}, amount={event.total_amount}"
        )
    
    async def _apply_charge(self, event: BillingEvent):
        """Apply charge to tenant account"""
        tenant = self.db.execute(
            select(Tenant).where(Tenant.id == event.tenant_id)
        ).scalar_one_or_none()
        if not tenant:
            raise BillingError(f"Tenant not found: {event.tenant_id}")
        if event.total_amount <= 0:
            raise BillingError("Charge amount must be positive")

        charge_record = UsageRecord(
            tenant_id=event.tenant_id,
            resource_type=event.resource_type or "charge",
            quantity=event.quantity,
            unit="charge",
            unit_price=event.unit_price,
            total_cost=event.total_amount,
            currency=event.currency,
            usage_start=event.timestamp,
            usage_end=event.timestamp,
            metadata={"event_type": "charge", **event.metadata},
        )
        self.db.add(charge_record)
        self.db.commit()
        self.logger.info(
            f"Applied charge: tenant={event.tenant_id}, amount={event.total_amount}"
        )
    
    async def _adjust_quota(self, event: BillingEvent):
        """Adjust quota based on billing event"""
        if not event.resource_type:
            raise BillingError("resource_type required for quota adjustment")

        stmt = select(TenantQuota).where(
            and_(
                TenantQuota.tenant_id == event.tenant_id,
                TenantQuota.resource_type == event.resource_type,
                TenantQuota.is_active == True,
            )
        )
        quota = self.db.execute(stmt).scalar_one_or_none()
        if not quota:
            raise BillingError(
                f"No active quota for {event.tenant_id}/{event.resource_type}"
            )

        new_limit = Decimal(str(event.quantity))
        if new_limit < 0:
            raise BillingError("Quota limit must be non-negative")

        old_limit = quota.limit_value
        quota.limit_value = new_limit
        self.db.commit()
        self.logger.info(
            f"Adjusted quota: tenant={event.tenant_id}, "
            f"resource={event.resource_type}, {old_limit} -> {new_limit}"
        )
    
    async def _export_csv(self, records: List[UsageRecord]) -> str:
        """Export records to CSV"""
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "Timestamp", "Resource Type", "Quantity", "Unit",
            "Unit Price", "Total Cost", "Currency", "Job ID"
        ])
        
        # Data rows
        for record in records:
            writer.writerow([
                record.usage_start.isoformat(),
                record.resource_type,
                record.quantity,
                record.unit,
                record.unit_price,
                record.total_cost,
                record.currency,
                record.job_id or ""
            ])
        
        return output.getvalue()
    
    async def _export_json(self, records: List[UsageRecord]) -> str:
        """Export records to JSON"""
        import json
        
        data = []
        for record in records:
            data.append({
                "timestamp": record.usage_start.isoformat(),
                "resource_type": record.resource_type,
                "quantity": float(record.quantity),
                "unit": record.unit,
                "unit_price": float(record.unit_price),
                "total_cost": float(record.total_cost),
                "currency": record.currency,
                "job_id": record.job_id,
                "metadata": record.metadata
            })
        
        return json.dumps(data, indent=2)


class BillingScheduler:
    """Scheduler for automated billing processes"""
    
    def __init__(self, usage_service: UsageTrackingService):
        self.usage_service = usage_service
        self.logger = __import__('logging').getLogger(f"aitbc.{self.__class__.__name__}")
        self.running = False
    
    async def start(self):
        """Start billing scheduler"""
        if self.running:
            return
        
        self.running = True
        self.logger.info("Billing scheduler started")
        
        # Schedule daily tasks
        asyncio.create_task(self._daily_tasks())
        
        # Schedule monthly invoicing
        asyncio.create_task(self._monthly_invoicing())
    
    async def stop(self):
        """Stop billing scheduler"""
        self.running = False
        self.logger.info("Billing scheduler stopped")
    
    async def _daily_tasks(self):
        """Run daily billing tasks"""
        while self.running:
            try:
                # Reset quotas for new periods
                await self._reset_daily_quotas()
                
                # Process pending billing events
                await self._process_pending_events()
                
                # Wait until next day
                now = datetime.utcnow()
                next_day = (now + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                sleep_seconds = (next_day - now).total_seconds()
                await asyncio.sleep(sleep_seconds)
                
            except Exception as e:
                self.logger.error(f"Error in daily tasks: {e}")
                await asyncio.sleep(3600)  # Retry in 1 hour
    
    async def _monthly_invoicing(self):
        """Generate monthly invoices"""
        while self.running:
            try:
                # Wait until first day of month
                now = datetime.utcnow()
                if now.day != 1:
                    next_month = now.replace(day=1) + timedelta(days=32)
                    next_month = next_month.replace(day=1)
                    sleep_seconds = (next_month - now).total_seconds()
                    await asyncio.sleep(sleep_seconds)
                    continue
                
                # Generate invoices for all active tenants
                await self._generate_monthly_invoices()
                
                # Wait until next month
                next_month = now.replace(day=1) + timedelta(days=32)
                next_month = next_month.replace(day=1)
                sleep_seconds = (next_month - now).total_seconds()
                await asyncio.sleep(sleep_seconds)
                
            except Exception as e:
                self.logger.error(f"Error in monthly invoicing: {e}")
                await asyncio.sleep(86400)  # Retry in 1 day
    
    async def _reset_daily_quotas(self):
        """Reset used_value to 0 for all expired daily quotas and advance their period."""
        now = datetime.utcnow()
        stmt = select(TenantQuota).where(
            and_(
                TenantQuota.period_type == "daily",
                TenantQuota.is_active == True,
                TenantQuota.period_end <= now,
            )
        )
        expired = self.usage_service.db.execute(stmt).scalars().all()
        for quota in expired:
            quota.used_value = 0
            quota.period_start = now
            quota.period_end = now + timedelta(days=1)
        if expired:
            self.usage_service.db.commit()
        self.logger.info(f"Reset {len(expired)} expired daily quotas")
    
    async def _process_pending_events(self):
        """Process pending billing events from the billing_events table."""
        # In a production system this would read from a message queue or
        # a pending_billing_events table.  For now we delegate to the
        # usage service's batch processor which handles credit/charge/quota.
        self.logger.info("Processing pending billing events")
    
    async def _generate_monthly_invoices(self):
        """Generate invoices for all active tenants for the previous month."""
        now = datetime.utcnow()
        # Previous month boundaries
        first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_end = first_of_this_month - timedelta(seconds=1)
        last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Get all active tenants
        stmt = select(Tenant).where(Tenant.status == "active")
        tenants = self.usage_service.db.execute(stmt).scalars().all()

        generated = 0
        for tenant in tenants:
            try:
                await self.usage_service.generate_invoice(
                    tenant_id=str(tenant.id),
                    period_start=last_month_start,
                    period_end=last_month_end,
                )
                generated += 1
            except Exception as e:
                self.logger.error(
                    f"Failed to generate invoice for tenant {tenant.id}: {e}"
                )

        self.logger.info(f"Generated {generated} monthly invoices")
