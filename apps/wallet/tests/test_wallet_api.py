from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.deps import get_keystore, get_ledger, get_settings
from app.main import create_app
from app.keystore.service import KeystoreService
from app.ledger_mock import SQLiteLedgerAdapter


@pytest.fixture(name="client")
def client_fixture(tmp_path, monkeypatch):
    # Override ledger path to temporary directory
    from app.settings import Settings

    test_settings = Settings(LEDGER_DB_PATH=str(tmp_path / "ledger.db"))

    monkeypatch.setattr("app.settings.settings", test_settings)

    from app import deps

    deps.get_settings.cache_clear()
    deps.get_keystore.cache_clear()
    deps.get_ledger.cache_clear()

    app = create_app()

    keystore = KeystoreService()
    ledger = SQLiteLedgerAdapter(Path(test_settings.ledger_db_path))

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_keystore] = lambda: keystore
    app.dependency_overrides[get_ledger] = lambda: ledger
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
    body = response.json()
    assert body["detail"]["reason"] == "password_too_weak"
    assert "min_length" in body["detail"]
