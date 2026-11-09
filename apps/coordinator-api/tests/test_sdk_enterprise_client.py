"""Coverage for coordinator_api.sdk.enterprise_client.

The SDK client speaks raw aiohttp, so tests run it against a real local
aiohttp server (aiohttp.test_utils) that records requests and returns
canned responses — no HTTP mocking library needed.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from coordinator_api.sdk.enterprise_client import (
    CRMIntegration,
    ERPIntegration,
    APIResponse,
    AuthenticationMethod,
    AuthenticationResponse,
    EnterpriseClient,
    EnterpriseConfig,
    IntegrationConfig,
    IntegrationType,
    SDKVersion,
    WebhookHandler,
    create_sap_integration,
    create_salesforce_integration,
)

AUTH_RESPONSE = {
    "access_token": "tok-123",
    "token_type": "Bearer",
    "expires_in": 3600,
    "refresh_token": "rt-1",
    "scopes": ["read", "write"],
    "tenant_info": {"tenant_id": "t1", "plan": "enterprise"},
}


class FakeEnterpriseAPI:
    """aiohttp app that records requests and serves canned route responses."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        # (method, path_prefix, status, json_body, text, content_type)
        self.routes: list[tuple] = []
        self.app = web.Application()
        self.app.router.add_route("*", "/{tail:.*}", self._handle)
        self.base_url = ""

    def add(
        self,
        method: str,
        path: str,
        *,
        status: int = 200,
        json_body: dict | list | None = None,
        text: str | None = None,
        content_type: str = "text/plain",
    ) -> None:
        self.routes.append((method.upper(), path, status, json_body, text, content_type))

    async def _handle(self, request: web.Request) -> web.Response:
        raw = await request.read()
        try:
            body = json.loads(raw) if raw else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = raw.decode(errors="replace")
        self.requests.append(
            {
                "method": request.method,
                "path": request.path,
                "body": body,
                "headers": dict(request.headers),
            }
        )
        matches = [r for r in self.routes if r[0] == request.method and request.path.startswith(r[1])]
        if not matches:
            return web.Response(status=404, text="no route")
        _, _, status, json_body, text, content_type = max(matches, key=lambda r: len(r[1]))
        if json_body is not None:
            return web.json_response(json_body, status=status)
        return web.Response(text="" if text is None else text, status=status, content_type=content_type)


@pytest.fixture
async def api() -> FakeEnterpriseAPI:
    fake = FakeEnterpriseAPI()
    client = TestClient(TestServer(fake.app))
    await client.start_server()
    fake.base_url = str(client.make_url("/")).rstrip("/")
    yield fake
    await client.close()


def make_config(base_url: str, **overrides) -> EnterpriseConfig:
    kwargs = {
        "tenant_id": "tenant-1",
        "client_id": "client-1",
        "client_secret": "s3cret",
        "base_url": base_url,
    }
    kwargs.update(overrides)
    return EnterpriseConfig(**kwargs)


def make_client(base_url: str, **overrides) -> EnterpriseClient:
    return EnterpriseClient(make_config(base_url, **overrides))


# ---------------------------------------------------------------------------
# enums / config / models
# ---------------------------------------------------------------------------


def test_sdk_version_and_enums() -> None:
    assert SDKVersion.V1_0 == "1.0.0"
    assert SDKVersion.CURRENT == SDKVersion.V1_0
    assert AuthenticationMethod.CLIENT_CREDENTIALS == "client_credentials"
    assert IntegrationType.ERP == "erp"
    assert IntegrationType.CRM == "crm"
    assert IntegrationType.BI == "bi"
    assert IntegrationType.CUSTOM == "custom"


def test_enterprise_config_defaults() -> None:
    cfg = EnterpriseConfig(tenant_id="t", client_id="c", client_secret="s")
    assert cfg.base_url == "https://api.aitbc.dev/enterprise"
    assert cfg.api_version == "v1"
    assert cfg.timeout == 30
    assert cfg.retry_attempts == 3
    assert cfg.retry_delay == 1.0
    assert cfg.auth_method == AuthenticationMethod.CLIENT_CREDENTIALS


