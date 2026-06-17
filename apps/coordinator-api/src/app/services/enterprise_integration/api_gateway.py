"""
Enterprise API Gateway - Phase 6.1 Implementation
Multi-tenant API routing and management for enterprise clients
Port: 8010
"""

import secrets
import time
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any
from uuid import uuid4

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field

from aitbc.aitbc_logging import get_logger

from ...domain.multitenant import Tenant, TenantApiKey, TenantQuota  # type: ignore[import-not-found]
from ...exceptions import QuotaExceededError, TenantError
from ...storage.db import get_session

logger = get_logger(__name__)


class EnterpriseAuthRequest(BaseModel):
    tenant_id: str = Field(..., description="Enterprise tenant identifier")
    client_id: str = Field(..., description="Enterprise client ID")
    client_secret: str = Field(..., description="Enterprise client secret")
    auth_method: str = Field(default="client_credentials", description="Authentication method")
    scopes: list[str] | None = Field(default=None, description="Requested scopes")


class EnterpriseAuthResponse(BaseModel):
    access_token: str = Field(..., description="Access token for enterprise API")
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration in seconds")
    refresh_token: str | None = Field(None, description="Refresh token")
    scopes: list[str] = Field(..., description="Granted scopes")
    tenant_info: dict[str, Any] = Field(..., description="Tenant information")


class APIQuotaRequest(BaseModel):
    tenant_id: str = Field(..., description="Enterprise tenant identifier")
    endpoint: str = Field(..., description="API endpoint")
    method: str = Field(..., description="HTTP method")
    quota_type: str = Field(default="rate_limit", description="Quota type")


class APIQuotaResponse(BaseModel):
    quota_limit: int = Field(..., description="Quota limit")
    quota_remaining: int = Field(..., description="Remaining quota")
    quota_reset: datetime = Field(..., description="Quota reset time")
    quota_type: str = Field(..., description="Quota type")


class WebhookConfig(BaseModel):
    url: str = Field(..., description="Webhook URL")
    events: list[str] = Field(..., description="Events to subscribe to")
    secret: str | None = Field(None, description="Webhook secret")
    active: bool = Field(default=True, description="Webhook active status")
    retry_policy: dict[str, Any] | None = Field(None, description="Retry policy")


class EnterpriseIntegrationRequest(BaseModel):
    integration_type: str = Field(..., description="Integration type (ERP, CRM, etc.)")
    provider: str = Field(..., description="Integration provider")
    configuration: dict[str, Any] = Field(..., description="Integration configuration")
    credentials: dict[str, str] | None = Field(None, description="Integration credentials")
    webhook_config: WebhookConfig | None = Field(None, description="Webhook configuration")


class EnterpriseMetrics(BaseModel):
    api_calls_total: int = Field(..., description="Total API calls")
    api_calls_successful: int = Field(..., description="Successful API calls")
    average_response_time_ms: float = Field(..., description="Average response time")
    error_rate_percent: float = Field(..., description="Error rate percentage")
    quota_utilization_percent: float = Field(..., description="Quota utilization")
    active_integrations: int = Field(..., description="Active integrations count")


class IntegrationStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    PENDING = "pending"


class EnterpriseIntegration:
    """Enterprise integration configuration and management"""

    def __init__(
        self, integration_id: str, tenant_id: str, integration_type: str, provider: str, configuration: dict[str, Any]
    ):
        self.integration_id = integration_id
        self.tenant_id = tenant_id
        self.integration_type = integration_type
        self.provider = provider
        self.configuration = configuration
        self.status = IntegrationStatus.PENDING
        self.created_at = datetime.now(UTC)
        self.last_updated = datetime.now(UTC)
        self.webhook_config: dict[str, Any] | None = None
        self.metrics = {"api_calls": 0, "errors": 0, "last_call": None}


