import pytest
from sqlmodel import Session
from nacl.signing import SigningKey

from aitbc_crypto.signing import ReceiptVerifier

from app.models import MinerRegister, JobCreate, Constraints
from app.services.jobs import JobService
from app.services.miners import MinerService
from app.services.receipts import ReceiptService
from app.storage.db import init_db, session_scope
from app.config import settings
from app.domain import JobReceipt
from sqlmodel import select


@pytest.fixture(scope="module", autouse=True)
def _init_db(tmp_path_factory):
    db_file = tmp_path_factory.mktemp("data") / "miner.db"
    from app.config import settings

    settings.database_url = f"sqlite:///{db_file}"
    init_db()
    yield


@pytest.fixture()
def session():
    with session_scope() as sess:
        yield sess


def test_register_and_poll_inflight(session: Session):
    miner_service = MinerService(session)
    job_service = JobService(session)

    miner_service.register(
        "miner-1",
        MinerRegister(
            capabilities={"gpu": False},
            concurrency=1,
        ),
    )

    job_service.create_job("client-a", JobCreate(payload={"task": "demo"}))
    assigned = miner_service.poll("miner-1", max_wait_seconds=1)
    assert assigned is not None

    miner = miner_service.get("miner-1")
    assert miner.inflight == 1

    miner_service.release("miner-1")
    miner = miner_service.get("miner-1")
    assert miner.inflight == 0


def test_heartbeat_updates_metadata(session: Session):
    miner_service = MinerService(session)

    miner_service.register(
        "miner-2",
        MinerRegister(
            capabilities={"gpu": True},
            concurrency=2,
        ),
    )

    miner_service.heartbeat(
        "miner-2",
        payload=dict(inflight=3, status="BUSY", metadata={"load": 0.9}),
    )

    miner = miner_service.get("miner-2")
    assert miner.status == "BUSY"
    assert miner.inflight == 3
    assert miner.extra_metadata.get("load") == 0.9


def test_capability_constrained_assignment(session: Session):
    miner_service = MinerService(session)
    job_service = JobService(session)

    miner = miner_service.register(
        "miner-cap",
        MinerRegister(
            capabilities={
                "gpus": [{"name": "NVIDIA RTX 4090", "memory_mb": 24576}],
                "models": ["stable-diffusion", "llama"]
            },
            concurrency=1,
            region="eu-west",
        ),
    )

    job_service.create_job(
        "client-x",
        JobCreate(
            payload={"task": "render"},
            constraints=Constraints(region="us-east"),
        ),
    )
    job_service.create_job(
        "client-x",
        JobCreate(
            payload={"task": "render-hf"},
            constraints=Constraints(
                region="eu-west",
                gpu="NVIDIA RTX 4090",
                min_vram_gb=12,
                models=["stable-diffusion"],
            ),
        ),
    )

    assigned = miner_service.poll("miner-cap", max_wait_seconds=1)
    assert assigned is not None
    assert assigned.job_id is not None
    assert assigned.payload["task"] == "render-hf"

    miner_state = miner_service.get("miner-cap")
    assert miner_state.inflight == 1

    miner_service.release("miner-cap")


def test_price_constraint(session: Session):
    miner_service = MinerService(session)
    job_service = JobService(session)

    miner_service.register(
        "miner-price",
        MinerRegister(
            capabilities={
                "gpus": [{"name": "NVIDIA RTX 3070", "memory_mb": 8192}],
                "models": [],
                "price": 3.5,
            },
            concurrency=1,
        ),
    )

    job_service.create_job(
        "client-y",
        JobCreate(
            payload={"task": "cheap"},
            constraints=Constraints(max_price=2.0),
        ),
    )
    job_service.create_job(
        "client-y",
        JobCreate(
            payload={"task": "fair"},
            constraints=Constraints(max_price=4.0),
        ),
    )

    assigned = miner_service.poll("miner-price", max_wait_seconds=1)
    assert assigned is not None
    assert assigned.payload["task"] == "fair"

    miner_service.release("miner-price")


def test_receipt_signing(session: Session):
    signing_key = SigningKey.generate()
    settings.receipt_signing_key_hex = signing_key.encode().hex()

    job_service = JobService(session)
    miner_service = MinerService(session)
    receipt_service = ReceiptService(session)

    miner_service.register(
        "miner-r",
        MinerRegister(
            capabilities={"price": 1.0},
            concurrency=1,
        ),
    )

    job = job_service.create_job(
        "client-r",
        JobCreate(payload={"task": "sign"}),
    )

    receipt = receipt_service.create_receipt(
        job,
        "miner-r",
        {"units": 1.0, "unit_type": "gpu_seconds", "price": 1.2},
        {"units": 1.0},
    )

    assert receipt is not None
    signature = receipt.get("signature")
    assert signature is not None
    assert signature["alg"] == "Ed25519"

    miner_service.release("miner-r", success=True, duration_ms=500, receipt_id=receipt["receipt_id"])
    miner_state = miner_service.get("miner-r")
    assert miner_state.jobs_completed == 1
    assert miner_state.total_job_duration_ms == 500
    assert miner_state.average_job_duration_ms == 500
    assert miner_state.last_receipt_id == receipt["receipt_id"]

    verifier = ReceiptVerifier(signing_key.verify_key.encode())
    payload = {k: v for k, v in receipt.items() if k not in {"signature", "attestations"}}
    assert verifier.verify(payload, receipt["signature"]) is True

    # Reset signing key for subsequent tests
    settings.receipt_signing_key_hex = None


def test_receipt_signing_with_attestation(session: Session):
    signing_key = SigningKey.generate()
    attest_key = SigningKey.generate()
    settings.receipt_signing_key_hex = signing_key.encode().hex()
    settings.receipt_attestation_key_hex = attest_key.encode().hex()

    job_service = JobService(session)
    miner_service = MinerService(session)
    receipt_service = ReceiptService(session)

    miner_service.register(
        "miner-attest",
        MinerRegister(capabilities={"price": 1.0}, concurrency=1),
    )

    job = job_service.create_job(
        "client-attest",
        JobCreate(payload={"task": "attest"}),
    )

    receipt = receipt_service.create_receipt(
        job,
        "miner-attest",
        {"units": 1.0, "unit_type": "gpu_seconds", "price": 2.0},
        {"units": 1.0},
    )

    assert receipt is not None
    assert receipt.get("signature") is not None
    attestations = receipt.get("attestations")
    assert attestations is not None and len(attestations) == 1

    stored_receipts = session.exec(select(JobReceipt).where(JobReceipt.job_id == job.id)).all()
    assert len(stored_receipts) == 1
    assert stored_receipts[0].receipt_id == receipt["receipt_id"]

    payload = {k: v for k, v in receipt.items() if k not in {"signature", "attestations"}}

    miner_verifier = ReceiptVerifier(signing_key.verify_key.encode())
    assert miner_verifier.verify(payload, receipt["signature"]) is True

    attest_verifier = ReceiptVerifier(attest_key.verify_key.encode())
    assert attest_verifier.verify(payload, attestations[0]) is True

    settings.receipt_signing_key_hex = None
    settings.receipt_attestation_key_hex = None

