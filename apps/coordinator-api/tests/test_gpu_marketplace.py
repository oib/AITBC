"""
Tests for persistent GPU marketplace (SQLModel-backed GPURegistry, GPUBooking, GPUReview).

Uses an in-memory SQLite database via FastAPI TestClient.

The coordinator 'app' package collides with other 'app' packages on
sys.path when tests from multiple apps are collected together.  To work
around this, we force the coordinator src onto sys.path *first* and
flush any stale 'app' entries from sys.modules before importing.
"""

import sys
from pathlib import Path

_COORD_SRC = str(Path(__file__).resolve().parent.parent / "src")

# Flush any previously-cached 'app' package that doesn't belong to the
# coordinator so our imports resolve to the correct source tree.
_existing = sys.modules.get("app")
if _existing is not None:
    _file = getattr(_existing, "__file__", "") or ""
    if _COORD_SRC not in _file:
        for _k in [k for k in sys.modules if k == "app" or k.startswith("app.")]:
            del sys.modules[_k]

# Ensure coordinator src is the *first* entry so 'app' resolves here.
if _COORD_SRC in sys.path:
    sys.path.remove(_COORD_SRC)
sys.path.insert(0, _COORD_SRC)

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.domain.gpu_marketplace import GPURegistry, GPUBooking, GPUReview  # noqa: E402
from app.routers.marketplace_gpu import router  # noqa: E402
from app.storage import get_session  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(name="client")
def client_fixture(session: Session):
    app = FastAPI()
    app.include_router(router, prefix="/v1")

    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


def _register_gpu(client, **overrides):
    """Helper to register a GPU and return the response dict."""
    gpu = {
        "miner_id": "miner_001",
        "name": "RTX 4090",
        "memory": 24,
        "cuda_version": "12.0",
        "region": "us-west",
        "price_per_hour": 0.50,
        "capabilities": ["llama2-7b", "stable-diffusion-xl"],
    }
    gpu.update(overrides)
    resp = client.post("/v1/marketplace/gpu/register", json={"gpu": gpu})
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests: Register
# ---------------------------------------------------------------------------

class TestGPURegister:
    def test_register_gpu(self, client):
        data = _register_gpu(client)
        assert data["status"] == "registered"
        assert "gpu_id" in data

    def test_register_persists(self, client, session):
        data = _register_gpu(client)
        gpu = session.get(GPURegistry, data["gpu_id"])
        assert gpu is not None
        assert gpu.model == "RTX 4090"
        assert gpu.memory_gb == 24
        assert gpu.status == "available"


# ---------------------------------------------------------------------------
# Tests: List
# ---------------------------------------------------------------------------

class TestGPUList:
    def test_list_empty(self, client):
        resp = client.get("/v1/marketplace/gpu/list")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_registered(self, client):
        _register_gpu(client)
        _register_gpu(client, name="RTX 3080", memory=16, price_per_hour=0.35)
        resp = client.get("/v1/marketplace/gpu/list")
        assert len(resp.json()) == 2

    def test_filter_available(self, client, session):
        data = _register_gpu(client)
        # Mark one as booked
        gpu = session.get(GPURegistry, data["gpu_id"])
        gpu.status = "booked"
        session.commit()
        _register_gpu(client, name="RTX 3080")

        resp = client.get("/v1/marketplace/gpu/list", params={"available": True})
        results = resp.json()
        assert len(results) == 1
        assert results[0]["model"] == "RTX 3080"

    def test_filter_price_max(self, client):
        _register_gpu(client, price_per_hour=0.50)
        _register_gpu(client, name="A100", price_per_hour=1.20)
        resp = client.get("/v1/marketplace/gpu/list", params={"price_max": 0.60})
        assert len(resp.json()) == 1

    def test_filter_region(self, client):
        _register_gpu(client, region="us-west")
        _register_gpu(client, name="A100", region="eu-west")
        resp = client.get("/v1/marketplace/gpu/list", params={"region": "eu-west"})
        assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# Tests: Details
# ---------------------------------------------------------------------------

