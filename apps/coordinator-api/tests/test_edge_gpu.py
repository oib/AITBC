import os
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

os.environ["DATABASE_URL"] = "sqlite:///./data/test_edge_gpu.db"
os.makedirs("data", exist_ok=True)

from app.main import app  # noqa: E402
from app.storage import db  # noqa: E402
from app.storage.db import get_session  # noqa: E402
from app.domain.gpu_marketplace import (
    GPURegistry,
    GPUArchitecture,
    ConsumerGPUProfile,
    EdgeGPUMetrics,
)  # noqa: E402


TEST_DB_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/test_edge_gpu.db")
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
SQLModel.metadata.create_all(engine)


def override_get_session() -> Generator[Session, None, None]:
    db._engine = engine  # ensure storage uses this engine
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_session] = override_get_session
# Create client after overrides and table creation
client = TestClient(app)


def test_profiles_seed_and_filter():
    resp = client.get("/v1/marketplace/edge-gpu/profiles")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 3

    resp_filter = client.get(
        "/v1/marketplace/edge-gpu/profiles",
        params={"architecture": GPUArchitecture.ADA_LOVELACE.value},
    )
    assert resp_filter.status_code == 200
    filtered = resp_filter.json()
    assert all(item["architecture"] == GPUArchitecture.ADA_LOVELACE.value for item in filtered)


def test_metrics_ingest_and_list():
    # create gpu registry entry
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        existing = session.get(GPURegistry, "gpu_test")
        if existing:
            session.delete(existing)
            session.commit()

        gpu = GPURegistry(
            id="gpu_test",
            miner_id="miner-1",
            model="RTX 4090",
            memory_gb=24,
            cuda_version="12.0",
            region="us-east",
            price_per_hour=1.5,
            capabilities=["tensor", "cuda"],
        )
        session.add(gpu)
        session.commit()

    payload = {
        "gpu_id": "gpu_test",
        "network_latency_ms": 10.5,
        "compute_latency_ms": 20.1,
        "total_latency_ms": 30.6,
        "gpu_utilization_percent": 75.0,
        "memory_utilization_percent": 65.0,
        "power_draw_w": 200.0,
        "temperature_celsius": 68.0,
        "thermal_throttling_active": False,
        "power_limit_active": False,
        "clock_throttling_active": False,
        "region": "us-east",
        "city": "nyc",
        "isp": "test-isp",
        "connection_type": "ethernet",
    }

    resp = client.post("/v1/marketplace/edge-gpu/metrics", json=payload)
    assert resp.status_code == 200, resp.text
    created = resp.json()
    assert created["gpu_id"] == "gpu_test"

    list_resp = client.get(f"/v1/marketplace/edge-gpu/metrics/{payload['gpu_id']}")
    assert list_resp.status_code == 200
    metrics = list_resp.json()
    assert len(metrics) >= 1
    assert metrics[0]["gpu_id"] == "gpu_test"
