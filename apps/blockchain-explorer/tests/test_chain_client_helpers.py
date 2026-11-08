"""Unit tests for chain_client helpers and RPC error paths (not DB pagination)."""

import asyncio

import httpx
import pytest
from aitbc.constants import BLOCKCHAIN_RPC_URL

import chain_client


def test_normalize_block_empty():
    assert chain_client.normalize_block({}) == {}


def test_normalize_block_maps_proposer_and_snake_case():
    raw = {
        "proposer": "0xvalidator",
        "tx_count": 3,
        "state_root": "0xroot",
        "height": 10,
    }
    out = chain_client.normalize_block(raw)
    assert out["validator"] == "0xvalidator"
    assert out["txCount"] == 3
    assert out["stateRoot"] == "0xroot"
    assert out["proposer"] == "0xvalidator"


def test_rpc_url_for_local_and_mainnet(monkeypatch):
    monkeypatch.setenv("MAINNET_RPC_URL", "http://mainnet-rpc.test")
    assert chain_client.rpc_url_for("ait-testchain") == BLOCKCHAIN_RPC_URL
    assert chain_client.rpc_url_for("ait-mainnet") == "http://mainnet-rpc.test"
    monkeypatch.delenv("MAINNET_RPC_URL", raising=False)
    assert chain_client.rpc_url_for("ait-mainnet") == BLOCKCHAIN_RPC_URL


def test_chain_db_path_prefers_chain_specific(monkeypatch):
    monkeypatch.setattr(chain_client, "resolve_chain_id", lambda: "ait-testchain")

    class FakePath:
        def __init__(self, value: str):
            self.value = value

        def exists(self) -> bool:
            return "ait-testchain" in self.value

    monkeypatch.setattr(chain_client, "Path", FakePath)
    found = chain_client.chain_db_path()
    assert isinstance(found, FakePath)
    assert "ait-testchain" in found.value


def test_chain_db_path_none_when_missing(monkeypatch):
    monkeypatch.setattr(chain_client, "resolve_chain_id", lambda: "ait-testchain")

    class FakePath:
        def __init__(self, value: str):
            self.value = value

        def exists(self) -> bool:
            return False

    monkeypatch.setattr(chain_client, "Path", FakePath)
    assert chain_client.chain_db_path() is None


def test_lazy_getattr_shims():
    assert chain_client.__getattr__("DEFAULT_CHAIN") == "ait-testchain"
    urls = chain_client.__getattr__("BLOCKCHAIN_RPC_URLS")
    assert "ait-testchain" in urls and "ait-mainnet" in urls
    with pytest.raises(AttributeError):
        chain_client.__getattr__("NOT_EXPORTED")


@pytest.mark.parametrize("chain_id", ["", "ab", "chain/bad"])
def test_get_transaction_rejects_invalid_chain_id(chain_id):
    out = asyncio.run(chain_client.get_transaction("0x" + "a" * 64, chain_id=chain_id))
    assert out == {}


def test_get_chain_head_success_normalizes(monkeypatch):
    payload = {"height": 99, "proposer": "0x1", "tx_count": 0}

    class FakeResponse:
        status_code = 200

        def json(self):
            return payload

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, params=None):
            assert "rpc/head" in url
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: FakeClient())
    head = asyncio.run(chain_client.get_chain_head("ait-testchain"))
    assert head["validator"] == "0x1"
    assert head["txCount"] == 0


def test_get_chain_head_non_200_returns_empty(monkeypatch):
    class FakeResponse:
        status_code = 503

        def json(self):
            return {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, params=None):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: FakeClient())
    assert asyncio.run(chain_client.get_chain_head()) == {}


def test_get_chain_head_network_error_returns_empty(monkeypatch):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, params=None):
            raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: FakeClient())
    assert asyncio.run(chain_client.get_chain_head()) == {}
