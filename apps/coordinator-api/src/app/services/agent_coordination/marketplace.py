"""
AI Agent Service Marketplace Service
Implements a sophisticated marketplace where agents can offer specialized services
"""

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from aitbc import get_logger

logger = get_logger(__name__)


class ServiceStatus(StrEnum):
    """Service status types"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"


class RequestStatus(StrEnum):
    """Service request status types"""

    PENDING = "pending"
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class GuildStatus(StrEnum):
    """Guild status types"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class ServiceType(StrEnum):
    """Service categories"""

    DATA_ANALYSIS = "data_analysis"
    CONTENT_CREATION = "content_creation"
    RESEARCH = "research"
    CONSULTING = "consulting"
    DEVELOPMENT = "development"
    DESIGN = "design"
    MARKETING = "marketing"
    TRANSLATION = "translation"
    WRITING = "writing"
    ANALYSIS = "analysis"
    PREDICTION = "prediction"
    OPTIMIZATION = "optimization"
    AUTOMATION = "automation"
    MONITORING = "monitoring"
    TESTING = "testing"
    SECURITY = "security"
    INTEGRATION = "integration"
    CUSTOMIZATION = "customization"
    TRAINING = "training"
    SUPPORT = "support"


@dataclass
class Service:
    """Agent service information"""

    id: str
    agent_id: str
    service_type: ServiceType
    name: str
    description: str
    metadata: dict[str, Any]
    base_price: float
    reputation: int
    status: ServiceStatus
    total_earnings: float
    completed_jobs: int
    average_rating: float
    rating_count: int
    listed_at: datetime
    last_updated: datetime
    guild_id: str | None = None
    tags: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    pricing_model: str = "fixed"
    estimated_duration: int = 0
    availability: dict[str, Any] = field(default_factory=dict)


@dataclass
class ServiceRequest:
    """Service request information"""

    id: str
    client_id: str
    service_id: str
    budget: float
    requirements: str
    deadline: datetime
    status: RequestStatus
    assigned_agent: str | None = None
    accepted_at: datetime | None = None
    completed_at: datetime | None = None
    payment: float = 0.0
    rating: int = 0
    review: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    results_hash: str | None = None
    priority: str = "normal"
    complexity: str = "medium"
    confidentiality: str = "public"


@dataclass
class Guild:
    """Agent guild information"""

    id: str
    name: str
    description: str
    founder: str
    service_category: ServiceType
    member_count: int
    total_services: int
    total_earnings: float
    reputation: int
    status: GuildStatus
    created_at: datetime
    members: dict[str, dict[str, Any]] = field(default_factory=dict)
    requirements: list[str] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)
    guild_rules: dict[str, Any] = field(default_factory=dict)


@dataclass
class ServiceCategory:
    """Service category information"""

    name: str
    description: str
    service_count: int
    total_volume: float
    average_price: float
    is_active: bool
    trending: bool = False
    popular_services: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)


@dataclass
class MarketplaceAnalytics:
    """Marketplace analytics data"""

    total_services: int
    active_services: int
    total_requests: int
    pending_requests: int
    total_volume: float
    total_guilds: int
    average_service_price: float
    popular_categories: list[str]
    top_agents: list[str]
    revenue_trends: dict[str, float]
    growth_metrics: dict[str, float]


