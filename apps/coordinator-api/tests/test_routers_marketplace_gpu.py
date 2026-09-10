"""Tests for the GPU marketplace router endpoints (E1/G1/G4).

These exercise the full quote/buy path for fixed-duration GPU rentals:
- Registration defaults region/miner binding.
- Quote prepares a priced job that cannot be dispatched until it is bought.
- Buy clamps short-duration TTL and escrow timeout to the 300s minimum.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from aitbc.auth import create_access_token
from aitbc.marketplace.energy_pricing import FIXED_POINT_SCALE

from coordinator_api.contexts.infrastructure.domain import Job, Miner
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.contexts.marketplace.domain.energy import NativeEnergyProfile, NativeEnergyRate
from coordinator_api.contexts.marketplace.domain.gpu_marketplace import GPURegistry
from coordinator_api.contexts.payments.services.payments import PaymentService
from coordinator_api.main import app
from aitbc_shared import JobPayment

BUYER = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
PROVIDER = "0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2"
MODEL = "NVIDIA GeForce RTX 4060 Ti"
RESOURCE = "node2-rtx4060ti"


@pytest.fixture
def client_token() -> str:
    return create_access_token("client1", "client")


@pytest.fixture
def miner_token() -> str:
    return create_access_token("gpu_miner", "miner")


@pytest.fixture
def native_pricing(monkeypatch):
    """Use the native energy oracle instead of an EVM contract."""
    from coordinator_api.config import settings

    monkeypatch.setattr(settings, "native_energy_pricing", True)
    return settings


@pytest.fixture
def pricing_engine_override():
    """Make the dynamic-pricing dependency fail closed so it falls back to listing price."""
    from coordinator_api.contexts.marketplace.routers.marketplace_gpu import get_pricing_engine

    engine = type("FakeEngine", (), {"calculate_dynamic_price": AsyncMock(side_effect=Exception("skip"))})()
    app.dependency_overrides[get_pricing_engine] = lambda: engine
    yield engine
    app.dependency_overrides.pop(get_pricing_engine, None)


def _seed_energy(db_session):
    """Create the native profile and rate records a fixed-duration quote needs."""
    db_session.add(
        NativeEnergyProfile(
            resource_id=RESOURCE,
            provider=PROVIDER,
            model_id=RESOURCE,
            tdp_watts=165,
            eur_per_kwh_scaled=int(Decimal("0.30") * FIXED_POINT_SCALE),
            enabled=True,
            revision=1,
        )
    )
    db_session.add(
        NativeEnergyRate(
            id=1,
            ait_per_eur_scaled=int(Decimal("1.5") * FIXED_POINT_SCALE),
            version=1,
            observed_at=int(time.time()),
            submitted_at=int(time.time()),
            source_kind="native_operator",
            enabled=True,
        )
    )
    db_session.commit()


def _register_gpu(client, token, **overrides) -> str:
    """Register a GPU and return its generated id."""
    payload = {
        "gpu": {
            "name": MODEL,
            "memory_gb": 16,
            "compute_capability": "8.9",
            "price_per_hour": "0.05",
            "resource_id": RESOURCE,
            **overrides,
        }
    }
    resp = client.post(
        "/v1/marketplace/gpu/register",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert resp.status_code == 200
    return str(resp.json()["gpu_id"])


@pytest.fixture
def available_gpu(client, miner_token, db_session) -> str:
    """A registered, available GPU for tests that need one."""
    return _register_gpu(client, miner_token)


@pytest.mark.unit
def test_register_gpu_defaults_region_and_miner(client, miner_token, db_session):
    """An unqualified GPU registration is bound to the authenticated miner and localhost."""
    gpu_id = _register_gpu(client, miner_token)
    gpu = db_session.get(GPURegistry, gpu_id)
    assert gpu is not None
    assert gpu.region == "localhost"
    assert gpu.miner_id == "gpu_miner"
    assert gpu.resource_id == RESOURCE
    assert gpu.status == "available"


@pytest.mark.unit
def test_register_gpu_allows_explicit_region(client, miner_token, db_session):
    """A caller can still override the default region when needed."""
    gpu_id = _register_gpu(client, miner_token, region="eu-west")
    gpu = db_session.get(GPURegistry, gpu_id)
    assert gpu.region == "eu-west"


@pytest.mark.unit
def test_quote_gpu_creates_priced_non_dispatchable_job(client, client_token, db_session, native_pricing, available_gpu):
    """A quote-only job carries a positive payment_amount so the dispatch gate blocks it."""
    _seed_energy(db_session)
    resp = client.post(
        "/v1/marketplace/gpu/quote",
        headers={"Authorization": f"Bearer {client_token}"},
        json={
            "buyer_id": BUYER,
            "gpu_id": available_gpu,
            "duration_hours": 0.05,
            "gpu_count": 1,
            "settlement_route": "native",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data["buyer_charge_ait"] is not None

    job = db_session.get(Job, data["job_id"])
    assert job is not None
    assert job.payment_amount is not None and job.payment_amount > 0
    assert job.payment_token == "AITBC"
    assert job.constraints.get("min_vram_gb") is None

    # Even a miner that matches the constraints may not run an unfunded quote.
    db_session.add(
        Miner(
            id="miner_test",
            region="localhost",
            capabilities={"gpus": [{"name": MODEL, "memory_mb": 16380}]},
            status="ONLINE",
            last_heartbeat=datetime.now(UTC),
        )
    )
    db_session.commit()
    assert JobService(db_session).acquire_next_job(db_session.get(Miner, "miner_test")) is None
    assert job.state == "QUEUED"


@pytest.mark.unit
def test_quote_gpu_is_public(client, db_session, native_pricing, available_gpu):
    """The quote endpoint is public so callers can price a rental before buying."""
    _seed_energy(db_session)
    resp = client.post(
        "/v1/marketplace/gpu/quote",
        json={
            "buyer_id": BUYER,
            "gpu_id": available_gpu,
            "duration_hours": 0.05,
            "gpu_count": 1,
            "settlement_route": "native",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data.get("buyer_charge_ait")

    job = db_session.get(Job, data["job_id"])
    assert job is not None
    assert job.payment_amount is not None


@pytest.mark.unit
def test_buy_gpu_short_duration_clamps_ttl_and_escrow_timeout(
    client,
    client_token,
    db_session,
    native_pricing,
    available_gpu,
    pricing_engine_override,
    monkeypatch,
):
    """A 0.05h buy clamps both the job TTL and the payment escrow timeout to 300s."""
    _seed_energy(db_session)

    quote_resp = client.post(
        "/v1/marketplace/gpu/quote",
        headers={"Authorization": f"Bearer {client_token}"},
        json={
            "buyer_id": BUYER,
            "gpu_id": available_gpu,
            "duration_hours": 0.05,
            "gpu_count": 1,
            "settlement_route": "native",
        },
    )
    assert quote_resp.status_code == 200
    quote = quote_resp.json()

    captured = {}

    async def fake_create_payment(self, client_id: str, job_id: str, payment_data) -> JobPayment:
        captured["payment_data"] = payment_data
        return JobPayment(
            id="pay_test",
            job_id=job_id,
            amount=payment_data.amount,
            status="escrowed",
            currency="AITBC",
            payment_method="aitbc_token",
        )

    monkeypatch.setattr(PaymentService, "create_payment", fake_create_payment)

    buy_resp = client.post(
        "/v1/marketplace/gpu/purchase",
        headers={"Authorization": f"Bearer {client_token}"},
        json={
            "buyer_id": BUYER,
            "gpu_id": available_gpu,
            "duration_hours": 0.05,
            "payment_method": "blockchain",
            "energy_quote": quote["energy_quote"],
            "protected": True,
        },
    )
    assert buy_resp.status_code == 200
    data = buy_resp.json()
    assert data["status"] == "purchased"
    assert data["job_id"] is not None

    assert captured["payment_data"].escrow_timeout_seconds == 300

    db_session.expire_all()
    job = db_session.get(Job, data["job_id"])
    assert job is not None
    assert job.ttl_seconds == 300
    assert job.constraints.get("min_vram_gb") is None
