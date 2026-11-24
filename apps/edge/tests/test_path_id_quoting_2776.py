"""#2776: user-controlled ids interpolated into authenticated upstream URLs
must be percent-encoded as a single path segment — '/', '?', '..' and '%'
may not alter the request path or smuggle a query string.
"""

import httpx
import pytest
from aitbc.utils import quote_path_segment
from aitbc.market.blockchain_rpc import BlockchainRPCClient as MarketRPCClient
from aitbc_edge.clients.blockchain_rpc import BlockchainRPCClient as EdgeRPCClient
from aitbc_edge.clients.gpu_service import GPUServiceClient

HOSTILE = "../../transactions"
QUERY_SMUGGLE = "abc?chain_id=evil"


def test_quote_path_segment_encodes_separators_and_dots():
    assert quote_path_segment(HOSTILE) == "%2E%2E%2F%2E%2E%2Ftransactions"
    assert quote_path_segment(QUERY_SMUGGLE) == "abc%3Fchain_id%3Devil"
    assert quote_path_segment("a/b#c%d e") == "a%2Fb%23c%25d%20e"


def test_quote_path_segment_leaves_normal_ids_untouched():
    for value in ("job_abc-123", "0xAbC123", "gpu-9", "miner_1", "bc-2", "a~b_c"):
        assert quote_path_segment(value) == value


@pytest.mark.asyncio
async def test_edge_island_info_cannot_escape_its_prefix():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["raw_path"] = request.url.raw_path.decode()
        return httpx.Response(200, json={})

    async with EdgeRPCClient() as client:
        client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        await client.get_island_info(HOSTILE)

    assert seen["raw_path"].startswith("/rpc/islands/")
    assert "%2E%2E%2F" in seen["raw_path"]
    assert "/transactions" not in seen["raw_path"].split("/rpc/islands/", 1)[1]


@pytest.mark.asyncio
async def test_edge_gpu_client_paths_stay_single_segment():
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.raw_path.decode())
        return httpx.Response(200, json=[])

    async with GPUServiceClient() as client:
        client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        await client.scan_gpus(HOSTILE)
        await client.get_gpu_metrics(QUERY_SMUGGLE, limit=5)
        await client.get_miner_gpus("../x")

    assert len(seen_paths) == 3
    assert seen_paths[0].startswith("/v1/market/edge-gpu/scan/")
    assert seen_paths[1].startswith("/v1/market/edge-gpu/metrics/")
    assert seen_paths[2].startswith("/v1/miners/")
    assert seen_paths[2].endswith("/gpus")
    # every hostile id arrived percent-encoded — no literal '/', '?', '#'
    for path in seen_paths:
        assert "%2F" in path or "%3F" in path or "%2E" in path, path


class _Ctx:
    """Async-context-manager stand-in for the client's per-call _client()."""

    def __init__(self, real):
        self._real = real

    async def __aenter__(self):
        return self._real

    async def __aexit__(self, *args):
        return None


@pytest.mark.asyncio
async def test_market_client_path_ids_cannot_smuggle(monkeypatch):
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.raw_path.decode())
        return httpx.Response(200, json={})

    real = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(MarketRPCClient, "_client", lambda self: _Ctx(real))

    client = MarketRPCClient(rpc_url="http://rpc:8202")
    await client.verify_escrow(HOSTILE)
    await client.verify_escrow("job_ok-1")
    await client.release_escrow(QUERY_SMUGGLE)
    await client.refund_escrow("../admin")
    await client.get_offer("../../gpus")
    await client.get_account("0xabc?chain_id=evil")
    await client.get_transaction("../../blocks")

    expected_prefixes = [
        "/rpc/escrow/",
        "/rpc/escrow/",
        "/rpc/escrow/",
        "/rpc/escrow/",
        "/rpc/gpu/info/",
        "/rpc/account/",
        "/rpc/transaction/",
    ]
    assert len(seen_paths) == len(expected_prefixes)
    for path, prefix in zip(seen_paths, expected_prefixes, strict=False):
        assert path.startswith(prefix), path

    # normal id passes through byte-identical
    assert seen_paths[1] == "/rpc/escrow/job_ok-1"
    # hostile ids are encoded inside their own prefix — never a new path
    assert "/rpc/transactions" not in seen_paths[0]
    assert "%2E%2E%2F" in seen_paths[0]
    assert "%3F" in seen_paths[2]
    assert seen_paths[2].startswith("/rpc/escrow/") and seen_paths[2].endswith("/release")
    assert seen_paths[3].startswith("/rpc/escrow/") and seen_paths[3].endswith("/refund")
    assert "%2E%2E%2F" in seen_paths[4]
    assert "%3F" in seen_paths[5]
    assert "%2E%2E%2F" in seen_paths[6]
