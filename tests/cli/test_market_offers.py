"""Tests for the market offers CLI helpers."""

from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from aitbc.exceptions import NetworkError
from aitbc_cli.commands.market import market
from aitbc_cli.commands.market.offers import _hub_base_url, _sort_offers


class TestHubBaseUrl:
    """``_hub_base_url`` keeps an explicit scheme, maps localhost to http,
    and upgrades only a bare host to https — the TLS edge is the hub's
    reverse proxy, not something the CLI should assume is local."""

    def test_bare_host_gets_https(self):
        config = SimpleNamespace(hub_discovery_url="hub.example.net")
        assert _hub_base_url(config) == "https://hub.example.net"

    def test_explicit_scheme_is_kept(self):
        config = SimpleNamespace(hub_discovery_url="http://hub.example.net:8080")
        assert _hub_base_url(config) == "http://hub.example.net:8080"

    def test_localhost_gets_http(self):
        config = SimpleNamespace(hub_discovery_url="localhost:8102")
        assert _hub_base_url(config) == "http://localhost:8102"


_OFFER = {
    "offer_id": "sw_offer_1",
    "plugin_id": "ollama-llama3",
    "service_type": "ollama",
    "model": "llama3",
    "price": 1.0,
    "price_unit": "per_1k_tokens",
    "provider_address": "0xProviderAddress",
    "node_id": "node-1",
    "gpu_name": "RTX 4090",
    "gpu_device": "0",
    "gpu_memory_gb": 24,
    "disk_quota_mb": 100,
    "public_endpoint": "https://provider.example/",
    "status": "active",
    "avg_rating": 4.5,
    "rating_count": 3,
}

_SOFTWARE_OFFER_TX = {
    "payload": {
        "action": "software_offer",
        "offer_id": "sw_offer_chain",
        "service_type": "whisper",
        "model": "base",
        "gpu_name": "RTX 4090",
        "deployment_type": "local",
        "price": 0.5,
        "price_unit": "per_minute",
        "status": "active",
        "provider_address": "0xProviderAddress",
        "description": "chain-listed offer",
        "created_at": "2026-10-17T00:00:00",
    }
}


class TestMarketListFallback:
    """`market list` reads the hub over https first, then the local service.

    On the hub itself the public name resolves to the TLS edge, which the
    node cannot hairpin back to — the local market service must carry the
    command instead of the command failing.
    """

    @pytest.fixture
    def config(self):
        return SimpleNamespace(
            hub_discovery_url="hub.aitbc.invalid",
            market_service_url="http://127.0.0.1:8102",
            coordinator_api_url="",
            blockchain_rpc_url="http://127.0.0.1:8202",
        )

    def test_falls_back_to_local_market_service(self, monkeypatch, config):
        from aitbc_cli.commands.market import offers as offers_mod

        seen: list[str] = []

        class _Client:
            def __init__(self, base_url="", timeout=0, **_kw):
                self.base_url = base_url

            def get(self, path, params=None, **_kw):
                seen.append(f"{self.base_url}{path}")
                if "hub.aitbc.invalid" in self.base_url:
                    raise NetworkError("connection refused")
                if path == "/v1/market/offer":
                    return {"offers": [_OFFER]}
                raise NetworkError("unexpected path")

            def get_json(self, path, params=None, **_kw):
                raise NetworkError("unreachable")

        monkeypatch.setattr(offers_mod, "AITBCHTTPClient", _Client)
        monkeypatch.setattr(offers_mod, "get_config", lambda: config)

        result = CliRunner().invoke(market, ["list"], obj={})
        assert result.exit_code == 0, result.output
        assert "Found 1 market offers" in result.output
        assert seen[0].startswith("https://hub.aitbc.invalid")
        assert any(s.startswith("http://127.0.0.1:8102") for s in seen)

    def test_array_response_from_local_rpc_is_accepted(self, monkeypatch, config):
        """/rpc/transactions returns a JSON array — the local-RPC fallback
        must read it instead of crashing on the object shape check."""
        from aitbc_cli.commands.market import offers as offers_mod

        class _Client:
            def __init__(self, base_url="", timeout=0, **_kw):
                self.base_url = base_url

            def get(self, path, params=None, **_kw):
                raise NetworkError("market api down")

            def get_json(self, path, params=None, **_kw):
                if "hub.aitbc.invalid" in self.base_url:
                    raise NetworkError("edge unreachable")
                if path == "/rpc/transactions":
                    return [_SOFTWARE_OFFER_TX]
                return []

        monkeypatch.setattr(offers_mod, "AITBCHTTPClient", _Client)
        monkeypatch.setattr(offers_mod, "get_config", lambda: config)

        result = CliRunner().invoke(market, ["list"], obj={})
        assert result.exit_code == 0, result.output
        assert "sw_offer_chain" in result.output


