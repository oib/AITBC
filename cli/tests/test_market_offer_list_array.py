"""CLI-MARKET-OFFERLIST-ARRAY-1 (#543): `aitbc market offer-list` must render
the JSON array returned by GET /v1/market/offers.

The market service answers a bare JSON array for the offers listing;
`AITBCHTTPClient.get()` narrows the body through `expect_object` and raises
TypeError on arrays, so every `aitbc market offer-list` invocation aborts
with rc=1 (same class as #490 / #529). The command must use `get_json()`
and handle both the bare-array shape and the wrapped `{"offers": [...]}`
object shape.
"""

import json
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.market.offers as offers_mod
from aitbc.exceptions import NetworkError
from aitbc_cli.commands.market import market

_WALLET = "0xabc"

_OFFERS = [
    {
        "offer_id": "offer-1",
        "provider_address": _WALLET,
        "service_type": "ipfs",
        "status": "active",
    },
    {
        "offer_id": "offer-2",
        "provider_address": _WALLET,
        "service_type": "compute",
        "status": "inactive",
    },
    {
        "offer_id": "other-1",
        "provider_address": "0xdef",
        "service_type": "ipfs",
        "status": "active",
    },
]


class _ArrayClient:
    """Mimics AITBCHTTPClient: get() narrows to object via expect_object."""

    def __init__(self, payload):
        self._payload = payload

    def get(self, path, params=None):
        raise TypeError(f"Expected JSON object from http://hub{path}, got list")

    def get_json(self, path, params=None):
        return self._payload

    def close(self):
        pass


class _FailingClient:
    def get_json(self, path, params=None):
        raise NetworkError("connection refused")

    def close(self):
        pass


@pytest.fixture
def runner():
    return CliRunner()


def _patch(monkeypatch, client):
    monkeypatch.setattr(offers_mod, "AITBCHTTPClient", lambda *a, **kw: client)
    monkeypatch.setattr(offers_mod, "get_market_wallet", lambda *a, **kw: (_WALLET, None, "test"))
    monkeypatch.setattr(
        offers_mod,
        "get_config",
        lambda *a, **kw: SimpleNamespace(hub_discovery_url="http://hub"),
    )


def test_offer_list_array_json_output(runner, monkeypatch):
    _patch(monkeypatch, _ArrayClient(_OFFERS))
    result = runner.invoke(market, ["offer-list", "--output", "json"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    # Only this provider's offers survive the client-side filter.
    assert [row["offer_id"] for row in payload] == ["offer-1", "offer-2"]


def test_offer_list_array_table_output(runner, monkeypatch):
    _patch(monkeypatch, _ArrayClient(_OFFERS))
    result = runner.invoke(market, ["offer-list"], obj={})
    assert result.exit_code == 0, result.output
    assert "offer-1" in result.output
    assert "offer-2" in result.output
    assert "other-1" not in result.output
    assert "My Market Offers" in result.output


def test_offer_list_object_shape_still_works(runner, monkeypatch):
    _patch(monkeypatch, _ArrayClient({"offers": _OFFERS}))
    result = runner.invoke(market, ["offer-list", "--output", "json"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert [row["offer_id"] for row in payload] == ["offer-1", "offer-2"]


def test_offer_list_network_error_still_aborts(runner, monkeypatch):
    _patch(monkeypatch, _FailingClient())
    result = runner.invoke(market, ["offer-list"], obj={})
    assert result.exit_code != 0
    assert "Error listing offers" in result.output
