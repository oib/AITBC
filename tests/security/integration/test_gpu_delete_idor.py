"""Security pins — delete_gpu ownership/IDOR (#1174, CE-005).

``DELETE /v1/market/gpu/{id}`` must be restricted to the listing owner or an
admin; ``?force=true`` is admin-only even for the owner. Pre-fix any
authenticated user could delete any GPU listing.
"""

from __future__ import annotations

import pytest
from aitbc.auth import create_access_token

from coordinator_api.contexts.market.domain.gpu_market import GPURegistry


def _token(user_id: str, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


@pytest.fixture
def miner_gpu(client, db_session) -> str:
    """A GPU registered by miner_a; returns its id."""
    resp = client.post(
        "/v1/market/gpu/register",
        headers=_token("miner_a", "miner"),
        json={
            "gpu": {
                "name": "NVIDIA GeForce RTX 4060 Ti",
                "memory_gb": 16,
                "compute_capability": "8.9",
                "price_per_hour": "0.05",
                "resource_id": "sec-pin-gpu-1",
            }
        },
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["gpu_id"])


def test_unauthenticated_delete_rejected(client, miner_gpu):
    resp = client.delete(f"/v1/market/gpu/{miner_gpu}")
    assert resp.status_code == 401


def test_other_miner_cannot_delete(client, miner_gpu, db_session):
    resp = client.delete(f"/v1/market/gpu/{miner_gpu}", headers=_token("miner_b", "miner"))
    assert resp.status_code == 403
    assert db_session.get(GPURegistry, miner_gpu) is not None


def test_owner_can_delete_own_listing(client, miner_gpu, db_session):
    resp = client.delete(f"/v1/market/gpu/{miner_gpu}", headers=_token("miner_a", "miner"))
    assert resp.status_code == 200
    assert db_session.get(GPURegistry, miner_gpu) is None


def test_client_role_cannot_delete_gpu(client, miner_gpu):
    resp = client.delete(f"/v1/market/gpu/{miner_gpu}", headers=_token("client1", "client"))
    assert resp.status_code == 403
