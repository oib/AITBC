"""
Test for global chain marketplace system
"""

import asyncio
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from aitbc_cli.core.config import MultiChainConfig
from aitbc_cli.core.marketplace import (
    GlobalChainMarketplace, ChainListing, ChainType, MarketplaceStatus,
    MarketplaceTransaction, TransactionStatus, ChainEconomy, MarketplaceMetrics
)

def test_marketplace_creation():
    """Test marketplace system creation"""
    config = MultiChainConfig()
    marketplace = GlobalChainMarketplace(config)
    
    assert marketplace.config == config
    assert marketplace.listings == {}
    assert marketplace.transactions == {}
    assert marketplace.chain_economies == {}
    assert marketplace.user_reputations == {}
    assert marketplace.market_metrics is None

async def test_create_listing():
    """Test chain listing creation"""
    config = MultiChainConfig()
    marketplace = GlobalChainMarketplace(config)
    
    # Set up user reputation
    marketplace.user_reputations["seller-1"] = 0.8
    
    # Create listing
    listing_id = await marketplace.create_listing(
        chain_id="healthcare-chain-001",
        chain_name="Healthcare Analytics Chain",
        chain_type=ChainType.TOPIC,
        description="Advanced healthcare data analytics chain",
        seller_id="seller-1",
        price=Decimal("1.5"),
        currency="ETH",
        chain_specifications={"consensus": "pos", "block_time": 5},
        metadata={"category": "healthcare", "compliance": "hipaa"}
    )
    
    assert listing_id is not None
    assert listing_id in marketplace.listings
    
    listing = marketplace.listings[listing_id]
    assert listing.chain_id == "healthcare-chain-001"
    assert listing.chain_name == "Healthcare Analytics Chain"
    assert listing.chain_type == ChainType.TOPIC
    assert listing.price == Decimal("1.5")
    assert listing.status == MarketplaceStatus.ACTIVE

async def test_purchase_chain():
    """Test chain purchase"""
    config = MultiChainConfig()
    marketplace = GlobalChainMarketplace(config)
    
    # Set up user reputations
    marketplace.user_reputations["seller-1"] = 0.8
    marketplace.user_reputations["buyer-1"] = 0.7
    
    # Create listing
    listing_id = await marketplace.create_listing(
        chain_id="trading-chain-001",
        chain_name="Trading Analytics Chain",
        chain_type=ChainType.PRIVATE,
        description="Private trading analytics chain",
        seller_id="seller-1",
        price=Decimal("2.0"),
        currency="ETH",
        chain_specifications={"consensus": "pos"},
        metadata={"category": "trading"}
    )
    
    # Purchase chain
    transaction_id = await marketplace.purchase_chain(listing_id, "buyer-1", "crypto")
    
    assert transaction_id is not None
    assert transaction_id in marketplace.transactions
    
    transaction = marketplace.transactions[transaction_id]
    assert transaction.buyer_id == "buyer-1"
    assert transaction.seller_id == "seller-1"
    assert transaction.price == Decimal("2.0")
    assert transaction.status == TransactionStatus.PENDING
    
    # Check listing status
    listing = marketplace.listings[listing_id]
    assert listing.status == MarketplaceStatus.SOLD

async def test_complete_transaction():
    """Test transaction completion"""
    config = MultiChainConfig()
    marketplace = GlobalChainMarketplace(config)
    
    # Set up user reputations
    marketplace.user_reputations["seller-1"] = 0.8
    marketplace.user_reputations["buyer-1"] = 0.7
    
    # Create listing and purchase
    listing_id = await marketplace.create_listing(
        chain_id="research-chain-001",
        chain_name="Research Collaboration Chain",
        chain_type=ChainType.RESEARCH,
        description="Research collaboration chain",
        seller_id="seller-1",
        price=Decimal("0.5"),
        currency="ETH",
        chain_specifications={"consensus": "pos"},
        metadata={"category": "research"}
    )
    
    transaction_id = await marketplace.purchase_chain(listing_id, "buyer-1", "crypto")
    
    # Complete transaction
    success = await marketplace.complete_transaction(transaction_id, "0x1234567890abcdef")
    
    assert success
    
    transaction = marketplace.transactions[transaction_id]
    assert transaction.status == TransactionStatus.COMPLETED
    assert transaction.transaction_hash == "0x1234567890abcdef"
    assert transaction.completed_at is not None
    
    # Check escrow release
    escrow_contract = marketplace.escrow_contracts.get(transaction.escrow_address)
    assert escrow_contract is not None
    assert escrow_contract["status"] == "released"

