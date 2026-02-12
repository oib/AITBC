"""
Tests for coordinator billing stubs: usage tracking, billing events, and tenant context.

Uses lightweight in-memory mocks to avoid PostgreSQL/UUID dependencies.
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass

import pytest


# ---------------------------------------------------------------------------
# Lightweight stubs for the ORM models so we don't need a real DB
# ---------------------------------------------------------------------------

@dataclass
class FakeTenant:
    id: str
    slug: str
    name: str
    status: str = "active"
    plan: str = "basic"
    contact_email: str = "t@test.com"
    billing_email: str = "b@test.com"
    settings: dict = None
    features: dict = None
    balance: Decimal = Decimal("100.00")

    def __post_init__(self):
        self.settings = self.settings or {}
        self.features = self.features or {}


@dataclass
class FakeQuota:
    id: str
    tenant_id: str
    resource_type: str
    limit_value: Decimal
    used_value: Decimal = Decimal("0")
    period_type: str = "daily"
    period_start: datetime = None
    period_end: datetime = None
    is_active: bool = True

    def __post_init__(self):
        if self.period_start is None:
            self.period_start = datetime.utcnow() - timedelta(hours=1)
        if self.period_end is None:
            self.period_end = datetime.utcnow() + timedelta(hours=23)


@dataclass
class FakeUsageRecord:
    id: str
    tenant_id: str
    resource_type: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    total_cost: Decimal
    currency: str = "USD"
    usage_start: datetime = None
    usage_end: datetime = None
    job_id: str = None
    metadata: dict = None


# ---------------------------------------------------------------------------
# In-memory billing store used by the implementations under test
# ---------------------------------------------------------------------------

class InMemoryBillingStore:
    """Replaces the DB session for testing."""

    def __init__(self):
        self.tenants: dict[str, FakeTenant] = {}
        self.quotas: list[FakeQuota] = []
        self.usage_records: list[FakeUsageRecord] = []
        self.credits: list[dict] = []
        self.charges: list[dict] = []
        self.invoices_generated: list[str] = []
        self.pending_events: list[dict] = []

    # helpers
    def get_tenant(self, tenant_id: str):
        return self.tenants.get(tenant_id)

    def get_active_quota(self, tenant_id: str, resource_type: str):
        now = datetime.utcnow()
        for q in self.quotas:
            if (q.tenant_id == tenant_id
                    and q.resource_type == resource_type
                    and q.is_active
                    and q.period_start <= now <= q.period_end):
                return q
        return None


# ---------------------------------------------------------------------------
# Implementations (the actual code we're testing / implementing)
# ---------------------------------------------------------------------------

async def apply_credit(store: InMemoryBillingStore, tenant_id: str, amount: Decimal, reason: str = "") -> bool:
    """Apply credit to tenant account."""
    tenant = store.get_tenant(tenant_id)
    if not tenant:
        raise ValueError(f"Tenant not found: {tenant_id}")
    if amount <= 0:
        raise ValueError("Credit amount must be positive")
    tenant.balance += amount
    store.credits.append({
        "tenant_id": tenant_id,
        "amount": amount,
        "reason": reason,
        "timestamp": datetime.utcnow(),
    })
    return True


async def apply_charge(store: InMemoryBillingStore, tenant_id: str, amount: Decimal, reason: str = "") -> bool:
    """Apply charge to tenant account."""
    tenant = store.get_tenant(tenant_id)
    if not tenant:
        raise ValueError(f"Tenant not found: {tenant_id}")
    if amount <= 0:
        raise ValueError("Charge amount must be positive")
    if tenant.balance < amount:
        raise ValueError(f"Insufficient balance: {tenant.balance} < {amount}")
    tenant.balance -= amount
    store.charges.append({
        "tenant_id": tenant_id,
        "amount": amount,
        "reason": reason,
        "timestamp": datetime.utcnow(),
    })
    return True


async def adjust_quota(
    store: InMemoryBillingStore,
    tenant_id: str,
    resource_type: str,
    new_limit: Decimal,
) -> bool:
    """Adjust quota limit for a tenant resource."""
    quota = store.get_active_quota(tenant_id, resource_type)
    if not quota:
        raise ValueError(f"No active quota for {tenant_id}/{resource_type}")
    if new_limit < 0:
        raise ValueError("Quota limit must be non-negative")
    quota.limit_value = new_limit
    return True


async def reset_daily_quotas(store: InMemoryBillingStore) -> int:
    """Reset used_value to 0 for all daily quotas whose period has ended."""
    now = datetime.utcnow()
    count = 0
    for q in store.quotas:
        if q.period_type == "daily" and q.is_active and q.period_end <= now:
            q.used_value = Decimal("0")
            q.period_start = now
            q.period_end = now + timedelta(days=1)
            count += 1
    return count


async def process_pending_events(store: InMemoryBillingStore) -> int:
    """Process all pending billing events and clear the queue."""
    processed = len(store.pending_events)
    for event in store.pending_events:
        etype = event.get("event_type")
        tid = event.get("tenant_id")
        amount = Decimal(str(event.get("amount", 0)))
        if etype == "credit":
            await apply_credit(store, tid, amount, reason="pending_event")
        elif etype == "charge":
            await apply_charge(store, tid, amount, reason="pending_event")
    store.pending_events.clear()
    return processed


async def generate_monthly_invoices(store: InMemoryBillingStore) -> list[str]:
    """Generate invoices for all active tenants with usage."""
    generated = []
    for tid, tenant in store.tenants.items():
        if tenant.status != "active":
            continue
        tenant_usage = [r for r in store.usage_records if r.tenant_id == tid]
        if not tenant_usage:
            continue
        total = sum(r.total_cost for r in tenant_usage)
        inv_id = f"INV-{tenant.slug}-{datetime.utcnow().strftime('%Y%m')}-{len(generated)+1:04d}"
        store.invoices_generated.append(inv_id)
        generated.append(inv_id)
    return generated


async def extract_from_token(token: str, secret: str = "test-secret") -> dict | None:
    """Extract tenant_id from a JWT-like token. Returns claims dict or None."""
    import json, hmac, hashlib, base64
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        # Verify signature (HS256-like)
        payload_b64 = parts[1]
        sig = parts[2]
        expected_sig = hmac.new(
            secret.encode(), f"{parts[0]}.{payload_b64}".encode(), hashlib.sha256
        ).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected_sig):
            return None
        # Decode payload
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        if "tenant_id" not in payload:
            return None
        return payload
    except Exception:
        return None


def _make_token(claims: dict, secret: str = "test-secret") -> str:
    """Helper to create a test token."""
    import json, hmac, hashlib, base64
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    sig = hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).hexdigest()[:16]
    return f"{header}.{payload}.{sig}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store():
    s = InMemoryBillingStore()
    s.tenants["t1"] = FakeTenant(id="t1", slug="acme", name="Acme Corp", balance=Decimal("500.00"))
    s.tenants["t2"] = FakeTenant(id="t2", slug="beta", name="Beta Inc", balance=Decimal("50.00"), status="inactive")
    s.quotas.append(FakeQuota(
        id="q1", tenant_id="t1", resource_type="gpu_hours",
        limit_value=Decimal("100"), used_value=Decimal("40"),
    ))
    s.quotas.append(FakeQuota(
        id="q2", tenant_id="t1", resource_type="api_calls",
        limit_value=Decimal("10000"), used_value=Decimal("5000"),
        period_type="daily",
        period_start=datetime.utcnow() - timedelta(days=2),
        period_end=datetime.utcnow() - timedelta(hours=1),  # expired
    ))
    return s


# ---------------------------------------------------------------------------
# Tests: apply_credit
# ---------------------------------------------------------------------------

class TestApplyCredit:
    @pytest.mark.asyncio
    async def test_credit_increases_balance(self, store):
        await apply_credit(store, "t1", Decimal("25.00"), reason="promo")
        assert store.tenants["t1"].balance == Decimal("525.00")
        assert len(store.credits) == 1
        assert store.credits[0]["amount"] == Decimal("25.00")

    @pytest.mark.asyncio
    async def test_credit_unknown_tenant_raises(self, store):
        with pytest.raises(ValueError, match="Tenant not found"):
            await apply_credit(store, "unknown", Decimal("10"))

    @pytest.mark.asyncio
    async def test_credit_zero_or_negative_raises(self, store):
        with pytest.raises(ValueError, match="positive"):
            await apply_credit(store, "t1", Decimal("0"))
        with pytest.raises(ValueError, match="positive"):
            await apply_credit(store, "t1", Decimal("-5"))


# ---------------------------------------------------------------------------
# Tests: apply_charge
# ---------------------------------------------------------------------------

class TestApplyCharge:
    @pytest.mark.asyncio
    async def test_charge_decreases_balance(self, store):
        await apply_charge(store, "t1", Decimal("100.00"), reason="usage")
        assert store.tenants["t1"].balance == Decimal("400.00")
        assert len(store.charges) == 1

    @pytest.mark.asyncio
    async def test_charge_insufficient_balance_raises(self, store):
        with pytest.raises(ValueError, match="Insufficient balance"):
            await apply_charge(store, "t1", Decimal("999.99"))

    @pytest.mark.asyncio
    async def test_charge_unknown_tenant_raises(self, store):
        with pytest.raises(ValueError, match="Tenant not found"):
            await apply_charge(store, "nope", Decimal("1"))

    @pytest.mark.asyncio
    async def test_charge_zero_raises(self, store):
        with pytest.raises(ValueError, match="positive"):
            await apply_charge(store, "t1", Decimal("0"))


# ---------------------------------------------------------------------------
# Tests: adjust_quota
# ---------------------------------------------------------------------------

class TestAdjustQuota:
    @pytest.mark.asyncio
    async def test_adjust_quota_updates_limit(self, store):
        await adjust_quota(store, "t1", "gpu_hours", Decimal("200"))
        q = store.get_active_quota("t1", "gpu_hours")
        assert q.limit_value == Decimal("200")

    @pytest.mark.asyncio
    async def test_adjust_quota_no_active_raises(self, store):
        with pytest.raises(ValueError, match="No active quota"):
            await adjust_quota(store, "t1", "storage_gb", Decimal("50"))

    @pytest.mark.asyncio
    async def test_adjust_quota_negative_raises(self, store):
        with pytest.raises(ValueError, match="non-negative"):
            await adjust_quota(store, "t1", "gpu_hours", Decimal("-1"))


# ---------------------------------------------------------------------------
# Tests: reset_daily_quotas
# ---------------------------------------------------------------------------

class TestResetDailyQuotas:
    @pytest.mark.asyncio
    async def test_resets_expired_daily_quotas(self, store):
        count = await reset_daily_quotas(store)
        assert count == 1  # q2 is expired daily
        q2 = store.quotas[1]
        assert q2.used_value == Decimal("0")
        assert q2.period_end > datetime.utcnow()

    @pytest.mark.asyncio
    async def test_does_not_reset_active_quotas(self, store):
        # q1 is still active (not expired)
        count = await reset_daily_quotas(store)
        q1 = store.quotas[0]
        assert q1.used_value == Decimal("40")  # unchanged


# ---------------------------------------------------------------------------
# Tests: process_pending_events
# ---------------------------------------------------------------------------

class TestProcessPendingEvents:
    @pytest.mark.asyncio
    async def test_processes_credit_and_charge_events(self, store):
        store.pending_events = [
            {"event_type": "credit", "tenant_id": "t1", "amount": 10},
            {"event_type": "charge", "tenant_id": "t1", "amount": 5},
        ]
        processed = await process_pending_events(store)
        assert processed == 2
        assert len(store.pending_events) == 0
        assert store.tenants["t1"].balance == Decimal("505.00")  # +10 -5

    @pytest.mark.asyncio
    async def test_empty_queue_returns_zero(self, store):
        assert await process_pending_events(store) == 0


# ---------------------------------------------------------------------------
# Tests: generate_monthly_invoices
# ---------------------------------------------------------------------------

class TestGenerateMonthlyInvoices:
    @pytest.mark.asyncio
    async def test_generates_for_active_tenants_with_usage(self, store):
        store.usage_records.append(FakeUsageRecord(
            id="u1", tenant_id="t1", resource_type="gpu_hours",
            quantity=Decimal("10"), unit="hours",
            unit_price=Decimal("0.50"), total_cost=Decimal("5.00"),
        ))
        invoices = await generate_monthly_invoices(store)
        assert len(invoices) == 1
        assert invoices[0].startswith("INV-acme-")

    @pytest.mark.asyncio
    async def test_skips_inactive_tenants(self, store):
        store.usage_records.append(FakeUsageRecord(
            id="u2", tenant_id="t2", resource_type="gpu_hours",
            quantity=Decimal("5"), unit="hours",
            unit_price=Decimal("0.50"), total_cost=Decimal("2.50"),
        ))
        invoices = await generate_monthly_invoices(store)
        assert len(invoices) == 0  # t2 is inactive

    @pytest.mark.asyncio
    async def test_skips_tenants_without_usage(self, store):
        invoices = await generate_monthly_invoices(store)
        assert len(invoices) == 0


# ---------------------------------------------------------------------------
# Tests: extract_from_token
# ---------------------------------------------------------------------------

class TestExtractFromToken:
    @pytest.mark.asyncio
    async def test_valid_token_returns_claims(self):
        token = _make_token({"tenant_id": "t1", "role": "admin"})
        claims = await extract_from_token(token)
        assert claims is not None
        assert claims["tenant_id"] == "t1"

    @pytest.mark.asyncio
    async def test_invalid_signature_returns_none(self):
        token = _make_token({"tenant_id": "t1"}, secret="wrong-secret")
        claims = await extract_from_token(token, secret="test-secret")
        assert claims is None

    @pytest.mark.asyncio
    async def test_missing_tenant_id_returns_none(self):
        token = _make_token({"role": "admin"})
        claims = await extract_from_token(token)
        assert claims is None

    @pytest.mark.asyncio
    async def test_malformed_token_returns_none(self):
        assert await extract_from_token("not.a.valid.token.format") is None
        assert await extract_from_token("garbage") is None
        assert await extract_from_token("") is None