class TestGPUDetails:
    def test_get_details(self, client):
        data = _register_gpu(client)
        resp = client.get(f"/v1/marketplace/gpu/{data['gpu_id']}")
        assert resp.status_code == 200
        assert resp.json()["model"] == "RTX 4090"

    def test_get_details_not_found(self, client):
        resp = client.get("/v1/marketplace/gpu/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: Book
# ---------------------------------------------------------------------------

class TestGPUBook:
    def test_book_gpu(self, client, session):
        data = _register_gpu(client)
        gpu_id = data["gpu_id"]
        resp = client.post(
            f"/v1/marketplace/gpu/{gpu_id}/book",
            json={"duration_hours": 2.0},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "booked"
        assert body["total_cost"] == 1.0  # 2h * $0.50

        # GPU status updated in DB
        session.expire_all()
        gpu = session.get(GPURegistry, gpu_id)
        assert gpu.status == "booked"

    def test_book_already_booked_returns_409(self, client):
        data = _register_gpu(client)
        gpu_id = data["gpu_id"]
        client.post(f"/v1/marketplace/gpu/{gpu_id}/book", json={"duration_hours": 1})
        resp = client.post(f"/v1/marketplace/gpu/{gpu_id}/book", json={"duration_hours": 1})
        assert resp.status_code == 409

    def test_book_not_found(self, client):
        resp = client.post("/v1/marketplace/gpu/nope/book", json={"duration_hours": 1})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: Release
# ---------------------------------------------------------------------------

class TestGPURelease:
    def test_release_booked_gpu(self, client, session):
        data = _register_gpu(client)
        gpu_id = data["gpu_id"]
        client.post(f"/v1/marketplace/gpu/{gpu_id}/book", json={"duration_hours": 2})
        resp = client.post(f"/v1/marketplace/gpu/{gpu_id}/release")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "released"
        assert body["refund"] == 0.5  # 50% of $1.0

        session.expire_all()
        gpu = session.get(GPURegistry, gpu_id)
        assert gpu.status == "available"

    def test_release_not_booked_returns_400(self, client):
        data = _register_gpu(client)
        resp = client.post(f"/v1/marketplace/gpu/{data['gpu_id']}/release")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Tests: Reviews
# ---------------------------------------------------------------------------

class TestGPUReviews:
    def test_add_review(self, client):
        data = _register_gpu(client)
        gpu_id = data["gpu_id"]
        resp = client.post(
            f"/v1/marketplace/gpu/{gpu_id}/reviews",
            json={"rating": 5, "comment": "Excellent!"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "review_added"
        assert body["average_rating"] == 5.0

    def test_get_reviews(self, client):
        data = _register_gpu(client, name="Review Test GPU")
        gpu_id = data["gpu_id"]
        client.post(f"/v1/marketplace/gpu/{gpu_id}/reviews", json={"rating": 5, "comment": "Great"})
        client.post(f"/v1/marketplace/gpu/{gpu_id}/reviews", json={"rating": 3, "comment": "OK"})

        resp = client.get(f"/v1/marketplace/gpu/{gpu_id}/reviews")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_reviews"] == 2
        assert len(body["reviews"]) == 2

    def test_review_not_found_gpu(self, client):
        resp = client.post(
            "/v1/marketplace/gpu/nope/reviews",
            json={"rating": 5, "comment": "test"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: Orders
# ---------------------------------------------------------------------------

class TestOrders:
    def test_list_orders_empty(self, client):
        resp = client.get("/v1/marketplace/orders")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_orders_after_booking(self, client):
        data = _register_gpu(client)
        client.post(f"/v1/marketplace/gpu/{data['gpu_id']}/book", json={"duration_hours": 3})
        resp = client.get("/v1/marketplace/orders")
        orders = resp.json()
        assert len(orders) == 1
        assert orders[0]["gpu_model"] == "RTX 4090"
        assert orders[0]["status"] == "active"

    def test_filter_orders_by_status(self, client):
        data = _register_gpu(client)
        gpu_id = data["gpu_id"]
        client.post(f"/v1/marketplace/gpu/{gpu_id}/book", json={"duration_hours": 1})
        client.post(f"/v1/marketplace/gpu/{gpu_id}/release")

        resp = client.get("/v1/marketplace/orders", params={"status": "cancelled"})
        assert len(resp.json()) == 1
        resp = client.get("/v1/marketplace/orders", params={"status": "active"})
        assert len(resp.json()) == 0


# ---------------------------------------------------------------------------
# Tests: Pricing
# ---------------------------------------------------------------------------

class TestPricing:
    def test_pricing_for_model(self, client):
        _register_gpu(client, price_per_hour=0.50, capabilities=["llama2-7b"])
        _register_gpu(client, name="A100", price_per_hour=1.20, capabilities=["llama2-7b", "gpt-4"])

        resp = client.get("/v1/marketplace/pricing/llama2-7b")
        assert resp.status_code == 200
        body = resp.json()
        assert body["min_price"] == 0.50
        assert body["max_price"] == 1.20
        assert body["total_gpus"] == 2

    def test_pricing_not_found(self, client):
        resp = client.get("/v1/marketplace/pricing/nonexistent-model")
        assert resp.status_code == 404
