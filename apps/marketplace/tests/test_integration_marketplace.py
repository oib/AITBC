"""Integration tests for agent marketplace service"""

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


@pytest.mark.integration
def test_health_check():
    """Test health check endpoint"""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "supported_chains" in data


@pytest.mark.integration
def test_get_supported_chains():
    """Test getting supported chains"""
    client = TestClient(app)
    response = client.get("/api/v1/chains")
    assert response.status_code == 200
    data = response.json()
    assert "chains" in data


@pytest.mark.integration
def test_register_miner():
    """Test registering a miner"""
    client = TestClient(app)
    registration = MinerRegistration(
        miner_id="miner_123",
        wallet_address="0x1234567890abcdef",
        preferred_chains=["ait-devnet"],
        gpu_specs={"model": "RTX 4090"}
    )
    response = client.post("/api/v1/miners/register", json=registration.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["miner_id"] == "miner_123"


@pytest.mark.integration
def test_register_miner_update_existing():
    """Test updating existing miner registration"""
    client = TestClient(app)
    registration = MinerRegistration(
        miner_id="miner_123",
        wallet_address="0x1234567890abcdef",
        preferred_chains=["ait-devnet"],
        gpu_specs={"model": "RTX 4090"}
    )
    client.post("/api/v1/miners/register", json=registration.model_dump())
    
    # Update with new data
    registration.wallet_address = "0xabcdef1234567890"
    response = client.post("/api/v1/miners/register", json=registration.model_dump())
    assert response.status_code == 200


@pytest.mark.integration
def test_create_gpu_offering():
    """Test creating a GPU offering"""
    client = TestClient(app)
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
    response = client.post("/api/v1/offerings/create", json=offering.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "offering_id" in data


@pytest.mark.integration
def test_create_gpu_offering_invalid_chain():
    """Test creating GPU offering with invalid chain"""
    client = TestClient(app)
    offering = GPUOffering(
        miner_id="miner_123",
        gpu_model="RTX 4090",
        gpu_memory=24576,
        cuda_cores=16384,
        price_per_hour=0.50,
        available_hours=24,
        chains=["invalid-chain"],
        capabilities=["inference"]
    )
    response = client.post("/api/v1/offerings/create", json=offering.model_dump())
    assert response.status_code == 400


@pytest.mark.integration
def test_get_gpu_offerings():
    """Test getting GPU offerings"""
    client = TestClient(app)
    # Create an offering first
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
    client.post("/api/v1/offerings/create", json=offering.model_dump())
    
    response = client.get("/api/v1/offerings")
    assert response.status_code == 200
    data = response.json()
    assert "offerings" in data


@pytest.mark.integration
def test_get_gpu_offerings_with_filters():
    """Test getting GPU offerings with filters"""
    client = TestClient(app)
    # Create offerings
    offering1 = GPUOffering(
        miner_id="miner_123",
        gpu_model="RTX 4090",
        gpu_memory=24576,
        cuda_cores=16384,
        price_per_hour=0.50,
        available_hours=24,
        chains=["ait-devnet"],
        capabilities=["inference"]
    )
    offering2 = GPUOffering(
        miner_id="miner_456",
        gpu_model="RTX 3080",
        gpu_memory=10240,
        cuda_cores=8704,
        price_per_hour=0.30,
        available_hours=24,
        chains=["ait-testnet"],
        capabilities=["inference"]
    )
    client.post("/api/v1/offerings/create", json=offering1.model_dump())
    client.post("/api/v1/offerings/create", json=offering2.model_dump())
    
    response = client.get("/api/v1/offerings?chain=ait-devnet&gpu_model=RTX")
    assert response.status_code == 200


@pytest.mark.integration
def test_get_gpu_offering():
    """Test getting specific GPU offering"""
    client = TestClient(app)
    # Create an offering first
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
    
    response = client.get(f"/api/v1/offerings/{offering_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["offering_id"] == offering_id


@pytest.mark.integration
def test_get_gpu_offering_not_found():
    """Test getting nonexistent GPU offering"""
    client = TestClient(app)
    response = client.get("/api/v1/offerings/nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_request_deal():
    """Test requesting a deal"""
    client = TestClient(app)
    # Create an offering first
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
    response = client.post("/api/v1/deals/request", json=deal_request.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "deal_id" in data


@pytest.mark.integration
def test_request_deal_offering_not_found():
    """Test requesting deal for nonexistent offering"""
    client = TestClient(app)
    deal_request = DealRequest(
        offering_id="nonexistent",
        buyer_id="buyer_123",
        rental_hours=10,
        chain="ait-devnet"
    )
    response = client.post("/api/v1/deals/request", json=deal_request.model_dump())
    assert response.status_code == 404


@pytest.mark.integration
def test_request_deal_chain_not_supported():
    """Test requesting deal with unsupported chain"""
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
    
    deal_request = DealRequest(
        offering_id=offering_id,
        buyer_id="buyer_123",
        rental_hours=10,
        chain="ait-testnet"
    )
    response = client.post("/api/v1/deals/request", json=deal_request.model_dump())
    assert response.status_code == 400


@pytest.mark.integration
def test_confirm_deal():
    """Test confirming a deal"""
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
    
    confirmation = DealConfirmation(
        deal_id=deal_id,
        miner_confirmation=True,
        chain="ait-devnet"
    )
    response = client.post(f"/api/v1/deals/{deal_id}/confirm", json=confirmation.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "confirmed"


@pytest.mark.integration
def test_confirm_deal_reject():
    """Test rejecting a deal"""
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
    
    confirmation = DealConfirmation(
        deal_id=deal_id,
        miner_confirmation=False,
        chain="ait-devnet"
    )
    response = client.post(f"/api/v1/deals/{deal_id}/confirm", json=confirmation.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"


@pytest.mark.integration
def test_confirm_deal_not_found():
    """Test confirming nonexistent deal"""
    client = TestClient(app)
    confirmation = DealConfirmation(
        deal_id="nonexistent",
        miner_confirmation=True,
        chain="ait-devnet"
    )
    response = client.post("/api/v1/deals/nonexistent/confirm", json=confirmation.model_dump())
    assert response.status_code == 404


@pytest.mark.integration
def test_get_deals():
    """Test getting deals"""
    client = TestClient(app)
    response = client.get("/api/v1/deals")
    assert response.status_code == 200
    data = response.json()
    assert "deals" in data


@pytest.mark.integration
def test_get_deals_with_filters():
    """Test getting deals with filters"""
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
    client.post("/api/v1/deals/request", json=deal_request.model_dump())
    
    response = client.get("/api/v1/deals?miner_id=miner_123")
    assert response.status_code == 200


@pytest.mark.integration
def test_get_miner_offerings():
    """Test getting offerings for a specific miner"""
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
    client.post("/api/v1/offerings/create", json=offering.model_dump())
    
    response = client.get("/api/v1/miners/miner_123/offerings")
    assert response.status_code == 200
    data = response.json()
    assert data["miner_id"] == "miner_123"


@pytest.mark.integration
def test_get_chain_offerings():
    """Test getting offerings for a specific chain"""
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
    client.post("/api/v1/offerings/create", json=offering.model_dump())
    
    response = client.get("/api/v1/chains/ait-devnet/offerings")
    assert response.status_code == 200
    data = response.json()
    assert data["chain"] == "ait-devnet"


@pytest.mark.integration
def test_get_chain_offerings_unsupported_chain():
    """Test getting offerings for unsupported chain"""
    client = TestClient(app)
    response = client.get("/api/v1/chains/unsupported-chain/offerings")
    assert response.status_code == 400


@pytest.mark.integration
def test_remove_offering():
    """Test removing a GPU offering"""
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
    
    response = client.delete(f"/api/v1/offerings/{offering_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


@pytest.mark.integration
def test_remove_offering_not_found():
    """Test removing nonexistent offering"""
    client = TestClient(app)
    response = client.delete("/api/v1/offerings/nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_get_marketplace_stats():
    """Test getting marketplace statistics"""
    client = TestClient(app)
    response = client.get("/api/v1/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_offerings" in data
    assert "chain_stats" in data
