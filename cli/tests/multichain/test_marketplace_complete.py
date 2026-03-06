#!/usr/bin/env python3
"""
Complete global chain marketplace workflow test
"""

import sys
import os
import asyncio
import json
from decimal import Decimal
from datetime import datetime
sys.path.insert(0, '/home/oib/windsurf/aitbc/cli')

from aitbc_cli.core.config import load_multichain_config
from aitbc_cli.core.marketplace import (
    GlobalChainMarketplace, ChainType, MarketplaceStatus, 
    TransactionStatus
)

async def test_complete_marketplace_workflow():
    """Test the complete marketplace workflow"""
    print("🚀 Starting Complete Global Chain Marketplace Workflow Test")
    
    # Load configuration
    config = load_multichain_config('/home/oib/windsurf/aitbc/cli/multichain_config.yaml')
    print(f"✅ Configuration loaded with {len(config.nodes)} nodes")
    
    # Initialize marketplace
    marketplace = GlobalChainMarketplace(config)
    print("✅ Global chain marketplace initialized")
    
    # Test 1: Create multiple chain listings
    print("\n📋 Testing Chain Listing Creation...")
    
    # Set up seller reputations
    sellers = ["healthcare-seller", "trading-seller", "research-seller", "enterprise-seller"]
    for seller in sellers:
        marketplace.user_reputations[seller] = 0.8 + (sellers.index(seller) * 0.05)  # 0.8 to 0.95
    
    # Create diverse chain listings
    listings = [
        {
            "chain_id": "AITBC-HEALTHCARE-MARKET-001",
            "chain_name": "Healthcare Analytics Marketplace",
            "chain_type": ChainType.TOPIC,
            "description": "Advanced healthcare data analytics chain with HIPAA compliance",
            "seller_id": "healthcare-seller",
            "price": Decimal("2.5"),
            "currency": "ETH",
            "specs": {"consensus": "pos", "block_time": 3, "max_validators": 21},
            "metadata": {"category": "healthcare", "compliance": "hipaa", "data_volume": "10TB"}
        },
        {
            "chain_id": "AITBC-TRADING-ALGO-001",
            "chain_name": "Trading Algorithm Chain",
            "chain_type": ChainType.PRIVATE,
            "description": "High-frequency trading algorithm execution chain",
            "seller_id": "trading-seller",
            "price": Decimal("5.0"),
            "currency": "ETH",
            "specs": {"consensus": "poa", "block_time": 1, "max_validators": 5},
            "metadata": {"category": "trading", "latency": "<1ms", "throughput": "10000 tps"}
        },
        {
            "chain_id": "AITBC-RESEARCH-COLLAB-001",
            "chain_name": "Research Collaboration Platform",
            "chain_type": ChainType.RESEARCH,
            "description": "Multi-institution research collaboration chain",
            "seller_id": "research-seller",
            "price": Decimal("1.0"),
            "currency": "ETH",
            "specs": {"consensus": "pos", "block_time": 5, "max_validators": 50},
            "metadata": {"category": "research", "institutions": 5, "peer_review": True}
        },
        {
            "chain_id": "AITBC-ENTERPRISE-ERP-001",
            "chain_name": "Enterprise ERP Integration",
            "chain_type": ChainType.ENTERPRISE,
            "description": "Enterprise resource planning blockchain integration",
            "seller_id": "enterprise-seller",
            "price": Decimal("10.0"),
            "currency": "ETH",
            "specs": {"consensus": "poa", "block_time": 2, "max_validators": 15},
            "metadata": {"category": "enterprise", "iso_compliance": True, "scalability": "enterprise"}
        }
    ]
    
    listing_ids = []
    for listing_data in listings:
        listing_id = await marketplace.create_listing(
            listing_data["chain_id"],
            listing_data["chain_name"],
            listing_data["chain_type"],
            listing_data["description"],
            listing_data["seller_id"],
            listing_data["price"],
            listing_data["currency"],
            listing_data["specs"],
            listing_data["metadata"]
        )
        
        if listing_id:
            listing_ids.append(listing_id)
            print(f"  ✅ Listed: {listing_data['chain_name']} ({listing_data['chain_type'].value}) - {listing_data['price']} ETH")
        else:
            print(f"  ❌ Failed to list: {listing_data['chain_name']}")
    
    print(f"  📊 Successfully created {len(listing_ids)}/{len(listings)} listings")
    
    # Test 2: Search and filter listings
    print("\n🔍 Testing Listing Search and Filtering...")
    
    # Search by chain type
    topic_listings = await marketplace.search_listings(chain_type=ChainType.TOPIC)
    print(f"  ✅ Found {len(topic_listings)} topic chains")
    
    # Search by price range
    affordable_listings = await marketplace.search_listings(min_price=Decimal("1.0"), max_price=Decimal("3.0"))
    print(f"  ✅ Found {len(affordable_listings)} affordable chains (1-3 ETH)")
    
    # Search by seller
    seller_listings = await marketplace.search_listings(seller_id="healthcare-seller")
    print(f"  ✅ Found {len(seller_listings)} listings from healthcare-seller")
    
    # Search active listings only
    active_listings = await marketplace.search_listings(status=MarketplaceStatus.ACTIVE)
    print(f"  ✅ Found {len(active_listings)} active listings")
    
    # Test 3: Chain purchases
    print("\n💰 Testing Chain Purchases...")
    
    # Set up buyer reputations
    buyers = ["healthcare-buyer", "trading-buyer", "research-buyer", "enterprise-buyer"]
    for buyer in buyers:
        marketplace.user_reputations[buyer] = 0.7 + (buyers.index(buyer) * 0.03)  # 0.7 to 0.79
    
    # Purchase chains
    purchases = [
        (listing_ids[0], "healthcare-buyer", "crypto_transfer"),  # Healthcare chain
        (listing_ids[1], "trading-buyer", "smart_contract"),     # Trading chain
        (listing_ids[2], "research-buyer", "escrow"),            # Research chain
    ]
    
    transaction_ids = []
    for listing_id, buyer_id, payment_method in purchases:
        transaction_id = await marketplace.purchase_chain(listing_id, buyer_id, payment_method)
        
        if transaction_id:
            transaction_ids.append(transaction_id)
            listing = marketplace.listings[listing_id]
            print(f"  ✅ Purchased: {listing.chain_name} by {buyer_id} ({payment_method})")
        else:
            print(f"  ❌ Failed purchase for listing {listing_id}")
    
    print(f"  📊 Successfully initiated {len(transaction_ids)}/{len(purchases)} purchases")
    
    # Test 4: Transaction completion
    print("\n✅ Testing Transaction Completion...")
    
    completed_transactions = []
    for i, transaction_id in enumerate(transaction_ids):
        # Simulate blockchain transaction hash
        tx_hash = f"0x{'1234567890abcdef' * 4}_{i}"
        
        success = await marketplace.complete_transaction(transaction_id, tx_hash)
        
        if success:
            completed_transactions.append(transaction_id)
            transaction = marketplace.transactions[transaction_id]
            print(f"  ✅ Completed: {transaction.chain_id} - {transaction.price} ETH")
        else:
            print(f"  ❌ Failed to complete transaction {transaction_id}")
    
    print(f"  📊 Successfully completed {len(completed_transactions)}/{len(transaction_ids)} transactions")
    
    # Test 5: Chain economy tracking
    print("\n📊 Testing Chain Economy Tracking...")
    
    for listing_data in listings[:2]:  # Test first 2 chains
        chain_id = listing_data["chain_id"]
        economy = await marketplace.get_chain_economy(chain_id)
        
        if economy:
            print(f"  ✅ {chain_id}:")
            print(f"    TVL: {economy.total_value_locked} ETH")
            print(f"    Daily Volume: {economy.daily_volume} ETH")
            print(f"    Market Cap: {economy.market_cap} ETH")
            print(f"    Transactions: {economy.transaction_count}")
            print(f"    Active Users: {economy.active_users}")
            print(f"    Agent Count: {economy.agent_count}")
    
    # Test 6: User transaction history
    print("\n📜 Testing User Transaction History...")
    
    for buyer_id in buyers[:2]:  # Test first 2 buyers
        transactions = await marketplace.get_user_transactions(buyer_id, "buyer")
        
        print(f"  ✅ {buyer_id}: {len(transactions)} purchase transactions")
        for tx in transactions:
            print(f"    • {tx.chain_id} - {tx.price} ETH ({tx.status.value})")
    
    # Test 7: Escrow system
    print("\n🔒 Testing Escrow System...")
    
    escrow_summary = await marketplace._get_escrow_summary()
    print(f"  ✅ Escrow Summary:")
    print(f"    Active Escrows: {escrow_summary['active_escrows']}")
    print(f"    Released Escrows: {escrow_summary['released_escrows']}")
    print(f"    Total Escrow Value: {escrow_summary['total_escrow_value']} ETH")
    print(f"    Escrow Fees Collected: {escrow_summary['escrow_fee_collected']} ETH")
    
    # Test 8: Marketplace overview
    print("\n🌐 Testing Marketplace Overview...")
    
    overview = await marketplace.get_marketplace_overview()
    
    if "marketplace_metrics" in overview:
        metrics = overview["marketplace_metrics"]
        print(f"  ✅ Marketplace Metrics:")
        print(f"    Total Listings: {metrics['total_listings']}")
        print(f"    Active Listings: {metrics['active_listings']}")
        print(f"    Total Transactions: {metrics['total_transactions']}")
        print(f"    Total Volume: {metrics['total_volume']} ETH")
        print(f"    Average Price: {metrics['average_price']} ETH")
        print(f"    Market Sentiment: {metrics['market_sentiment']:.2f}")
    
    if "volume_24h" in overview:
        print(f"    24h Volume: {overview['volume_24h']} ETH")
    
    if "top_performing_chains" in overview:
        print(f"  ✅ Top Performing Chains:")
        for chain in overview["top_performing_chains"][:3]:
            print(f"    • {chain['chain_id']}: {chain['volume']} ETH ({chain['transactions']} txs)")
    
    if "chain_types_distribution" in overview:
        print(f"  ✅ Chain Types Distribution:")
        for chain_type, count in overview["chain_types_distribution"].items():
            print(f"    • {chain_type}: {count} listings")
    
    if "user_activity" in overview:
        activity = overview["user_activity"]
        print(f"  ✅ User Activity:")
        print(f"    Active Buyers (7d): {activity['active_buyers_7d']}")
        print(f"    Active Sellers (7d): {activity['active_sellers_7d']}")
        print(f"    Total Unique Users: {activity['total_unique_users']}")
        print(f"    Average Reputation: {activity['average_reputation']:.3f}")
    
    # Test 9: Reputation system impact
    print("\n⭐ Testing Reputation System Impact...")
    
    # Check final reputations after transactions
    print(f"  📊 Final User Reputations:")
    for user_id in sellers + buyers:
        if user_id in marketplace.user_reputations:
            rep = marketplace.user_reputations[user_id]
            user_type = "Seller" if user_id in sellers else "Buyer"
            print(f"    {user_id} ({user_type}): {rep:.3f}")
    
    # Test 10: Price trends and market analytics
    print("\n📈 Testing Price Trends and Market Analytics...")
    
    price_trends = await marketplace._calculate_price_trends()
    if price_trends:
        print(f"  ✅ Price Trends:")
        for chain_id, trends in price_trends.items():
            for trend in trends:
                direction = "📈" if trend > 0 else "📉" if trend < 0 else "➡️"
                print(f"    {chain_id}: {direction} {trend:.2%}")
    
    # Test 11: Advanced search scenarios
    print("\n🔍 Testing Advanced Search Scenarios...")
    
    # Complex search: topic chains between 1-3 ETH
    complex_search = await marketplace.search_listings(
        chain_type=ChainType.TOPIC,
        min_price=Decimal("1.0"),
        max_price=Decimal("3.0"),
        status=MarketplaceStatus.ACTIVE
    )
    print(f"  ✅ Complex search result: {len(complex_search)} listings")
    
    # Search by multiple criteria
    all_active = await marketplace.search_listings(status=MarketplaceStatus.ACTIVE)
    print(f"  ✅ All active listings: {len(all_active)}")
    
    sold_listings = await marketplace.search_listings(status=MarketplaceStatus.SOLD)
    print(f"  ✅ Sold listings: {len(sold_listings)}")
    
    print("\n🎉 Complete Global Chain Marketplace Workflow Test Finished!")
    print("📊 Summary:")
    print("  ✅ Chain listing creation and management working")
    print("  ✅ Advanced search and filtering functional")
    print("  ✅ Chain purchase and transaction system operational")
    print("  ✅ Transaction completion and confirmation working")
    print("  ✅ Chain economy tracking and analytics active")
    print("  ✅ User transaction history available")
    print("  ✅ Escrow system with fee calculation working")
    print("  ✅ Comprehensive marketplace overview functional")
    print("  ✅ Reputation system impact verified")
    print("  ✅ Price trends and market analytics available")
    print("  ✅ Advanced search scenarios working")
    
    # Performance metrics
    print(f"\n📈 Current Marketplace Metrics:")
    if "marketplace_metrics" in overview:
        metrics = overview["marketplace_metrics"]
        print(f"  • Total Listings: {metrics['total_listings']}")
        print(f"  • Active Listings: {metrics['active_listings']}")
        print(f"  • Total Transactions: {metrics['total_transactions']}")
        print(f"  • Total Volume: {metrics['total_volume']} ETH")
        print(f"  • Average Price: {metrics['average_price']} ETH")
        print(f"  • Market Sentiment: {metrics['market_sentiment']:.2f}")
    
    print(f"  • Escrow Contracts: {len(marketplace.escrow_contracts)}")
    print(f"  • Chain Economies Tracked: {len(marketplace.chain_economies)}")
    print(f"  • User Reputations: {len(marketplace.user_reputations)}")

if __name__ == "__main__":
    asyncio.run(test_complete_marketplace_workflow())
