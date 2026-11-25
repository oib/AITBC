"""Tests for aitbc.blockchain.rpc_client.BlockchainClient URL handling.

#2948: chain discovery registers public endpoints that already include the
``/rpc`` mount prefix (``https://hub.example/rpc``); the client appended
``/rpc/<endpoint>`` again and every registered chain reported unreachable.
"""

from __future__ import annotations

import httpx

from aitbc.blockchain.rpc_client import BlockchainClient, _rpc_base_url


class TestRpcBaseUrl:
    def test_bare_host_unchanged(self):
        assert _rpc_base_url("http://127.0.0.1:8202") == "http://127.0.0.1:8202"

    def test_trailing_slash_stripped(self):
        assert _rpc_base_url("http://127.0.0.1:8202/") == "http://127.0.0.1:8202"

    def test_rpc_prefix_stripped(self):
        assert _rpc_base_url("https://hub.example.net/rpc") == "https://hub.example.net"

    def test_rpc_prefix_with_trailing_slash(self):
        assert _rpc_base_url("https://hub.example.net/rpc/") == "https://hub.example.net"

    def test_nested_rpc_prefix(self):
        assert _rpc_base_url("https://hub.example/api/rpc") == "https://hub.example/api"

    def test_hostname_rpc_not_treated_as_prefix(self):
        # 'http://rpc' has an empty path — '/rpc' must be a path segment,
        # not part of the authority.
        assert _rpc_base_url("http://rpc") == "http://rpc"

    def test_non_rpc_suffix_unchanged(self):
        assert _rpc_base_url("http://host:8202/rpcfoo") == "http://host:8202/rpcfoo"
        assert _rpc_base_url("http://host:8202/v1") == "http://host:8202/v1"


class TestClientUrlNormalization:
    def test_rpc_url_property_normalized(self):
        client = BlockchainClient(rpc_url="https://hub.example/rpc")
        assert client.rpc_url == "https://hub.example"

    async def test_get_chain_health_builds_single_rpc_prefix(self, monkeypatch) -> None:
        """The reported defect: /rpc/rpc/info must never be requested."""
        requested: list[str] = []

        class _Resp:
            status_code = 200

            def raise_for_status(self) -> None:
                return None

            def json(self):
                return {"healthy": True}

        async def _fake_get(self, url, params=None):
            requested.append(str(url))
            return _Resp()

        monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)
        client = BlockchainClient(rpc_url="https://hub.example/rpc")
        result = await client.get_chain_health("bc-2")
        await client.aclose()

        assert result == {"healthy": True}
        assert requested == ["https://hub.example/rpc/info"]