_OLLAMA_OFFER_TX = {
    "payload": {
        "action": "software_offer",
        "offer_id": "sw_offer_ollama",
        "service_type": "ollama",
        "model": "llama3",
        "gpu_name": "RTX 4090",
        "deployment_type": "local",
        "price": 0.1,
        "price_unit": "per_1k_tokens",
        "status": "active",
        "provider_address": "0xProviderAddress",
        "description": "ollama listing",
        "created_at": "2026-10-17T00:00:00",
    }
}


class TestMarketListServiceTypeChainFallback:
    """#2220: `market list --service-type` must filter the chain-tx fallback
    too — the market-API path sent the filter but `_chain_offer_row` ignored
    it, so a whisper query returned every software offer on chain."""

    @pytest.fixture
    def config(self):
        return SimpleNamespace(
            hub_discovery_url="hub.aitbc.invalid",
            market_service_url="http://127.0.0.1:8102",
            coordinator_api_url="",
            blockchain_rpc_url="http://127.0.0.1:8202",
        )

    def _patch_chain_only(self, monkeypatch, offers_mod, config, txs):
        class _Client:
            def __init__(self, base_url="", timeout=0, **_kw):
                self.base_url = base_url

            def get(self, path, params=None, **_kw):
                raise NetworkError("market api down")

            def get_json(self, path, params=None, **_kw):
                if "hub.aitbc.invalid" in self.base_url:
                    raise NetworkError("edge unreachable")
                if path == "/rpc/transactions":
                    return list(txs)
                return []

        monkeypatch.setattr(offers_mod, "AITBCHTTPClient", _Client)
        monkeypatch.setattr(offers_mod, "get_config", lambda: config)

    def test_service_type_filters_chain_rows(self, monkeypatch, config):
        from aitbc_cli.commands.market import offers as offers_mod

        self._patch_chain_only(monkeypatch, offers_mod, config, [_SOFTWARE_OFFER_TX, _OLLAMA_OFFER_TX])

        result = CliRunner().invoke(market, ["list", "--service-type", "whisper"], obj={})
        assert result.exit_code == 0, result.output
        assert "sw_offer_chain" in result.output
        assert "sw_offer_ollama" not in result.output

    def test_service_type_filtering_everything_is_honest_empty(self, monkeypatch, config):
        from aitbc_cli.commands.market import offers as offers_mod

        self._patch_chain_only(monkeypatch, offers_mod, config, [_SOFTWARE_OFFER_TX, _OLLAMA_OFFER_TX])

        result = CliRunner().invoke(market, ["list", "--service-type", "ffmpeg"], obj={})
        assert result.exit_code == 0, result.output
        assert "No market offers found" in result.output
        assert "service_type=ffmpeg" in result.output
        assert "sw_offer_chain" not in result.output
        assert "sw_offer_ollama" not in result.output


