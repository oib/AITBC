"""#2967: GET /v1/tasks/{task_id}/result — the party-scoped result proxy.

Symmetric reverse of the #2955 payload proxy: the provider pins its result
CID on its own island daemon and the buyer reads it through the swarm — the
same best-effort data plane, opposite direction. The coordinator streams
the bytes from the hub daemon over the authenticated control plane. The ref
is recorded on the durable escrow entry by the completing provider (never
caller-controlled at read time), reads are party-scoped, the stream is
byte-capped.
"""

from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aitbc.crypto.payment_escrow import EscrowStatus, PaymentEscrow  # noqa: E402

from agent_app.config import settings  # noqa: E402
from agent_app.routers import tasks as tasks_router  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    fake_state = MagicMock()
    fake_state.task_distributor = MagicMock()
    fake_state.task_distributor.submit_task = AsyncMock(return_value=True)
    fake_state.payment_escrow = PaymentEscrow()
    fake_state.escrow_rpc = None
    app = FastAPI()
    app.include_router(tasks_router.router, prefix="/v1")
    monkeypatch.setattr(tasks_router, "state", fake_state)
    monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
    monkeypatch.setattr(settings, "task_payment_escrow_enabled", True)
    return TestClient(app), fake_state


def _mk_entry(fake_state, task_id: str, result_ref: str | None = "QmTestResult"):
    entry = fake_state.payment_escrow.create_escrow(
        task_id=task_id,
        chain_id="test-chain",
        requester="0xBuyer",
        agent="0xAgent",
        amount=100,
        fee=0,
        timeout=3600.0,
    )
    if result_ref is not None:
        entry.metadata["result_ref"] = result_ref
        fake_state.payment_escrow.persist_entry(entry)
    return entry


def _install_fake_ipfs(monkeypatch, cat_content: bytes = b"result-bytes", cat_status: int = 200, dag_size: int | None = None):
    """Route fake Kubo calls by URL: dag/stat answers TotalSize, cat streams."""

    def fake_post(url, params=None, timeout=None, stream=None, **kwargs):
        if "dag/stat" in url:
            resp = MagicMock()
            resp.status_code = 200
            resp.text = f'{{"TotalSize": {dag_size}}}\n' if dag_size is not None else ""
            return resp
        resp = MagicMock()
        resp.status_code = cat_status
        resp.text = "" if cat_status == 200 else "cat-error"
        resp.iter_content = lambda n=8192, *a, **k: iter([cat_content] if cat_content else [])
        resp.close = MagicMock()
        return resp

    monkeypatch.setattr(tasks_router.requests, "post", fake_post)


class TestResultProxy:
    def test_serves_result_bytes(self, client, monkeypatch):
        test_client, fake_state = client
        _mk_entry(fake_state, "t-r1")
        _install_fake_ipfs(monkeypatch, cat_content=b"transcript-bytes")
        resp = test_client.get("/v1/tasks/t-r1/result")
        assert resp.status_code == 200, resp.text
        assert resp.content == b"transcript-bytes"

    def test_404_without_result_ref(self, client, monkeypatch):
        test_client, fake_state = client
        _mk_entry(fake_state, "t-r2", result_ref=None)
        _install_fake_ipfs(monkeypatch)
        resp = test_client.get("/v1/tasks/t-r2/result")
        assert resp.status_code == 404

    def test_404_malformed_result_ref(self, client, monkeypatch):
        test_client, fake_state = client
        _mk_entry(fake_state, "t-r3", result_ref="../../etc/passwd")
        _install_fake_ipfs(monkeypatch)
        resp = test_client.get("/v1/tasks/t-r3/result")
        assert resp.status_code == 404

    def test_404_unknown_task(self, client, monkeypatch):
        test_client, _ = client
        _install_fake_ipfs(monkeypatch)
        resp = test_client.get("/v1/tasks/t-unknown/result")
        assert resp.status_code == 404

    def test_413_oversized_dag_preflight(self, client, monkeypatch):
        test_client, fake_state = client
        _mk_entry(fake_state, "t-r4")
        _install_fake_ipfs(monkeypatch, dag_size=600 * 1024 * 1024)
        resp = test_client.get("/v1/tasks/t-r4/result")
        assert resp.status_code == 413

    def test_502_when_daemon_unreachable(self, client, monkeypatch):
        test_client, fake_state = client
        _mk_entry(fake_state, "t-r5")

        def failing_post(url, **kwargs):
            if "dag/stat" in url:
                resp = MagicMock()
                resp.status_code = 500
                resp.text = ""
                return resp
            raise tasks_router.requests.RequestException("connection refused")

        monkeypatch.setattr(tasks_router.requests, "post", failing_post)
        resp = test_client.get("/v1/tasks/t-r5/result")
        assert resp.status_code == 502