class AgentServiceMarketplace:
    """Service for managing AI agent service marketplace"""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.services: dict[str, Service] = {}
        self.service_requests: dict[str, ServiceRequest] = {}
        self.guilds: dict[str, Guild] = {}
        self.categories: dict[str, ServiceCategory] = {}
        self.agent_services: dict[str, list[str]] = {}
        self.client_requests: dict[str, list[str]] = {}
        self.guild_services: dict[str, list[str]] = {}
        self.agent_guilds: dict[str, str] = {}
        self.services_by_type: dict[str, list[str]] = {}
        self.guilds_by_category: dict[str, list[str]] = {}
        self.marketplace_fee = 0.025
        self.min_service_price = 0.001
        self.max_service_price = 1000.0
        self.min_reputation_to_list = 500
        self.request_timeout = 7 * 24 * 3600
        self.rating_weight = 100
        self._initialize_categories()

    async def initialize(self) -> None:
        """Initialize the marketplace service"""
        logger.info("Initializing Agent Service Marketplace")
        await self._load_marketplace_data()
        asyncio.create_task(self._monitor_request_timeouts())
        asyncio.create_task(self._update_marketplace_analytics())
        asyncio.create_task(self._process_service_recommendations())
        asyncio.create_task(self._maintain_guild_reputation())
        logger.info("Agent Service Marketplace initialized")

    async def list_service(
        self,
        agent_id: str,
        service_type: ServiceType,
        name: str,
        description: str,
        metadata: dict[str, Any],
        base_price: float,
        tags: list[str],
        capabilities: list[str],
        requirements: list[str],
        pricing_model: str = "fixed",
        estimated_duration: int = 0,
    ) -> Service:
        """List a new service on the marketplace"""
        try:
            if base_price < self.min_service_price:
                raise ValueError(f"Price below minimum: {self.min_service_price}")
            if base_price > self.max_service_price:
                raise ValueError(f"Price above maximum: {self.max_service_price}")
            if not description or len(description) < 10:
                raise ValueError("Description too short")
            agent_reputation = await self._get_agent_reputation(agent_id)
            if agent_reputation < self.min_reputation_to_list:
                raise ValueError(f"Insufficient reputation: {agent_reputation}")
            service_id = await self._generate_service_id()
            service = Service(
                id=service_id,
                agent_id=agent_id,
                service_type=service_type,
                name=name,
                description=description,
                metadata=metadata,
                base_price=base_price,
                reputation=agent_reputation,
                status=ServiceStatus.ACTIVE,
                total_earnings=0.0,
                completed_jobs=0,
                average_rating=0.0,
                rating_count=0,
                listed_at=datetime.now(UTC),
                last_updated=datetime.now(UTC),
                tags=tags,
                capabilities=capabilities,
                requirements=requirements,
                pricing_model=pricing_model,
                estimated_duration=estimated_duration,
                availability={
                    "monday": True,
                    "tuesday": True,
                    "wednesday": True,
                    "thursday": True,
                    "friday": True,
                    "saturday": False,
                    "sunday": False,
                },
            )
            self.services[service_id] = service
            if agent_id not in self.agent_services:
                self.agent_services[agent_id] = []
            self.agent_services[agent_id].append(service_id)
            if service_type.value not in self.services_by_type:
                self.services_by_type[service_type.value] = []
            self.services_by_type[service_type.value].append(service_id)
            if service_type.value in self.categories:
                self.categories[service_type.value].service_count += 1
            logger.info("Service listed: %s by agent %s", service_id, agent_id)
            return service
        except Exception as e:
            logger.error("Failed to list service: %s", e)
            raise

    async def request_service(
        self,
        client_id: str,
        service_id: str,
        budget: float,
        requirements: str,
        deadline: datetime,
        priority: str = "normal",
        complexity: str = "medium",
        confidentiality: str = "public",
    ) -> ServiceRequest:
        """Request a service"""
        try:
            if service_id not in self.services:
                raise ValueError(f"Service not found: {service_id}")
            service = self.services[service_id]
            if service.status != ServiceStatus.ACTIVE:
                raise ValueError("Service not active")
            if budget < service.base_price:
                raise ValueError(f"Budget below service price: {service.base_price}")
            if deadline <= datetime.now(UTC):
                raise ValueError("Invalid deadline")
            if deadline > datetime.now(UTC) + timedelta(days=365):
                raise ValueError("Deadline too far in future")
            request_id = await self._generate_request_id()
            request = ServiceRequest(
                id=request_id,
                client_id=client_id,
                service_id=service_id,
                budget=budget,
                requirements=requirements,
                deadline=deadline,
                status=RequestStatus.PENDING,
                priority=priority,
                complexity=complexity,
                confidentiality=confidentiality,
            )
            self.service_requests[request_id] = request
            if client_id not in self.client_requests:
                self.client_requests[client_id] = []
            self.client_requests[client_id].append(request_id)
            logger.info("Service requested: %s for service %s", request_id, service_id)
            return request
        except Exception as e:
            logger.error("Failed to request service: %s", e)
            raise

    async def accept_request(self, request_id: str, agent_id: str) -> bool:
        """Accept a service request"""
        try:
            if request_id not in self.service_requests:
                raise ValueError(f"Request not found: {request_id}")
            request = self.service_requests[request_id]
            service = self.services[request.service_id]
            if request.status != RequestStatus.PENDING:
                raise ValueError("Request not pending")
            if request.assigned_agent:
                raise ValueError("Request already assigned")
            if service.agent_id != agent_id:
                raise ValueError("Not service provider")
            if datetime.now(UTC) > request.deadline:
                raise ValueError("Request expired")
            request.status = RequestStatus.ACCEPTED
            request.assigned_agent = agent_id
            request.accepted_at = datetime.now(UTC)
            final_price = await self._calculate_dynamic_price(request.service_id, request.budget)
            request.payment = final_price
            logger.info("Request accepted: %s by agent %s", request_id, agent_id)
            return True
        except Exception as e:
            logger.error("Failed to accept request: %s", e)
            raise

    async def complete_request(self, request_id: str, agent_id: str, results: dict[str, Any]) -> bool:
        """Complete a service request"""
        try:
            if request_id not in self.service_requests:
                raise ValueError(f"Request not found: {request_id}")
            request = self.service_requests[request_id]
            service = self.services[request.service_id]
            if request.status != RequestStatus.ACCEPTED:
                raise ValueError("Request not accepted")
            if request.assigned_agent != agent_id:
                raise ValueError("Not assigned agent")
            if datetime.now(UTC) > request.deadline:
                raise ValueError("Request expired")
            request.status = RequestStatus.COMPLETED
            request.completed_at = datetime.now(UTC)
            request.results_hash = hashlib.sha256(json.dumps(results, sort_keys=True).encode()).hexdigest()
            payment = request.payment
            fee = payment * self.marketplace_fee
            agent_payment = payment - fee
            service.total_earnings += agent_payment
            service.completed_jobs += 1
            service.last_updated = datetime.now(UTC)
            if service.service_type.value in self.categories:
                self.categories[service.service_type.value].total_volume += payment
            if service.guild_id and service.guild_id in self.guilds:
                guild = self.guilds[service.guild_id]
                guild.total_earnings += agent_payment
            logger.info("Request completed: %s with payment %s", request_id, agent_payment)
            return True
        except Exception as e:
            logger.error("Failed to complete request: %s", e)
            raise

    async def rate_service(self, request_id: str, client_id: str, rating: int, review: str) -> bool:
        """Rate and review a completed service"""
        try:
            if request_id not in self.service_requests:
                raise ValueError(f"Request not found: {request_id}")
            request = self.service_requests[request_id]
            service = self.services[request.service_id]
            if request.status != RequestStatus.COMPLETED:
                raise ValueError("Request not completed")
            if request.client_id != client_id:
                raise ValueError("Not request client")
            if rating < 1 or rating > 5:
                raise ValueError("Invalid rating")
            if datetime.now(UTC) > request.deadline + timedelta(days=30):
                raise ValueError("Rating period expired")
            request.rating = rating
            request.review = review
            total_rating = service.average_rating * service.rating_count + rating
            service.rating_count += 1
            service.average_rating = total_rating / service.rating_count
            reputation_change = await self._calculate_reputation_change(rating, service.reputation)
            await self._update_agent_reputation(service.agent_id, reputation_change)
            logger.info("Service rated: %s with rating %s", request_id, rating)
            return True
        except Exception as e:
            logger.error("Failed to rate service: %s", e)
            raise

    async def create_guild(
        self,
        founder_id: str,
        name: str,
        description: str,
        service_category: ServiceType,
        requirements: list[str],
        benefits: list[str],
        guild_rules: dict[str, Any],
    ) -> Guild:
        """Create a new guild"""
        try:
            if not name or len(name) < 3:
                raise ValueError("Invalid guild name")
            if service_category not in list(ServiceType):
                raise ValueError("Invalid service category")
            guild_id = await self._generate_guild_id()
            founder_reputation = await self._get_agent_reputation(founder_id)
            guild = Guild(
                id=guild_id,
                name=name,
                description=description,
                founder=founder_id,
                service_category=service_category,
                member_count=1,
                total_services=0,
                total_earnings=0.0,
                reputation=founder_reputation,
                status=GuildStatus.ACTIVE,
                created_at=datetime.now(UTC),
                requirements=requirements,
                benefits=benefits,
                guild_rules=guild_rules,
            )
            guild.members[founder_id] = {
                "joined_at": datetime.now(UTC),
                "reputation": founder_reputation,
                "role": "founder",
                "contributions": 0,
            }
            self.guilds[guild_id] = guild
            if service_category.value not in self.guilds_by_category:
                self.guilds_by_category[service_category.value] = []
            self.guilds_by_category[service_category.value].append(guild_id)
            self.agent_guilds[founder_id] = guild_id
            logger.info("Guild created: %s by %s", guild_id, founder_id)
            return guild
        except Exception as e:
            logger.error("Failed to create guild: %s", e)
            raise

    async def join_guild(self, agent_id: str, guild_id: str) -> bool:
        """Join a guild"""
        try:
            if guild_id not in self.guilds:
                raise ValueError(f"Guild not found: {guild_id}")
            guild = self.guilds[guild_id]
            if agent_id in guild.members:
                raise ValueError("Already a member")
            if guild.status != GuildStatus.ACTIVE:
                raise ValueError("Guild not active")
            agent_reputation = await self._get_agent_reputation(agent_id)
            if agent_reputation < guild.reputation // 2:
                raise ValueError("Insufficient reputation")
            guild.members[agent_id] = {
                "joined_at": datetime.now(UTC),
                "reputation": agent_reputation,
                "role": "member",
                "contributions": 0,
            }
            guild.member_count += 1
            self.agent_guilds[agent_id] = guild_id
            logger.info("Agent %s joined guild %s", agent_id, guild_id)
            return True
        except Exception as e:
            logger.error("Failed to join guild: %s", e)
            raise

    async def search_services(
        self,
        query: str | None = None,
        service_type: ServiceType | None = None,
        tags: list[str] | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        min_rating: float | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Service]:
        """Search services with various filters"""
        try:
            results = []
            for service in self.services.values():
                if service.status != ServiceStatus.ACTIVE:
                    continue
                if service_type and service.service_type != service_type:
                    continue
                if min_price and service.base_price < min_price:
                    continue
                if max_price and service.base_price > max_price:
                    continue
                if min_rating and service.average_rating < min_rating:
                    continue
                if tags and (not any(tag in service.tags for tag in tags)):
                    continue
                if query:
                    query_lower = query.lower()
                    if (
                        query_lower not in service.name.lower()
                        and query_lower not in service.description.lower()
                        and (not any(query_lower in tag.lower() for tag in service.tags))
                    ):
                        continue
                results.append(service)
            results.sort(key=lambda x: (x.average_rating, x.reputation), reverse=True)
            return results[offset : offset + limit]
        except Exception as e:
            logger.error("Failed to search services: %s", e)
            raise

    async def get_agent_services(self, agent_id: str) -> list[Service]:
        """Get all services for an agent"""
        try:
            if agent_id not in self.agent_services:
                return []
            services = []
            for service_id in self.agent_services[agent_id]:
                if service_id in self.services:
                    services.append(self.services[service_id])
            return services
        except Exception as e:
            logger.error("Failed to get agent services: %s", e)
            raise

    async def get_client_requests(self, client_id: str) -> list[ServiceRequest]:
        """Get all requests for a client"""
        try:
            if client_id not in self.client_requests:
                return []
            requests = []
            for request_id in self.client_requests[client_id]:
                if request_id in self.service_requests:
                    requests.append(self.service_requests[request_id])
            return requests
        except Exception as e:
            logger.error("Failed to get client requests: %s", e)
            raise

    async def get_marketplace_analytics(self) -> MarketplaceAnalytics:
        """Get marketplace analytics"""
        try:
            total_services = len(self.services)
            active_services = len([s for s in self.services.values() if s.status == ServiceStatus.ACTIVE])
            total_requests = len(self.service_requests)
            pending_requests = len([r for r in self.service_requests.values() if r.status == RequestStatus.PENDING])
            total_guilds = len(self.guilds)
            total_volume = sum(service.total_earnings for service in self.services.values())
            active_service_prices = [
                service.base_price for service in self.services.values() if service.status == ServiceStatus.ACTIVE
            ]
            average_price = sum(active_service_prices) / len(active_service_prices) if active_service_prices else 0
            category_counts: dict[str, int] = {}
            for service in self.services.values():
                if service.status == ServiceStatus.ACTIVE:
                    category_counts[service.service_type.value] = category_counts.get(service.service_type.value, 0) + 1
            popular_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            agent_earnings: dict[str, float] = {}
            for service in self.services.values():
                agent_earnings[service.agent_id] = agent_earnings.get(service.agent_id, 0) + service.total_earnings
            top_agents = sorted(agent_earnings.items(), key=lambda x: x[1], reverse=True)[:5]
            return MarketplaceAnalytics(
                total_services=total_services,
                active_services=active_services,
                total_requests=total_requests,
                pending_requests=pending_requests,
                total_volume=total_volume,
                total_guilds=total_guilds,
                average_service_price=average_price,
                popular_categories=[cat[0] for cat in popular_categories],
                top_agents=[agent[0] for agent in top_agents],
                revenue_trends={},
                growth_metrics={},
            )
        except Exception as e:
            logger.error("Failed to get marketplace analytics: %s", e)
            raise

    async def _calculate_dynamic_price(self, service_id: str, budget: float) -> float:
        """Calculate dynamic price based on demand and reputation"""
        service = self.services[service_id]
        dynamic_price = service.base_price
        reputation_multiplier = 1.0 + service.reputation / 10000 * 0.5
        dynamic_price *= reputation_multiplier
        demand_multiplier = 1.0
        if service.completed_jobs > 10:
            demand_multiplier = 1.0 + service.completed_jobs / 100 * 0.5
        dynamic_price *= demand_multiplier
        rating_multiplier = 1.0 + service.average_rating / 5 * 0.3
        dynamic_price *= rating_multiplier
        return min(dynamic_price, budget)

    async def _calculate_reputation_change(self, rating: int, current_reputation: int) -> int:
        """Calculate reputation change based on rating"""
        if rating == 5:
            return self.rating_weight * 2
        elif rating == 4:
            return self.rating_weight
        elif rating == 3:
            return 0
        elif rating == 2:
            return -self.rating_weight
        else:
            return -self.rating_weight * 2

    async def _get_agent_reputation(self, agent_id: str) -> int:
        """Get agent reputation (simplified)"""
        return 1000

    async def _update_agent_reputation(self, agent_id: str, change: int) -> None:
        """Update agent reputation (simplified)"""
        pass

    async def _generate_service_id(self) -> str:
        """Generate unique service ID"""
        import uuid

        return str(uuid.uuid4())

    async def _generate_request_id(self) -> str:
        """Generate unique request ID"""
        import uuid

        return str(uuid.uuid4())

    async def _generate_guild_id(self) -> str:
        """Generate unique guild ID"""
        import uuid

        return str(uuid.uuid4())

    def _initialize_categories(self) -> None:
        """Initialize service categories"""
        for service_type in ServiceType:
            self.categories[service_type.value] = ServiceCategory(
                name=service_type.value,
                description=f"Services related to {service_type.value}",
                service_count=0,
                total_volume=0.0,
                average_price=0.0,
                is_active=True,
            )

    async def _load_marketplace_data(self) -> None:
        """Load existing marketplace data"""
        pass

    async def _monitor_request_timeouts(self) -> None:
        """Monitor and handle request timeouts"""
        while True:
            try:
                current_time = datetime.now(UTC)
                for request in self.service_requests.values():
                    if request.status == RequestStatus.PENDING and current_time > request.deadline:
                        request.status = RequestStatus.EXPIRED
                        logger.info("Request expired: %s", request.id)
                await asyncio.sleep(3600)
            except Exception as e:
                logger.error("Error monitoring timeouts: %s", e)
                await asyncio.sleep(3600)

    async def _update_marketplace_analytics(self) -> None:
        """Update marketplace analytics"""
        while True:
            try:
                for category in self.categories.values():
                    category.trending = category.service_count > 10
                await asyncio.sleep(3600)
            except Exception as e:
                logger.error("Error updating analytics: %s", e)
                await asyncio.sleep(3600)

    async def _process_service_recommendations(self) -> None:
        """Process service recommendations"""
        while True:
            try:
                await asyncio.sleep(1800)
            except Exception as e:
                logger.error("Error processing recommendations: %s", e)
                await asyncio.sleep(1800)

    async def _maintain_guild_reputation(self) -> None:
        """Maintain guild reputation scores"""
        while True:
            try:
                for guild in self.guilds.values():
                    total_reputation = 0
                    active_members = 0
                    for member_id, _member_data in guild.members.items():
                        member_reputation = await self._get_agent_reputation(member_id)
                        total_reputation += member_reputation
                        active_members += 1
                    if active_members > 0:
                        guild.reputation = total_reputation // active_members
                await asyncio.sleep(3600)
            except Exception as e:
                logger.error("Error maintaining guild reputation: %s", e)
                await asyncio.sleep(3600)
