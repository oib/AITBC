"""Tests for the marketplace → market legacy path compatibility middleware."""

from collections.abc import Mapping

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from aitbc.middleware import MARKETPLACE_PATH_ALIASES, LegacyPathRewriteMiddleware
from aitbc.middleware.legacy_paths import DEPRECATION_HEADER


def _build_app(aliases: Mapping[str, str] | None = None) -> FastAPI:
    """An app whose routes exist only under the canonical spelling."""
    app = FastAPI()

    @app.get("/v1/market")
    async def market_root() -> dict[str, str]:
        return {"route": "root"}

    @app.get("/v1/market/offers")
    async def offers(limit: int = 0) -> dict[str, object]:
        return {"route": "offers", "limit": limit}

    @app.get("/v1/market/gpu/{gpu_id}")
    async def gpu(gpu_id: str) -> dict[str, str]:
        return {"route": "gpu", "id": gpu_id}

    @app.get("/rpc/market/listings")
    async def listings() -> dict[str, str]:
        return {"route": "listings"}

    @app.get("/v1/marketplaces")
    async def neighbour() -> dict[str, str]:
        return {"route": "neighbour"}

    @app.websocket("/v1/market/stream")
    async def stream(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_text(websocket.scope["path"])
        await websocket.close()

    app.add_middleware(LegacyPathRewriteMiddleware, aliases=aliases)
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app())


class TestLegacyPathRewrite:
    def test_legacy_prefix_reaches_the_canonical_route(self, client: TestClient) -> None:
        response = client.get("/v1/marketplace/offers")
        assert response.status_code == 200
        assert response.json() == {"route": "offers", "limit": 0}

    def test_exact_prefix_is_rewritten(self, client: TestClient) -> None:
        assert client.get("/v1/marketplace").json() == {"route": "root"}

    def test_path_parameters_survive_the_rewrite(self, client: TestClient) -> None:
        assert client.get("/v1/marketplace/gpu/rtx-4090").json() == {"route": "gpu", "id": "rtx-4090"}

    def test_query_string_survives_the_rewrite(self, client: TestClient) -> None:
        assert client.get("/v1/marketplace/offers?limit=7").json()["limit"] == 7

    def test_rpc_prefix_is_rewritten_too(self, client: TestClient) -> None:
        assert client.get("/rpc/marketplace/listings").json() == {"route": "listings"}

    def test_canonical_path_is_untouched(self, client: TestClient) -> None:
        response = client.get("/v1/market/offers")
        assert response.status_code == 200
        assert DEPRECATION_HEADER not in response.headers

    def test_rewrite_stops_at_a_segment_boundary(self, client: TestClient) -> None:
        """/v1/marketplaces is its own route family, not a legacy spelling."""
        response = client.get("/v1/marketplaces")
        assert response.status_code == 200
        assert response.json() == {"route": "neighbour"}
        assert DEPRECATION_HEADER not in response.headers

    def test_unknown_path_still_404s(self, client: TestClient) -> None:
        assert client.get("/v1/marketplace/nope").status_code == 404

    def test_response_reports_the_legacy_path(self, client: TestClient) -> None:
        response = client.get("/v1/marketplace/gpu/rtx-4090")
        assert response.headers[DEPRECATION_HEADER] == "/v1/marketplace/gpu/rtx-4090"

    def test_websockets_are_rewritten(self, client: TestClient) -> None:
        """BaseHTTPMiddleware would not see this scope at all."""
        with client.websocket_connect("/v1/marketplace/stream") as websocket:
            assert websocket.receive_text() == "/v1/market/stream"

    def test_unsupported_scope_types_pass_through(self) -> None:
        seen: list[str] = []

        async def app(scope: dict[str, object], receive: object, send: object) -> None:
            seen.append(str(scope["type"]))

        middleware = LegacyPathRewriteMiddleware(app)  # type: ignore[arg-type]
        import asyncio

        asyncio.run(middleware({"type": "lifespan"}, None, None))  # type: ignore[arg-type]
        assert seen == ["lifespan"]


class TestAliasTable:
    def test_default_aliases_cover_both_mount_points(self) -> None:
        assert MARKETPLACE_PATH_ALIASES == {
            "/v1/marketplace": "/v1/market",
            "/rpc/marketplace": "/rpc/market",
        }

    def test_custom_aliases_replace_the_defaults(self) -> None:
        client = TestClient(_build_app(aliases={"/legacy": "/v1/market"}))
        assert client.get("/legacy/offers").json()["route"] == "offers"
        assert client.get("/v1/marketplace/offers").status_code == 404

    def test_longest_prefix_wins(self) -> None:
        """A specific alias is not shadowed by a shorter one it starts with."""
        client = TestClient(
            _build_app(aliases={"/old": "/v1/marketplaces", "/old/shop": "/v1/market"}),
        )
        assert client.get("/old/shop/offers").json()["route"] == "offers"
        assert client.get("/old").json()["route"] == "neighbour"

    def test_trailing_slashes_in_the_table_are_ignored(self) -> None:
        client = TestClient(_build_app(aliases={"/legacy/": "/v1/market/"}))
        assert client.get("/legacy/offers").json()["route"] == "offers"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
