"""Pin: #3021 AUTHZ-ANY-SURFACE-MUTATION-EXPOSURE-1 per-surface authz rulings.

The #3002 auth audit found route families at ``AuthLevel.ANY`` — any valid
JWT, any role — that expose mutations or sensitive reads. This module pins
the ruling sweep end to end: matrix level per path AND middleware admission
(correct role reaches the handler, wrong role 403s, anonymous 401s).

Rulings (see ``aitbc/auth/security_matrix.py`` for the full rationale):

* ``/v1/monitoring/dashboard*`` → ADMIN — internal service topology + host
  vitals; ``/v1/monitoring/metrics`` stays ANY (aggregate stats consumed
  cross-role by the public shop dashboard and ``aitbc monitor``).
* ``/v1/inference`` generate/batch → ADMIN_OR_CLIENT (GPU compute);
  ``models/{name}/pull`` → ADMIN (disk+network mutation); models/health
  stay ANY.
* ``/v1/knowledge*`` → ADMIN_OR_CLIENT (graph writes are customer surface).
* ``/v1/edge-gpu*`` → MINER; ``POST /discover`` additionally binds
  ``miner_id`` to the caller via ``MinerDep``.
* ``/v1/fhe*``, ``/v1/ml-zk*`` → ADMIN_OR_CLIENT (expensive compute).
* ``/v1/zk*`` stays ANY — documented multi-role ops surface (miner MCP,
  admin/client CLI); rate-limited.

The shared ``client`` fixture runs under ``TEST_MODE=true`` so AuthMiddleware
is never installed; this module builds the same auth-enabled app as
``test_exchange_admin_lockout_3019.py`` so the pins exercise the real gate.

Coder: A
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aitbc.auth.jwt import create_access_token
from aitbc.auth.security_matrix import AuthLevel, check_role_match, get_auth_level


@pytest.fixture(scope="module")
def auth_client() -> TestClient:
    """TestClient on a coordinator-api app built with AuthMiddleware enabled."""
    from coordinator_api.config import settings
    from coordinator_api.main import create_app

    previous = (settings.test_mode, settings.auth_enabled)
    settings.test_mode = False
    settings.auth_enabled = True
    try:
        authed_app = create_app()
    finally:
        settings.test_mode, settings.auth_enabled = previous
    return TestClient(authed_app)


def _headers(sub: str, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


ADMIN = _headers("admin-1", "admin")
CLIENT = _headers("client-1", "client")
MINER = _headers("miner-1", "miner")


class TestMatrixLevels:
    """Path → level pins; a silent matrix regression fails here first."""

    @pytest.mark.parametrize(
        ("path", "level"),
        [
            ("/v1/monitoring/dashboard", AuthLevel.ADMIN),
            ("/v1/monitoring/dashboard/summary", AuthLevel.ADMIN),
            ("/v1/monitoring/dashboard/metrics", AuthLevel.ADMIN),
            ("/v1/monitoring/metrics", AuthLevel.ANY),
            ("/v1/inference/generate", AuthLevel.ADMIN_OR_CLIENT),
            ("/v1/inference/generate/stream", AuthLevel.ADMIN_OR_CLIENT),
            ("/v1/inference/batch", AuthLevel.ADMIN_OR_CLIENT),
            ("/v1/inference/models", AuthLevel.ANY),
            ("/v1/inference/models/llama3/pull", AuthLevel.ADMIN),
            ("/v1/inference/health", AuthLevel.ANY),
            ("/v1/knowledge/graphs", AuthLevel.ADMIN_OR_CLIENT),
            ("/v1/knowledge/graphs/g1/nodes", AuthLevel.ADMIN_OR_CLIENT),
            ("/v1/edge-gpu/discover", AuthLevel.MINER),
            ("/v1/edge-gpu/profiles", AuthLevel.MINER),
            ("/v1/fhe/encrypt", AuthLevel.ADMIN_OR_CLIENT),
            ("/v1/fhe/health", AuthLevel.ADMIN_OR_CLIENT),
            ("/v1/ml-zk/prove/training", AuthLevel.ADMIN_OR_CLIENT),
            ("/v1/ml-zk/circuits", AuthLevel.ADMIN_OR_CLIENT),
            ("/v1/zk/generate", AuthLevel.ANY),
            ("/v1/zk/receipt/verify", AuthLevel.ANY),
        ],
    )
    def test_surface_levels(self, path: str, level: AuthLevel) -> None:
        assert get_auth_level(path) is level, f"{path} resolved to {get_auth_level(path)}"
        assert get_auth_level(path, "POST") is level, f"POST {path} resolved to {get_auth_level(path, 'POST')}"


class TestMonitoringDashboard:
    """Ops internals → ADMIN; aggregate /metrics stays ANY (documented)."""

    def test_dashboard_rejects_client_and_miner(self, auth_client: TestClient) -> None:
        for headers in (CLIENT, MINER):
            resp = auth_client.get("/v1/monitoring/dashboard", headers=headers)
            assert resp.status_code == 403, resp.text

    def test_dashboard_admits_admin(self, auth_client: TestClient) -> None:
        resp = auth_client.get("/v1/monitoring/dashboard", headers=ADMIN)
        assert resp.status_code == 200, resp.text

    def test_metrics_still_admits_any_role(self, auth_client: TestClient) -> None:
        for headers in (ADMIN, CLIENT, MINER):
            resp = auth_client.get("/v1/monitoring/metrics", headers=headers)
            assert resp.status_code == 200, resp.text

    def test_anonymous_denied(self, auth_client: TestClient) -> None:
        assert auth_client.get("/v1/monitoring/dashboard").status_code == 401
        assert auth_client.get("/v1/monitoring/metrics").status_code == 401


class TestInference:
    """GPU compute → customer roles; model pull → admin; reads stay ANY."""

    def test_generate_rejects_miner(self, auth_client: TestClient) -> None:
        resp = auth_client.post(
            "/v1/inference/generate",
            json={"prompt": "hi"},
            headers=MINER,
        )
        assert resp.status_code == 403, resp.text

    @pytest.mark.parametrize("headers", [ADMIN, CLIENT], ids=["admin", "client"])
    def test_generate_admits_customer_roles(self, auth_client: TestClient, headers: dict) -> None:
        # Ollama is not part of the test deployment — 503/502 prove the
        # request cleared auth; 401/403 would mean the matrix rejected it.
        resp = auth_client.post("/v1/inference/generate", json={"prompt": "hi"}, headers=headers)
        assert resp.status_code in (200, 502, 503), resp.text

    def test_batch_rejects_miner(self, auth_client: TestClient) -> None:
        resp = auth_client.post("/v1/inference/batch", json={"prompts": ["hi"]}, headers=MINER)
        assert resp.status_code == 403, resp.text

    def test_model_pull_rejects_client(self, auth_client: TestClient) -> None:
        resp = auth_client.post("/v1/inference/models/llama3/pull", headers=CLIENT)
        assert resp.status_code == 403, resp.text

    def test_model_pull_admits_admin(self, auth_client: TestClient) -> None:
        resp = auth_client.post("/v1/inference/models/llama3/pull", headers=ADMIN)
        assert resp.status_code in (200, 502, 503), resp.text

    def test_models_list_admits_any_role(self, auth_client: TestClient) -> None:
        for headers in (ADMIN, CLIENT, MINER):
            resp = auth_client.get("/v1/inference/models", headers=headers)
            assert resp.status_code in (200, 502, 503), resp.text

    def test_anonymous_denied(self, auth_client: TestClient) -> None:
        assert auth_client.post("/v1/inference/generate", json={"prompt": "hi"}).status_code == 401
        assert auth_client.post("/v1/inference/models/x/pull").status_code == 401


class TestKnowledge:
    def test_graph_write_rejects_miner(self, auth_client: TestClient) -> None:
        resp = auth_client.post(
            "/v1/knowledge/graphs",
            json={"name": "g", "description": "d"},
            headers=MINER,
        )
        assert resp.status_code == 403, resp.text

    @pytest.mark.parametrize("headers", [ADMIN, CLIENT], ids=["admin", "client"])
    def test_graph_write_admits_customer_roles(self, auth_client: TestClient, headers: dict) -> None:
        resp = auth_client.post(
            "/v1/knowledge/graphs",
            json={"name": "g", "description": "d"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

    def test_anonymous_denied(self, auth_client: TestClient) -> None:
        assert auth_client.post("/v1/knowledge/graphs", json={"name": "g", "description": "d"}).status_code == 401
        assert auth_client.get("/v1/knowledge/graphs").status_code == 401


class TestEdgeGpu:
    def test_discover_rejects_non_miner(self, auth_client: TestClient) -> None:
        for headers in (CLIENT, ADMIN):
            resp = auth_client.post("/v1/edge-gpu/discover", params={"miner_id": "x"}, headers=headers)
            assert resp.status_code == 403, resp.text

    def test_discover_admits_matching_miner(self, auth_client: TestClient) -> None:
        resp = auth_client.post(
            "/v1/edge-gpu/discover",
            params={"miner_id": "miner-1"},
            headers=_headers("miner-1", "miner"),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["miner_id"] == "miner-1"

    def test_discover_rejects_miner_id_mismatch(self, auth_client: TestClient) -> None:
        """Handler-level binding: caller-asserted miner_id must equal sub."""
        resp = auth_client.post(
            "/v1/edge-gpu/discover",
            params={"miner_id": "miner-2"},
            headers=_headers("miner-1", "miner"),
        )
        assert resp.status_code == 403, resp.text

    def test_anonymous_denied(self, auth_client: TestClient) -> None:
        assert auth_client.post("/v1/edge-gpu/discover", params={"miner_id": "x"}).status_code == 401
        assert auth_client.get("/v1/edge-gpu/profiles").status_code == 401


class TestFheAndMlZk:
    @pytest.mark.parametrize("path", ["/v1/fhe/health", "/v1/ml-zk/circuits"])
    def test_customer_roles_admitted(self, auth_client: TestClient, path: str) -> None:
        for headers in (ADMIN, CLIENT):
            resp = auth_client.get(path, headers=headers)
            assert resp.status_code not in (401, 403), f"{path} {resp.status_code}: {resp.text}"

    @pytest.mark.parametrize("path", ["/v1/fhe/health", "/v1/ml-zk/circuits"])
    def test_miner_rejected(self, auth_client: TestClient, path: str) -> None:
        resp = auth_client.get(path, headers=MINER)
        assert resp.status_code == 403, resp.text

    @pytest.mark.parametrize("path", ["/v1/fhe/health", "/v1/ml-zk/circuits"])
    def test_anonymous_denied(self, auth_client: TestClient, path: str) -> None:
        assert auth_client.get(path).status_code == 401


class TestZkDocumentedAny:
    """/v1/zk* stays ANY — the caller set spans miner+admin+client (#3021)."""

    def test_all_roles_reach_handler(self, auth_client: TestClient) -> None:
        for headers in (ADMIN, CLIENT, MINER):
            resp = auth_client.get("/v1/zk/info", headers=headers)
            assert resp.status_code == 200, resp.text

    def test_anonymous_denied(self, auth_client: TestClient) -> None:
        assert auth_client.get("/v1/zk/info").status_code == 401

    def test_matrix_documents_any(self) -> None:
        level = get_auth_level("/v1/zk/receipt/verify")
        assert level is AuthLevel.ANY
        for role in ("admin", "client", "miner"):
            assert check_role_match(level, role)
        assert not check_role_match(level, None)