async def test_chain_economy():
    """Test chain economy tracking"""
    config = MultiChainConfig()
    marketplace = GlobalChainMarketplace(config)
    
    # Get chain economy (should create new one)
    economy = await marketplace.get_chain_economy("test-chain-001")
    
    assert economy is not None
    assert economy.chain_id == "test-chain-001"
    assert isinstance(economy.total_value_locked, Decimal)
    assert isinstance(economy.daily_volume, Decimal)
    assert economy.transaction_count >= 0
    assert economy.last_updated is not None

async def test_search_listings():
    """Test listing search functionality"""
    config = MultiChainConfig()
    marketplace = GlobalChainMarketplace(config)
    
    # Set up user reputation
    marketplace.user_reputations["seller-1"] = 0.8
    
    # Create multiple listings
    listings = [
        ("healthcare-chain-001", "Healthcare Chain", ChainType.TOPIC, Decimal("1.0")),
        ("trading-chain-001", "Trading Chain", ChainType.PRIVATE, Decimal("2.0")),
        ("research-chain-001", "Research Chain", ChainType.RESEARCH, Decimal("0.5")),
        ("enterprise-chain-001", "Enterprise Chain", ChainType.ENTERPRISE, Decimal("5.0"))
    ]
    
    listing_ids = []
    for chain_id, name, chain_type, price in listings:
        listing_id = await marketplace.create_listing(
            chain_id=chain_id,
            chain_name=name,
            chain_type=chain_type,
            description=f"Description for {name}",
            seller_id="seller-1",
            price=price,
            currency="ETH",
            chain_specifications={},
            metadata={}
        )
        listing_ids.append(listing_id)
    
    # Search by chain type
    topic_listings = await marketplace.search_listings(chain_type=ChainType.TOPIC)
    assert len(topic_listings) == 1
    assert topic_listings[0].chain_type == ChainType.TOPIC
    
    # Search by price range
    price_listings = await marketplace.search_listings(min_price=Decimal("1.0"), max_price=Decimal("2.0"))
    assert len(price_listings) == 2
    
    # Search by seller
    seller_listings = await marketplace.search_listings(seller_id="seller-1")
    assert len(seller_listings) == 4

async def test_user_transactions():
    """Test user transaction retrieval"""
    config = MultiChainConfig()
    marketplace = GlobalChainMarketplace(config)
    
    # Set up user reputations
    marketplace.user_reputations["seller-1"] = 0.8
    marketplace.user_reputations["buyer-1"] = 0.7
    marketplace.user_reputations["buyer-2"] = 0.6
    
    # Create listings and purchases
    listing_id1 = await marketplace.create_listing(
        chain_id="chain-001",
        chain_name="Chain 1",
        chain_type=ChainType.TOPIC,
        description="Description",
        seller_id="seller-1",
        price=Decimal("1.0"),
        currency="ETH",
        chain_specifications={},
        metadata={}
    )
    
    listing_id2 = await marketplace.create_listing(
        chain_id="chain-002",
        chain_name="Chain 2",
        chain_type=ChainType.PRIVATE,
        description="Description",
        seller_id="seller-1",
        price=Decimal("2.0"),
        currency="ETH",
        chain_specifications={},
        metadata={}
    )
    
    transaction_id1 = await marketplace.purchase_chain(listing_id1, "buyer-1", "crypto")
    transaction_id2 = await marketplace.purchase_chain(listing_id2, "buyer-2", "crypto")
    
    # Get seller transactions
    seller_transactions = await marketplace.get_user_transactions("seller-1", "seller")
    assert len(seller_transactions) == 2
    
    # Get buyer transactions
    buyer_transactions = await marketplace.get_user_transactions("buyer-1", "buyer")
    assert len(buyer_transactions) == 1
    assert buyer_transactions[0].buyer_id == "buyer-1"
    
    # Get all user transactions
    all_transactions = await marketplace.get_user_transactions("seller-1", "both")
    assert len(all_transactions) == 2

