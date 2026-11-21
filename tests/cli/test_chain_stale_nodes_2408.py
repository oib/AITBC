"""#2408 item 3: synthesized chain rows report only published fields.

``NodeClient._chain_info_from_id`` used to hardcode ``size_mb=50.5``,
``nodes=3``, ``clients=25`` etc. for every chain the node listed — which is
why ``bc-2`` and ``bc-2-island-1`` showed an identical "50.5MB". The record
now carries the ``/rpc/info`` height/block_time and the real local
``chain.db`` size; everything the RPC does not publish stays 0.

The stale-registry half of item 3 (per-node failure noise → ``ok:false``)
landed separately in #2424 — see ``cli/tests/test_chain_stale_node_noise_2424.py``.
"""

import httpx
import pytest

from aitbc_cli.core.config import NodeConfig
from aitbc_cli.core.node_client import NodeClient


class TestSynthesizedChainInfoHonesty:
    def test_no_fabricated_metrics(self, monkeypatch):
        monkeypatch.setenv("AITBC_DATA_DIR", "/nonexistent-aitbc-data")
        client = NodeClient(NodeConfig(id="n1", endpoint="http://127.0.0.1:8202"))
        info = client._chain_info_from_id("bc-2-island-1", 42)
        assert info.size_mb == 0.0
        assert info.node_count == 0
        assert info.active_nodes == 0
        assert info.client_count == 0
        assert info.miner_count == 0
        assert info.contract_count == 0
        assert info.name == "bc-2-island-1"
        assert info.block_height == 42

    def test_real_chain_db_size_when_local(self, monkeypatch, tmp_path):
        db = tmp_path / "data" / "bc-2" / "chain.db"
        db.parent.mkdir(parents=True)
        db.write_bytes(b"x" * (3 * 1024 * 1024 + 1))
        monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
        client = NodeClient(NodeConfig(id="n1", endpoint="http://127.0.0.1:8202"))
        info = client._chain_info_from_id("bc-2", 7)
        assert info.size_mb == pytest.approx(3.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_hosted_chains_uses_rpc_info_fields(self, monkeypatch):
        """/rpc/info supplies height + block_time; nothing is invented."""
        calls = []

        def _handler(request: httpx.Request) -> httpx.Response:
            calls.append(f"{request.method} {request.url.path}?{request.url.query}")
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "ok", "supported_chains": ["bc-2"]})
            if request.url.path == "/rpc/info":
                return httpx.Response(
                    200,
                    json={
                        "chain_id": "bc-2",
                        "height": 555,
                        "genesis_params": {"block_time_seconds": 3},
                    },
                )
            return httpx.Response(404, json={"detail": "not found"})

        transport = httpx.MockTransport(_handler)
        orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: orig(transport=transport))
        monkeypatch.setenv("AITBC_DATA_DIR", "/nonexistent-aitbc-data")

        client = NodeClient(NodeConfig(id="n1", endpoint="http://127.0.0.1:8202"))
        async with client:
            chains = await client.get_hosted_chains()

        assert len(chains) == 1
        info = chains[0]
        assert info.id == "bc-2"
        assert info.block_height == 555
        assert info.block_time == 3
        assert info.size_mb == 0.0
        # No fabricated /rpc/head fallback needed when /info answered.
        assert not any("/rpc/head" in c for c in calls)
