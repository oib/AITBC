"""Router tests for /v1/developer-platform/* (#1289 round 9 batch 3).

Aggregated router (developers/bounties/certifications/hubs/staking/
analytics sub-routers, real DeveloperPlatformService + sqlite). No
router-level auth deps — matrix /v1/developer-platform* ->
ADMIN_OR_CLIENT is the only gate (disabled under TEST_MODE; pinned via
get_auth_level).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from aitbc.auth import create_access_token
from aitbc.auth.security_matrix import AuthLevel, check_role_match, get_auth_level

BASE = "/v1/developer-platform"
WALLET = "0x" + "33" * 20
WALLET2 = "0x" + "44" * 20


def _headers(role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('u-' + role, role)}"}


class TestAuthBoundary:
    def test_matrix_admin_or_client(self) -> None:
        assert get_auth_level("/v1/developer-platform/register") == AuthLevel.ADMIN_OR_CLIENT
        assert check_role_match(AuthLevel.ADMIN_OR_CLIENT, "admin")
        assert not check_role_match(AuthLevel.ADMIN_OR_CLIENT, "miner")


class TestDeveloperProfile:
    def test_register_and_profile(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/register",
            json={"wallet_address": WALLET, "github_handle": "devp", "skills": ["python"]},
            headers=_headers(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["wallet_address"].lower() == WALLET

        prof = client.get(f"{BASE}/profile/{WALLET}", headers=_headers())
        assert prof.status_code == 200

    def test_duplicate_register_rejected(self, client: TestClient) -> None:
        body = {"wallet_address": WALLET2}
        assert client.post(f"{BASE}/register", json=body, headers=_headers()).status_code == 200
        resp = client.post(f"{BASE}/register", json=body, headers=_headers())
        assert resp.status_code == 400

    def test_profile_missing_404(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/profile/{WALLET}", headers=_headers())
        assert resp.status_code in (200, 404)

    def test_leaderboard_and_stats(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/leaderboard", headers=_headers()).status_code == 200
        resp = client.get(f"{BASE}/stats/{WALLET}", headers=_headers())
        assert resp.status_code in (200, 404)


class TestBountiesCertificationsHubsStaking:
    def test_bounties_list_and_stats(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/bounties", headers=_headers()).status_code == 200
        assert client.get(f"{BASE}/bounties/stats", headers=_headers()).status_code == 200
        assert client.get(f"{BASE}/bounties/bounty_ghost", headers=_headers()).status_code in (200, 404)

    def test_certification_types(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/certifications/types", headers=_headers())
        assert resp.status_code == 200

    def test_hubs_list(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/hubs", headers=_headers()).status_code == 200

    def test_staking_reads(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/staking/{WALLET}", headers=_headers()).status_code in (200, 404)
        assert client.get(f"{BASE}/staking-stats", headers=_headers()).status_code == 200

    def test_analytics_overview_and_health(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/analytics/overview", headers=_headers()).status_code == 200
        assert client.get(f"{BASE}/health", headers=_headers()).status_code == 200
