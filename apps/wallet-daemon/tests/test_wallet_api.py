from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from aitbc_chain.app import create_app  # noqa: I100

from app.deps import get_keystore, get_ledger


@pytest.fixture(name="client")
def client_fixture(tmp_path, monkeypatch):
    # Override ledger path to temporary directory
    from app.settings import Settings

    class TestSettings(Settings):
        ledger_db_path = tmp_path / "ledger.db"

    monkeypatch.setattr("app.deps.get_settings", lambda: TestSettings())

    app = create_app()
    return TestClient(app)


def _create_wallet(client: TestClient, wallet_id: str, password: str = "Password!234") -> None:
    payload = {
        "wallet_id": wallet_id,
        "password": password,
    }
    response = client.post("/v1/wallets", json=payload)
    assert response.status_code == 201, response.text


def test_wallet_workflow(client: TestClient):
    wallet_id = "wallet-1"
    password = "StrongPass!234"

    # Create wallet
    response = client.post(
        "/v1/wallets",
        json={
            "wallet_id": wallet_id,
            "password": password,
            "metadata": {"label": "test"},
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()["wallet"]
    assert data["wallet_id"] == wallet_id
    assert "public_key" in data

    # List wallets
    response = client.get("/v1/wallets")
    assert response.status_code == 200
    items = response.json()["items"]
    assert any(item["wallet_id"] == wallet_id for item in items)

    # Unlock wallet
    response = client.post(f"/v1/wallets/{wallet_id}/unlock", json={"password": password})
    assert response.status_code == 200
    assert response.json()["unlocked"] is True

    # Sign payload
    message = base64.b64encode(b"hello").decode()
    response = client.post(
        f"/v1/wallets/{wallet_id}/sign",
        json={"password": password, "message_base64": message},
    )
    assert response.status_code == 200, response.text
    signature = response.json()["signature_base64"]
    assert isinstance(signature, str) and len(signature) > 0


def test_wallet_password_rules(client: TestClient):
    response = client.post(
        "/v1/wallets",
        json={"wallet_id": "weak", "password": "short"},
    )
    assert response.status_code == 400
***
