"""Router tests for /v1/cross-chain/* (#1289 round 9 batch 6).

cross_chain_integration — AuthDep/AdminDep gated, real sqlite session,
SecureWalletService + chain adapters. Wallet creation needs
settings.wallet_encryption_password; chain calls resolve RPC URLs from
NetworkConfig and degrade honestly when absent. Covers auth floors,
validation, health/config/chain reads, and wallet ownership binding.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from aitbc.auth import create_access_token

BASE = "/v1/cross-chain"


def _headers(sub: str = "agent-1", role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


class TestCrossChainAuth:
    def test_requires_auth(self, client: TestClient) -> None:
        # /health is public; gated endpoints require AuthDep
        assert client.get(f"{BASE}/health").status_code == 200
        assert client.post(
            f"{BASE}/wallets/create",
            params={"owner_address": "0x" + "22" * 20, "chain_id": 1, "security_config": {}},
            headers={"Authorization": "Bearer invalid"},
        ).status_code in (401, 403)
        assert client.get(f"{BASE}/wallets/0x{'11' * 20}/balance").status_code == 401

    def test_any_authenticated_role(self, client: TestClient) -> None:
        for role in ("client", "miner", "admin"):
            resp = client.get(f"{BASE}/health", headers=_headers("u", role))
            assert resp.status_code == 200, role


class TestCrossChainReads:
    def test_health_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/health", headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)

    def test_config_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/config", headers=_headers())
        assert resp.status_code == 200

    def test_supported_chains_empty_or_list(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/chains/supported", headers=_headers())
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_chain_info_unknown_404_or_error(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/chains/999999/info", headers=_headers())
        assert resp.status_code in (200, 400, 404, 503)

    def test_bridge_statistics_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/bridge/statistics", headers=_headers())
        assert resp.status_code in (200, 503)

    def test_bridge_whitelist_shape(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/bridge/whitelist", headers=_headers())
        assert resp.status_code in (200, 503)


class TestWalletOwnership:
    def test_balance_unknown_wallet_404_or_403(self, client: TestClient) -> None:
        # _require_agent_wallet binds wallet_address to the caller's agent wallets
        resp = client.get(f"{BASE}/wallets/0x{'11' * 20}/balance", params={"chain_id": 1}, headers=_headers())
        assert resp.status_code in (403, 404)

    def test_verify_signature_validation(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/wallets/verify-signature",
            json={"message": "hello", "signature": "0x", "address": "0x" + "11" * 20},
            headers=_headers(),
        )
        # malformed signature must not verify — 200 with valid:false or a 4xx
        if resp.status_code == 200:
            assert resp.json().get("valid") is not True
        else:
            assert resp.status_code in (400, 422)

    def test_create_wallet_requires_encryption_config(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/wallets/create",
            params={"owner_address": "0x" + "22" * 20, "chain_id": 1, "security_config": {}},
            headers=_headers(),
        )
        # without WALLETS_ENCRYPTION_PASSWORD configured this is an honest 400;
        # with it configured the service may succeed — accept both, reject 500
        assert resp.status_code in (200, 400, 422, 503)
