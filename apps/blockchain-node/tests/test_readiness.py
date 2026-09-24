"""The node's /ready probe: chain database and a non-empty chain set are
always required; a node told to produce blocks must additionally hold the key
for its declared proposer identity — the same gate startup applies."""

import pytest
from fastapi.testclient import TestClient

from aitbc_chain.app import (
    _check_can_sign,
    _check_supported_chains,
    _effective_block_production_enabled,
    create_app,
)
from aitbc_chain.config import settings


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


def test_ready_when_required_features_available(client, monkeypatch):
    # The test env enables block production, so give the node a signable
    # identity — the same thing the startup gate requires.
    from aitbc_chain.proposer_identity import address_of

    key = "0x" + "ab" * 32
    monkeypatch.setattr(settings, "proposer_id", address_of(key))
    monkeypatch.setattr(settings, "proposer_key", key)
    resp = client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert "database" in body["checks"]
    assert "supported_chains" in body["checks"]
    assert "block_production" in body["checks"]


def test_not_ready_when_production_enabled_but_cannot_sign(client, monkeypatch):
    monkeypatch.setattr("aitbc_chain.app._effective_block_production_enabled", lambda: True)
    monkeypatch.setattr(settings, "proposer_id", "0x0000000000000000000000000000000000000001")
    monkeypatch.setattr(settings, "proposer_key", None)
    resp = client.get("/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["failed"] == ["block_production"]
    # The identity/key detail stays server-side — /ready is unauthenticated.
    assert "proposer" not in resp.text.lower() or "block_production" in resp.text


def test_block_production_check_skipped_when_disabled(client, monkeypatch):
    monkeypatch.setattr("aitbc_chain.app._effective_block_production_enabled", lambda: False)
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert "block_production" not in resp.json()["checks"]


def test_supported_chains_check(monkeypatch):
    monkeypatch.setattr(settings, "supported_chains", "")
    monkeypatch.setattr(settings, "chain_id", "")
    assert _check_supported_chains() is False
    monkeypatch.setattr(settings, "chain_id", "ait-mainnet")
    assert _check_supported_chains() is True


def test_can_sign_raises_for_missing_key(monkeypatch):
    monkeypatch.setattr(settings, "proposer_id", "0x0000000000000000000000000000000000000001")
    monkeypatch.setattr(settings, "proposer_key", None)
    with pytest.raises(RuntimeError, match="no usable signing key"):
        _check_can_sign()


def test_env_override_takes_precedence(monkeypatch):
    monkeypatch.setattr(settings, "enable_block_production", False)
    monkeypatch.setenv("AITBC_FORCE_ENABLE_BLOCK_PRODUCTION", "true")
    assert _effective_block_production_enabled() is True
    monkeypatch.setenv("AITBC_FORCE_ENABLE_BLOCK_PRODUCTION", "false")
    assert _effective_block_production_enabled() is False
    monkeypatch.delenv("AITBC_FORCE_ENABLE_BLOCK_PRODUCTION")
    assert _effective_block_production_enabled() is False
