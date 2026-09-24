"""The /v1/marketplace compatibility aliases for the market rename.

The rename moved every route from /v1/marketplace/* to /v1/market/* and
announced aliases for the old spelling that were never implemented. These
tests pin the aliases to the canonical table so the two cannot drift apart
again: a /v1/market entry added without its twin fails here.
"""

import pytest

from api_gateway import main as gateway

LEGACY = "v1/marketplace"
CANONICAL = "v1/market"

# One path per coordinator-owned sub-family, plus market-service routes that
# must NOT be captured by a sub-family prefix.
SAMPLE_SUFFIXES = [
    *(f"/{sub}/list" for sub in gateway._MARKET_COORDINATOR_PREFIXES),
    "",
    "/offers",
    "/jobs/42",
    "/ratings/sync",
    "/ipfs/upload",
]


def _twin(name: str) -> str:
    """The marketplace entry that mirrors a given market entry."""
    return "marketplace" + name[len("market") :]


class TestAliasTable:
    def test_every_market_entry_has_a_marketplace_twin(self) -> None:
        market = [n for n in gateway.SERVICES if n == "market" or n.startswith("market-")]
        assert market, "the market entries disappeared from the routing table"
        for name in market:
            assert _twin(name) in gateway.SERVICES, f"{name} has no legacy alias"

    def test_twins_point_at_the_same_upstream(self) -> None:
        for name, config in gateway.SERVICES.items():
            if name != "market" and not name.startswith("market-"):
                continue
            assert gateway.SERVICES[_twin(name)]["base_url"] == config["base_url"]

    def test_no_stray_marketplace_entries(self) -> None:
        """Every alias mirrors a real canonical entry, not a route of its own."""
        for name in gateway.SERVICES:
            if not (name == "marketplace" or name.startswith("marketplace-")):
                continue
            canonical = "market" + name[len("marketplace") :]
            assert canonical in gateway.SERVICES, f"{name} aliases nothing"

    def test_subfamilies_precede_the_generic_alias(self) -> None:
        """First prefix match wins, so the carving has to be mirrored in order."""
        order = list(gateway.SERVICES)
        generic = order.index("marketplace")
        for sub in gateway._MARKET_COORDINATOR_PREFIXES:
            assert order.index(f"marketplace-{sub}") < generic


class TestResolution:
    @pytest.mark.parametrize("suffix", SAMPLE_SUFFIXES)
    def test_legacy_resolves_exactly_like_canonical(self, suffix: str) -> None:
        legacy = gateway.resolve_v1_route(LEGACY + suffix)
        canonical = gateway.resolve_v1_route(CANONICAL + suffix)
        assert canonical is not None, f"{CANONICAL + suffix} is not routed at all"
        assert legacy is not None, f"{LEGACY + suffix} has no alias"
        assert legacy[1] == canonical[1]

    @pytest.mark.parametrize("sub", gateway._MARKET_COORDINATOR_PREFIXES)
    def test_coordinator_subfamilies_do_not_fall_through_to_the_market_service(self, sub: str) -> None:
        """The regression the carving exists to prevent."""
        resolved = gateway.resolve_v1_route(f"{LEGACY}/{sub}/list")
        assert resolved is not None
        assert resolved[0] == f"marketplace-{sub}"
        assert resolved[1].startswith(gateway.COORDINATOR_URL)

    def test_the_generic_alias_reaches_the_market_service(self) -> None:
        resolved = gateway.resolve_v1_route(f"{LEGACY}/offers")
        assert resolved == ("marketplace", f"{gateway._MARKET_SERVICE_URL}/v1/market/offers")

    def test_an_unrouted_prefix_still_resolves_to_nothing(self) -> None:
        assert gateway.resolve_v1_route("v1/not-a-service/thing") is None

    def test_the_catch_all_route_is_the_proxy(self) -> None:
        """Guards the decorator stack above proxy_request."""
        catch_all = [r for r in gateway.app.routes if getattr(r, "path", None) == "/{path:path}"]
        names = [getattr(getattr(r, "endpoint", None), "__name__", None) for r in catch_all]
        assert names == ["proxy_request"]


class TestV2IsUnaffected:
    def test_marketplace_is_not_a_v2_qualifier(self) -> None:
        assert "marketplace" not in gateway._V2_SERVICE_URLS
        assert not any(q.startswith("marketplace") for q in gateway._V2_SERVICE_URLS)

    def test_no_alias_claims_a_v2_prefix(self) -> None:
        for name, config in gateway.SERVICES.items():
            assert not str(config["prefix"]).lstrip("/").startswith("v2"), name


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