class TestCompleteRecordsResultRef:
    """The result proxy is only as good as the write path: the completing
    provider must land result_ref on the durable escrow entry."""

    def _locked(self, escrow, task_id: str, agent: str, amount: int = 100):
        entry = escrow.create_escrow(task_id=task_id, chain_id="c", requester="0xBuyer", agent=agent, amount=amount)
        escrow.lock(entry.escrow_id)
        return entry

    def _complete(self, test_client, task_id: str, pk: str, **body_extra):
        from aitbc.crypto.crypto import sign_transaction_data

        signed_at = int(time.time())
        fields: dict = {"action": "complete", "task_id": task_id, "signed_at": signed_at, "amount_units": 30}
        sig = sign_transaction_data(fields, pk)
        return test_client.post(
            f"/v1/tasks/{task_id}/complete",
            json={"signed_at": signed_at, "signature": sig, "amount_units": 30, **body_extra},
        )

    def test_complete_records_result_ref(self, client):
        from aitbc.crypto.crypto import derive_ethereum_address, generate_ethereum_private_key

        test_client, fake_state = client
        pk = generate_ethereum_private_key()
        self._locked(fake_state.payment_escrow, "t-rec", derive_ethereum_address(pk))
        resp = self._complete(test_client, "t-rec", pk, result_ref="QmResultCid123")
        assert resp.status_code == 200, resp.text
        entry = fake_state.payment_escrow.get_escrow_for_task("t-rec")
        assert entry.metadata.get("result_ref") == "QmResultCid123"

    def test_complete_ignores_malformed_result_ref(self, client):
        from aitbc.crypto.crypto import derive_ethereum_address, generate_ethereum_private_key

        test_client, fake_state = client
        pk = generate_ethereum_private_key()
        self._locked(fake_state.payment_escrow, "t-mal", derive_ethereum_address(pk))
        resp = self._complete(test_client, "t-mal", pk, result_ref="/ipfs/../../evil")
        assert resp.status_code == 200, resp.text
        entry = fake_state.payment_escrow.get_escrow_for_task("t-mal")
        assert "result_ref" not in entry.metadata
        assert entry.status == EscrowStatus.RELEASED

    def test_complete_without_result_ref_still_releases(self, client):
        from aitbc.crypto.crypto import derive_ethereum_address, generate_ethereum_private_key

        test_client, fake_state = client
        pk = generate_ethereum_private_key()
        self._locked(fake_state.payment_escrow, "t-plain", derive_ethereum_address(pk))
        resp = self._complete(test_client, "t-plain", pk)
        assert resp.status_code == 200, resp.text
        entry = fake_state.payment_escrow.get_escrow_for_task("t-plain")
        assert "result_ref" not in entry.metadata
        assert entry.status == EscrowStatus.RELEASED

    def test_result_roundtrip_after_complete(self, client, monkeypatch):
        """Wiring: provider completes with result_ref → buyer-scope read serves it."""
        from aitbc.crypto.crypto import derive_ethereum_address, generate_ethereum_private_key

        test_client, fake_state = client
        pk = generate_ethereum_private_key()
        self._locked(fake_state.payment_escrow, "t-wired", derive_ethereum_address(pk))
        resp = self._complete(test_client, "t-wired", pk, result_ref="QmWiredResult")
        assert resp.status_code == 200, resp.text
        _install_fake_ipfs(monkeypatch, cat_content=b"wired-result-bytes")
        resp = test_client.get("/v1/tasks/t-wired/result")
        assert resp.status_code == 200, resp.text
        assert resp.content == b"wired-result-bytes"