class TestMarketListEmpty:
    """#2225: an empty `market list` must say so, and dead fallback bases
    must not shout warnings that become the only output."""

    @pytest.fixture
    def config(self):
        return SimpleNamespace(
            hub_discovery_url="hub.aitbc.invalid",
            market_service_url="http://127.0.0.1:8102",
            coordinator_api_url="",
            blockchain_rpc_url="http://127.0.0.1:8202",
        )

    def _patch_clients(self, monkeypatch, offers_mod, config, market_payload, local_fails=True):
        seen_params: list[dict] = []

        class _Client:
            def __init__(self, base_url="", timeout=0, **_kw):
                self.base_url = base_url

            def get(self, path, params=None, **_kw):
                if path == "/v1/market/offer":
                    if "hub.aitbc.invalid" in self.base_url:
                        seen_params.append(params or {})
                        return market_payload
                    if local_fails:
                        raise NetworkError("connection refused")
                    return market_payload
                raise NetworkError("unexpected path")

            def get_json(self, path, params=None, **_kw):
                raise NetworkError("unreachable")

        monkeypatch.setattr(offers_mod, "AITBCHTTPClient", _Client)
        monkeypatch.setattr(offers_mod, "get_config", lambda: config)
        return seen_params

    def test_empty_result_prints_honest_message_and_sends_filter(self, monkeypatch, config, caplog):
        import logging

        from aitbc_cli.commands.market import offers as offers_mod

        seen_params = self._patch_clients(monkeypatch, offers_mod, config, {"offers": []})

        with caplog.at_level(logging.DEBUG, logger="aitbc_cli.commands.market.offers"):
            result = CliRunner().invoke(market, ["list", "--service-type", "whisper"], obj={})
        assert result.exit_code == 0, result.output
        assert "No market offers found" in result.output
        assert "service_type=whisper" in result.output
        # The dead local fallback must not warn — that warning was the only
        # output in #2225.
        assert "Market service not available" not in result.output
        assert not [
            r
            for r in caplog.records
            if r.levelno >= logging.WARNING and "127.0.0.1:8102" in r.getMessage()
        ]
        # The filter still reaches the API as a query param.
        assert seen_params and seen_params[0].get("service_type") == "whisper"

    def test_empty_result_json_keeps_parseable_stdout(self, monkeypatch, config):
        import json

        from aitbc_cli.commands.market import offers as offers_mod

        self._patch_clients(monkeypatch, offers_mod, config, {"offers": []})

        result = CliRunner().invoke(market, ["list", "--service-type", "nosuchtype99", "--output", "json"], obj={})
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) == []
        assert "No market offers found" in result.stderr
        assert "service_type=nosuchtype99" in result.stderr

    def test_filtered_to_empty_is_still_an_honest_empty(self, monkeypatch, config):
        """Hub answers offers of another type; --service-type filters them
        all out client-side — still 'no offers', not silence."""
        from aitbc_cli.commands.market import offers as offers_mod

        self._patch_clients(monkeypatch, offers_mod, config, {"offers": [_OFFER]})

        result = CliRunner().invoke(market, ["list", "--service-type", "whisper"], obj={})
        assert result.exit_code == 0, result.output
        assert "No market offers found" in result.output
        assert "ollama-llama3" not in result.output

    def test_all_sources_fail_is_an_error_not_empty(self, monkeypatch, config, caplog):
        import logging

        from aitbc_cli.commands.market import offers as offers_mod

        class _DeadClient:
            def __init__(self, base_url="", timeout=0, **_kw):
                pass

            def get(self, path, params=None, **_kw):
                raise NetworkError("connection refused")

            def get_json(self, path, params=None, **_kw):
                raise NetworkError("unreachable")

        monkeypatch.setattr(offers_mod, "AITBCHTTPClient", _DeadClient)
        monkeypatch.setattr(offers_mod, "get_config", lambda: config)

        with caplog.at_level(logging.DEBUG, logger="aitbc_cli.commands.market.offers"):
            result = CliRunner().invoke(market, ["list"], obj={})
        assert result.exit_code != 0
        assert "No market data source answered" in result.output
        # Only the primary base warns; the local fallback is debug-level.
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        market_warnings = [r for r in warnings if "Market service" in r.getMessage()]
        assert len(market_warnings) == 1
        assert "hub.aitbc.invalid" in market_warnings[0].getMessage()
        # The demoted fallback failure is still recorded at debug level.
        assert any("127.0.0.1:8102" in r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG)