def test_pydantic_models() -> None:
    auth = AuthenticationResponse(**AUTH_RESPONSE)
    assert auth.access_token == "tok-123"
    assert auth.token_type == "Bearer"
    assert auth.expires_in == 3600
    assert auth.refresh_token == "rt-1"
    assert auth.scopes == ["read", "write"]
    assert auth.tenant_info["plan"] == "enterprise"

    resp = APIResponse(success=True, data={"k": 1})
    assert resp.success is True
    assert resp.data == {"k": 1}
    assert resp.error is None
    assert resp.metadata == {}

    cfg = IntegrationConfig(
        integration_type=IntegrationType.ERP,
        provider="sap",
        configuration={"host": "h"},
        webhook_url="https://hook.example.com/x",
        webhook_events=["sync.done"],
    )
    assert cfg.webhook_url == "https://hook.example.com/x"
    assert cfg.webhook_events == ["sync.done"]


# ---------------------------------------------------------------------------
# initialize / authenticate
# ---------------------------------------------------------------------------


async def test_initialize_authenticates_and_sets_headers(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", json_body=AUTH_RESPONSE)
    client = make_client(api.base_url)
    async with client:
        assert client.access_token == "tok-123"
        assert client.refresh_token == "rt-1"
        assert client.token_expires_at is not None
        assert client.token_expires_at > datetime.now(UTC)
        assert client.session is not None
        assert client.session.headers["Authorization"] == "Bearer tok-123"
        assert client.session.headers["User-Agent"].startswith("AITBC-Enterprise-SDK/")
        assert client.session.headers["Content-Type"] == "application/json"

    assert len(api.requests) == 1
    req = api.requests[0]
    assert req["method"] == "POST"
    assert req["path"] == "/auth"
    assert req["body"] == {
        "tenant_id": "tenant-1",
        "client_id": "client-1",
        "client_secret": "s3cret",
        "auth_method": "client_credentials",
    }
    # context manager exit closed the session
    assert client.session.closed


async def test_unsupported_auth_method_raises(api: FakeEnterpriseAPI) -> None:
    client = make_client(api.base_url, auth_method=AuthenticationMethod.API_KEY)
    with pytest.raises(ValueError, match="Unsupported auth method"):
        await client.initialize()
    await client.close()
    assert api.requests == []


async def test_authenticate_without_session_raises() -> None:
    client = EnterpriseClient(make_config("http://127.0.0.1:1"))
    with pytest.raises(RuntimeError, match="Session not initialized"):
        await client.authenticate()


async def test_auth_failure_status_raises(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", status=401, text="bad credentials")
    client = make_client(api.base_url)
    with pytest.raises(Exception, match="Authentication failed: 401"):
        await client.initialize()
    await client.close()


async def test_auth_invalid_json_raises(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", status=200, text="this is not json", content_type="text/plain")
    client = make_client(api.base_url)
    with pytest.raises(Exception, match="Failed to parse auth response"):
        await client.initialize()
    await client.close()


async def test_close_without_session_is_noop() -> None:
    client = make_client("http://127.0.0.1:1")
    await client.close()  # must not raise


# ---------------------------------------------------------------------------
# token refresh
# ---------------------------------------------------------------------------


async def test_expired_token_triggers_reauth(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", json_body=AUTH_RESPONSE)
    api.add("GET", "/analytics", json_body={"jobs": 5})
    client = make_client(api.base_url)
    async with client:
        client.token_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        resp = await client.get_analytics()
        assert resp.success is True

    auth_calls = [r for r in api.requests if r["path"] == "/auth"]
    assert len(auth_calls) == 2  # initial + refresh


async def test_valid_token_does_not_reauth(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", json_body=AUTH_RESPONSE)
    api.add("GET", "/analytics", json_body={"jobs": 5})
    client = make_client(api.base_url)
    async with client:
        await client.get_analytics()

    auth_calls = [r for r in api.requests if r["path"] == "/auth"]
    assert len(auth_calls) == 1


# ---------------------------------------------------------------------------
# integration endpoints
# ---------------------------------------------------------------------------


async def test_create_integration_with_webhook(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", json_body=AUTH_RESPONSE)
    api.add("POST", "/integrations", json_body={"id": "int-1", "status": "created"})
    client = make_client(api.base_url)
    async with client:
        cfg = IntegrationConfig(
            integration_type=IntegrationType.ERP,
            provider="sap",
            configuration={"host": "sap.internal"},
            webhook_url="https://hooks.example.com/aitbc",
            webhook_events=["sync.done", "error"],
        )
        resp = await client.create_integration(cfg)

    assert resp.success is True
    assert resp.data == {"id": "int-1", "status": "created"}
    body = api.requests[-1]["body"]
    assert body["integration_type"] == "erp"
    assert body["provider"] == "sap"
    assert body["configuration"] == {"host": "sap.internal"}
    assert body["webhook_config"] == {
        "url": "https://hooks.example.com/aitbc",
        "events": ["sync.done", "error"],
        "active": True,
    }


async def test_create_integration_without_webhook(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", json_body=AUTH_RESPONSE)
    api.add("POST", "/integrations", json_body={"id": "int-2"})
    client = make_client(api.base_url)
    async with client:
        cfg = IntegrationConfig(
            integration_type=IntegrationType.CRM,
            provider="salesforce",
            configuration={"instance": "prod"},
        )
        resp = await client.create_integration(cfg)

    assert resp.success is True
    body = api.requests[-1]["body"]
    assert "webhook_config" not in body


async def test_create_integration_error_status(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", json_body=AUTH_RESPONSE)
    api.add("POST", "/integrations", status=422, text="invalid provider")
    client = make_client(api.base_url)
    async with client:
        cfg = IntegrationConfig(integration_type=IntegrationType.BI, provider="x", configuration={})
        resp = await client.create_integration(cfg)

    assert resp.success is False
    assert resp.error == "Integration creation failed: 422 - invalid provider"


async def test_create_integration_transport_error(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", json_body=AUTH_RESPONSE)
    client = make_client(api.base_url)
    async with client:
        # Point the client at a dead port after auth succeeded.
        client.config.base_url = "http://127.0.0.1:1"
        cfg = IntegrationConfig(integration_type=IntegrationType.CUSTOM, provider="x", configuration={})
        resp = await client.create_integration(cfg)

    assert resp.success is False
    assert resp.error  # connector error string


async def test_get_integration_status_success(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", json_body=AUTH_RESPONSE)
    api.add("GET", "/integrations/", json_body={"id": "int-1", "state": "active"})
    client = make_client(api.base_url)
    async with client:
        resp = await client.get_integration_status("int-1")

    assert resp.success is True
    assert resp.data == {"id": "int-1", "state": "active"}
    assert api.requests[-1]["path"] == "/integrations/int-1/status"
    assert api.requests[-1]["method"] == "GET"


async def test_get_integration_status_error(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", json_body=AUTH_RESPONSE)
    api.add("GET", "/integrations/", status=404, text="not found")
    client = make_client(api.base_url)
    async with client:
        resp = await client.get_integration_status("missing")

    assert resp.success is False
    assert "Failed to get integration status: 404" in resp.error


async def test_test_integration_success(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", json_body=AUTH_RESPONSE)
    api.add("POST", "/integrations/", json_body={"reachable": True, "latency_ms": 12})
    client = make_client(api.base_url)
    async with client:
        resp = await client.test_integration("int-9")

    assert resp.success is True
    assert resp.data["reachable"] is True
    assert api.requests[-1]["path"] == "/integrations/int-9/test"
    assert api.requests[-1]["method"] == "POST"


async def test_test_integration_error(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", json_body=AUTH_RESPONSE)
    api.add("POST", "/integrations/", status=503, text="upstream down")
    client = make_client(api.base_url)
    async with client:
        resp = await client.test_integration("int-9")

    assert resp.success is False
    assert "Integration test failed: 503" in resp.error


async def test_sync_data_success(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", json_body=AUTH_RESPONSE)
    api.add("POST", "/integrations/", json_body={"synced": 42})
    client = make_client(api.base_url)
    async with client:
        resp = await client.sync_data("int-1", "customers", {"since": "2026-01-01"})

    assert resp.success is True
    assert resp.data == {"synced": 42}
    assert api.requests[-1]["path"] == "/integrations/int-1/sync"
    assert api.requests[-1]["body"] == {
        "operation": "sync_data",
        "parameters": {"data_type": "customers", "filters": {"since": "2026-01-01"}},
    }


async def test_sync_data_no_filters(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", json_body=AUTH_RESPONSE)
    api.add("POST", "/integrations/", json_body={"synced": 0})
    client = make_client(api.base_url)
    async with client:
        resp = await client.sync_data("int-1", "orders")

    assert resp.success is True
    assert api.requests[-1]["body"]["parameters"]["filters"] == {}


async def test_sync_data_error(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", json_body=AUTH_RESPONSE)
    api.add("POST", "/integrations/", status=500, text="sync blew up")
    client = make_client(api.base_url)
    async with client:
        resp = await client.sync_data("int-1", "products")

    assert resp.success is False
    assert "Data sync failed: 500" in resp.error


async def test_push_data_success(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", json_body=AUTH_RESPONSE)
    api.add("POST", "/integrations/", json_body={"pushed": True})
    client = make_client(api.base_url)
    async with client:
        resp = await client.push_data("int-1", "orders", {"order_id": "o-1", "total": 99})

    assert resp.success is True
    assert api.requests[-1]["path"] == "/integrations/int-1/push"
    assert api.requests[-1]["body"] == {
        "operation": "push_data",
        "data": {"order_id": "o-1", "total": 99},
        "parameters": {"data_type": "orders"},
    }


async def test_push_data_error(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", json_body=AUTH_RESPONSE)
    api.add("POST", "/integrations/", status=400, text="bad payload")
    client = make_client(api.base_url)
    async with client:
        resp = await client.push_data("int-1", "customers", {})

    assert resp.success is False
    assert "Data push failed: 400" in resp.error


async def test_get_analytics_success(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", json_body=AUTH_RESPONSE)
    api.add("GET", "/analytics", json_body={"jobs": 7, "revenue": 123.4})
    client = make_client(api.base_url)
    async with client:
        resp = await client.get_analytics()

    assert resp.success is True
    assert resp.data == {"jobs": 7, "revenue": 123.4}
    assert api.requests[-1]["path"] == "/analytics"


async def test_get_analytics_error(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", json_body=AUTH_RESPONSE)
    api.add("GET", "/analytics", status=502, text="bad gateway")
    client = make_client(api.base_url)
    async with client:
        resp = await client.get_analytics()

    assert resp.success is False
    assert "Failed to get analytics: 502" in resp.error


async def test_get_quota_status_success(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", json_body=AUTH_RESPONSE)
    api.add("GET", "/quota/", json_body={"used": 10, "limit": 100})
    client = make_client(api.base_url)
    async with client:
        resp = await client.get_quota_status()

    assert resp.success is True
    assert resp.data == {"used": 10, "limit": 100}
    assert api.requests[-1]["path"] == "/quota/status"


async def test_get_quota_status_error(api: FakeEnterpriseAPI) -> None:
    api.add("POST", "/auth", json_body=AUTH_RESPONSE)
    api.add("GET", "/quota/", status=403, text="forbidden")
    client = make_client(api.base_url)
    async with client:
        resp = await client.get_quota_status()

    assert resp.success is False
    assert "Failed to get quota status: 403" in resp.error


async def test_method_without_session_returns_failure() -> None:
    """A token but no session short-circuits to a failed APIResponse."""
    client = make_client("http://127.0.0.1:1")
    client.access_token = "tok"
    client.token_expires_at = None  # never expires -> no re-auth attempted
    resp = await client.get_analytics()
    assert resp.success is False
    assert resp.error == "Session not initialized"


# ---------------------------------------------------------------------------
# ERP / CRM helper wrappers
# ---------------------------------------------------------------------------


def _stubbed_client() -> EnterpriseClient:
    client = EnterpriseClient(make_config("http://127.0.0.1:1"))
    client.sync_data = AsyncMock(return_value=APIResponse(success=True, data={"ok": True}))
    client.push_data = AsyncMock(return_value=APIResponse(success=True, data={"ok": True}))
    return client


async def test_erp_integration_helpers() -> None:
    client = _stubbed_client()
    erp = ERPIntegration(client)

    await erp.sync_customers("int-1", {"active": True})
    client.sync_data.assert_awaited_with("int-1", "customers", {"active": True})

    await erp.sync_orders("int-1")
    client.sync_data.assert_awaited_with("int-1", "orders", None)

    await erp.sync_products("int-1", {"sku": "x"})
    client.sync_data.assert_awaited_with("int-1", "products", {"sku": "x"})

    await erp.create_customer("int-1", {"name": "Acme"})
    client.push_data.assert_awaited_with("int-1", "customers", {"name": "Acme"})

    await erp.create_order("int-1", {"total": 10})
    client.push_data.assert_awaited_with("int-1", "orders", {"total": 10})


async def test_crm_integration_helpers() -> None:
    client = _stubbed_client()
    crm = CRMIntegration(client)

    await crm.sync_contacts("int-2", {"tag": "vip"})
    client.sync_data.assert_awaited_with("int-2", "contacts", {"tag": "vip"})

    await crm.sync_opportunities("int-2")
    client.sync_data.assert_awaited_with("int-2", "opportunities", None)

    await crm.create_lead("int-2", {"email": "a@b.c"})
    client.push_data.assert_awaited_with("int-2", "leads", {"email": "a@b.c"})

    await crm.update_contact("int-2", "c-9", {"phone": "123"})
    client.push_data.assert_awaited_with("int-2", "contacts", {"contact_id": "c-9", "data": {"phone": "123"}})


# ---------------------------------------------------------------------------
# provider factory helpers
# ---------------------------------------------------------------------------


async def test_create_sap_integration() -> None:
    client = _stubbed_client()
    client.create_integration = AsyncMock(return_value=APIResponse(success=True))

    resp = await create_sap_integration(client, "SYS1", "100", "user", "pass", "sap.host", port=443)

    assert resp.success is True
    cfg = client.create_integration.await_args.args[0]
    assert isinstance(cfg, IntegrationConfig)
    assert cfg.integration_type == IntegrationType.ERP
    assert cfg.provider == "sap"
    assert cfg.configuration["system_id"] == "SYS1"
    assert cfg.configuration["client"] == "100"
    assert cfg.configuration["endpoint_url"] == "http://sap.host:443/sap"
    assert cfg.configuration["port"] == 443


async def test_create_sap_integration_default_port() -> None:
    client = _stubbed_client()
    client.create_integration = AsyncMock(return_value=APIResponse(success=True))

    await create_sap_integration(client, "SYS", "200", "u", "p", "h")

    cfg = client.create_integration.await_args.args[0]
    assert cfg.configuration["port"] == 8000
    assert cfg.configuration["endpoint_url"] == "http://h:8000/sap"


async def test_create_salesforce_integration() -> None:
    client = _stubbed_client()
    client.create_integration = AsyncMock(return_value=APIResponse(success=True))

    resp = await create_salesforce_integration(client, "cid", "csec", "u", "p", "token")

    assert resp.success is True
    cfg = client.create_integration.await_args.args[0]
    assert cfg.integration_type == IntegrationType.CRM
    assert cfg.provider == "salesforce"
    assert cfg.configuration["client_id"] == "cid"
    assert cfg.configuration["security_token"] == "token"
    assert cfg.configuration["endpoint_url"] == "https://login.salesforce.com"


# ---------------------------------------------------------------------------
# WebhookHandler
# ---------------------------------------------------------------------------


def _sign(secret: str, payload: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def test_webhook_verify_without_secret_always_true() -> None:
    handler = WebhookHandler(secret=None)
    assert handler.verify_webhook_signature("anything", "bogus") is True


def test_webhook_verify_signature_valid_and_invalid() -> None:
    secret = "whsec"
    handler = WebhookHandler(secret=secret)
    payload = '{"event":"sync.done"}'
    good = _sign(secret, payload)
    assert handler.verify_webhook_signature(payload, good) is True
    assert handler.verify_webhook_signature(payload, "0" * 64) is False
    assert handler.verify_webhook_signature(payload + "x", good) is False


async def test_handle_webhook_success() -> None:
    handler = WebhookHandler()

    async def on_event(payload: dict) -> dict:
        return {"received": payload["id"]}

    handler.register_handler("sync.done", on_event)
    result = await handler.handle_webhook("sync.done", {"id": 7})
    assert result == {"status": "success", "result": {"received": 7}}


async def test_handle_webhook_handler_raises() -> None:
    handler = WebhookHandler()

    async def boom(payload: dict) -> dict:
        raise RuntimeError("handler exploded")

    handler.register_handler("err", boom)
    result = await handler.handle_webhook("err", {})
    assert result["status"] == "error"
    assert "handler exploded" in result["error"]


async def test_handle_webhook_no_handler() -> None:
    handler = WebhookHandler()
    result = await handler.handle_webhook("unknown.event", {"x": 1})
    assert result == {"status": "error", "error": "No handler for event type: unknown.event"}
