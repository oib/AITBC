"""#2759: GET /agent/genesis.json serves the canonical genesis document.

``/rpc/network-info`` and ``/rpc/join`` advertise ``{base}/agent/genesis.json``
as the public join bootstrap, and ``aitbc genesis sync-from-hub`` fetches it —
but only the public hub's nginx vhost actually served the path (a static
``/etc/aitbc/genesis.json`` alias). On the raw RPC port and on hosts without
the vhost (sandbox mesh) the advertised URL 404'd, so genesis sync could never
complete. The app now serves the same document from
``DATA_DIR/data/<chain_id>/genesis.json`` — the file every node file-loads.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aitbc.constants import DATA_DIR
from aitbc_chain.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


def _write_genesis(chain_id: str, document: dict) -> Path:
    path = DATA_DIR / "data" / chain_id / "genesis.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document))
    return path


def test_agent_genesis_json_serves_configured_chain(client: TestClient) -> None:
    document = {
        "chain_id": "bc-2.test",
        "genesis_hash": "0x" + "ab" * 32,
        "state_root": "0x" + "cd" * 32,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "allocations": [{"address": "0x" + "11" * 20, "balance": "1000"}],
        "parameters": {"p": "1"},
    }
    _write_genesis("bc-2.test", document)

    response = client.get("/agent/genesis.json")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == document


def test_agent_genesis_json_chain_id_selects_supported_chain(client: TestClient) -> None:
    document = {"chain_id": "chain-a", "genesis_hash": "0x" + "ef" * 32}
    _write_genesis("chain-a", document)

    response = client.get("/agent/genesis.json", params={"chain_id": "chain-a"})

    assert response.status_code == 200
    assert response.json()["chain_id"] == "chain-a"


def test_agent_genesis_json_unknown_chain_is_400(client: TestClient) -> None:
    # The app's chain-resolution middleware rejects unsupported chain_id
    # query params before the route runs.
    response = client.get("/agent/genesis.json", params={"chain_id": "no-such-chain"})
    assert response.status_code == 400


def test_agent_genesis_json_missing_file_is_404(client: TestClient) -> None:
    # bc-2.test is the configured default; ensure no file exists for it.
    stray = DATA_DIR / "data" / "bc-2.test" / "genesis.json"
    if stray.exists():
        stray.unlink()
    response = client.get("/agent/genesis.json")
    assert response.status_code == 404
