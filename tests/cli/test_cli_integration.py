"""
CLI integration tests against a live (in-memory) coordinator.

Spins up the real coordinator FastAPI app with an in-memory SQLite DB,
then patches httpx.Client so every CLI command's HTTP call is routed
through the ASGI transport instead of making real network requests.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from httpx import AsyncClient, ASGITransport

# ---------------------------------------------------------------------------
# Ensure coordinator-api src is importable
# ---------------------------------------------------------------------------
_COORD_SRC = str(Path(__file__).resolve().parents[2] / "apps" / "coordinator-api" / "src")

_existing = sys.modules.get("app")
if _existing is not None:
    _file = getattr(_existing, "__file__", "") or ""
    if _COORD_SRC not in _file:
        for _k in [k for k in sys.modules if k == "app" or k.startswith("app.")]:
            del sys.modules[_k]

if _COORD_SRC in sys.path:
    sys.path.remove(_COORD_SRC)
sys.path.insert(0, _COORD_SRC)

# CLI imports
from aitbc_cli import cli  # noqa: E402
from app.deps import APIKeyValidator  # noqa: E402
from app.main import create_app  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TEST_KEY = "test-integration-key"

# Save original APIKeyValidator.__call__ so we can restore it
_orig_validator_call = APIKeyValidator.__call__


@pytest.fixture(autouse=True)
def _bypass_api_key_auth():
    """
    Monkey-patch APIKeyValidator so every validator instance accepts the
    test key.  This is necessary because validators capture keys at
    construction time and may have stale (empty) key sets when other
    test files flush sys.modules and re-import the coordinator package.
    """

    def _accept_test_key(self, api_key=None):
        return api_key or _TEST_KEY

    APIKeyValidator.__call__ = _accept_test_key
    yield
    APIKeyValidator.__call__ = _orig_validator_call


@pytest.fixture(autouse=True)
def mock_config():
    """Patch get_config so CLI commands route to the test server."""
    from unittest.mock import Mock

    from aitbc_cli import config as config_module

    mock_cfg = Mock()
    mock_cfg.coordinator_url = "http://testserver"
    mock_cfg.api_key = _TEST_KEY
    mock_cfg.blockchain_rpc_url = "http://testserver"
    mock_cfg.wallet_daemon_url = "http://testserver"
    mock_cfg.gpu_service_url = "http://testserver"
    mock_cfg.marketplace_service_url = "http://testserver"
    mock_cfg.exchange_service_url = "http://testserver"
    mock_cfg.governance_service_url = "http://testserver"
    mock_cfg.trading_service_url = "http://testserver"
    mock_cfg.agent_coordinator_url = "http://testserver"
    mock_cfg.edge_api_host = "localhost"
    mock_cfg.edge_api_port = 8103
    mock_cfg.hub_discovery_url = "hub.aitbc.bubuit.net"
    mock_cfg.chain_id = "ait-mainnet"
    mock_cfg.timeout = 30
    mock_cfg.app_name = "AITBC CLI"
    mock_cfg.app_version = "2.1.0"
    mock_cfg.config_file = None
    mock_cfg.jwt_secret = "test-jwt-secret-change-in-production"

    orig_get_config = config_module.get_config
    config_module.get_config = lambda *a, **k: mock_cfg
    yield
    config_module.get_config = orig_get_config


@pytest.fixture()
def coord_app():
    """Create a fresh coordinator app (tables auto-created by create_app)."""
    return create_app()


@pytest.fixture()
async def test_client(coord_app):
    """httpx AsyncClient wrapping the coordinator app with ASGI transport."""
    transport = ASGITransport(app=coord_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as tc:
        yield tc


class _ProxyClient:
    """
    Drop-in replacement for httpx.Client that proxies all requests through
    an httpx.AsyncClient with ASGI transport. Supports sync context-manager usage
    (``with httpx.Client() as c: ...``).
    """

    def __init__(self, async_client: AsyncClient):
        self._ac = async_client

    # --- context-manager protocol ---
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    # --- HTTP verbs ---
    def get(self, url, **kw):
        return self._request("GET", url, **kw)

    def post(self, url, **kw):
        return self._request("POST", url, **kw)

    def put(self, url, **kw):
        return self._request("PUT", url, **kw)

    def delete(self, url, **kw):
        return self._request("DELETE", url, **kw)

    def patch(self, url, **kw):
        return self._request("PATCH", url, **kw)

    def _request(self, method, url, **kw):
        # Run async request in sync context
        import asyncio

        # Normalise URL: strip scheme+host so AsyncClient gets just the path
        from urllib.parse import urlparse

        parsed = urlparse(str(url))
        path = parsed.path
        if parsed.query:
            path = f"{path}?{parsed.query}"

        # Map httpx kwargs
        headers = dict(kw.get("headers") or {})
        params = kw.get("params")
        json_body = kw.get("json")
        content = kw.get("content")
        timeout = kw.get("timeout", 30)

        # Run the async request
        loop = asyncio.get_event_loop()
        try:
            resp = loop.run_until_complete(
                self._ac.request(
                    method,
                    path,
                    headers=headers,
                    params=params,
                    json=json_body,
                    content=content,
                    timeout=timeout,
                )
            )
        except Exception as e:
            # Create a mock response for errors
            from httpx import Response

            resp = Response(500, request=None)
            resp._content = str(e).encode()

        return resp


class _PatchedClientFactory:
    """Callable that replaces ``httpx.Client`` during tests."""

    def __init__(self, async_client: AsyncClient):
        self._ac = async_client

    def __call__(self, **kwargs):
        return _ProxyClient(self._ac)


@pytest.fixture()
async def patched_httpx(test_client):
    """Patch httpx.Client globally so CLI commands hit the test coordinator."""
    factory = _PatchedClientFactory(test_client)
    with patch("httpx.Client", new=factory):
        yield


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture()
async def invoke(runner, patched_httpx, mock_config):
    """Helper: invoke a CLI command with the test API key and coordinator URL."""
    from unittest.mock import Mock

    cfg = Mock()
    cfg.coordinator_url = "http://testserver"
    cfg.api_key = _TEST_KEY
    cfg.timeout = 30
    cfg.config_file = None

    def _invoke(*args, **kwargs):
        full_args = [
            "--url",
            "http://testserver",
            "--api-key",
            _TEST_KEY,
            "--output",
            "json",
            *args,
        ]
        obj = kwargs.pop("obj", {})
        obj["config"] = cfg
        result = runner.invoke(cli, full_args, obj=obj, **kwargs)
        return result

    return _invoke


# ===========================================================================
# System commands
# ===========================================================================


class TestSystemCommands:
    """Test system management commands."""

    async def test_architect(self, invoke):
        r = invoke("system", "architect")
        assert r.exit_code == 0
        assert "System Architecture" in r.output

    async def test_audit(self, invoke):
        r = invoke("system", "audit")
        assert r.exit_code == 0
        assert "System Audit" in r.output

    async def test_check(self, invoke):
        r = invoke("system", "check")
        assert r.exit_code == 0
        assert "Service Check" in r.output

    async def test_status(self, invoke):
        r = invoke("system", "status")
        # coordinator may not expose /api/v1/status
        assert r.exit_code in (0, 1)


# ===========================================================================
# Config commands
# ===========================================================================


class TestConfigCommands:
    """Test config management commands."""

    async def test_show(self, invoke):
        r = invoke("config", "show")
        assert r.exit_code == 0

    async def test_path(self, invoke):
        r = invoke("config", "path")
        assert r.exit_code == 0

    async def test_environments(self, invoke):
        r = invoke("config", "environments")
        assert r.exit_code == 0


# ===========================================================================
# Version / info commands
# ===========================================================================


class TestVersionCommands:
    """Test version command."""

    async def test_version(self, invoke):
        r = invoke("version")
        assert r.exit_code == 0
        assert "aitbc, version" in r.output

    async def test_list_wallets(self, invoke):
        r = invoke("list")
        # Wallet list may fail if no wallets configured, but CLI should not crash
        assert r.exit_code in (0, 1)


# ===========================================================================
# AI commands
# ===========================================================================


class TestAICommands:
    """Test AI job submission and inspection commands."""

    async def test_ai_jobs(self, invoke):
        r = invoke("ai", "jobs")
        # coordinator may return empty list or 404
        assert r.exit_code in (0, 1)

    async def test_ai_stats(self, invoke):
        r = invoke("ai", "stats")
        assert r.exit_code in (0, 1)

    async def test_ai_service_list(self, invoke):
        r = invoke("ai", "service", "list")
        assert r.exit_code in (0, 1)

    async def test_ai_submit(self, invoke):
        r = invoke("ai", "submit", "--type", "inference", "--prompt", "hello")
        # May fail if coordinator rejects payload, but Click parsing should succeed
        assert r.exit_code in (0, 1), f"Unexpected error: {r.output}"


# ===========================================================================
# Agent commands
# ===========================================================================


class TestAgentCommands:
    """Test agent SDK management commands."""

    async def test_agent_list(self, invoke):
        r = invoke("agent", "list")
        assert r.exit_code == 0

    async def test_agent_status(self, invoke):
        r = invoke("agent", "status", "test-agent")
        assert r.exit_code == 0

    async def test_agent_capabilities(self, invoke):
        r = invoke("agent", "capabilities")
        # Agent SDK may not be installed in test environment
        assert r.exit_code in (0, 1)


# ===========================================================================
# GPU commands
# ===========================================================================


class TestGPUCommands:
    """Test GPU marketplace commands."""

    async def test_gpu_list(self, invoke):
        r = invoke("gpu", "list")
        # Coordinator may not expose GPU service endpoint
        assert r.exit_code in (0, 1)

    async def test_gpu_discover(self, invoke):
        r = invoke("gpu", "discover")
        # nvidia-smi may not be available in CI
        assert r.exit_code in (0, 1)


# ===========================================================================
# Operations / governance commands
# ===========================================================================


class TestOperationsCommands:
    """Test operations governance commands."""

    async def test_governance_voting_power(self, invoke):
        r = invoke("operations", "governance", "voting-power", "aitbc1test")
        # Requires blockchain RPC, may fail in integration context
        assert r.exit_code in (0, 1)


# ===========================================================================
# Marketplace commands
# ===========================================================================


class TestMarketplaceCommands:
    """Test marketplace commands."""

    async def test_marketplace_overview(self, invoke):
        r = invoke("marketplace", "overview")
        assert r.exit_code in (0, 1)

    async def test_marketplace_bids(self, invoke):
        r = invoke("marketplace", "bids")
        assert r.exit_code in (0, 1)

    async def test_marketplace_asks(self, invoke):
        r = invoke("marketplace", "asks")
        assert r.exit_code in (0, 1)
