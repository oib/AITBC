"""Tests for the Agent Coordinator public key exchange endpoints."""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from agent_app.encryption import MessageEncryptor, public_keys
from agent_app.main import create_app


@pytest.fixture(autouse=True)
def clean_public_key_registry():
    """Start each test with an empty in-memory public key registry."""
    public_keys.PUBLIC_KEY_REGISTRY.clear()
    yield
    public_keys.PUBLIC_KEY_REGISTRY.clear()


@pytest.fixture
def app_client():
    """TestClient for the Agent Coordinator app."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def sample_public_key():
    """A PEM-encoded RSA public key for tests."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def test_register_and_fetch_public_key(app_client, sample_public_key):
    """POST /keys/register and GET /keys/{agent_id} round-trip."""
    public_key_b64 = base64.b64encode(sample_public_key).decode("utf-8")

    register_response = app_client.post(
        "/api/v1/agent/keys/register",
        json={"agent_id": "agent-1", "public_key": public_key_b64, "key_id": "key-1"},
    )
    assert register_response.status_code == 200
    data = register_response.json()
    assert data["success"] is True
    assert data["agent_id"] == "agent-1"
    assert data["key_id"] == "key-1"

    fetch_response = app_client.get("/api/v1/agent/keys/agent-1")
    assert fetch_response.status_code == 200
    fetched = fetch_response.json()
    assert fetched["agent_id"] == "agent-1"
    assert fetched["public_key"] == public_key_b64
    assert fetched["key_id"] == "key-1"
    assert "created_at" in fetched


def test_get_missing_public_key_returns_404(app_client):
    """GET /keys/{agent_id} returns 404 for an unknown agent."""
    response = app_client.get("/api/v1/agent/keys/unknown-agent")
    assert response.status_code == 404
    body = response.json()
    message = body.get("message", "")
    assert "No public key found" in message


def test_encryptor_fetches_public_key_from_registry(tmp_path, sample_public_key):
    """The MessageEncryptor can fetch a public key from the in-memory registry."""
    encryptor = MessageEncryptor(keys_dir=str(tmp_path / "keys"))

    # No local key, but a key is registered by another agent.
    public_keys.register_public_key("remote-agent", sample_public_key, "remote-key")

    fetched = encryptor.get_public_key("remote-agent")
    assert fetched == sample_public_key

    # Generate a local sender key so we can encrypt.
    encryptor.generate_key_pair("local-agent")

    message = {"content": "secret", "message_type": "direct"}
    encrypted = encryptor.encrypt_message(message, "local-agent", "remote-agent")
    assert encrypted is not None
    assert encrypted.sender_id == "local-agent"
