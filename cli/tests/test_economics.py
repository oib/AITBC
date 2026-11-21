"""Tests for `aitbc economics market|model|distributed` live-data paths (#2344).

The three analysis commands used to emit ``status: "simulated"`` stubs. They
now probe the configured market service, exchange order book, blockchain RPC,
coordinator API and oracle prices, recording each source's outcome in a
``sources`` map. These tests pin the live path, the partial-failure path,
the all-sources-down abort, and the unknown-model-type abort.
"""

import json
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from aitbc.exceptions import NetworkError
import aitbc_cli.commands.economics as econ
from aitbc_cli.commands.economics import economics

_MARKET = "http://market:8102"
_EXCHANGE = "http://exchange:8106"
_RPC = "http://rpc:8202"
_COORD = "http://coord"

_OFFERS = {
    "offers": [
        {
            "plugin_id": "gpu-1",
            "service_type": "gpu_market",
            "price": "0.50",
            "price_unit": "per_hour",
            "status": "active",
            "provider_address": "0xaaa",
        },
        {
            "plugin_id": "gpu-2",
            "service_type": "gpu_market",
            "price": "0.75",
            "price_unit": "per_hour",
            "status": "active",
            "provider_address": "0xbbb",
        },
        {
            "plugin_id": "llm-1",
            "service_type": "llm_inference",
            "price": "0.0001",
            "price_unit": "per_1k_tokens",
            "status": "active",
            "provider_address": "0xccc",
        },
        {
            "plugin_id": "old-1",
            "service_type": "gpu_market",
            "price": "9.99",
            "price_unit": "per_hour",
            "status": "retired",
            "provider_address": "0xddd",
        },
    ],
    "total": 4,
}

_ORDERBOOK = {
    "buys": [{"id": 1, "price": "0.48"}],
    "sells": [{"id": 2, "price": "0.52"}, {"id": 3, "price": "0.55"}],
    "levels": {"bids": [], "asks": []},
}

_CHAIN_INFO = {
    "chain_id": "aitbc-mainnet",
    "height": 1000,
    "total_transactions": 5000,
    "genesis_params": {"block_time_seconds": 10},
}

_CONSENSUS = {
    "mode": "MultiValidatorPoA",
    "multi_validator_enabled": True,
    "active_validators": 4,
    "configured_validators": 4,
}

_HEALTH = {"status": "ok", "env": "test"}

_PRICES = {"prices": {"AIT/USD": {"price": "1.50", "source": "test"}}}


