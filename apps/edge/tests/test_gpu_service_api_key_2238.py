"""#2238 — edge -> gpu service API key propagation and honest error surfacing."""

import httpx
import pytest
from fastapi import HTTPException

from aitbc_edge.clients.gpu_service import GPUServiceClient
from aitbc_edge.config import Settings
from aitbc_edge.routers.gpu import ScanGPUsRequest, scan_gpus


@pytest.mark.asyncio
async def test_gpu_service_client_sends_api_key_header():
    """The gpu service's APIKeyAuthenticator gates scan behind X-Api-Key —
    the shared client must carry it on every request once configured."""
    async with GPUServiceClient(api_key="edge-secret") as client:
        assert client.client.headers["X-Api-Key"] == "edge-secret"


@pytest.mark.asyncio
async def test_gpu_service_client_no_header_without_key():
    async with GPUServiceClient(api_key="") as client:
        assert "X-Api-Key" not in client.client.headers


def test_gpu_service_api_key_settings_alias(monkeypatch):
    """GPU_SERVICE_API_KEY is the edge-specific name; GPU_API_KEY (the var
    aitbc-gpu itself reads) is the fallback alias."""
    monkeypatch.setenv("GPU_SERVICE_API_KEY", "svc-key")
    assert Settings().gpu_service_api_key == "svc-key"

    monkeypatch.delenv("GPU_SERVICE_API_KEY")
    monkeypatch.setenv("GPU_API_KEY", "gpu-key")
    assert Settings().gpu_service_api_key == "gpu-key"


@pytest.mark.asyncio
async def test_scan_gpus_surfaces_upstream_401_as_4xx():
    """An upstream gpu-service 401 is an edge/gpu misconfiguration, not an
    edge-internal fault — the route must not return the blanket 500."""

    class _FailingService:
        async def scan_gpus(self, miner_id: str):
            request = httpx.Request("POST", "http://localhost:8101/v1/market/edge-gpu/scan/x")
            response = httpx.Response(401, request=request)
            raise httpx.HTTPStatusError("401", request=request, response=response)

    with pytest.raises(HTTPException) as exc_info:
        await scan_gpus(None, ScanGPUsRequest(miner_id="m1"), _FailingService())
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_scan_gpus_maps_upstream_5xx_to_502():
    class _FailingService:
        async def scan_gpus(self, miner_id: str):
            request = httpx.Request("POST", "http://localhost:8101/v1/market/edge-gpu/scan/x")
            response = httpx.Response(503, request=request)
            raise httpx.HTTPStatusError("503", request=request, response=response)

    with pytest.raises(HTTPException) as exc_info:
        await scan_gpus(None, ScanGPUsRequest(miner_id="m1"), _FailingService())
    assert exc_info.value.status_code == 502
