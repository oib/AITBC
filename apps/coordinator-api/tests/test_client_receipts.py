import pytest
from fastapi.testclient import TestClient
from nacl.signing import SigningKey

from app.main import create_app
from app.models import JobCreate, MinerRegister, JobResultSubmit
from app.storage.db import init_db
from app.config import settings


@pytest.fixture(scope="module", autouse=True)
def test_client(tmp_path_factory):
    db_file = tmp_path_factory.mktemp("data") / "client_receipts.db"
    settings.database_url = f"sqlite:///{db_file}"
    init_db()
    app = create_app()
    with TestClient(app) as client:
        yield client


def test_receipt_endpoint_returns_signed_receipt(test_client: TestClient):
    signing_key = SigningKey.generate()
    settings.receipt_signing_key_hex = signing_key.encode().hex()

    # register miner
    resp = test_client.post(
        "/v1/miners/register",
        json={"capabilities": {"price": 1}, "concurrency": 1},
        headers={"X-Api-Key": "${MINER_API_KEY}"},
    )
    assert resp.status_code == 200

    # submit job
    job_payload = {
        "payload": {"task": "receipt"},
    }
    resp = test_client.post(
        "/v1/jobs",
        json=job_payload,
        headers={"X-Api-Key": "${CLIENT_API_KEY}"},
    )
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]

    # poll for job assignment
    poll_resp = test_client.post(
        "/v1/miners/poll",
        json={"max_wait_seconds": 1},
        headers={"X-Api-Key": "${MINER_API_KEY}"},
    )
    assert poll_resp.status_code in (200, 204)

    # submit result
    result_payload = {
        "result": {"units": 1, "unit_type": "gpu_seconds", "price": 1},
        "metrics": {"units": 1, "duration_ms": 500}
    }
    result_resp = test_client.post(
        f"/v1/miners/{job_id}/result",
        json=result_payload,
        headers={"X-Api-Key": "${MINER_API_KEY}"},
    )
    assert result_resp.status_code == 200
    signed_receipt = result_resp.json()["receipt"]
    assert signed_receipt["signature"]["alg"] == "Ed25519"

    # fetch receipt via client endpoint
    receipt_resp = test_client.get(
        f"/v1/jobs/{job_id}/receipt",
        headers={"X-Api-Key": "${CLIENT_API_KEY}"},
    )
    assert receipt_resp.status_code == 200
    payload = receipt_resp.json()
    assert payload["receipt_id"] == signed_receipt["receipt_id"]
    assert payload["signature"]["alg"] == "Ed25519"

    settings.receipt_signing_key_hex = None
