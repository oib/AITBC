"""Tests for the GPU market router endpoints (E1/G1/G4).

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
from aitbc.market.energy_pricing import FIXED_POINT_SCALE

from coordinator_api.contexts.infrastructure.domain import Job, Miner
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.contexts.market.domain.energy import NativeEnergyProfile, NativeEnergyRate
from coordinator_api.contexts.market.domain.gpu_market import GPURegistry
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
    from coordinator_api.contexts.market.routers.market_gpu import get_pricing_engine

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
            tbp_watts=165,
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
        "/v1/market/gpu/register",
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
        "/v1/market/gpu/quote",
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
        "/v1/market/gpu/quote",
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
        "/v1/market/gpu/quote",
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
        "/v1/market/gpu/purchase",
        headers={"Authorization": f"Bearer {client_token}"},
        json={
            "buyer_id": "client1",
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


def test_native_energy_profile_get(client, db_session, native_pricing):
    """Public read of a registered native energy profile."""
    _seed_energy(db_session)
    resp = client.get(f"/v1/market/native-energy/profile/{RESOURCE}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["resource_id"] == RESOURCE
    assert data["tbp_watts"] == 165
    assert data["eur_per_kwh_scaled"] == int(Decimal("0.30") * FIXED_POINT_SCALE)
    assert data["eur_per_kwh"] == "0.3"
    assert data["revision"] == 1


def test_native_energy_profile_get_404(client, native_pricing):
    resp = client.get("/v1/market/native-energy/profile/nope")
    assert resp.status_code == 404


def test_native_energy_rate_get(client, db_session, native_pricing, miner_token):
    _seed_energy(db_session)
    resp = client.get(
        "/v1/market/native-energy/rate",
        headers={"Authorization": f"Bearer {miner_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ait_per_eur_scaled"] == int(Decimal("1.5") * FIXED_POINT_SCALE)
    assert data["ait_per_eur"] == "1.5"
    assert data["version"] == 1


def test_native_energy_rate_post_accepts_in_band(client, miner_token):
    """A plausible rate publishes and bumps the version."""
    resp = client.post(
        "/v1/market/native-energy/rate",
        headers={"Authorization": f"Bearer {miner_token}"},
        json={"ait_per_eur": "4.0"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ait_per_eur_scaled"] == int(Decimal("4.0") * FIXED_POINT_SCALE)
    assert data["version"] == 1


def test_native_energy_rate_post_rejects_below_band(client, miner_token):
    """SD-7: the stub value 1 sat accepted for nine days — a clearly-absurd rate
    must now be refused at admission."""
    resp = client.post(
        "/v1/market/native-energy/rate",
        headers={"Authorization": f"Bearer {miner_token}"},
        json={"ait_per_eur": "0.1"},
    )
    assert resp.status_code == 400
    assert "plausible band" in resp.json()["detail"]


def test_native_energy_rate_post_rejects_above_band(client, miner_token):
    resp = client.post(
        "/v1/market/native-energy/rate",
        headers={"Authorization": f"Bearer {miner_token}"},
        json={"ait_per_eur_scaled": int(Decimal("9") * FIXED_POINT_SCALE)},
    )
    assert resp.status_code == 400
    assert "plausible band" in resp.json()["detail"]


def test_native_energy_rate_post_band_is_configurable(client, miner_token, monkeypatch):
    """The band bounds are config keys — an operator can widen them, and the
    POST honours the override."""
    from coordinator_api.config import settings

    monkeypatch.setattr(settings, "energy_rate_min_ait_per_eur", Decimal("0.1"))
    resp = client.post(
        "/v1/market/native-energy/rate",
        headers={"Authorization": f"Bearer {miner_token}"},
        json={"ait_per_eur": "0.2"},
    )
    assert resp.status_code == 200


def test_native_energy_rate_post_band_boundaries(client, miner_token):
    """The configured bounds are inclusive and stay inside the int64 scaled range."""
    for rate in ("0.5", "8"):
        resp = client.post(
            "/v1/market/native-energy/rate",
            headers={"Authorization": f"Bearer {miner_token}"},
            json={"ait_per_eur": rate},
        )
        assert resp.status_code == 200, f"boundary {rate} refused: {resp.text}"


def test_native_energy_rate_post_rejects_int64_overflow(client, miner_token):
    """A scaled value above int64 must 400 at admission, not 500 on insert."""
    resp = client.post(
        "/v1/market/native-energy/rate",
        headers={"Authorization": f"Bearer {miner_token}"},
        json={"ait_per_eur_scaled": 10_000_000_000_000_000_000},
    )
    assert resp.status_code == 400
    assert "int64" in resp.json()["detail"]


def test_native_energy_rate_post_always_bumps_version(client, miner_token, db_session, native_pricing):
    """SD-7 inventory: this endpoint is the only repository writer of the
    native_energy_rates row, and it must bump `version` on every write —
    an observed_at that moves under a fixed version (hub's protected escrow
    snapshots showed exactly that, pinned at 5) cannot come from this path.
    If this test fails, a version-preserving observed_at write exists and
    the out-of-band-writer conclusion no longer holds."""
    _seed_energy(db_session)  # seeds version=1, observed_at pinned
    for expected_version in (2, 3):
        resp = client.post(
            "/v1/market/native-energy/rate",
            headers={"Authorization": f"Bearer {miner_token}"},
            json={"ait_per_eur": "4.0"},
        )
        assert resp.status_code == 200
        assert resp.json()["version"] == expected_version


def test_native_energy_floor_get(client, db_session, native_pricing):
    """Floor read matches the shared pricing arithmetic (165W, 0.30 EUR/kWh, 1.5 AIT/EUR)."""
    _seed_energy(db_session)
    resp = client.get(
        "/v1/market/native-energy/floor",
        params={"resource_id": RESOURCE, "gpu_count": 1, "duration_seconds": 3600},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["rail"] == "native"
    # 0.165 kW * 0.30 EUR/kWh * 1.5 AIT/EUR * 1h = 0.07425 AIT
    assert data["net_floor_units"] == int(Decimal("0.07425") * 36_000_000)
    assert Decimal(data["net_floor_ait"]) == Decimal("0.07425")


def test_native_energy_floor_get_unknown_resource(client, native_pricing):
    resp = client.get(
        "/v1/market/native-energy/floor",
        params={"resource_id": "ghost", "gpu_count": 1, "duration_seconds": 60},
    )
    assert resp.status_code == 404


@pytest.mark.unit
def test_quote_gpu_derives_chain_id_when_native_unset(client, db_session, native_pricing, available_gpu, monkeypatch):
    """NATIVE_CHAIN_ID unset + CHAIN_ID=x → the quote binds x (#307)."""
    from coordinator_api.config import settings

    monkeypatch.setattr(settings, "native_chain_id", "")
    monkeypatch.setenv("CHAIN_ID", "derived-chain")
    _seed_energy(db_session)
    resp = client.post(
        "/v1/market/gpu/quote",
        json={
            "buyer_id": BUYER,
            "gpu_id": available_gpu,
            "duration_hours": 1,
            "gpu_count": 1,
            "settlement_route": "native",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["energy_quote"]["chain_id"] == "derived-chain"


@pytest.mark.unit
def test_quote_gpu_explicit_native_chain_id_wins(client, db_session, native_pricing, available_gpu, monkeypatch):
    """An explicit NATIVE_CHAIN_ID still wins over CHAIN_ID (#307)."""
    from coordinator_api.config import settings

    monkeypatch.setattr(settings, "native_chain_id", "explicit-chain")
    monkeypatch.setenv("CHAIN_ID", "derived-chain")
    _seed_energy(db_session)
    resp = client.post(
        "/v1/market/gpu/quote",
        json={
            "buyer_id": BUYER,
            "gpu_id": available_gpu,
            "duration_hours": 1,
            "gpu_count": 1,
            "settlement_route": "native",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["energy_quote"]["chain_id"] == "explicit-chain"


@pytest.mark.unit
def test_quote_gpu_unconfigured_chain_id_raises_named(client, db_session, native_pricing, available_gpu, monkeypatch, caplog):
    """Neither NATIVE_CHAIN_ID nor CHAIN_ID → loud 500, env var named (#307)."""
    import logging

    from coordinator_api.config import settings

    monkeypatch.setattr(settings, "native_chain_id", "")
    monkeypatch.delenv("CHAIN_ID", raising=False)
    _seed_energy(db_session)
    with caplog.at_level(logging.ERROR):
        resp = client.post(
            "/v1/market/gpu/quote",
            json={
                "buyer_id": BUYER,
                "gpu_id": available_gpu,
                "duration_hours": 1,
                "gpu_count": 1,
                "settlement_route": "native",
            },
        )
    assert resp.status_code == 500
    assert "CHAIN_ID" in caplog.text


@pytest.fixture
def miner_b_token() -> str:
    return create_access_token("miner_B", "miner")


def _booked_gpu(client, token, db_session, client_id: str = "client1") -> str:
    """A registered GPU in 'booked' status with an active booking row."""
    from coordinator_api.contexts.market.domain.gpu_market import GPUBooking

    gpu_id = _register_gpu(client, token)
    gpu = db_session.get(GPURegistry, gpu_id)
    gpu.status = "booked"
    db_session.add(
        GPUBooking(
            gpu_id=gpu_id,
            client_id=client_id,
            duration_hours=1.0,
            total_cost=Decimal("1.0"),
            start_time=datetime.now(UTC),
            status="active",
        )
    )
    db_session.commit()
    return gpu_id


@pytest.mark.unit
def test_register_gpu_ignores_body_miner_id(client, miner_token, db_session):
    """#1074: the body miner_id can no longer register a GPU under someone else."""
    gpu_id = _register_gpu(client, miner_token, miner_id="victim_miner")
    gpu = db_session.get(GPURegistry, gpu_id)
    assert gpu.miner_id == "gpu_miner"


@pytest.mark.unit
def test_sell_gpu_requires_owner(client, miner_token, miner_b_token, available_gpu):
    """#1074: another miner's token cannot reprice the GPU."""
    resp = client.post(
        "/v1/market/gpu/sell",
        headers={"Authorization": f"Bearer {miner_b_token}"},
        json={"seller_id": "miner_B", "gpu_id": available_gpu, "listing_price": "0.0001"},
    )
    assert resp.status_code == 403
    resp = client.post(
        "/v1/market/gpu/sell",
        headers={"Authorization": f"Bearer {miner_token}"},
        json={"seller_id": "gpu_miner", "gpu_id": available_gpu, "listing_price": "0.04"},
    )
    assert resp.status_code == 200


@pytest.mark.unit
def test_release_gpu_requires_owner_or_client(client, miner_token, miner_b_token, db_session):
    """#1074: another miner cannot cancel someone else's active booking."""
    gpu_id = _booked_gpu(client, miner_token, db_session)
    resp = client.post(f"/v1/market/gpu/{gpu_id}/release", headers={"Authorization": f"Bearer {miner_b_token}"})
    assert resp.status_code == 403
    gpu = db_session.get(GPURegistry, gpu_id)
    assert gpu.status == "booked"
    resp = client.post(f"/v1/market/gpu/{gpu_id}/release", headers={"Authorization": f"Bearer {miner_token}"})
    assert resp.status_code == 200


@pytest.mark.unit
def test_confirm_gpu_client_id_must_be_caller(client, miner_token, client_token, db_session):
    """#1074: a booking's client_id can only be set to the caller's own id."""
    gpu_id = _booked_gpu(client, miner_token, db_session, client_id="client1")
    resp = client.post(
        f"/v1/market/gpu/{gpu_id}/confirm",
        headers={"Authorization": f"Bearer {client_token}"},
        json={"client_id": "attacker"},
    )
    assert resp.status_code == 403
    resp = client.post(
        f"/v1/market/gpu/{gpu_id}/confirm",
        headers={"Authorization": f"Bearer {client_token}"},
        json={"client_id": "client1"},
    )
    assert resp.status_code == 200


def test_buy_gpu_rejects_body_buyer_id_mismatch(client, client_token, db_session, native_pricing, available_gpu):
    """#1075 pin: a purchase whose body buyer_id is not the token sub is 403."""
    _seed_energy(db_session)
    resp = client.post(
        "/v1/market/gpu/purchase",
        headers={"Authorization": f"Bearer {client_token}"},
        json={
            "buyer_id": "0x08aB801150eF3496344cFA78fe025c3B48Caf435",
            "gpu_id": available_gpu,
            "duration_hours": 1,
            "payment_method": "blockchain",
        },
    )
    assert resp.status_code == 403
    assert "buyer_id" in resp.text


# --- AGENT-SPEND-D-1: agent_id binding on GPU quote/purchase ---

BUYER_AGENT = "gpu-buyer-agent-1"
PROVIDER_AGENT = "gpu-provider-agent-1"


def _seed_agent_mappings(db_session, user_id: str = "client1") -> None:
    from sqlmodel import select

    from coordinator_api.contexts.agent_identity.domain.agent_identity import AgentIdentity, ChainType, CrossChainMapping
    from coordinator_api.contexts.infrastructure.domain.user import User, Wallet

    if db_session.get(User, user_id) is None:
        db_session.add(User(id=user_id, email=f"{user_id}@example.com", username=user_id))
    if not db_session.exec(select(Wallet).where(Wallet.user_id == user_id)).first():
        db_session.add(Wallet(user_id=user_id, address=BUYER.lower()))
    if db_session.exec(select(AgentIdentity).where(AgentIdentity.agent_id == BUYER_AGENT)).first() is None:
        db_session.add(AgentIdentity(agent_id=BUYER_AGENT, owner_address=BUYER.lower()))
    if db_session.exec(select(AgentIdentity).where(AgentIdentity.agent_id == PROVIDER_AGENT)).first() is None:
        db_session.add(AgentIdentity(agent_id=PROVIDER_AGENT, owner_address=PROVIDER.lower()))
    if not db_session.exec(
        select(CrossChainMapping).where(CrossChainMapping.agent_id == BUYER_AGENT, CrossChainMapping.chain_id == 1)
    ).first():
        db_session.add(
            CrossChainMapping(agent_id=BUYER_AGENT, chain_id=1, chain_type=ChainType.ETHEREUM, chain_address=BUYER.lower())
        )
    if not db_session.exec(
        select(CrossChainMapping).where(CrossChainMapping.agent_id == PROVIDER_AGENT, CrossChainMapping.chain_id == 1)
    ).first():
        db_session.add(
            CrossChainMapping(
                agent_id=PROVIDER_AGENT, chain_id=1, chain_type=ChainType.ETHEREUM, chain_address=PROVIDER.lower()
            )
        )
    db_session.commit()


@pytest.mark.unit
def test_gpu_quote_uses_resolved_buyer_in_energy_quote(
    client, db_session, native_pricing, available_gpu, pricing_engine_override
):
    _seed_energy(db_session)
    _seed_agent_mappings(db_session)
    resp = client.post(
        "/v1/market/gpu/quote",
        json={
            "buyer_id": "client1",
            "buyer_agent_id": BUYER_AGENT,
            "gpu_id": available_gpu,
            "duration_hours": 1.0,
            "gpu_count": 1,
            "settlement_route": "native",
        },
    )
    assert resp.status_code == 200, resp.text
    quote = resp.json()["energy_quote"]
    assert quote["buyer"].lower() == BUYER.lower()


@pytest.mark.unit
def test_gpu_purchase_forwards_agent_ids_to_payment(
    client,
    client_token,
    db_session,
    native_pricing,
    available_gpu,
    pricing_engine_override,
    monkeypatch,
):
    _seed_energy(db_session)
    _seed_agent_mappings(db_session)
    quote_resp = client.post(
        "/v1/market/gpu/quote",
        json={
            "buyer_id": "client1",
            "buyer_agent_id": BUYER_AGENT,
            "gpu_id": available_gpu,
            "duration_hours": 0.05,
            "gpu_count": 1,
            "settlement_route": "native",
        },
    )
    assert quote_resp.status_code == 200
    quote = quote_resp.json()
    captured = {}

    async def fake_create_payment(self, client_id: str, job_id: str, payment_data):
        captured["payment_data"] = payment_data
        return JobPayment(
            id="pay_gpu_agent",
            job_id=job_id,
            amount=payment_data.amount,
            status="escrowed",
            currency="AITBC",
            payment_method="aitbc_token",
        )

    monkeypatch.setattr(PaymentService, "create_payment", fake_create_payment)

    buy_resp = client.post(
        "/v1/market/gpu/purchase",
        headers={"Authorization": f"Bearer {client_token}"},
        json={
            "buyer_id": "client1",
            "gpu_id": available_gpu,
            "duration_hours": 0.05,
            "payment_method": "blockchain",
            "energy_quote": quote["energy_quote"],
            "protected": True,
            "job_id": quote["job_id"],
            "buyer_address": BUYER,
            "provider_address": PROVIDER,
            "buyer_agent_id": BUYER_AGENT,
            "provider_agent_id": PROVIDER_AGENT,
            "buyer_lock_signature": "0xdeadbeef",
            "buyer_lock_nonce": 1,
        },
    )
    assert buy_resp.status_code == 200, buy_resp.text
    pd = captured.get("payment_data")
    assert pd is not None
    assert pd.buyer_agent_id == BUYER_AGENT
    assert pd.provider_agent_id == PROVIDER_AGENT


@pytest.mark.unit
def test_gpu_quote_rejects_mismatching_buyer_address_with_agent_id(
    client, db_session, native_pricing, available_gpu, pricing_engine_override
):
    _seed_energy(db_session)
    _seed_agent_mappings(db_session)
    resp = client.post(
        "/v1/market/gpu/quote",
        json={
            "buyer_id": "0x0000000000000000000000000000000000000001",
            "buyer_agent_id": BUYER_AGENT,
            "gpu_id": available_gpu,
            "duration_hours": 1.0,
            "gpu_count": 1,
            "settlement_route": "native",
        },
    )
    assert resp.status_code == 400
    assert "buyer_id" in resp.text.lower()


@pytest.mark.unit
def test_gpu_purchase_resolves_buyer_address_from_agent_id(
    client,
    client_token,
    db_session,
    native_pricing,
    available_gpu,
    pricing_engine_override,
    monkeypatch,
):
    _seed_energy(db_session)
    _seed_agent_mappings(db_session)
    quote_resp = client.post(
        "/v1/market/gpu/quote",
        json={
            "buyer_id": "client1",
            "buyer_agent_id": BUYER_AGENT,
            "gpu_id": available_gpu,
            "duration_hours": 0.05,
            "gpu_count": 1,
            "settlement_route": "native",
        },
    )
    assert quote_resp.status_code == 200
    quote = quote_resp.json()
    captured = {}

    async def fake_create_payment(self, client_id: str, job_id: str, payment_data):
        captured["payment_data"] = payment_data
        return JobPayment(
            id="pay_gpu_agent2",
            job_id=job_id,
            amount=payment_data.amount,
            status="escrowed",
            currency="AITBC",
            payment_method="aitbc_token",
        )

    monkeypatch.setattr(PaymentService, "create_payment", fake_create_payment)

    buy_resp = client.post(
        "/v1/market/gpu/purchase",
        headers={"Authorization": f"Bearer {client_token}"},
        json={
            "buyer_id": "client1",
            "gpu_id": available_gpu,
            "duration_hours": 0.05,
            "payment_method": "blockchain",
            "energy_quote": quote["energy_quote"],
            "protected": True,
            "job_id": quote["job_id"],
            "provider_address": PROVIDER,
            "buyer_agent_id": BUYER_AGENT,
            "provider_agent_id": PROVIDER_AGENT,
            "buyer_lock_signature": "0xdeadbeef",
            "buyer_lock_nonce": 1,
        },
    )
    assert buy_resp.status_code == 200, buy_resp.text
    pd = captured["payment_data"]
    assert pd.buyer_address.lower() == BUYER.lower()
    assert pd.buyer_agent_id == BUYER_AGENT


# --- CE-004/CE-005: booking squatting expiry + delete_gpu IDOR ---


@pytest.fixture
def admin_token() -> str:
    return create_access_token("admin1", "admin")


@pytest.mark.unit
def test_book_gpu_binds_calling_client(client, client_token, available_gpu, pricing_engine_override, db_session):
    """CE-004: the booking row records who booked it, so they can release it."""
    from coordinator_api.contexts.market.domain.gpu_market import GPUBooking
    from sqlmodel import select

    resp = client.post(
        f"/v1/market/gpu/{available_gpu}/book",
        headers={"Authorization": f"Bearer {client_token}"},
        json={"duration_hours": 1},
    )
    assert resp.status_code == 201, resp.text
    booking = db_session.exec(select(GPUBooking).where(GPUBooking.gpu_id == available_gpu)).one()
    assert booking.client_id == "client1"
    # The booker can now release their own hold.
    rel = client.post(f"/v1/market/gpu/{available_gpu}/release", headers={"Authorization": f"Bearer {client_token}"})
    assert rel.status_code == 200


@pytest.mark.unit
def test_book_gpu_stale_unpaid_hold_expires(
    client, client_token, miner_token, available_gpu, pricing_engine_override, db_session
):
    """CE-004: an unpaid hold older than the TTL frees the GPU for the next booker."""
    from datetime import timedelta

    from coordinator_api.contexts.market.domain.gpu_market import GPUBooking
    from sqlmodel import select

    resp = client.post(
        f"/v1/market/gpu/{available_gpu}/book",
        headers={"Authorization": f"Bearer {client_token}"},
        json={"duration_hours": 1},
    )
    assert resp.status_code == 201, resp.text
    booking = db_session.exec(select(GPUBooking).where(GPUBooking.gpu_id == available_gpu)).one()
    # Fresh hold still blocks a second booking.
    resp2 = client.post(
        f"/v1/market/gpu/{available_gpu}/book",
        headers={"Authorization": f"Bearer {miner_token}"},
        json={"duration_hours": 1},
    )
    assert resp2.status_code == 409
    # Age the hold past the TTL with no payment recorded.
    booking.created_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.add(booking)
    db_session.commit()
    # The next gated access expires it lazily and the GPU is bookable again.
    resp3 = client.post(
        f"/v1/market/gpu/{available_gpu}/book",
        headers={"Authorization": f"Bearer {miner_token}"},
        json={"duration_hours": 1},
    )
    assert resp3.status_code == 201, resp3.text
    db_session.refresh(booking)
    assert booking.status == "expired"
    gpu = db_session.get(GPURegistry, available_gpu)
    assert gpu.status == "booked"  # re-booked by the second caller


def _book_with_job(client, token, gpu_id, job_id=None):
    body = {"duration_hours": 1}
    if job_id is not None:
        body["job_id"] = job_id
    return client.post(
        f"/v1/market/gpu/{gpu_id}/book",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )


@pytest.mark.unit
def test_book_gpu_stale_paid_hold_survives(client, client_token, available_gpu, pricing_engine_override, db_session):
    """CE-004/#1199: a hold whose own job carries a funded payment does not expire.

    Production shape: JobPayment.job_id is the Job.id stored on
    GPUBooking.job_id — never the booking's bk_* primary key.
    """
    from datetime import timedelta

    from coordinator_api.contexts.market.domain.gpu_market import GPUBooking
    from sqlmodel import select

    job = Job(id="job_paid_1", client_id="client1", payload={"type": "gpu_compute"}, constraints={})
    db_session.add(job)
    db_session.commit()
    resp = _book_with_job(client, client_token, available_gpu, job_id=job.id)
    assert resp.status_code == 201, resp.text
    booking = db_session.exec(select(GPUBooking).where(GPUBooking.gpu_id == available_gpu)).one()
    assert booking.job_id == job.id
    booking.created_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.add(booking)
    db_session.add(
        JobPayment(
            id="pay_" + booking.id,
            job_id=job.id,
            amount=Decimal("1.0"),
            status="escrowed",
        )
    )
    db_session.commit()
    # Paid hold: a second booking attempt still conflicts and the hold survives.
    resp2 = _book_with_job(client, client_token, available_gpu)
    assert resp2.status_code == 409
    db_session.refresh(booking)
    assert booking.status == "active"


@pytest.mark.unit
def test_book_gpu_stale_foreign_paid_job_does_not_pin_hold(
    client, client_token, miner_token, available_gpu, pricing_engine_override, db_session
):
    """#1199: a caller-supplied job_id pointing at someone else's paid job
    must not keep this booking alive past the TTL."""
    from datetime import timedelta

    from coordinator_api.contexts.market.domain.gpu_market import GPUBooking
    from sqlmodel import select

    victim_job = Job(id="job_victim_1", client_id="victim_user", payload={"type": "gpu_compute"}, constraints={})
    db_session.add(victim_job)
    db_session.commit()
    resp = _book_with_job(client, client_token, available_gpu, job_id=victim_job.id)
    assert resp.status_code == 201, resp.text
    booking = db_session.exec(select(GPUBooking).where(GPUBooking.gpu_id == available_gpu)).one()
    booking.created_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.add(booking)
    db_session.add(
        JobPayment(
            id="pay_victim_1",
            job_id=victim_job.id,
            amount=Decimal("1.0"),
            status="escrowed",
        )
    )
    db_session.commit()
    # The foreign paid job must not pin the hold: next gated call expires it.
    resp2 = _book_with_job(client, miner_token, available_gpu)
    assert resp2.status_code == 201, resp2.text
    db_session.refresh(booking)
    assert booking.status == "expired"


@pytest.mark.unit
def test_delete_gpu_requires_owner_or_admin(client, miner_token, miner_b_token, admin_token, available_gpu, db_session):
    """CE-005: a non-owner non-admin cannot delete another miner's listing."""
    resp = client.delete(f"/v1/market/gpu/{available_gpu}", headers={"Authorization": f"Bearer {miner_b_token}"})
    assert resp.status_code == 403
    assert db_session.get(GPURegistry, available_gpu) is not None
    resp = client.delete(f"/v1/market/gpu/{available_gpu}", headers={"Authorization": f"Bearer {miner_token}"})
    assert resp.status_code == 200
    assert db_session.get(GPURegistry, available_gpu) is None


@pytest.mark.unit
def test_delete_gpu_force_requires_admin(client, miner_token, admin_token, db_session):
    """CE-005: force-deleting a booked GPU is admin-only, even for the owner."""
    gpu_id = _booked_gpu(client, miner_token, db_session)
    resp = client.delete(f"/v1/market/gpu/{gpu_id}?force=true", headers={"Authorization": f"Bearer {miner_token}"})
    assert resp.status_code == 403
    assert db_session.get(GPURegistry, gpu_id) is not None
    resp = client.delete(f"/v1/market/gpu/{gpu_id}?force=true", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert db_session.get(GPURegistry, gpu_id) is None


@pytest.mark.unit
def test_purchase_sibling_bookings_do_not_share_payment(
    client, client_token, miner_token, db_session, native_pricing, pricing_engine_override, monkeypatch
):
    """#1231: two purchase bookings bound to ONE prepared job_id — the funded
    payment on booking A must not keep unpaid sibling booking B alive past
    the TTL. The paid-check keys on GPUBooking.payment_id, not job_id."""
    from datetime import timedelta

    from coordinator_api.contexts.market.domain.gpu_market import GPUBooking
    from sqlmodel import select

    _seed_energy(db_session)
    gpu_a = _register_gpu(client, miner_token)
    gpu_b = _register_gpu(client, miner_token)

    quote_resp = client.post(
        "/v1/market/gpu/quote",
        headers={"Authorization": f"Bearer {client_token}"},
        json={
            "buyer_id": "client1",
            "gpu_id": gpu_a,
            "duration_hours": 1,
            "gpu_count": 1,
            "settlement_route": "native",
        },
    )
    assert quote_resp.status_code == 200, quote_resp.text
    quote = quote_resp.json()
    job_id = quote["job_id"]

    payments = iter(
        [
            JobPayment(
                id="pay_sib_a",
                job_id=job_id,
                amount=Decimal("1.0"),
                status="escrowed",
                currency="AITBC",
                payment_method="aitbc_token",
            ),
            JobPayment(
                id="pay_sib_b",
                job_id=job_id,
                amount=Decimal("1.0"),
                status="pending",
                currency="AITBC",
                payment_method="aitbc_token",
            ),
        ]
    )

    async def fake_create_payment(self, client_id: str, job_id: str, payment_data) -> JobPayment:
        payment = next(payments)
        # Persist like the real service does — the expiry check reads the
        # job_payments table, not the returned object.
        self.session.add(payment)
        self.session.commit()
        return payment

    monkeypatch.setattr(PaymentService, "create_payment", fake_create_payment)

    for gpu_id in (gpu_a, gpu_b):
        resp = client.post(
            "/v1/market/gpu/purchase",
            headers={"Authorization": f"Bearer {client_token}"},
            json={
                "buyer_id": "client1",
                "gpu_id": gpu_id,
                "duration_hours": 1,
                "payment_method": "blockchain",
                "job_id": job_id,
                "energy_quote": quote["energy_quote"],
                "protected": True,
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "purchased"

    bookings = {b.gpu_id: b for b in db_session.exec(select(GPUBooking).where(GPUBooking.job_id == job_id)).all()}
    assert set(bookings) == {gpu_a, gpu_b}
    assert bookings[gpu_a].payment_id == "pay_sib_a"
    assert bookings[gpu_b].payment_id == "pay_sib_b"

    # Age both holds past the TTL.
    for b in bookings.values():
        b.created_at = datetime.now(UTC) - timedelta(hours=1)
        db_session.add(b)
    db_session.commit()

    # GPU-B's own payment is pending → its hold expires and frees the GPU.
    resp_b = _book_with_job(client, miner_token, gpu_b)
    assert resp_b.status_code == 201, resp_b.text
    db_session.refresh(bookings[gpu_b])
    assert bookings[gpu_b].status == "expired"

    # GPU-A's own payment is escrowed → its hold survives.
    resp_a = _book_with_job(client, miner_token, gpu_a)
    assert resp_a.status_code == 409
    db_session.refresh(bookings[gpu_a])
    assert bookings[gpu_a].status == "active"


@pytest.mark.unit
def test_pricing_endpoint_survives_zero_static_price(client, client_token, miner_token, db_session, pricing_engine_override):
    """#1373: zero-priced listings made avg_price_change_percent divide by
    zero -> unhandled 500 on GET /market/pricing/{model}."""
    from urllib.parse import quote

    _register_gpu(client, miner_token, price_per_hour="0")
    resp = client.get(
        f"/v1/market/pricing/{quote(MODEL)}",
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["price_comparison"]["avg_price_change_percent"] == 0


@pytest.mark.unit
def test_add_gpu_review_binds_authenticated_user(client, client_token, db_session, available_gpu):
    """#1377: review user_id comes from the JWT sub, not a hardcoded placeholder."""
    from coordinator_api.contexts.market.domain.gpu_market import GPUReview

    resp = client.post(
        f"/v1/market/gpu/{available_gpu}/reviews",
        headers={"Authorization": f"Bearer {client_token}"},
        json={"rating": 5, "comment": "fast"},
    )
    assert resp.status_code == 201, resp.text
    review = db_session.query(GPUReview).filter_by(gpu_id=available_gpu).one()
    assert review.user_id == "client1"


@pytest.mark.unit
def test_add_gpu_review_requires_auth(client, db_session, available_gpu):
    """#1377: the review write route must reject unauthenticated callers."""
    resp = client.post(
        f"/v1/market/gpu/{available_gpu}/reviews",
        json={"rating": 4, "comment": "x"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.unit
def test_get_gpu_reviews_respects_limit(client, client_token, available_gpu):
    """#1377: the limit query param was accepted but never applied."""
    for rating in (5, 4, 3):
        resp = client.post(
            f"/v1/market/gpu/{available_gpu}/reviews",
            headers={"Authorization": f"Bearer {client_token}"},
            json={"rating": rating, "comment": f"r{rating}"},
        )
        assert resp.status_code == 201, resp.text
    resp = client.get(f"/v1/market/gpu/{available_gpu}/reviews?limit=2")
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["reviews"]) == 2
