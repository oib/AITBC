"""Tests for /v1/knowledge/* — stub knowledge-graph endpoints (#1289 round 4).

The router is a stub: handlers return canned responses and never touch the
session. It carries **no auth dependency** — production gating relies
entirely on the security matrix (`/v1/knowledge*` → AuthLevel.ANY,
enforced by AuthMiddleware, which is disabled under TEST_MODE). These
tests pin the router-level contract: request validation, response shapes,
and the documented absence of dep-level auth so a future auth regression
is visible here too.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

BASE = "/v1/knowledge"


class TestKnowledgeGraphs:
    def test_create_graph_shape(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/graphs",
            json={"name": "genomics", "description": "gene interactions", "graph_schema": "bio"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "genomics"
        assert data["id"].startswith("kg-")
        assert data["node_count"] == 0 and data["edge_count"] == 0

    def test_create_graph_requires_name_and_description(self, client: TestClient) -> None:
        assert client.post(f"{BASE}/graphs", json={"name": ""}).status_code == 422
        assert client.post(f"{BASE}/graphs", json={"name": "x"}).status_code == 422

    def test_list_graphs_empty(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/graphs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_graph_echoes_id(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/graphs/kg-123")
        assert resp.status_code == 200
        assert resp.json()["id"] == "kg-123"

    def test_contribute_node_shape(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/graphs/kg-1/nodes",
            json={
                "graph_id": "kg-1",
                "node_type": "gene",
                "data": {"symbol": "BRCA1"},
                "relationships": [{"type": "interacts_with", "target": "n2"}],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["graph_id"] == "kg-1"
        assert data["node_type"] == "gene"
        assert data["data"]["symbol"] == "BRCA1"

    def test_contribute_node_requires_graph_id(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/graphs/kg-1/nodes",
            json={"graph_id": "", "node_type": "gene"},
        )
        assert resp.status_code == 422

    def test_query_graph_empty(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/graphs/kg-1/query", params={"node_type": "gene"})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_join_graph(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/graphs/kg-9/join")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_no_dep_level_auth_documented(self, client: TestClient) -> None:
        """Pins current contract: these endpoints answer without a token at
        router level. Prod enforcement is the matrix ANY floor + middleware;
        if a dep is added later this test should be updated deliberately."""
        assert client.get(f"{BASE}/graphs").status_code == 200
        assert client.post(f"{BASE}/graphs/kg-1/join").status_code == 200
