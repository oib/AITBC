#!/usr/bin/env python3
"""
Simple test to verify Agent Identity SDK basic functionality
"""

import asyncio
import sys
import os

# Add the app path to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_imports():
    """Test that all modules can be imported"""
    print("🧪 Testing imports...")
    
    try:
        # Test domain models
        from app.domain.agent_identity import (
            AgentIdentity, CrossChainMapping, IdentityVerification, AgentWallet,
            IdentityStatus, VerificationType, ChainType
        )
        print("✅ Domain models imported successfully")
        
        # Test core components
        from app.agent_identity.core import AgentIdentityCore
        from app.agent_identity.registry import CrossChainRegistry
        from app.agent_identity.wallet_adapter import MultiChainWalletAdapter
        from app.agent_identity.manager import AgentIdentityManager
        print("✅ Core components imported successfully")
        
        # Test SDK components
        from app.agent_identity.sdk.client import AgentIdentityClient
        from app.agent_identity.sdk.models import (
            AgentIdentity as SDKAgentIdentity, 
            CrossChainMapping as SDKCrossChainMapping,
            AgentWallet as SDKAgentWallet,
            IdentityStatus as SDKIdentityStatus,
            VerificationType as SDKVerificationType,
            ChainType as SDKChainType
        )
        from app.agent_identity.sdk.exceptions import (
            AgentIdentityError,
            ValidationError,
            NetworkError
        )
        print("✅ SDK components imported successfully")
        
        # Test API router
        from app.routers.agent_identity import router
        print("✅ API router imported successfully")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_models():
    """Test that models can be instantiated"""
    print("\n🧪 Testing model instantiation...")
    
    try:
        from app.domain.agent_identity import (
            AgentIdentity, CrossChainMapping, AgentWallet,
            IdentityStatus, VerificationType, ChainType
        )
        from datetime import datetime
        
        # Test AgentIdentity
        identity = AgentIdentity(
            id="test_identity",
            agent_id="test_agent",
            owner_address="0x1234567890123456789012345678901234567890",
            display_name="Test Agent",
            description="A test agent",
            status=IdentityStatus.ACTIVE,
            verification_level=VerificationType.BASIC,
            is_verified=False,
            supported_chains=["1", "137"],
            primary_chain=1,
            reputation_score=0.0,
            total_transactions=0,
            successful_transactions=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            identity_data={'key': 'value'}
        )
        print("✅ AgentIdentity model created")
        
        # Test CrossChainMapping
        mapping = CrossChainMapping(
            id="test_mapping",
            agent_id="test_agent",
            chain_id=1,
            chain_type=ChainType.ETHEREUM,
            chain_address="0x1234567890123456789012345678901234567890",
            is_verified=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        print("✅ CrossChainMapping model created")
        
        # Test AgentWallet
        wallet = AgentWallet(
            id="test_wallet",
            agent_id="test_agent",
            chain_id=1,
            chain_address="0x1234567890123456789012345678901234567890",
            wallet_type="agent-wallet",
            balance=0.0,
            spending_limit=0.0,
            total_spent=0.0,
            is_active=True,
            permissions=[],
            requires_multisig=False,
            multisig_threshold=1,
            multisig_signers=[],
            transaction_count=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        print("✅ AgentWallet model created")
        
        return True
        
    except Exception as e:
        print(f"❌ Model instantiation error: {e}")
        return False

def test_sdk_client():
    """Test that SDK client can be instantiated"""
    print("\n🧪 Testing SDK client...")
    
    try:
        from app.agent_identity.sdk.client import AgentIdentityClient
        
        # Test client creation
        client = AgentIdentityClient(
            base_url="http://localhost:8000/v1",
            api_key="test_key",
            timeout=30
        )
        print("✅ SDK client created")
        
        # Test client attributes
        assert client.base_url == "http://localhost:8000/v1"
        assert client.api_key == "test_key"
        assert client.timeout.total == 30
        assert client.max_retries == 3
        print("✅ SDK client attributes correct")
        
        return True
        
    except Exception as e:
        print(f"❌ SDK client error: {e}")
        return False

def test_api_router():
    """Test that API router can be imported and has endpoints"""
    print("\n🧪 Testing API router...")
    
    try:
        from app.routers.agent_identity import router
        
        # Test router attributes
        assert router.prefix == "/agent-identity"
        assert "Agent Identity" in router.tags
        print("✅ API router created with correct prefix and tags")
        
        # Check that router has routes
        if hasattr(router, 'routes'):
            route_count = len(router.routes)
            print(f"✅ API router has {route_count} routes")
        else:
            print("✅ API router created (routes not accessible in this test)")
        
        return True
        
    except Exception as e:
        print(f"❌ API router error: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Agent Identity SDK - Basic Functionality Test")
    print("=" * 60)
    
    tests = [
        test_imports,
        test_models,
        test_sdk_client,
        test_api_router
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
        print("🎉 All basic functionality tests passed!")
        print("\n✅ Agent Identity SDK is ready for integration testing")
        return True
    else:
        print("❌ Some tests failed - check the errors above")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