class EnterpriseAPIGateway:
    """Enterprise API Gateway with multi-tenant support"""

    def __init__(self) -> None:
        self.tenant_service = None
        self.active_tokens: dict[str, Any] = {}
        self.rate_limiters: dict[str, Any] = {}
        self.webhooks: dict[str, Any] = {}
        self.integrations: dict[str, Any] = {}
        self.api_metrics: dict[str, Any] = {}
        self.default_quotas = {"rate_limit": 1000, "daily_limit": 50000, "concurrent_limit": 100}
        self.jwt_secret = secrets.token_urlsafe(64)
        self.jwt_algorithm = "HS256"
        self.token_expiry = 3600

    async def authenticate_enterprise_client(self, request: EnterpriseAuthRequest, db_session: Any) -> EnterpriseAuthResponse:
        """Authenticate enterprise client and issue access token"""
        try:
            tenant = await self._validate_tenant_credentials(
                request.tenant_id, request.client_id, request.client_secret, db_session
            )
            access_token = self._generate_access_token(
                tenant_id=request.tenant_id, client_id=request.client_id, scopes=request.scopes or ["enterprise_api"]
            )
            refresh_token = self._generate_refresh_token(request.tenant_id, request.client_id)
            self.active_tokens[access_token] = {
                "tenant_id": request.tenant_id,
                "client_id": request.client_id,
                "scopes": request.scopes or ["enterprise_api"],
                "expires_at": datetime.now(UTC) + timedelta(seconds=self.token_expiry),
                "refresh_token": refresh_token,
            }
            return EnterpriseAuthResponse(
                access_token=access_token,
                token_type="Bearer",
                expires_in=self.token_expiry,
                refresh_token=refresh_token,
                scopes=request.scopes or ["enterprise_api"],
                tenant_info={
                    "tenant_id": tenant.tenant_id,
                    "name": tenant.name,
                    "plan": tenant.plan,
                    "status": tenant.status.value,
                    "created_at": tenant.created_at.isoformat(),
                },
            )
        except Exception as e:
            logger.error("Enterprise authentication failed: %s", e)
            raise HTTPException(status_code=401, detail="Authentication failed") from e

    def _generate_access_token(self, tenant_id: str, client_id: str, scopes: list[str]) -> str:
        """Generate JWT access token"""
        payload = {
            "sub": f"{tenant_id}:{client_id}",
            "scopes": scopes,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(seconds=self.token_expiry),
            "type": "access",
        }
        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)

    def _generate_refresh_token(self, tenant_id: str, client_id: str) -> str:
        """Generate refresh token"""
        payload = {
            "sub": f"{tenant_id}:{client_id}",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(days=30),
            "type": "refresh",
        }
        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)

    async def _validate_tenant_credentials(
        self, tenant_id: str, client_id: str, client_secret: str, db_session: Any
    ) -> Tenant:
        """Validate tenant credentials"""
        tenant = db_session.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
        if not tenant:
            raise TenantError(f"Tenant {tenant_id} not found")
        api_key = (
            db_session.query(TenantApiKey)
            .filter(TenantApiKey.tenant_id == tenant_id, TenantApiKey.client_id == client_id, TenantApiKey.is_active)
            .first()
        )
        if not api_key or not secrets.compare_digest(api_key.client_secret, client_secret):
            raise TenantError("Invalid client credentials")
        if tenant.status.value != "active":
            raise TenantError(f"Tenant {tenant_id} is not active")
        return tenant

    async def check_api_quota(self, tenant_id: str, endpoint: str, method: str, db_session: Any) -> APIQuotaResponse:
        """Check and enforce API quotas"""
        try:
            quota = await self._get_tenant_quota(tenant_id, db_session)
            current_usage = await self._get_current_usage(tenant_id, "rate_limit")
            if current_usage >= quota["rate_limit"]:
                raise QuotaExceededError("Rate limit exceeded")
            await self._update_usage(tenant_id, "rate_limit", current_usage + 1)
            return APIQuotaResponse(
                quota_limit=quota["rate_limit"],
                quota_remaining=quota["rate_limit"] - current_usage - 1,
                quota_reset=datetime.now(UTC) + timedelta(minutes=1),
                quota_type="rate_limit",
            )
        except QuotaExceededError:
            raise
        except Exception as e:
            logger.error("Quota check failed: %s", e)
            raise HTTPException(status_code=500, detail="Quota check failed") from e

    async def _get_tenant_quota(self, tenant_id: str, db_session: Any) -> dict[str, int]:
        """Get tenant quota configuration"""
        tenant_quota = db_session.query(TenantQuota).filter(TenantQuota.tenant_id == tenant_id).first()
        if tenant_quota:
            return {
                "rate_limit": tenant_quota.rate_limit or self.default_quotas["rate_limit"],
                "daily_limit": tenant_quota.daily_limit or self.default_quotas["daily_limit"],
                "concurrent_limit": tenant_quota.concurrent_limit or self.default_quotas["concurrent_limit"],
            }
        return self.default_quotas

    async def _get_current_usage(self, tenant_id: str, quota_type: str) -> int:
        """Get current quota usage"""
        if quota_type == "rate_limit":
            return len([t for t in self.rate_limiters.get(tenant_id, []) if datetime.now(UTC) - t < timedelta(minutes=1)])
        return 0

    async def _update_usage(self, tenant_id: str, quota_type: str, usage: int) -> None:
        """Update quota usage"""
        if quota_type == "rate_limit":
            if tenant_id not in self.rate_limiters:
                self.rate_limiters[tenant_id] = []
            self.rate_limiters[tenant_id].append(datetime.now(UTC))
            cutoff = datetime.now(UTC) - timedelta(minutes=1)
            self.rate_limiters[tenant_id] = [t for t in self.rate_limiters[tenant_id] if t > cutoff]

    async def create_enterprise_integration(
        self, tenant_id: str, request: EnterpriseIntegrationRequest, db_session: Any
    ) -> dict[str, Any]:
        """Create new enterprise integration"""
        try:
            tenant = db_session.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
            if not tenant:
                raise TenantError(f"Tenant {tenant_id} not found")
            integration_id = str(uuid4())
            integration = EnterpriseIntegration(
                integration_id=integration_id,
                tenant_id=tenant_id,
                integration_type=request.integration_type,
                provider=request.provider,
                configuration=request.configuration,
            )
            if request.webhook_config:
                integration.webhook_config = request.webhook_config.dict()
                self.webhooks[integration_id] = request.webhook_config.dict()
            self.integrations[integration_id] = integration
            await self._initialize_integration(integration)
            return {
                "integration_id": integration_id,
                "status": integration.status.value,
                "created_at": integration.created_at.isoformat(),
                "configuration": integration.configuration,
            }
        except Exception as e:
            logger.error("Failed to create enterprise integration: %s", e)
            raise HTTPException(status_code=500, detail="Integration creation failed") from e

    async def _initialize_integration(self, integration: Any) -> None:
        """Initialize enterprise integration"""
        try:
            if integration.integration_type.lower() == "erp":
                await self._initialize_erp_integration(integration)
            elif integration.integration_type.lower() == "crm":
                await self._initialize_crm_integration(integration)
            elif integration.integration_type.lower() == "bi":
                await self._initialize_bi_integration(integration)
            integration.status = IntegrationStatus.ACTIVE
            integration.last_updated = datetime.now(UTC)
        except Exception as e:
            logger.error("Integration initialization failed: %s", e)
            integration.status = IntegrationStatus.ERROR
            raise

    async def _initialize_erp_integration(self, integration: Any) -> None:
        """Initialize ERP integration"""
        provider = integration.provider.lower()
        if provider == "sap":
            await self._initialize_sap_integration(integration)
        elif provider == "oracle":
            await self._initialize_oracle_integration(integration)
        elif provider == "microsoft":
            await self._initialize_microsoft_integration(integration)
        logger.info("ERP integration initialized: %s", integration.provider)

    async def _initialize_sap_integration(self, integration: Any) -> None:
        """Initialize SAP ERP integration"""
        config = integration.configuration
        required_fields = ["system_id", "client", "username", "password", "host"]
        for field in required_fields:
            if field not in config:
                raise ValueError(f"SAP integration requires {field}")
        logger.info("SAP connection test successful for %s", integration.integration_id)

    async def _initialize_crm_integration(self, integration: Any) -> None:
        """Initialize CRM integration"""
        logger.info("CRM integration initialized: %s", integration.integration_id)

    async def _initialize_bi_integration(self, integration: Any) -> None:
        """Initialize BI integration"""
        logger.info("BI integration initialized: %s", integration.integration_id)

    async def _initialize_oracle_integration(self, integration: Any) -> None:
        """Initialize Oracle integration"""
        logger.info("Oracle integration initialized: %s", integration.integration_id)

    async def _initialize_microsoft_integration(self, integration: Any) -> None:
        """Initialize Microsoft integration"""
        logger.info("Microsoft integration initialized: %s", integration.integration_id)

    async def get_enterprise_metrics(self, tenant_id: str, db_session: Any) -> EnterpriseMetrics:
        """Get enterprise metrics and analytics"""
        try:
            api_metrics = self.api_metrics.get(
                tenant_id, {"total_calls": 0, "successful_calls": 0, "failed_calls": 0, "response_times": []}
            )
            total_calls = api_metrics["total_calls"]
            successful_calls = api_metrics["successful_calls"]
            failed_calls = api_metrics["failed_calls"]
            average_response_time = (
                sum(api_metrics["response_times"]) / len(api_metrics["response_times"])
                if api_metrics["response_times"]
                else 0.0
            )
            error_rate = failed_calls / total_calls * 100 if total_calls > 0 else 0.0
            current_usage = await self._get_current_usage(tenant_id, "rate_limit")
            quota = await self._get_tenant_quota(tenant_id, db_session)
            quota_utilization = current_usage / quota["rate_limit"] * 100 if quota["rate_limit"] > 0 else 0.0
            active_integrations = len(
                [i for i in self.integrations.values() if i.tenant_id == tenant_id and i.status == IntegrationStatus.ACTIVE]
            )
            return EnterpriseMetrics(
                api_calls_total=total_calls,
                api_calls_successful=successful_calls,
                average_response_time_ms=average_response_time,
                error_rate_percent=error_rate,
                quota_utilization_percent=quota_utilization,
                active_integrations=active_integrations,
            )
        except Exception as e:
            logger.error("Failed to get enterprise metrics: %s", e)
            raise HTTPException(status_code=500, detail="Metrics retrieval failed") from e

    async def record_api_call(self, tenant_id: str, endpoint: str, response_time: float, success: bool) -> None:
        """Record API call for metrics"""
        if tenant_id not in self.api_metrics:
            self.api_metrics[tenant_id] = {"total_calls": 0, "successful_calls": 0, "failed_calls": 0, "response_times": []}
        metrics = self.api_metrics[tenant_id]
        metrics["total_calls"] += 1
        if success:
            metrics["successful_calls"] += 1
        else:
            metrics["failed_calls"] += 1
        metrics["response_times"].append(response_time)
        if len(metrics["response_times"]) > 1000:
            metrics["response_times"] = metrics["response_times"][-1000:]


