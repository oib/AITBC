"""Router tests for the escrow relay endpoints (#1289 round 9) —
POST /v1/escrow/{relay,release,rerefund}. The routers are thin: JWT dep
(AdminOrClientDep), pydantic validation, idempotency-ledger begin, then
delegation to EscrowRelayService / EscrowReleaseRelayService /
EscrowRefundRelayService. The chain-RPC boundary lives in the services,
so they are faked here; begin/complete_operation run for real (no
Idempotency-Key -> pass-through).
"""

from __future__ import annotations

import importlib

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token

ADMIN = "admin-a"
CLIENT = "client-1"


def _headers(sub: str, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _admin() -> dict[str, str]:
    return _headers(ADMIN, "admin")


def _client() -> dict[str, str]:
    return _headers(CLIENT, "client")


def _create_body() -> dict:
    return {
        "job_id": "job-1",
        "buyer": "0xbuyer",
        "provider": "0xprovider",
        "amount": "100",
        "lock_tx": {"tx": "0xlock"},
    }


class _OkService:
    def __init__(self, session):  # noqa: ANN001, ARG002
        pass

    async def relay(self, client_id: str, is_admin: bool, body: dict) -> dict:  # noqa: ARG002
        return {"contract_id": "ctr-1", "duplicate": False}

    async def release(self, client_id: str, is_admin: bool, body: dict) -> dict:  # noqa: ARG002
        return {"success": True, "tx_hash": "0xtx", "duplicate": False}

    async def refund(self, client_id: str, is_admin: bool, body: dict) -> dict:  # noqa: ARG002
        return {"success": True, "refund_tx_hash": "0xrf", "refunded_amount": "100", "duplicate": False}


class _RejectService:
    def __init__(self, session):  # noqa: ANN001, ARG002
        pass

    async def relay(self, client_id: str, is_admin: bool, body: dict) -> dict:  # noqa: ARG002
        raise HTTPException(status_code=403, detail="not the escrow buyer")

    async def release(self, client_id: str, is_admin: bool, body: dict) -> dict:  # noqa: ARG002
        raise HTTPException(status_code=403, detail="not the escrow buyer")

    async def refund(self, client_id: str, is_admin: bool, body: dict) -> dict:  # noqa: ARG002
        raise HTTPException(status_code=409, detail="job not refundable")


class _BoomService:
    def __init__(self, session):  # noqa: ANN001, ARG002
        pass

    async def relay(self, client_id: str, is_admin: bool, body: dict) -> dict:  # noqa: ARG002
        raise RuntimeError("chain rpc down")

    async def release(self, client_id: str, is_admin: bool, body: dict) -> dict:  # noqa: ARG002
        raise RuntimeError("chain rpc down")

    async def refund(self, client_id: str, is_admin: bool, body: dict) -> dict:  # noqa: ARG002
        raise RuntimeError("chain rpc down")


class TestEscrowCreateRelay:
    URL = "/v1/escrow/relay"

    def test_requires_auth(self, client: TestClient) -> None:
        assert client.post(self.URL, json=_create_body()).status_code == 401

    def test_validation(self, client: TestClient) -> None:
        bad = _create_body()
        del bad["lock_tx"]
        assert client.post(self.URL, json=bad, headers=_client()).status_code == 422
        bad2 = _create_body()
        bad2["job_id"] = ""
        assert client.post(self.URL, json=bad2, headers=_client()).status_code == 422

    def test_happy_path_admin_and_client(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            importlib.import_module("coordinator_api.contexts.payments.routers.escrow_relay"), "EscrowRelayService", _OkService
        )
        for headers in (_admin(), _client()):
            resp = client.post(self.URL, json=_create_body(), headers=headers)
            assert resp.status_code == 200
            assert resp.json()["contract_id"] == "ctr-1"

    def test_service_http_exception_propagates(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            importlib.import_module("coordinator_api.contexts.payments.routers.escrow_relay"),
            "EscrowRelayService",
            _RejectService,
        )
        resp = client.post(self.URL, json=_create_body(), headers=_client())
        assert resp.status_code == 403
        assert "not the escrow buyer" in resp.text

    def test_service_error_500(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            importlib.import_module("coordinator_api.contexts.payments.routers.escrow_relay"),
            "EscrowRelayService",
            _BoomService,
        )
        resp = client.post(self.URL, json=_create_body(), headers=_admin())
        assert resp.status_code == 500


class TestEscrowReleaseRelay:
    URL = "/v1/escrow/release"

    def test_requires_auth(self, client: TestClient) -> None:
        assert client.post(self.URL, json={"job_id": "j1"}).status_code == 401

    def test_happy_and_reject(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            importlib.import_module("coordinator_api.contexts.payments.routers.escrow_release_relay"),
            "EscrowReleaseRelayService",
            _OkService,
        )
        resp = client.post(self.URL, json={"job_id": "j1", "amount": "50"}, headers=_client())
        assert resp.status_code == 200
        assert resp.json()["tx_hash"] == "0xtx"
        monkeypatch.setattr(
            importlib.import_module("coordinator_api.contexts.payments.routers.escrow_release_relay"),
            "EscrowReleaseRelayService",
            _RejectService,
        )
        assert client.post(self.URL, json={"job_id": "j1"}, headers=_client()).status_code == 403

    def test_validation_amount_optional(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            importlib.import_module("coordinator_api.contexts.payments.routers.escrow_release_relay"),
            "EscrowReleaseRelayService",
            _OkService,
        )
        # amount omitted -> full locked amount per #469 ruling
        resp = client.post(self.URL, json={"job_id": "j1"}, headers=_admin())
        assert resp.status_code == 200
        # missing job_id -> 422
        assert client.post(self.URL, json={}, headers=_admin()).status_code == 422


class TestEscrowRefundRelay:
    URL = "/v1/escrow/refund"

    def test_requires_auth(self, client: TestClient) -> None:
        assert client.post(self.URL, json={"job_id": "j1"}).status_code == 401

    def test_happy_path(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            importlib.import_module("coordinator_api.contexts.payments.routers.escrow_refund_relay"),
            "EscrowRefundRelayService",
            _OkService,
        )
        resp = client.post(self.URL, json={"job_id": "j1", "reason": "job_failed"}, headers=_client())
        assert resp.status_code == 200
        assert resp.json()["refund_tx_hash"] == "0xrf"

    def test_reason_literal_enforced(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            importlib.import_module("coordinator_api.contexts.payments.routers.escrow_refund_relay"),
            "EscrowRefundRelayService",
            _OkService,
        )
        resp = client.post(self.URL, json={"job_id": "j1", "reason": "whatever"}, headers=_client())
        assert resp.status_code == 422

    def test_conflict_and_500(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            importlib.import_module("coordinator_api.contexts.payments.routers.escrow_refund_relay"),
            "EscrowRefundRelayService",
            _RejectService,
        )
        resp = client.post(self.URL, json={"job_id": "j1"}, headers=_client())
        assert resp.status_code == 409
        monkeypatch.setattr(
            importlib.import_module("coordinator_api.contexts.payments.routers.escrow_refund_relay"),
            "EscrowRefundRelayService",
            _BoomService,
        )
        assert client.post(self.URL, json={"job_id": "j1"}, headers=_admin()).status_code == 500
