"""Unit tests for agent marketplace service"""

import pytest
import sys
from pathlib import Path

# Add app src to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "apps" / "marketplace"))

from agent_marketplace import app, GPUOffering, DealRequest, DealConfirmation, MinerRegistration


@pytest.mark.unit
def test_app_initialization():
    """Test that the FastAPI app initializes correctly"""
    assert app is not None
    assert app.title == "AITBC Agent-First GPU Marketplace"
    assert app.version == "1.0.0"


@pytest.mark.unit
def test_gpu_offering_model():
    """Test GPUOffering model"""
    offering = GPUOffering(
        miner_id="miner_123",
        gpu_model="RTX 4090",
        gpu_memory=24576,
        cuda_cores=16384,
        price_per_hour=0.50,
        available_hours=24,
        chains=["ait-devnet", "ait-testnet"],
        capabilities=["inference", "training"]
    )
    assert offering.miner_id == "miner_123"
    assert offering.gpu_model == "RTX 4090"
    assert offering.gpu_memory == 24576
    assert offering.price_per_hour == 0.50
    assert offering.chains == ["ait-devnet", "ait-testnet"]


@pytest.mark.unit
def test_gpu_offering_defaults():
    """Test GPUOffering with default values"""
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
    assert offering.min_rental_hours == 1
    assert offering.max_concurrent_jobs == 1


@pytest.mark.unit
def test_deal_request_model():
    """Test DealRequest model"""
    request = DealRequest(
        offering_id="offering_123",
        buyer_id="buyer_123",
        rental_hours=10,
        chain="ait-devnet",
        special_requirements="Need for high performance"
    )
    assert request.offering_id == "offering_123"
    assert request.buyer_id == "buyer_123"
    assert request.rental_hours == 10
    assert request.chain == "ait-devnet"


@pytest.mark.unit
def test_deal_request_without_special_requirements():
    """Test DealRequest without special requirements"""
    request = DealRequest(
        offering_id="offering_123",
        buyer_id="buyer_123",
        rental_hours=10,
        chain="ait-devnet"
    )
    assert request.special_requirements is None


@pytest.mark.unit
def test_deal_confirmation_model():
    """Test DealConfirmation model"""
    confirmation = DealConfirmation(
        deal_id="deal_123",
        miner_confirmation=True,
        chain="ait-devnet"
    )
    assert confirmation.deal_id == "deal_123"
    assert confirmation.miner_confirmation is True
    assert confirmation.chain == "ait-devnet"


@pytest.mark.unit
def test_deal_confirmation_rejection():
    """Test DealConfirmation with rejection"""
    confirmation = DealConfirmation(
        deal_id="deal_123",
        miner_confirmation=False,
        chain="ait-devnet"
    )
    assert confirmation.miner_confirmation is False


@pytest.mark.unit
def test_miner_registration_model():
    """Test MinerRegistration model"""
    registration = MinerRegistration(
        miner_id="miner_123",
        wallet_address="0x1234567890abcdef",
        preferred_chains=["ait-devnet", "ait-testnet"],
        gpu_specs={"model": "RTX 4090", "memory": 24576}
    )
    assert registration.miner_id == "miner_123"
    assert registration.wallet_address == "0x1234567890abcdef"
    assert registration.preferred_chains == ["ait-devnet", "ait-testnet"]


@pytest.mark.unit
def test_miner_registration_defaults():
    """Test MinerRegistration with default pricing model"""
    registration = MinerRegistration(
        miner_id="miner_123",
        wallet_address="0x1234567890abcdef",
        preferred_chains=["ait-devnet"],
        gpu_specs={"model": "RTX 4090"}
    )
    assert registration.pricing_model == "hourly"


@pytest.mark.unit
def test_gpu_offering_negative_price():
    """Test GPUOffering with negative price"""
    offering = GPUOffering(
        miner_id="miner_123",
        gpu_model="RTX 4090",
        gpu_memory=24576,
        cuda_cores=16384,
        price_per_hour=-0.50,
        available_hours=24,
        chains=["ait-devnet"],
        capabilities=["inference"]
    )
    assert offering.price_per_hour == -0.50


@pytest.mark.unit
def test_gpu_offering_zero_hours():
    """Test GPUOffering with zero available hours"""
    offering = GPUOffering(
        miner_id="miner_123",
        gpu_model="RTX 4090",
        gpu_memory=24576,
        cuda_cores=16384,
        price_per_hour=0.50,
        available_hours=0,
        chains=["ait-devnet"],
        capabilities=["inference"]
    )
    assert offering.available_hours == 0


@pytest.mark.unit
def test_deal_request_negative_hours():
    """Test DealRequest with negative rental hours"""
    request = DealRequest(
        offering_id="offering_123",
        buyer_id="buyer_123",
        rental_hours=-10,
        chain="ait-devnet"
    )
    assert request.rental_hours == -10
