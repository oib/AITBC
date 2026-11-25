"""MINER-PHANTOM-OFFERS-1 (#2954): `aitbc market offer` must repair a missing
market-service registration when the chain listing is identical.

The dedup probe (`/rpc/market/listings`) used to return early on an
identical listing — before the GPU_MARKET tx submit *and* before the signed
``POST /v1/market/offer`` registration. Chain listings and registry rows are
written by different paths, so offers could stay listed on-chain yet be
invisible to `market list` (live: whisper/base + ffmpeg/h264-transcode for
one provider, only ollama+ipfs in the registry). The identical path now
probes ``GET /v1/market/offer/{plugin_id}``: a present row keeps the old
"skipping" contract (the miner maps that substring to "unchanged"), an
absent row is re-registered anchored to the *chain* ``offer_id`` recovered
via ``/rpc/transactions/market/match`` → ``/rpc/transaction/{hash}``.
"""

import json
import logging
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.market.offers as offers_mod
from aitbc.exceptions import NetworkError
from aitbc_cli.commands.market import market

_WALLET = "0x4A5b00000000000000000000000000000000B5D2"
_CHAIN_OFFER_ID = "sw_offer_20261121215912_49d92c3c"
_GPU = {
    "gpu_name": "RTX 4090",
    "gpu_model": "RTX 4090",
    "gpu_device": "0",
    "gpu_uuid": "GPU-UUID-1",
    "gpu_memory_gb": 24,
    "compute_capability": "8.9",
}
_PUBLIC_ENDPOINT = "https://node.example/whisper"
_LOCAL_ENDPOINT = "http://localhost:8110"
# Same default the command builds when --description is omitted.
_DESCRIPTION = "whisper — base at 0.5 AIT/per_audio_min"

_IDENTICAL_LISTING = {
    "listing_id": "tx_9",
    "seller_address": _WALLET,
    "service_type": "whisper",
    "model": "base",
    "gpu_uuid": "GPU-UUID-1",
    "price": 0.5,
    "price_unit": "per_audio_min",
    "description": _DESCRIPTION,
    "gpu_name": "RTX 4090",
    "gpu_model": "RTX 4090",
    "gpu_device": "0",
    "memory_gb": 24,
    "disk_quota_mb": None,
    "compute_capability": "8.9",
    "endpoint": _PUBLIC_ENDPOINT,
}

_MATCH_ITEM = {
    "listing_id": "tx_9",
    "offer_tx_hash": "0xofferTxHash",
    "seller": _WALLET,
    "service_type": "whisper",
    "model": "base",
    "gpu_uuid": "GPU-UUID-1",
}

_OFFER_ARGS = [
    "offer",
    "--service-type",
    "whisper",
    "--model-or-variant",
    "base",
    "--price",
    "0.5",
    "--unit",
    "per_audio_min",
]


class _Router:
    """Path → payload (or exception) for GET; recorded POSTs."""

    def __init__(self):
        self.get_routes: dict[str, object] = {}
        self.post_routes: dict[str, object] = {}
        self.posts: list[tuple[str, dict]] = []
        self.gets: list[tuple[str, dict | None]] = []

    def get(self, path, params=None):
        self.gets.append((path, params))
        route = self.get_routes.get(path, {})
        if isinstance(route, Exception):
            raise route
        return route

    def post(self, path, json=None, **kwargs):
        self.posts.append((path, json or {}))
        route = self.post_routes.get(path, {})
        if isinstance(route, Exception):
            raise route
        return route


class _FakeClient:
    """Duck-typed AITBCHTTPClient bound to a shared router."""

    def __init__(self, router, base_url, *args, **kwargs):
        self._router = router
        self.base_url = base_url

    def get(self, path, params=None, **kwargs):
        return self._router.get(path, params=params)

    def get_json(self, path, params=None, **kwargs):
        return self._router.get(path, params=params)

    def post(self, path, json=None, **kwargs):
        return self._router.post(path, json=json, **kwargs)

    def delete(self, path, **kwargs):
        return {}

    def close(self):
        pass


@pytest.fixture
def router():
    return _Router()


@pytest.fixture
def runner():
    return CliRunner()


def _patch_offer(monkeypatch, router):
    """Wire `market offer`'s collaborators to hermetic fakes."""
    monkeypatch.setattr(offers_mod, "AITBCHTTPClient", lambda *a, **kw: _FakeClient(router, *a, **kw))
    monkeypatch.setattr(offers_mod, "get_market_wallet", lambda *a, **kw: (_WALLET, "0xpriv", "test"))
    monkeypatch.setattr(
        offers_mod,
        "get_config",
        lambda *a, **kw: SimpleNamespace(hub_discovery_url="http://hub", market_service_url=""),
    )
    monkeypatch.setattr(offers_mod, "get_chain_id", lambda *a, **kw: "ait-test")
    monkeypatch.setattr(offers_mod, "get_island_id", lambda *a, **kw: "island-1")
    monkeypatch.setattr(offers_mod, "_resolve_offer_gpu", lambda *a, **kw: dict(_GPU))
    monkeypatch.setattr(offers_mod, "_verify_offer_service", lambda *a, **kw: (0, ""))
    monkeypatch.setattr(offers_mod, "_offer_endpoints", lambda *a, **kw: (_PUBLIC_ENDPOINT, _LOCAL_ENDPOINT))
    monkeypatch.setattr(offers_mod, "get_next_nonce", lambda *a, **kw: 7)
    monkeypatch.setattr(offers_mod, "sign_transaction_data", lambda *a, **kw: "deadbeef")
    monkeypatch.setattr(offers_mod, "_resolve_market_api_key", lambda *a, **kw: "test-key")


