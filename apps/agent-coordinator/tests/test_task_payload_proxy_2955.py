"""#2955: GET /v1/tasks/{task_id}/payload — the party-scoped payload proxy.

The buyer pins its input CID on its own island daemon; a provider whose
swarm path is broken cannot serve the paid task. The coordinator streams
the same bytes from the hub island daemon over the authenticated control
plane. The ref is pinned to the durable escrow entry at submit time, reads
are party-scoped like the escrow row itself, and the stream is byte-capped.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aitbc.crypto.payment_escrow import EscrowStatus, PaymentEscrow  # noqa: E402

from agent_app.config import settings  # noqa: E402
from agent_app.routers import tasks as tasks_router  # noqa: E402


class FakeEscrowRPC:
    def create(self, **_kwargs) -> dict:
        return {"lock_tx_hash": "0x" + "ab" * 32, "contract_id": "contract-1"}


@pytest.fixture
def client(monkeypatch):
    fake_state = MagicMock()
    fake_state.task_distributor = MagicMock()
    fake_state.task_distributor.submit_task = AsyncMock(return_value=True)
    fake_state.payment_escrow = PaymentEscrow()
    fake_state.escrow_rpc = FakeEscrowRPC()
    app = FastAPI()
    app.include_router(tasks_router.router, prefix="/v1")
    monkeypatch.setattr(tasks_router, "state", fake_state)
    monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
    monkeypatch.setattr(settings, "task_payment_escrow_enabled", True)
    return TestClient(app), fake_state


def _submission(task_id: str, payload_ref: str | None = "QmTestPayload") -> dict:
    task_data: dict = {"task_id": task_id}
    if payload_ref is not None:
        task_data["payload_ref"] = payload_ref
    return {
        "task_data": task_data,
        "payment": {"requester": "0xBuyer", "agent": "0xAgent", "amount": 100},
    }


def _mk_entry(fake_state, task_id: str, payload_ref: str | None = "QmTestPayload"):
    entry = fake_state.payment_escrow.create_escrow(
        task_id=task_id,
        chain_id="test-chain",
        requester="0xBuyer",
        agent="0xAgent",
        amount=100,
        fee=0,
        timeout=3600.0,
    )
    if payload_ref is not None:
        entry.metadata["payload_ref"] = payload_ref
        fake_state.payment_escrow.persist_entry(entry)
    return entry


def _ipfs_response(content: bytes = b"payload-bytes", status: int = 200, dag_size: int | None = None):
    resp = MagicMock()
    resp.status_code = status
    resp.text = content.decode(errors="replace") if status != 200 else ""
    resp.iter_content = lambda n=8192, *a, **k: iter([content] if content else [])
    resp.close = MagicMock()
    return resp


def _install_fake_ipfs(monkeypatch, cat_content: bytes = b"payload-bytes", cat_status: int = 200, dag_size: int | None = None):
    """Route fake Kubo calls by URL: dag/stat answers TotalSize, cat streams."""

    def fake_post(url, params=None, timeout=None, stream=None, **kwargs):
        if "dag/stat" in url:
            resp = MagicMock()
            resp.status_code = 200
            resp.text = f'{{"TotalSize": {dag_size}}}\n' if dag_size is not None else ""
            return resp
        return _ipfs_response(content=cat_content, status=cat_status)

    monkeypatch.setattr(tasks_router.requests, "post", fake_post)


class TestSubmitRecordsPayloadRef:
    def test_payload_ref_pinned_to_escrow_metadata(self, client):
        test_client, fake_state = client
        resp = test_client.post("/v1/tasks/submit", json=_submission("t-pr"))
        assert resp.status_code == 200, resp.text
        entry = fake_state.payment_escrow.get_escrow_for_task("t-pr")
        assert entry is not None
        assert entry.metadata.get("payload_ref") == "QmTestPayload"

    def test_replay_backfills_payload_ref(self, client):
        test_client, fake_state = client
        entry = fake_state.payment_escrow.create_escrow(
            task_id="t-pr2",
            chain_id=settings.default_chain_id,
            requester="0xBuyer",
            agent="0xAgent",
            amount=100,
            fee=0,
            timeout=3600.0,
        )
        entry.status = EscrowStatus.LOCKED
        entry.metadata["timeout_seconds"] = "3600.0"
        fake_state.payment_escrow.persist_entry(entry)
        resp = test_client.post(
            "/v1/tasks/submit",
            json=_submission("t-pr2", payload_ref="QmBackfill"),
        )
        assert resp.status_code == 200, resp.text
        reloaded = fake_state.payment_escrow.get_escrow_for_task("t-pr2")
        assert reloaded.metadata.get("payload_ref") == "QmBackfill"


class TestPayloadEndpoint:
    def test_streams_payload_bytes(self, client, monkeypatch):
        test_client, fake_state = client
        _mk_entry(fake_state, "t-p1")
        _install_fake_ipfs(monkeypatch, cat_content=b"hello-payload")
        resp = test_client.get("/v1/tasks/t-p1/payload")
        assert resp.status_code == 200, resp.text
        assert resp.content == b"hello-payload"
        assert resp.headers["content-type"].startswith("application/octet-stream")

    def test_unknown_task_404(self, client, monkeypatch):
        test_client, _ = client
        _install_fake_ipfs(monkeypatch)
        resp = test_client.get("/v1/tasks/t-nope/payload")
        assert resp.status_code == 404

    def test_missing_payload_ref_404(self, client, monkeypatch):
        test_client, fake_state = client
        _mk_entry(fake_state, "t-p2", payload_ref=None)
        _install_fake_ipfs(monkeypatch)
        resp = test_client.get("/v1/tasks/t-p2/payload")
        assert resp.status_code == 404

    def test_malformed_cid_never_reaches_kubo(self, client, monkeypatch):
        test_client, fake_state = client
        _mk_entry(fake_state, "t-p3", payload_ref="../../etc/passwd")
        calls = []

        def fake_post(url, **kwargs):
            calls.append(url)
            return _ipfs_response()

        monkeypatch.setattr(tasks_router.requests, "post", fake_post)
        resp = test_client.get("/v1/tasks/t-p3/payload")
        assert resp.status_code == 404
        assert calls == []

    def test_preflight_size_over_cap_413(self, client, monkeypatch):
        test_client, fake_state = client
        _mk_entry(fake_state, "t-p4")
        monkeypatch.setenv("AGENT_TASK_PAYLOAD_PROXY_MAX_BYTES", "1024")
        _install_fake_ipfs(monkeypatch, cat_content=b"x" * 2048, dag_size=2048)
        resp = test_client.get("/v1/tasks/t-p4/payload")
        assert resp.status_code == 413

    def test_ipfs_cat_failure_is_502(self, client, monkeypatch):
        test_client, fake_state = client
        _mk_entry(fake_state, "t-p5")
        _install_fake_ipfs(monkeypatch, cat_status=500)
        resp = test_client.get("/v1/tasks/t-p5/payload")
        assert resp.status_code == 502

    def test_enforce_mode_requires_principal(self, client, monkeypatch):
        test_client, fake_state = client
        _mk_entry(fake_state, "t-p6")
        _install_fake_ipfs(monkeypatch)
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        resp = test_client.get("/v1/tasks/t-p6/payload")
        assert resp.status_code == 401
