"""Coverage pin for #1541: developer-platform /health runs REAL probes.

``GET /v1/developer-platform/health`` used to hardcode
``blockchain``/``ipfs``/``smart_contracts`` to ``"healthy"``. The merged
fix probes AITBC ``/rpc/head``, IPFS ``POST /api/v0/id`` and
``eth_chainId`` on ``ETH_RPC_URL`` (``not_configured`` when no EVM rail is
set), and any probed-but-failed dependency degrades the overall status.
No test covered any of it — this file pins the probe functions and the
endpoint aggregation.

Coder: C
"""

from __future__ import annotations


from coordinator_api.contexts.developer_platform.routers import analytics


class _Resp:
    def __init__(self, status_code: int = 200, json_data=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}

    def json(self):
        return self._json


def _patch_httpx(monkeypatch, *, get=None, post=None):
    """Install fake httpx.get/post; callables receive the URL."""
    monkeypatch.setattr(analytics.httpx, "get", get or (lambda *a, **k: _Resp(200)))
    monkeypatch.setattr(analytics.httpx, "post", post or (lambda *a, **k: _Resp(200)))


class TestBlockchainProbe:
    def test_healthy_on_200(self, monkeypatch):
        _patch_httpx(monkeypatch)
        assert analytics._probe_blockchain() == "healthy"

    def test_unhealthy_on_http_error(self, monkeypatch):
        _patch_httpx(monkeypatch, get=lambda *a, **k: _Resp(503))
        assert analytics._probe_blockchain() == "unhealthy"

    def test_unhealthy_on_exception(self, monkeypatch):
        def _boom(*a, **k):
            raise ConnectionError("node down")

        _patch_httpx(monkeypatch, get=_boom)
        assert analytics._probe_blockchain() == "unhealthy"


class TestIpfsProbe:
    def test_healthy_on_200(self, monkeypatch):
        _patch_httpx(monkeypatch)
        assert analytics._probe_ipfs() == "healthy"

    def test_unhealthy_on_error(self, monkeypatch):
        _patch_httpx(monkeypatch, post=lambda *a, **k: _Resp(500))
        assert analytics._probe_ipfs() == "unhealthy"

    def test_unhealthy_on_exception(self, monkeypatch):
        def _boom(*a, **k):
            raise TimeoutError("ipfs unreachable")

        _patch_httpx(monkeypatch, post=_boom)
        assert analytics._probe_ipfs() == "unhealthy"


class TestSmartContractsProbe:
    def test_not_configured_without_eth_rpc(self, monkeypatch):
        from coordinator_api.config import settings

        monkeypatch.setattr(settings, "eth_rpc_url", None)
        assert analytics._probe_smart_contracts() == "not_configured"

    def test_healthy_on_chainid_result(self, monkeypatch):
        from coordinator_api.config import settings

        monkeypatch.setattr(settings, "eth_rpc_url", "http://evm.test:8545")
        _patch_httpx(monkeypatch, post=lambda *a, **k: _Resp(200, {"result": "0x1"}))
        assert analytics._probe_smart_contracts() == "healthy"

    def test_unhealthy_without_result(self, monkeypatch):
        from coordinator_api.config import settings

        monkeypatch.setattr(settings, "eth_rpc_url", "http://evm.test:8545")
        _patch_httpx(monkeypatch, post=lambda *a, **k: _Resp(200, {"error": "nope"}))
        assert analytics._probe_smart_contracts() == "unhealthy"

    def test_unhealthy_on_exception(self, monkeypatch):
        from coordinator_api.config import settings

        monkeypatch.setattr(settings, "eth_rpc_url", "http://evm.test:8545")

        def _boom(*a, **k):
            raise OSError("refused")

        _patch_httpx(monkeypatch, post=_boom)
        assert analytics._probe_smart_contracts() == "unhealthy"


class TestPlatformHealthEndpoint:
    """End-to-end: the /health payload aggregates real probe outcomes."""

    def _all_healthy(self, monkeypatch):
        from coordinator_api.config import settings

        monkeypatch.setattr(settings, "eth_rpc_url", "http://evm.test:8545")

        def _post(url, *a, **k):
            # Both IPFS /api/v0/id and the EVM eth_chainId POST land here.
            if "api/v0/id" in str(url):
                return _Resp(200)
            return _Resp(200, {"result": "0x1"})

        _patch_httpx(monkeypatch, post=_post)

    def test_all_probes_healthy_reports_healthy(self, client, monkeypatch):
        self._all_healthy(monkeypatch)
        response = client.get("/v1/developer-platform/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["services"]["blockchain"] == "healthy"
        assert body["services"]["ipfs"] == "healthy"
        assert body["services"]["smart_contracts"] == "healthy"

    def test_failed_probe_degrades_overall(self, client, monkeypatch):
        from coordinator_api.config import settings

        monkeypatch.setattr(settings, "eth_rpc_url", "http://evm.test:8545")

        def _post(url, *a, **k):
            if "api/v0/id" in str(url):
                return _Resp(200)
            return _Resp(200, {"result": "0x1"})

        def _get(*a, **k):
            return _Resp(503)  # AITBC /rpc/head down

        _patch_httpx(monkeypatch, get=_get, post=_post)
        response = client.get("/v1/developer-platform/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "degraded"
        assert body["services"]["blockchain"] == "unhealthy"
        # A probed-but-failed dependency is what degrades — ipfs/contracts
        # stayed healthy and must not be dragged down with it.
        assert body["services"]["ipfs"] == "healthy"
        assert body["services"]["smart_contracts"] == "healthy"

    def test_unconfigured_evm_rail_does_not_degrade(self, client, monkeypatch):
        """``not_configured`` is honest, not a failure — no EVM rail on this
        deployment must not report degraded."""
        from coordinator_api.config import settings

        monkeypatch.setattr(settings, "eth_rpc_url", None)
        _patch_httpx(monkeypatch, post=lambda *a, **k: _Resp(200))
        response = client.get("/v1/developer-platform/health")
        assert response.status_code == 200
        body = response.json()
        assert body["services"]["smart_contracts"] == "not_configured"
        assert body["status"] == "healthy"
