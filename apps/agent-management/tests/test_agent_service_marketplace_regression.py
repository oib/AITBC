"""
Regression tests for agent_service_marketplace.py
These tests capture current behavior before extracting shared logic.
"""

from datetime import UTC, datetime

import pytest
from app.services.agent_service_marketplace import (
    GuildStatus,
    RequestStatus,
    Service,
    ServiceStatus,
    ServiceType,
)


@pytest.mark.unit
class TestServiceStatus:
    """Test ServiceStatus enum"""

    def test_service_status_values(self):
        """Test that all expected service status values exist"""
        assert ServiceStatus.ACTIVE == "active"
        assert ServiceStatus.INACTIVE == "inactive"
        assert ServiceStatus.SUSPENDED == "suspended"
        assert ServiceStatus.PENDING == "pending"


@pytest.mark.unit
class TestRequestStatus:
    """Test RequestStatus enum"""

    def test_request_status_values(self):
        """Test that all expected request status values exist"""
        assert RequestStatus.PENDING == "pending"
        assert RequestStatus.ACCEPTED == "accepted"
        assert RequestStatus.COMPLETED == "completed"
        assert RequestStatus.CANCELLED == "cancelled"
        assert RequestStatus.EXPIRED == "expired"


@pytest.mark.unit
class TestGuildStatus:
    """Test GuildStatus enum"""

    def test_guild_status_values(self):
        """Test that all expected guild status values exist"""
        assert GuildStatus.ACTIVE == "active"
        assert GuildStatus.INACTIVE == "inactive"
        assert GuildStatus.SUSPENDED == "suspended"


@pytest.mark.unit
class TestServiceType:
    """Test ServiceType enum"""

    def test_service_type_values(self):
        """Test that all expected service type values exist"""
        assert ServiceType.DATA_ANALYSIS == "data_analysis"
        assert ServiceType.CONTENT_CREATION == "content_creation"
        assert ServiceType.RESEARCH == "research"
        assert ServiceType.CONSULTING == "consulting"
        assert ServiceType.DEVELOPMENT == "development"
        assert ServiceType.DESIGN == "design"
        assert ServiceType.MARKETING == "marketing"
        assert ServiceType.TRANSLATION == "translation"
        assert ServiceType.WRITING == "writing"
        assert ServiceType.ANALYSIS == "analysis"
        assert ServiceType.PREDICTION == "prediction"
        assert ServiceType.OPTIMIZATION == "optimization"
        assert ServiceType.AUTOMATION == "automation"
        assert ServiceType.MONITORING == "monitoring"
        assert ServiceType.TESTING == "testing"
        assert ServiceType.SECURITY == "security"
        assert ServiceType.INTEGRATION == "integration"
        assert ServiceType.CUSTOMIZATION == "customization"
        assert ServiceType.TRAINING == "training"
        assert ServiceType.SUPPORT == "support"


@pytest.mark.unit
class TestService:
    """Test Service dataclass"""

    def test_service_creation_with_defaults(self):
        """Test creating a service with default values"""
        now = datetime.now(UTC)
        service = Service(
            id="service_123",
            agent_id="agent1",
            service_type=ServiceType.DEVELOPMENT,
            name="Test Service",
            description="A test service",
            metadata={"key": "value"},
            base_price=100.0,
            reputation=5,
            status=ServiceStatus.ACTIVE,
            total_earnings=1000.0,
            completed_jobs=10,
            average_rating=4.5,
            rating_count=8,
            listed_at=now,
            last_updated=now,
        )

        assert service.id == "service_123"
        assert service.agent_id == "agent1"
        assert service.service_type == ServiceType.DEVELOPMENT
        assert service.name == "Test Service"
        assert service.description == "A test service"
        assert service.metadata == {"key": "value"}
        assert service.base_price == 100.0
        assert service.reputation == 5
        assert service.status == ServiceStatus.ACTIVE
        assert service.total_earnings == 1000.0
        assert service.completed_jobs == 10
        assert service.average_rating == 4.5
        assert service.rating_count == 8
        assert service.guild_id is None
        assert service.tags == []
        assert service.capabilities == []
        assert service.requirements == []
        assert service.pricing_model == "fixed"
        assert service.estimated_duration == 0
        assert service.availability == {}

    def test_service_with_optional_fields(self):
        """Test creating a service with optional fields set"""
        now = datetime.now(UTC)
        service = Service(
            id="service_456",
            agent_id="agent2",
            service_type=ServiceType.DATA_ANALYSIS,
            name="Data Analysis Service",
            description="Professional data analysis",
            metadata={"complexity": "high"},
            base_price=250.0,
            reputation=10,
            status=ServiceStatus.ACTIVE,
            total_earnings=5000.0,
            completed_jobs=50,
            average_rating=4.8,
            rating_count=45,
            listed_at=now,
            last_updated=now,
            guild_id="guild_123",
            tags=["data", "analysis", "python"],
            capabilities=["ml", "visualization"],
            requirements=["dataset", "clear_objectives"],
            pricing_model="hourly",
            estimated_duration=5,
            availability={"monday": True, "tuesday": True},
        )

        assert service.guild_id == "guild_123"
        assert service.tags == ["data", "analysis", "python"]
        assert service.capabilities == ["ml", "visualization"]
        assert service.requirements == ["dataset", "clear_objectives"]
        assert service.pricing_model == "hourly"
        assert service.estimated_duration == 5
        assert service.availability == {"monday": True, "tuesday": True}
