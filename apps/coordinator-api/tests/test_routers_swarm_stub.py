"""Router tests for the intentionally-empty swarm + agent messaging
routers (#1289 round 9). Both modules document that their mock endpoints
were removed: the routers stay mounted for import stability but register
NO routes, so every request under their prefixes must 404 in every
environment — this pins that contract so a future re-introduction is
deliberate, not accidental.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token


def _admin() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('admin-a', 'admin')}"}


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/v1/swarm/status"),
        ("post", "/v1/swarm/join"),
        ("post", "/v1/swarm/coordinate"),
        ("get", "/v1/swarm/clusters"),
        ("post", "/v1/swarm/nodes/register"),
        ("get", "/v1/swarm/tasks"),
        ("post", "/v1/swarm/consensus"),
    ],
)
def test_swarm_routes_all_404(client: TestClient, method: str, path: str) -> None:
    resp = getattr(client, method)(path, headers=_admin(), json={} if method == "post" else None)
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/v1/agent/agents"),
        ("post", "/v1/agent/broadcast"),
        ("post", "/v1/agent/heartbeat"),
        ("get", "/v1/agent/stats"),
        ("get", "/v1/agent/messages"),
    ],
)
def test_agent_messaging_routes_all_404(client: TestClient, method: str, path: str) -> None:
    resp = getattr(client, method)(path, headers=_admin(), json={} if method == "post" else None)
    assert resp.status_code == 404
