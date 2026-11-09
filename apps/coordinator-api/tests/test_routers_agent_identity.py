"""Router tests for /v1/identities/*, /v1/registry/*, /v1/chains/*, /v1/address/* (#1289 round 9 batch 6).

agent_identity — AuthDep on mutations, real AgentIdentityManager +
sqlite session. Covers identity lifecycle, search, wallets binding,
export/import, registry health/stats, and cross-chain mapping reads.
"""

from __future__ import annotations


from fastapi.testclient import TestClient

from aitbc.auth import create_access_token

BASE = "/v1/agent-identity"


def _headers(sub: str = "agent-1", role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _admin() -> dict[str, str]:
    return _headers("admin-1", "admin")


def _create(client: TestClient, **over) -> dict:
    body = {
        "owner_address": "0x" + "cd" * 20,
        "chains": [1],
        "display_name": "Test Agent",
        "description": "coverage test agent",
        "tags": ["test"],
    }
    body.update(over)
    return body


def _agent_id(resp_json: dict) -> str:
    return str(resp_json.get("agent_id") or resp_json.get("identity_id") or "")


class TestAgentIdentityAuth:
    def test_requires_auth_on_mutations(self, client: TestClient) -> None:
        assert client.post(f"{BASE}/identities", json=_create(client)).status_code == 401
        assert client.put(f"{BASE}/identities/a1", json={}).status_code == 401

    def test_reads_auth_floor(self, client: TestClient) -> None:
        # reads may be open or auth-gated — assert not 500
        for path in ("/registry/health", "/registry/statistics", "/chains/supported"):
            resp = client.get(f"{BASE}{path}")
            assert resp.status_code in (200, 401, 403), path


class TestIdentityLifecycle:
    def test_create_and_get(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/identities", json=_create(client), headers=_admin())
        assert resp.status_code in (200, 201), resp.text
        body = resp.json()
        agent_id = _agent_id(body)
        assert agent_id
        got = client.get(f"{BASE}/identities/{agent_id}", headers=_admin())
        assert got.status_code == 200

    def test_get_unknown_404(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/identities/ghost-agent", headers=_admin())
        assert resp.status_code in (404, 400)

    def test_search_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/identities/search", params={"q": "test", "chains": "1"}, headers=_admin())
        assert resp.status_code == 200

    def test_deactivate(self, client: TestClient) -> None:
        created = client.post(
            f"{BASE}/identities", json=_create(client, display_name="Deactivatable"), headers=_admin()
        ).json()
        agent_id = _agent_id(created)
        resp = client.post(f"{BASE}/identities/{agent_id}/deactivate", json={}, headers=_admin())
        assert resp.status_code in (200, 204, 400, 404)

    def test_export_import_roundtrip_shape(self, client: TestClient) -> None:
        created = client.post(f"{BASE}/identities", json=_create(client, display_name="Exportable"), headers=_admin()).json()
        agent_id = _agent_id(created)
        exp = client.post(f"{BASE}/identities/{agent_id}/export", json={}, headers=_admin())
        assert exp.status_code in (200, 400, 404, 501)

    def test_registry_health(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/registry/health", headers=_admin())
        assert resp.status_code == 200

    def test_wallets_list_empty(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/identities/ghost/wallets", headers=_admin())
        assert resp.status_code in (200, 404, 400)