class TestSortOffers:
    """Test deterministic sorting of market offers."""

    @pytest.fixture
    def offers(self):
        return [
            {
                "plugin_id": "low-rated",
                "avg_rating": 0.0,
                "rating_count": 0,
                "price": 0.001,
                "status": "active",
                "capacity": 1,
            },
            {
                "plugin_id": "mid-rated",
                "avg_rating": 4.2,
                "rating_count": 8,
                "price": 0.0015,
                "status": "active",
                "capacity": 2,
            },
            {
                "plugin_id": "top-rated",
                "avg_rating": 4.5,
                "rating_count": 12,
                "price": 0.002,
                "status": "active",
                "capacity": 1,
            },
        ]

    def test_sort_reputation_desc(self, offers):
        sorted_offers = _sort_offers(offers, "reputation")
        assert [o["plugin_id"] for o in sorted_offers] == ["top-rated", "mid-rated", "low-rated"]

    def test_sort_price_asc(self, offers):
        sorted_offers = _sort_offers(offers, "price")
        assert [o["plugin_id"] for o in sorted_offers] == ["low-rated", "mid-rated", "top-rated"]

    def test_sort_availability_prefers_active(self, offers):
        offers[0]["status"] = "inactive"
        sorted_offers = _sort_offers(offers, "availability")
        # active ones first, then by capacity desc
        assert sorted_offers[0]["plugin_id"] != "low-rated"
        assert sorted_offers[-1]["plugin_id"] == "low-rated"

    def test_sort_default_is_reputation(self, offers):
        sorted_offers = _sort_offers(offers, "default")
        assert [o["plugin_id"] for o in sorted_offers] == ["top-rated", "mid-rated", "low-rated"]


class TestOfferDisableIsSigned:
    """``offer-disable`` must send the provider-signed removal the market service now requires.

    DELETE /v1/market/offer/{plugin_id} used to take any caller (M-2); the service now
    verifies an ``unregister`` proof and that the signer is the row's provider. These
    assert against the server's own verifier rather than a copy of the message format:
    a different key order or action string recovers a different signer and a 403 that
    names neither side.
    """

    CHAIN_ID = "ait-testchain.local"

    @pytest.fixture
    def wired(self, monkeypatch):
        from eth_account import Account

        from aitbc_cli.commands.market import offers

        signer = Account.create()
        sent: dict = {}

        class _Config:
            hub_discovery_url = "hub.example.net"

        class _Client:
            def __init__(self, base_url, timeout):
                sent["base_url"] = base_url

            def delete(self, endpoint, params=None, headers=None, idempotency_key=None):
                sent["endpoint"] = endpoint
                sent["params"] = params
                return {"plugin_id": "ipfs-ipfs-host", "status": "unregistered"}

        monkeypatch.setattr(offers, "get_config", lambda: _Config())
        monkeypatch.setattr(offers, "get_chain_id", lambda: self.CHAIN_ID)
        monkeypatch.setattr(offers, "AITBCHTTPClient", _Client)
        monkeypatch.setattr(
            offers, "get_market_wallet", lambda ctx, require_private_key=False: (signer.address, signer.key.hex(), "shop")
        )
        return offers, signer, sent

    def test_the_removal_carries_a_proof_the_service_accepts(self, wired):
        from click.testing import CliRunner

        from aitbc.market.offer_registration import verify_offer_registration

        offers, signer, sent = wired
        result = CliRunner().invoke(offers.offer_disable, ["--plugin-id", "ipfs-ipfs-host"], obj={})

        assert result.exit_code == 0, result.output
        assert sent["endpoint"] == "/v1/market/offer/ipfs-ipfs-host"
        proof = {"plugin_id": "ipfs-ipfs-host", **sent["params"]}
        error, recovered = verify_offer_registration(proof, self.CHAIN_ID, action="unregister")
        assert error is None
        assert recovered == signer.address

    def test_the_removal_is_not_a_registration_proof(self, wired):
        """action scopes the signature: the service must not read it as a register."""
        from click.testing import CliRunner

        from aitbc.market.offer_registration import verify_offer_registration

        offers, _, sent = wired
        CliRunner().invoke(offers.offer_disable, ["--plugin-id", "ipfs-ipfs-host"], obj={})

        error, _ = verify_offer_registration(
            {"plugin_id": "ipfs-ipfs-host", **sent["params"]}, self.CHAIN_ID, action="register"
        )
        assert error is not None

    def test_without_a_wallet_key_it_refuses_instead_of_sending_unsigned(self, wired, monkeypatch):
        from click.testing import CliRunner

        offers, signer, sent = wired
        monkeypatch.setattr(offers, "get_market_wallet", lambda ctx, require_private_key=False: (signer.address, None, "shop"))

        result = CliRunner().invoke(offers.offer_disable, ["--plugin-id", "ipfs-ipfs-host"], obj={})

        assert result.exit_code != 0
        assert "endpoint" not in sent