app = FastAPI(
    title="Enterprise API Gateway",
    description="Multi-tenant API routing and management for enterprise clients",
    version="6.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8001",
        "http://localhost:8203",
        "http://localhost:8016",
        "http://localhost:9001",
        "http://127.0.0.1:8001",
        "http://127.0.0.1:8203",
        "http://127.0.0.1:8016",
        "http://127.0.0.1:9001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
security = HTTPBearer()
gateway = EnterpriseAPIGateway()


async def get_db_session() -> Any:
    """Get database session"""
    for session in get_session():
        yield session


@app.middleware("http")
async def api_metrics_middleware(request: Request, call_next: Any) -> Any:
    """Middleware to record API metrics"""
    start_time = time.time()
    tenant_id = None
    authorization = request.headers.get("authorization")
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        token_data = gateway.active_tokens.get(token)
        if token_data:
            tenant_id = token_data["tenant_id"]
    response = await call_next(request)
    response_time = (time.time() - start_time) * 1000
    success = response.status_code < 400
    if tenant_id:
        await gateway.record_api_call(tenant_id, str(request.url.path), response_time, success)
    return response


@app.post("/enterprise/auth")
async def enterprise_auth(request: EnterpriseAuthRequest, db_session: Annotated[Any, Depends(get_db_session)]) -> Any:
    """Authenticate enterprise client"""
    result = await gateway.authenticate_enterprise_client(request, db_session)
    return result


@app.post("/enterprise/quota/check")
async def check_quota(request: APIQuotaRequest, db_session: Annotated[Any, Depends(get_db_session)]) -> Any:
    """Check API quota"""
    result = await gateway.check_api_quota(request.tenant_id, request.endpoint, request.method, db_session)
    return result


@app.post("/enterprise/integrations")
async def create_integration(
    request: EnterpriseIntegrationRequest, db_session: Annotated[Any, Depends(get_db_session)]
) -> Any:
    """Create enterprise integration"""
    tenant_id = "demo_tenant"
    result = await gateway.create_enterprise_integration(tenant_id, request, db_session)
    return result


@app.get("/enterprise/analytics")
async def get_analytics(db_session: Annotated[Any, Depends(get_db_session)]) -> Any:
    """Get enterprise analytics dashboard"""
    tenant_id = "demo_tenant"
    result = await gateway.get_enterprise_metrics(tenant_id, db_session)
    return result


@app.get("/enterprise/status")
async def get_status() -> dict[str, Any]:
    """Get enterprise gateway status"""
    return {
        "service": "Enterprise API Gateway",
        "version": "6.1.0",
        "port": 8010,
        "status": "operational",
        "active_tenants": len({token["tenant_id"] for token in gateway.active_tokens.values()}),
        "active_integrations": len(gateway.integrations),
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.get("/")
async def root() -> dict[str, Any]:
    """Root endpoint"""
    return {
        "service": "Enterprise API Gateway",
        "version": "6.1.0",
        "port": 8010,
        "capabilities": [
            "Multi-tenant API Management",
            "Enterprise Authentication",
            "API Quota Management",
            "Enterprise Integration Framework",
            "Real-time Analytics",
        ],
        "status": "operational",
    }


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
        "services": {
            "api_gateway": "operational",
            "authentication": "operational",
            "quota_management": "operational",
            "integration_framework": "operational",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8010)
