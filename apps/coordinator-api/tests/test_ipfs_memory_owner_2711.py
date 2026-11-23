"""#2711 — IPFS memory cid -> agent ownership must survive a service restart.

The service registries are process-local OrderedDicts; after a restart (or an
LRU eviction) ``retrieve_memory`` resolves the owner as ``"unknown"`` and the
#1882 bind 403s the legitimate owner. The durable ``ipfs_memory_owner`` row
written at upload time is the fallback.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token

from coordinator_api.contexts.agent_identity.domain.agent_identity import AgentIdentity
from coordinator_api.contexts.infrastructure.domain.user import User, Wallet
from coordinator_api.contexts.ipfs.domain.ipfs_memory_owner import IPFSMemoryOwner
from coordinator_api.contexts.ipfs.services.ipfs_service import MemoryMetadata

OWNER_WALLET = "0x5555555555555555555555555555555555555555"
AGENT = "agent-ipfs-2711"
CID = "bafy-restart-test"


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


class _UploadService:
    """First-instance service: upload succeeds, cid returned."""

    async def initialize(self) -> None:
        return None

    async def upload_memory(self, **kwargs):
        return SimpleNamespace(
            cid=CID,
            size=10,
            compressed_size=10,
            upload_time=datetime.now(UTC),
            pinned=True,
            filecoin_deal=None,
        )


class _RestartedService:
    """Post-restart service: empty registries — retrieve knows no owner."""

    async def initialize(self) -> None:
        return None

    async def retrieve_memory(self, cid: str, verify_integrity: bool = True):
        return {}, MemoryMetadata(
            agent_id="unknown",
            memory_type="unknown",
            timestamp=datetime.now(UTC),
            integrity_hash=cid,
        )

    async def delete_memory(self, cid: str) -> bool:
        return True


def test_owner_binding_survives_restart(client: TestClient, seeded, db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    import coordinator_api.contexts.ipfs.routers.ipfs as ipfs_mod

    # 1. Upload as the owner — writes the durable cid -> agent row.
    monkeypatch.setattr(ipfs_mod, "get_ipfs_service", lambda: _UploadService())
    resp = client.post(
        "/v1/ipfs/upload",
        json={"agent_id": AGENT, "memory_data": {"x": 1}},
        headers=_headers("owner1"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["cid"] == CID

    row = db_session.get(IPFSMemoryOwner, CID)
    assert row is not None and row.agent_id == AGENT

    # 2. "Restart": a fresh service instance has empty registries, so
    #    retrieve_memory reports agent_id="unknown".
    monkeypatch.setattr(ipfs_mod, "get_ipfs_service", lambda: _RestartedService())

    # The legitimate owner can still retrieve…
    resp = client.post("/v1/ipfs/retrieve", json={"cid": CID}, headers=_headers("owner1"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["metadata"]["agent_id"] == AGENT

    # …and an intruder is still refused.
    resp = client.post("/v1/ipfs/retrieve", json={"cid": CID}, headers=_headers("intruder"))
    assert resp.status_code == 403

    # Delete resolves the same durable owner.
    resp = client.request("DELETE", "/v1/ipfs/delete", json={"cid": CID}, headers=_headers("owner1"))
    assert resp.status_code == 200, resp.text
    resp = client.request("DELETE", "/v1/ipfs/delete", json={"cid": CID}, headers=_headers("intruder"))
    assert resp.status_code == 403


def test_unmapped_cid_still_fails_closed(client: TestClient, seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    """A CID with no owner row keeps the pre-fix fail-closed behaviour."""
    import coordinator_api.contexts.ipfs.routers.ipfs as ipfs_mod

    monkeypatch.setattr(ipfs_mod, "get_ipfs_service", lambda: _RestartedService())
    resp = client.post("/v1/ipfs/retrieve", json={"cid": "bafy-never-uploaded"}, headers=_headers("owner1"))
    assert resp.status_code == 403