async def test_marketplace_overview():
    """Test marketplace overview"""
    config = MultiChainConfig()
    marketplace = GlobalChainMarketplace(config)
    
    # Set up user reputations
    marketplace.user_reputations["seller-1"] = 0.8
    marketplace.user_reputations["buyer-1"] = 0.7
    
    # Create listings and transactions
    listing_id = await marketplace.create_listing(
        chain_id="overview-chain-001",
        chain_name="Overview Test Chain",
        chain_type=ChainType.TOPIC,
        description="Test chain for overview",
        seller_id="seller-1",
        price=Decimal("1.5"),
        currency="ETH",
        chain_specifications={},
        metadata={}
    )
    
    transaction_id = await marketplace.purchase_chain(listing_id, "buyer-1", "crypto")
    await marketplace.complete_transaction(transaction_id, "0x1234567890abcdef")
    
    # Get marketplace overview
    overview = await marketplace.get_marketplace_overview()
    
    assert overview is not None
    assert "marketplace_metrics" in overview
    assert "volume_24h" in overview
    assert "top_performing_chains" in overview
    assert "chain_types_distribution" in overview
    assert "user_activity" in overview
    assert "escrow_summary" in overview
    
    # Check marketplace metrics
    metrics = overview["marketplace_metrics"]
    assert metrics["total_listings"] == 1
    assert metrics["total_transactions"] == 1
    assert metrics["total_volume"] == Decimal("1.5")

def test_validation_functions():
    """Test validation functions"""
    config = MultiChainConfig()
    marketplace = GlobalChainMarketplace(config)
    
    # Test user reputation update
    marketplace._update_user_reputation("user-1", 0.1)
    print(f"After +0.1: {marketplace.user_reputations['user-1']}")
    assert marketplace.user_reputations["user-1"] == 0.6  # Started at 0.5
    
    marketplace._update_user_reputation("user-1", -0.2)
    print(f"After -0.2: {marketplace.user_reputations['user-1']}")
    assert abs(marketplace.user_reputations["user-1"] - 0.4) < 0.0001  # Allow for floating point precision
    
    # Test bounds
    marketplace._update_user_reputation("user-1", 0.6)  # Add 0.6 to reach 1.0
    print(f"After +0.6: {marketplace.user_reputations['user-1']}")
    assert marketplace.user_reputations["user-1"] == 1.0  # Max bound
    
    marketplace._update_user_reputation("user-1", -1.5)  # Subtract 1.5 to go below 0
    print(f"After -1.5: {marketplace.user_reputations['user-1']}")
    assert marketplace.user_reputations["user-1"] == 0.0  # Min bound

async def test_escrow_system():
    """Test escrow contract system"""
    config = MultiChainConfig()
    marketplace = GlobalChainMarketplace(config)
    
    # Set up user reputations
    marketplace.user_reputations["seller-1"] = 0.8
    marketplace.user_reputations["buyer-1"] = 0.7
    
    # Create listing and purchase
    listing_id = await marketplace.create_listing(
        chain_id="escrow-test-chain",
        chain_name="Escrow Test Chain",
        chain_type=ChainType.TOPIC,
        description="Test escrow functionality",
        seller_id="seller-1",
        price=Decimal("3.0"),
        currency="ETH",
        chain_specifications={},
        metadata={}
    )
    
    transaction_id = await marketplace.purchase_chain(listing_id, "buyer-1", "crypto")
    
    # Check escrow creation
    transaction = marketplace.transactions[transaction_id]
    escrow_address = transaction.escrow_address
    assert escrow_address in marketplace.escrow_contracts
    
    escrow_contract = marketplace.escrow_contracts[escrow_address]
    assert escrow_contract["status"] == "active"
    assert escrow_contract["amount"] == Decimal("3.0")
    assert escrow_contract["buyer_id"] == "buyer-1"
    assert escrow_contract["seller_id"] == "seller-1"
    
    # Complete transaction and check escrow release
    await marketplace.complete_transaction(transaction_id, "0xabcdef1234567890")
    
    escrow_contract = marketplace.escrow_contracts[escrow_address]
    assert escrow_contract["status"] == "released"
    assert "fee_breakdown" in escrow_contract
    
    fee_breakdown = escrow_contract["fee_breakdown"]
    assert fee_breakdown["escrow_fee"] == Decimal("0.06")  # 2% of 3.0
    assert fee_breakdown["marketplace_fee"] == Decimal("0.03")  # 1% of 3.0
    assert fee_breakdown["seller_amount"] == Decimal("2.91")  # 3.0 - 0.06 - 0.03

if __name__ == "__main__":
    # Run basic tests
    test_marketplace_creation()
    test_validation_functions()
    
    # Run async tests
    asyncio.run(test_create_listing())
    asyncio.run(test_purchase_chain())
    asyncio.run(test_complete_transaction())
    asyncio.run(test_chain_economy())
    asyncio.run(test_search_listings())
    asyncio.run(test_user_transactions())
    asyncio.run(test_marketplace_overview())
    asyncio.run(test_escrow_system())
    
    print("✅ All marketplace tests passed!")
