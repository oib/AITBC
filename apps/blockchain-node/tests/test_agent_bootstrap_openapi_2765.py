"""#2765: /agent/bootstrap.env + /agent/openapi.json served by the app.

``/rpc/network-info`` and ``/rpc/join`` advertise ``bootstrap_env_url`` and
``docs_url`` under ``/agent/``, but only the public hub's nginx vhost
answered those paths — on the raw RPC port and on hosts without the vhost
they 404'd, the same defect class as #2759's genesis.json. The app now
serves the sanitized ``CONFIG_DIR/bootstrap.env`` (allowlist-rendered, no
key material — with a denylist gate mirroring render-bootstrap-env.sh) and
its own OpenAPI document.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aitbc_chain.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("aitbc.constants.CONFIG_DIR", tmp_path)
    return tmp_path


def test_agent_bootstrap_env_serves_rendered_file(client: TestClient, config_dir: Path) -> None:
    body = (
        "# AITBC public bootstrap — sanitized follower configuration.\nCHAIN_ID=bc-2\nFOLLOWER_API_KEY=public-follower-key\n"
    )
    (config_dir / "bootstrap.env").write_text(body)

    response = client.get("/agent/bootstrap.env")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == body


def test_agent_bootstrap_env_missing_file_is_404(client: TestClient, config_dir: Path) -> None:
    response = client.get("/agent/bootstrap.env")
    assert response.status_code == 404


def test_agent_bootstrap_env_refuses_key_material(client: TestClient, config_dir: Path) -> None:
    (config_dir / "bootstrap.env").write_text("CHAIN_ID=bc-2\nPROPOSER_KEY=0xdeadbeef\n")
    response = client.get("/agent/bootstrap.env")
    assert response.status_code == 500


def test_agent_openapi_json_serves_app_schema(client: TestClient) -> None:
    response = client.get("/agent/openapi.json")

    assert response.status_code == 200
    spec = response.json()
    assert spec["info"]["title"]
    # The advertised docs_url documents the API the caller actually reached.
    assert "/agent/genesis.json" in spec["paths"]
    assert "/agent/bootstrap.env" in spec["paths"]


def test_agent_openapi_json_matches_native_openapi(client: TestClient) -> None:
    aliased = client.get("/agent/openapi.json").json()
    native = client.get("/openapi.json").json()
    assert aliased == native