def _identical_routes(router, registry_probe):
    """Chain says identical; registry probe answers ``registry_probe``."""
    router.get_routes.update(
        {
            "/rpc/market/listings": {"listings": [dict(_IDENTICAL_LISTING)], "total": 1},
            "/rpc/transactions/market/match": {"matches": [dict(_MATCH_ITEM)], "total": 1},
            "/rpc/transaction/0xofferTxHash": {
                "tx_hash": "0xofferTxHash",
                # The node stores payload as a JSON string — the resolver must parse it.
                "payload": json.dumps({"action": "software_offer", "offer_id": _CHAIN_OFFER_ID}),
            },
            "/v1/market/offer/whisper-base": registry_probe,
        }
    )


def _all_output(result) -> str:
    return f"{result.output}{getattr(result, 'stderr', '') or ''}"


def test_identical_listing_repairs_missing_registry_row(runner, monkeypatch, router):
    """Registry 404 → POST /v1/market/offer with the *chain* offer_id, no tx submit."""
    _patch_offer(monkeypatch, router)
    _identical_routes(
        router,
        NetworkError("GET request failed: 404 Client Error: Not Found for url: https://hub/v1/market/offer/whisper-base"),
    )
    router.post_routes["/v1/market/offer"] = {"plugin_id": "whisper-base"}

    result = runner.invoke(market, _OFFER_ARGS, obj={})

    assert result.exit_code == 0, _all_output(result)
    registrations = [body for path, body in router.posts if path == "/v1/market/offer"]
    assert len(registrations) == 1
    # Anchored to the chain payload's offer_id — never the fresh sw_offer_* one.
    assert registrations[0]["offer_id"] == _CHAIN_OFFER_ID
    assert registrations[0]["plugin_id"] == "whisper-base"
    # No new GPU_MARKET transaction may be submitted on the identical path.
    assert not [path for path, _ in router.posts if path == "/rpc/transactions/market"]
    assert "repaired missing market-service registration" in _all_output(result)
    assert "skipping" not in _all_output(result)


def test_identical_listing_with_registry_row_skips(runner, monkeypatch, router):
    """Registry row present → no POSTs at all; stdout keeps the 'skipping' contract."""
    _patch_offer(monkeypatch, router)
    _identical_routes(router, {"plugin_id": "whisper-base", "service_type": "whisper", "status": "active"})

    result = runner.invoke(market, _OFFER_ARGS, obj={})

    assert result.exit_code == 0, _all_output(result)
    assert router.posts == []
    assert "skipping" in _all_output(result)


def test_registration_post_failure_logs_warning(runner, monkeypatch, router, caplog):
    """A failed registration POST surfaces as a warning, not a silent debug."""
    _patch_offer(monkeypatch, router)
    router.get_routes.update(
        {
            "/rpc/market/listings": {"listings": [], "total": 0},
            "/rpc/mempool?limit=100": {},
        }
    )
    router.post_routes["/rpc/transactions/market"] = {"tx_hash": "0xnew"}
    router.post_routes["/v1/market/offer"] = NetworkError("connection refused")

    with caplog.at_level(logging.WARNING, logger="aitbc_cli.commands.market.offers"):
        result = runner.invoke(market, _OFFER_ARGS, obj={})

    assert result.exit_code == 0, _all_output(result)
    assert "Market-service registration for whisper/base failed" in caplog.text


def _patch_market_list(monkeypatch, router):
    monkeypatch.setattr(offers_mod, "AITBCHTTPClient", lambda *a, **kw: _FakeClient(router, *a, **kw))
    monkeypatch.setattr(
        offers_mod,
        "get_config",
        lambda *a, **kw: SimpleNamespace(hub_discovery_url="http://hub", market_service_url="", coordinator_api_url=""),
    )


_MARKET_OFFER = {
    "offer_id": "sw_offer_1",
    "plugin_id": "whisper-base",
    "service_type": "whisper",
    "model": "base",
    "price": 0.5,
    "price_unit": "per_audio_min",
    "provider_address": _WALLET,
    "status": "active",
}


def test_market_list_status_all_is_not_a_filter(runner, monkeypatch, router):
    """`market list --status all` must not send status=all nor filter rows out."""
    _patch_market_list(monkeypatch, router)
    router.get_routes["/v1/market/offer"] = {"offers": [dict(_MARKET_OFFER)], "total": 1}

    result = runner.invoke(market, ["list", "--status", "all"], obj={})

    assert result.exit_code == 0, _all_output(result)
    # The offer survived the (normalized-away) status filter and printed.
    assert "sw_offer_1" in _all_output(result)
    assert "No market offers found" not in _all_output(result)
    offer_gets = [params for path, params in router.gets if path == "/v1/market/offer"]
    assert offer_gets and all((params or {}).get("status") != "all" for params in offer_gets)


def test_offer_list_status_all_is_not_a_filter(runner, monkeypatch, router):
    """`market offer-list --status all` keeps every status for this provider."""
    _patch_market_list(monkeypatch, router)
    monkeypatch.setattr(offers_mod, "get_market_wallet", lambda *a, **kw: (_WALLET, None, "test"))
    router.get_routes["/v1/market/offers"] = [
        {"offer_id": "o-active", "provider_address": _WALLET, "service_type": "whisper", "status": "active"},
        {"offer_id": "o-inactive", "provider_address": _WALLET, "service_type": "whisper", "status": "inactive"},
    ]

    result = runner.invoke(market, ["offer-list", "--status", "all", "--output", "json"], obj={"output_format": "json"})

    assert result.exit_code == 0, _all_output(result)
    payload = json.loads(result.output)
    assert [row["offer_id"] for row in payload] == ["o-active", "o-inactive"]
