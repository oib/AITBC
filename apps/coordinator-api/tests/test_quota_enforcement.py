"""
Tests for multi-tenant quota enforcement.
"""

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from coordinator_api.contexts.security.services.quota_enforcement import QuotaEnforcementService
from coordinator_api.models.multitenant import Tenant


@pytest.mark.unit
async def test_consume_quota_records_job_id(db_session: Session):
    """UsageRecord should be created with the provided job_id and tenant."""
    tenant = Tenant(name="Test Tenant", slug="test-tenant", contact_email="test@example.com", plan="enterprise")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)

    service = QuotaEnforcementService(db_session)
    usage = await service.consume_quota(
        resource_type="gpu_hours",
        quantity=Decimal("1.5"),
        resource_id="job-123",
        tenant_id=tenant.id,
    )

    assert usage.job_id == "job-123"
    assert usage.tenant_id == tenant.id
    assert usage.usage_metadata == {}
