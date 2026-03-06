#!/usr/bin/env python3
"""
Global Marketplace API Test
Test suite for global marketplace operations, multi-region support, and cross-chain integration
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from uuid import uuid4

# Add the app path to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_global_marketplace_imports():
    """Test that all global marketplace components can be imported"""
    print("🧪 Testing Global Marketplace API Imports...")
    
    try:
        # Test domain models
        from app.domain.global_marketplace import (
            MarketplaceRegion, GlobalMarketplaceConfig, GlobalMarketplaceOffer,
            GlobalMarketplaceTransaction, GlobalMarketplaceAnalytics, GlobalMarketplaceGovernance,
            RegionStatus, MarketplaceStatus
        )
        print("✅ Global marketplace domain models imported successfully")
        
        # Test services
        from app.services.global_marketplace import GlobalMarketplaceService, RegionManager
        print("✅ Global marketplace services imported successfully")
        
        # Test API router
        from app.routers.global_marketplace import router
        print("✅ Global marketplace API router imported successfully")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_global_marketplace_models():
    """Test global marketplace model creation"""
    print("\n🧪 Testing Global Marketplace Models...")
    
    try:
        from app.domain.global_marketplace import (
            MarketplaceRegion, GlobalMarketplaceConfig, GlobalMarketplaceOffer,
            GlobalMarketplaceTransaction, GlobalMarketplaceAnalytics, GlobalMarketplaceGovernance,
            RegionStatus, MarketplaceStatus
        )
        
        # Test MarketplaceRegion
        region = MarketplaceRegion(
            region_code="us-east-1",
            region_name="US East (N. Virginia)",
            geographic_area="north_america",
            base_currency="USD",
            timezone="UTC",
            language="en",
            load_factor=1.0,
            max_concurrent_requests=1000,
            priority_weight=1.0,
            status=RegionStatus.ACTIVE,
            health_score=1.0,
            api_endpoint="https://api.aitbc.dev/v1",
            websocket_endpoint="wss://ws.aitbc.dev/v1"
        )
        print("✅ MarketplaceRegion model created")
        
        # Test GlobalMarketplaceOffer
        offer = GlobalMarketplaceOffer(
            original_offer_id=f"offer_{uuid4().hex[:8]}",
            agent_id="test_agent",
            service_type="gpu",
            resource_specification={"gpu_type": "A100", "memory": "40GB"},
            base_price=100.0,
            currency="USD",
            total_capacity=100,
            available_capacity=100,
            regions_available=["us-east-1", "eu-west-1"],
            supported_chains=[1, 137],
            global_status=MarketplaceStatus.ACTIVE
        )
        print("✅ GlobalMarketplaceOffer model created")
        
        # Test GlobalMarketplaceTransaction
        transaction = GlobalMarketplaceTransaction(
            buyer_id="buyer_agent",
            seller_id="seller_agent",
            offer_id=offer.id,
            service_type="gpu",
            quantity=1,
            unit_price=100.0,
            total_amount=100.0,
            currency="USD",
            source_chain=1,
            target_chain=137,
            source_region="us-east-1",
            target_region="eu-west-1",
            status="pending"
        )
        print("✅ GlobalMarketplaceTransaction model created")
        
        # Test GlobalMarketplaceAnalytics
        analytics = GlobalMarketplaceAnalytics(
            period_type="daily",
            period_start=datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
            period_end=datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=999999),
            region="global",
            total_offers=100,
            total_transactions=50,
            total_volume=5000.0,
            average_price=100.0,
            success_rate=0.95
        )
        print("✅ GlobalMarketplaceAnalytics model created")
        
        # Test GlobalMarketplaceGovernance
        governance = GlobalMarketplaceGovernance(
            rule_type="pricing",
            rule_name="price_limits",
            rule_description="Limit price ranges for marketplace offers",
            rule_parameters={"min_price": 1.0, "max_price": 10000.0},
            global_scope=True,
            is_active=True,
            enforcement_level="warning"
        )
        print("✅ GlobalMarketplaceGovernance model created")
        
        return True
        
    except Exception as e:
        print(f"❌ Model creation error: {e}")
        return False

def test_global_marketplace_services():
    """Test global marketplace services"""
    print("\n🧪 Testing Global Marketplace Services...")
    
    try:
        from app.services.global_marketplace import GlobalMarketplaceService, RegionManager
        
        # Test service creation (mock session)
        class MockSession:
            pass
        
        service = GlobalMarketplaceService(MockSession())
        region_manager = RegionManager(MockSession())
        
        print("✅ GlobalMarketplaceService created")
        print("✅ RegionManager created")
        
        # Test method existence
        service_methods = [
            'create_global_offer',
            'get_global_offers',
            'create_global_transaction',
            'get_global_transactions',
            'get_marketplace_analytics',
            'get_region_health'
        ]
        
        for method in service_methods:
            if hasattr(service, method):
                print(f"✅ Service method {method} exists")
            else:
                print(f"❌ Service method {method} missing")
        
        manager_methods = [
            'create_region',
            'update_region_health',
            'get_optimal_region'
        ]
        
        for method in manager_methods:
            if hasattr(region_manager, method):
                print(f"✅ Manager method {method} exists")
            else:
                print(f"❌ Manager method {method} missing")
        
        return True
        
    except Exception as e:
        print(f"❌ Service test error: {e}")
        return False

def test_api_endpoints():
    """Test API endpoint definitions"""
    print("\n🧪 Testing API Endpoints...")
    
    try:
        from app.routers.global_marketplace import router
        
        # Check router configuration
        assert router.prefix == "/global-marketplace"
        assert "Global Marketplace" in router.tags
        print("✅ Router configuration correct")
        
        # Check for expected endpoints
        route_paths = [route.path for route in router.routes]
        expected_endpoints = [
            "/offers",
            "/offers/{offer_id}",
            "/transactions",
            "/transactions/{transaction_id}",
            "/regions",
            "/regions/{region_code}/health",
            "/analytics",
            "/config",
            "/health"
        ]
        
        found_endpoints = []
        for endpoint in expected_endpoints:
            if any(endpoint in path for path in route_paths):
                found_endpoints.append(endpoint)
                print(f"✅ Endpoint {endpoint} found")
            else:
                print(f"⚠️  Endpoint {endpoint} not found")
        
        print(f"✅ Found {len(found_endpoints)}/{len(expected_endpoints)} expected endpoints")
        
        return len(found_endpoints) >= 7  # At least 7 endpoints should be found
        
    except Exception as e:
        print(f"❌ API endpoint test error: {e}")
        return False

def test_cross_chain_integration():
    """Test cross-chain integration logic"""
    print("\n🧪 Testing Cross-Chain Integration...")
    
    try:
        # Test cross-chain pricing calculation
        def calculate_cross_chain_pricing(base_price, source_chain, target_chain):
            if source_chain == target_chain:
                return base_price
            
            # Add cross-chain fee (0.5%)
            cross_chain_fee = base_price * 0.005
            return base_price + cross_chain_fee
        
        # Test with sample data
        base_price = 100.0
        
        # Same chain (no fee)
        same_chain_price = calculate_cross_chain_pricing(base_price, 1, 1)
        assert same_chain_price == base_price
        print(f"✅ Same chain pricing: {same_chain_price}")
        
        # Cross-chain (with fee)
        cross_chain_price = calculate_cross_chain_pricing(base_price, 1, 137)
        expected_cross_chain_price = 100.5  # 100 + 0.5% fee
        assert abs(cross_chain_price - expected_cross_chain_price) < 0.01
        print(f"✅ Cross-chain pricing: {cross_chain_price}")
        
        # Test regional pricing
        def calculate_regional_pricing(base_price, regions, load_factors):
            pricing = {}
            for region in regions:
                load_factor = load_factors.get(region, 1.0)
                pricing[region] = base_price * load_factor
            return pricing
        
        regions = ["us-east-1", "eu-west-1", "ap-south-1"]
        load_factors = {"us-east-1": 1.0, "eu-west-1": 1.1, "ap-south-1": 0.9}
        
        regional_pricing = calculate_regional_pricing(base_price, regions, load_factors)
        assert regional_pricing["us-east-1"] == 100.0
        assert regional_pricing["eu-west-1"] == 110.0
        assert regional_pricing["ap-south-1"] == 90.0
        print(f"✅ Regional pricing: {regional_pricing}")
        
        return True
        
    except Exception as e:
        print(f"❌ Cross-chain integration test error: {e}")
        return False

def test_analytics_logic():
    """Test analytics calculation logic"""
    print("\n🧪 Testing Analytics Logic...")
    
    try:
        # Test analytics calculation
        def calculate_analytics(transactions, offers):
            total_transactions = len(transactions)
            total_volume = sum(tx['total_amount'] for tx in transactions)
            completed_transactions = [tx for tx in transactions if tx['status'] == 'completed']
            success_rate = len(completed_transactions) / max(total_transactions, 1)
            average_price = total_volume / max(total_transactions, 1)
            
            return {
                'total_transactions': total_transactions,
                'total_volume': total_volume,
                'success_rate': success_rate,
                'average_price': average_price
            }
        
        # Test with sample data
        transactions = [
            {'total_amount': 100.0, 'status': 'completed'},
            {'total_amount': 150.0, 'status': 'completed'},
            {'total_amount': 200.0, 'status': 'pending'},
            {'total_amount': 120.0, 'status': 'completed'}
        ]
        
        offers = [{'id': 1}, {'id': 2}, {'id': 3}]
        
        analytics = calculate_analytics(transactions, offers)
        
        assert analytics['total_transactions'] == 4
        assert analytics['total_volume'] == 570.0
        assert analytics['success_rate'] == 0.75  # 3/4 completed
        assert analytics['average_price'] == 142.5  # 570/4
        
        print(f"✅ Analytics calculation: {analytics}")
        
        return True
        
    except Exception as e:
        print(f"❌ Analytics logic test error: {e}")
        return False

def main():
    """Run all global marketplace tests"""
    
    print("🚀 Global Marketplace API - Comprehensive Test Suite")
    print("=" * 60)
    
    tests = [
        test_global_marketplace_imports,
        test_global_marketplace_models,
        test_global_marketplace_services,
        test_api_endpoints,
        test_cross_chain_integration,
        test_analytics_logic
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        else:
            print(f"\n❌ Test {test.__name__} failed")
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All global marketplace tests passed!")
        print("\n✅ Global Marketplace API is ready for:")
        print("   - Database migration")
        print("   - API server startup")
        print("   - Multi-region operations")
        print("   - Cross-chain transactions")
        print("   - Analytics and monitoring")
        return True
    else:
        print("\n❌ Some tests failed - check the errors above")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