def _config(**overrides):
    values = {
        "coordinator_api_url": f"{_COORD}/v1",
        "api_key": None,
        "timeout": 5,
        "hub_discovery_url": "",
        "market_service_url": _MARKET,
        "exchange_service_url": _EXCHANGE,
        "blockchain_rpc_url": _RPC,
        "hub_blockchain_rpc_url": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _FakeClient:
    """Routes (base_url, path) -> payload or exception, mimicking AITBCHTTPClient."""

    def __init__(self, base_url, routes):
        self.base_url = base_url
        self._routes = routes

    def get(self, path, params=None):
        handler = self._routes.get((self.base_url, path))
        if handler is None:
            raise NetworkError(f"no route {self.base_url}{path}")
        if isinstance(handler, Exception):
            raise handler
        return handler

    def close(self):
        pass


def _patch(monkeypatch, config, routes):
    monkeypatch.setattr(econ, "get_config", lambda *a, **kw: config)
    monkeypatch.setattr(
        econ,
        "AITBCHTTPClient",
        lambda base_url="", timeout=30, **kw: _FakeClient(base_url.rstrip("/"), routes),
    )


def _full_routes():
    return {
        (_MARKET, "/v1/market/offer"): _OFFERS,
        (_EXCHANGE, "/api/orders/orderbook"): _ORDERBOOK,
        (_RPC, "/rpc/info"): _CHAIN_INFO,
        (_RPC, "/rpc/consensus/status"): _CONSENSUS,
        (_COORD, "/health"): _HEALTH,
        (_COORD, "/v1/oracle/prices"): _PRICES,
    }


@pytest.fixture
def runner():
    return CliRunner()


def test_market_live_aggregates(runner, monkeypatch):
    _patch(monkeypatch, _config(), _full_routes())
    result = runner.invoke(economics, ["market"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "live"
    assert payload["sources"] == {
        "market_offers": "ok",
        "exchange_orderbook": "ok",
        "blockchain_rpc": "ok",
    }
    offers = payload["offers"]
    assert offers["total_offers"] == 4
    assert offers["active_offers"] == 3
    assert set(offers["by_service_type"]) == {"gpu_market", "llm_inference"}
    gpu_stats = offers["price_stats"]["gpu_market/per_hour"]
    assert gpu_stats["min"] == "0.50"
    assert gpu_stats["median"] == "0.625"
    assert gpu_stats["max"] == "0.75"
    assert offers["top_providers"][0]["provider"] == "0xaaa"
    assert payload["orderbook"]["bids"] == 1
    assert payload["orderbook"]["asks"] == 2
    assert payload["chain"]["height"] == 1000
    assert payload["chain"]["avg_tps"] == 5.0
    assert payload["chain"]["consensus"]["active_validators"] == 4
    assert "simulated" not in result.output


def test_market_partial_sources_still_succeed(runner, monkeypatch):
    routes = _full_routes()
    routes[(_EXCHANGE, "/api/orders/orderbook")] = NetworkError("connection refused")
    routes[(_RPC, "/rpc/info")] = NetworkError("connection refused")
    _patch(monkeypatch, _config(), routes)
    result = runner.invoke(economics, ["market"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "live"
    assert payload["sources"]["market_offers"] == "ok"
    assert "NetworkError" in payload["sources"]["exchange_orderbook"]
    assert "NetworkError" in payload["sources"]["blockchain_rpc"]
    assert payload["orderbook"] is None
    assert payload["chain"] is None
    assert payload["warnings"]


def test_market_all_sources_down_aborts(runner, monkeypatch):
    _patch(monkeypatch, _config(coordinator_api_url=""), {})
    monkeypatch.delenv("COORDINATOR_API_URL", raising=False)
    result = runner.invoke(economics, ["market"], obj={"output_format": "json"})
    assert result.exit_code != 0
    assert "No live market data" in result.output


def test_model_cost_optimization_live(runner, monkeypatch):
    _patch(monkeypatch, _config(), _full_routes())
    result = runner.invoke(economics, ["model", "--type", "cost-optimization"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "live"
    assert payload["model_type"] == "cost-optimization"
    assert payload["sources"]["market_offers"] == "ok"
    assert payload["sources"]["oracle_prices"] == "ok"
    model = payload["model"]
    assert model["inputs"]["tx_fee_ait"] == "0.01"
    assert model["inputs"]["ait_usd_price"] == "1.50"
    gpu = next(r for r in model["recommendations"] if r["service_type"] == "gpu_market")
    assert gpu["cheapest_price"] == "0.50"
    assert gpu["cheapest_provider"] == "0xaaa"
    assert gpu["cheapest_price_usd"] == "0.7500"
    llm = next(r for r in model["recommendations"] if r["service_type"] == "llm_inference")
    assert model["cost_per_1k_tokens"] == [llm]


def test_model_unknown_type_aborts(runner, monkeypatch):
    _patch(monkeypatch, _config(), _full_routes())
    result = runner.invoke(economics, ["model", "--type", "bogus"], obj={"output_format": "json"})
    assert result.exit_code != 0
    assert "cost-optimization" in result.output


def test_model_all_sources_down_aborts(runner, monkeypatch):
    _patch(monkeypatch, _config(coordinator_api_url=""), {})
    monkeypatch.delenv("COORDINATOR_API_URL", raising=False)
    result = runner.invoke(economics, ["model"], obj={"output_format": "json"})
    assert result.exit_code != 0
    assert "No live economic model data" in result.output


def test_distributed_live(runner, monkeypatch):
    _patch(monkeypatch, _config(), _full_routes())
    result = runner.invoke(economics, ["distributed"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "live"
    assert payload["sources"]["coordinator_api"] == "ok"
    assert payload["totals"]["market_offers"] == 4
    assert payload["totals"]["market_active_offers"] == 3
    assert payload["totals"]["chain_height"] == 1000
    assert payload["totals"]["active_validators"] == 4
    assert payload["totals"]["orderbook_bids"] == 1
    assert payload["services"]["coordinator_api"]["status"] == "ok"


def test_distributed_cost_optimize(runner, monkeypatch):
    _patch(monkeypatch, _config(), _full_routes())
    result = runner.invoke(economics, ["distributed", "--cost-optimize"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["cost_optimize"] is True
    assert payload["cost_optimization"]["model"] == "cost-optimization"
    assert payload["sources"]["oracle_prices"] == "ok"


def test_distributed_partial_sources(runner, monkeypatch):
    routes = _full_routes()
    routes[(_COORD, "/health")] = NetworkError("refused")
    _patch(monkeypatch, _config(), routes)
    result = runner.invoke(economics, ["distributed"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "live"
    assert "NetworkError" in payload["sources"]["coordinator_api"]
    assert payload["services"]["coordinator_api"] is None


def test_distributed_all_down_aborts(runner, monkeypatch):
    _patch(monkeypatch, _config(coordinator_api_url=""), {})
    monkeypatch.delenv("COORDINATOR_API_URL", raising=False)
    result = runner.invoke(economics, ["distributed"], obj={"output_format": "json"})
    assert result.exit_code != 0
    assert "No live economics data" in result.output


# --- #2449: not-found mapping + unservable sentinel offers -------------------


def _http_404() -> NetworkError:
    err = NetworkError("GET request failed: 404 Client Error: Not Found")
    err.response = SimpleNamespace(status_code=404)  # type: ignore[attr-defined]
    return err


class _PostClient:
    def __init__(self, exc):
        self._exc = exc

    def post(self, path, json=None):
        raise self._exc

    def get(self, path, params=None):
        raise self._exc

    def close(self):
        pass


def test_vote_unknown_proposal_is_not_found(runner, monkeypatch):
    """Coordinator 404 -> NotFoundError (exit 2), not a NetworkError class."""
    from aitbc_cli.utils.error_handling import NotFoundError

    monkeypatch.setattr(econ, "_api_client", lambda *a, **kw: _PostClient(_http_404()))
    result = runner.invoke(economics, ["vote", "--proposal-id", "nosuch", "--vote", "abstain"], obj={"output_format": "json"})
    assert isinstance(result.exception, NotFoundError)
    assert result.exception.exit_code == 2
    payload = json.loads(result.output)
    assert payload["error"] == "NotFoundError"
    assert "nosuch" in payload["message"]


def test_status_unknown_proposal_is_not_found(runner, monkeypatch):
    from aitbc_cli.utils.error_handling import NotFoundError

    monkeypatch.setattr(econ, "_api_client", lambda *a, **kw: _PostClient(_http_404()))
    result = runner.invoke(economics, ["status", "--proposal-id", "nosuch"], obj={"output_format": "json"})
    assert isinstance(result.exception, NotFoundError)
    assert result.exception.exit_code == 2


def test_vote_non_404_still_network_error(runner, monkeypatch):
    """A 500 from the coordinator keeps the generic API-error path."""
    err = NetworkError("GET request failed: 500 Server Error")
    err.response = SimpleNamespace(status_code=500)  # type: ignore[attr-defined]
    monkeypatch.setattr(econ, "_api_client", lambda *a, **kw: _PostClient(err))
    result = runner.invoke(economics, ["vote", "--proposal-id", "p1", "--vote", "for"], obj={"output_format": "json"})
    assert result.exception is not None
    assert "Coordinator API error" in result.output


def test_model_ignores_unservable_sentinel_offers(runner, monkeypatch):
    """STRESS-GPU-style placeholder offers must not win 'cheapest' (#2449)."""
    offers = {
        "offers": [
            {
                "plugin_id": "stress-1",
                "service_type": "gpu_market",
                "price": "0.01",
                "price_unit": "per_hour",
                "status": "active",
                "provider_address": "default",
                "name": "STRESS-GPU-1",
            },
            {
                "plugin_id": "stress-2",
                "service_type": "gpu_market",
                "price": "0.02",
                "price_unit": "per_hour",
                "status": "active",
                "node_id": "none",
            },
            {
                "plugin_id": "gpu-real",
                "service_type": "gpu_market",
                "price": "0.50",
                "price_unit": "per_hour",
                "status": "active",
                "provider_address": "0xaaa",
            },
        ],
        "total": 3,
    }
    routes = _full_routes()
    routes[(_MARKET, "/v1/market/offer")] = offers
    _patch(monkeypatch, _config(), routes)
    result = runner.invoke(economics, ["model", "--type", "cost-optimization"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    gpu = next(r for r in payload["model"]["recommendations"] if r["service_type"] == "gpu_market")
    assert gpu["cheapest_price"] == "0.50"
    assert gpu["cheapest_provider"] == "0xaaa"
    assert payload["model"]["inputs"]["total_offers"] == 1
