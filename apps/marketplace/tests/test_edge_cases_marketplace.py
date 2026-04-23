"""Edge case and error handling tests for agent marketplace service"""

import pytest
import sys
import sys
from pathlib import Path
from fastapi.testclient import TestClient


from agent_marketplace import app, GPUOffering, DealRequest, DealConfirmation, MinerRegistration, gpu_offerings, marketplace_deals, miner_registrations, chain_offerings


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test"""
    gpu_offerings.clear()
    marketplace_deals.clear()
    miner_registrations.clear()
    chain_offerings.clear()
    yield
    gpu_offerings.clear()
    marketplace_deals.clear()
    miner_registrations.clear()
    chain_offerings.clear()


@pytest.mark.unit
def test_gpu_offering_empty_chains():
    """Test GPUOffering with empty chains"""
    offering = GPUOffering(
        miner_id="miner_123",
        gpu_model="RTX 4090",
        gpu_memory=24576,
        cuda_cores=16384,
        price_per_hour=0.50,
        available_hours=24,
        chains=[],
        capabilities=["inference"]
    )
    assert offering.chains == []


@pytest.mark.unit
def test_gpu_offering_empty_capabilities():
    """Test GPUOffering with empty capabilities"""
    offering = GPUOffering(
        miner_id="miner_123",
        gpu_model="RTX 4090",
        gpu_memory=24576,
        cuda_cores=16384,
        price_per_hour=0.50,
        available_hours=24,
        chains=["ait-devnet"],
        capabilities=[]
    )
    assert offering.capabilities == []


@pytest.mark.unit
def test_miner_registration_empty_chains():
    """Test MinerRegistration with empty preferred chains"""
    registration = MinerRegistration(
        miner_id="miner_123",
        wallet_address="0x1234567890abcdef",
        preferred_chains=[],
        gpu_specs={"model": "RTX 4090"}
    )
    assert registration.preferred_chains == []


@pytest.mark.unit
def test_deal_request_empty_offering_id():
    """Test DealRequest with empty offering_id"""
    request = DealRequest(
        offering_id="",
        buyer_id="buyer_123",
        rental_hours=10,
        chain="ait-devnet"
    )
    assert request.offering_id == ""


@pytest.mark.unit
def test_deal_confirmation_empty_deal_id():
    """Test DealConfirmation with empty deal_id"""
    confirmation = DealConfirmation(
        deal_id="",
        miner_confirmation=True,
        chain="ait-devnet"
    )
    assert confirmation.deal_id == ""


@pytest.mark.integration
def test_get_gpu_offerings_empty():
    """Test getting GPU offerings when none exist"""
    client = TestClient(app)
    response = client.get("/api/v1/offerings")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 0


@pytest.mark.integration
def test_get_deals_empty():
    """Test getting deals when none exist"""
    client = TestClient(app)
    response = client.get("/api/v1/deals")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 0


@pytest.mark.integration
def test_get_miner_offerings_no_offerings():
    """Test getting offerings for miner with no offerings"""
    client = TestClient(app)
    response = client.get("/api/v1/miners/miner_123/offerings")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 0


@pytest.mark.integration
def test_get_chain_offerings_no_offerings():
    """Test getting chain offerings when none exist"""
    client = TestClient(app)
    response = client.get("/api/v1/chains/ait-devnet/offerings")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 0


@pytest.mark.integration
def test_request_deal_offering_not_available():
    """Test requesting deal for unavailable offering"""
    client = TestClient(app)
    # Create an offering
    offering = GPUOffering(
        miner_id="miner_123",
        gpu_model="RTX 4090",
        gpu_memory=24576,
        cuda_cores=16384,
        price_per_hour=0.50,
        available_hours=24,
        chains=["ait-devnet"],
        capabilities=["inference"]
    )
    create_response = client.post("/api/v1/offerings/create", json=offering.model_dump())
    offering_id = create_response.json()["offering_id"]
    
    # Mark as occupied
    gpu_offerings[offering_id]["status"] = "occupied"
    
    deal_request = DealRequest(
        offering_id=offering_id,
        buyer_id="buyer_123",
        rental_hours=10,
        chain="ait-devnet"
    )
    response = client.post("/api/v1/deals/request", json=deal_request.model_dump())
    assert response.status_code == 400


@pytest.mark.integration
def test_confirm_deal_already_confirmed():
    """Test confirming a deal that's already confirmed"""
    client = TestClient(app)
    # Create offering and request deal
    offering = GPUOffering(
        miner_id="miner_123",
        gpu_model="RTX 4090",
        gpu_memory=24576,
        cuda_cores=16384,
        price_per_hour=0.50,
        available_hours=24,
        chains=["ait-devnet"],
        capabilities=["inference"]
    )
    create_response = client.post("/api/v1/offerings/create", json=offering.model_dump())
    offering_id = create_response.json()["offering_id"]
    
    deal_request = DealRequest(
        offering_id=offering_id,
        buyer_id="buyer_123",
        rental_hours=10,
        chain="ait-devnet"
    )
    deal_response = client.post("/api/v1/deals/request", json=deal_request.model_dump())
    deal_id = deal_response.json()["deal_id"]
    
    # Confirm the deal
    confirmation = DealConfirmation(
        deal_id=deal_id,
        miner_confirmation=True,
        chain="ait-devnet"
    )
    client.post(f"/api/v1/deals/{deal_id}/confirm", json=confirmation.model_dump())
    
    # Try to confirm again
    response = client.post(f"/api/v1/deals/{deal_id}/confirm", json=confirmation.model_dump())
    assert response.status_code == 400


@pytest.mark.integration
def test_confirm_deal_chain_mismatch():
    """Test confirming deal with wrong chain"""
    client = TestClient(app)
    # Create offering and request deal
    offering = GPUOffering(
        miner_id="miner_123",
        gpu_model="RTX 4090",
        gpu_memory=24576,
        cuda_cores=16384,
        price_per_hour=0.50,
        available_hours=24,
        chains=["ait-devnet"],
        capabilities=["inference"]
    )
    create_response = client.post("/api/v1/offerings/create", json=offering.model_dump())
    offering_id = create_response.json()["offering_id"]
    
    deal_request = DealRequest(
        offering_id=offering_id,
        buyer_id="buyer_123",
        rental_hours=10,
        chain="ait-devnet"
    )
    deal_response = client.post("/api/v1/deals/request", json=deal_request.model_dump())
    deal_id = deal_response.json()["deal_id"]
    
    # Confirm with wrong chain
    confirmation = DealConfirmation(
        deal_id=deal_id,
        miner_confirmation=True,
        chain="ait-testnet"
    )
    response = client.post(f"/api/v1/deals/{deal_id}/confirm", json=confirmation.model_dump())
    assert response.status_code == 400


@pytest.mark.integration
def test_get_marketplace_stats_empty():
    """Test getting marketplace stats with no data"""
    client = TestClient(app)
    response = client.get("/api/v1/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_offerings"] == 0
    assert data["active_deals"] == 0
