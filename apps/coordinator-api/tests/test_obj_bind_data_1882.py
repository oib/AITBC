"""#1882 COORD-OBJ-BIND-DATA-1 pins: data-path routers bind objects to the
JWT principal.

Pre-fix: rewards profile/tier/milestones/distributions trusted any path
agent_id; ipfs upload/batch/list/delete/retrieve trusted body/path agent_id
or cid with no owner check; developer-platform register/update trusted any
wallet_address; market provider-capacity trusted any provider_id.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token

from coordinator_api.contexts.agent_identity.domain.agent_identity import AgentIdentity
from coordinator_api.contexts.infrastructure.domain.user import User, Wallet

OWNER_WALLET = "0x5555555555555555555555555555555555555555"
DEV_WALLET = "0x6666666666666666666666666666666666666666"
AGENT = "agent-rewards-1"


def _headers(user_id: str, role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


@pytest.fixture
def seeded(db_session):
    db_session.add(User(id="owner1", email="o@x", username="owner1"))
    db_session.add(Wallet(user_id="owner1", address=OWNER_WALLET))
    db_session.add(User(id="intruder", email="i@x", username="intruder"))
    db_session.add(Wallet(user_id="intruder", address="0x7777777777777777777777777777777777777777"))
    db_session.add(AgentIdentity(agent_id=AGENT, owner_address=OWNER_WALLET))
    db_session.commit()


# --- rewards ---


class TestRewardsObjectBinding:
    @pytest.mark.parametrize(
        "path",
        [
            f"/v1/rewards/profile/{AGENT}",
            f"/v1/rewards/tier-progress/{AGENT}",
            f"/v1/rewards/milestones/{AGENT}",
            f"/v1/rewards/distributions/{AGENT}",
        ],
    )
    def test_foreign_agent_reads_403(self, client: TestClient, seeded, path: str) -> None:
        assert client.get(path, headers=_headers("intruder")).status_code == 403

    def test_foreign_agent_profile_create_403(self, client: TestClient, seeded) -> None:
        assert client.post(f"/v1/rewards/profile/{AGENT}", headers=_headers("intruder")).status_code == 403

    def test_owner_and_admin_pass_binding(self, client: TestClient, seeded) -> None:
        # binding passes; downstream may 404/200 — anything but 403
        for who in (_headers("owner1"), _headers("admin-a", "admin")):
            resp = client.get(f"/v1/rewards/milestones/{AGENT}", headers=who)
            assert resp.status_code != 403, resp.text


# --- ipfs ---


class TestIPFSObjectBinding:
    def test_upload_foreign_agent_403(self, client: TestClient, seeded) -> None:
        resp = client.post(
            "/v1/ipfs/upload",
            json={"agent_id": AGENT, "memory_data": {"x": 1}},
            headers=_headers("intruder"),
        )
        assert resp.status_code == 403

    def test_batch_upload_foreign_agent_403(self, client: TestClient, seeded) -> None:
        resp = client.post(
            "/v1/ipfs/batch-upload",
            json={"agent_id": AGENT, "memories": [{"data": {}}]},
            headers=_headers("intruder"),
        )
        assert resp.status_code == 403

    def test_list_foreign_agent_403(self, client: TestClient, seeded) -> None:
        assert client.get(f"/v1/ipfs/list/{AGENT}", headers=_headers("intruder")).status_code == 403

    def test_unowned_agent_fails_closed(self, client: TestClient, seeded) -> None:
        # agent with no AgentIdentity has no provable owner — non-admin 403
        resp = client.post(
            "/v1/ipfs/upload",
            json={"agent_id": "agent-ghost", "memory_data": {}},
            headers=_headers("owner1"),
        )
        assert resp.status_code == 403

    def test_delete_resolves_cid_owner(self, client: TestClient, seeded, monkeypatch) -> None:
        """delete carries only a cid — the stored metadata's agent_id is bound."""
        import coordinator_api.contexts.ipfs.routers.ipfs as ipfs_mod

        class _Meta:
            agent_id = AGENT

        class _Svc:
            async def initialize(self):
                return None

            async def retrieve_memory(self, cid, verify_integrity=True):
                return {}, _Meta()

            async def delete_memory(self, cid):
                return True

        monkeypatch.setattr(ipfs_mod, "get_ipfs_service", lambda: _Svc())
        resp = client.request(
            "DELETE",
            "/v1/ipfs/delete",
            json={"cid": "bafy-test"},
            headers=_headers("intruder"),
        )
        assert resp.status_code == 403


# --- developer platform ---


class TestDeveloperBinding:
    def test_register_foreign_wallet_403(self, client: TestClient, seeded) -> None:
        resp = client.post(
            "/v1/developer-platform/register",
            json={"wallet_address": DEV_WALLET},
            headers=_headers("intruder"),
        )
        assert resp.status_code == 403

    def test_update_foreign_wallet_403(self, client: TestClient, seeded) -> None:
        resp = client.put(
            f"/v1/developer-platform/profile/{DEV_WALLET}",
            json={"github_handle": "evil"},
            headers=_headers("intruder"),
        )
        assert resp.status_code == 403

    def test_owner_wallet_can_register(self, client: TestClient, seeded) -> None:
        # intruder's own wallet is a valid self-registration
        resp = client.post(
            "/v1/developer-platform/register",
            json={"wallet_address": "0x7777777777777777777777777777777777777777"},
            headers=_headers("intruder"),
        )
        assert resp.status_code != 403, resp.text

    def test_admin_can_update_any(self, client: TestClient, seeded) -> None:
        resp = client.put(
            f"/v1/developer-platform/profile/{DEV_WALLET}",
            json={"github_handle": "admin-edit"},
            headers=_headers("admin-a", "admin"),
        )
        assert resp.status_code != 403, resp.text


# --- market provider capacity ---


class TestCapacityBinding:
    def test_foreign_provider_capacity_403(self, client: TestClient, seeded, monkeypatch) -> None:
        monkeypatch.setenv("MINER_API_KEYS", "miner-key-1")
        headers = {"X-Api-Key": "miner-key-1", "X-Miner-ID": "miner-a"}
        resp = client.post(
            "/v1/market/providers/miner-b/capacity",
            json={"capacity": 4},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_own_provider_capacity_passes_binding(self, client: TestClient, seeded, monkeypatch) -> None:
        monkeypatch.setenv("MINER_API_KEYS", "miner-key-1")
        headers = {"X-Api-Key": "miner-key-1", "X-Miner-ID": "miner-b"}
        resp = client.post(
            "/v1/market/providers/miner-b/capacity",
            json={"capacity": 4},
            headers=headers,
        )
        # binding passed; downstream may 400 (no offer) — anything but 403
        assert resp.status_code != 403, resp.text
