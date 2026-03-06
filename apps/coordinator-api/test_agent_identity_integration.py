#!/usr/bin/env python3
"""
Simple integration test for Agent Identity SDK
Tests the core functionality without requiring full API setup
"""

import asyncio
import sys
import os

# Add the app path to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_basic_functionality():
    """Test basic functionality without API dependencies"""
    print("🚀 Agent Identity SDK - Integration Test")
    print("=" * 50)
    
    # Test 1: Import core components
    print("\n1. Testing core component imports...")
    try:
        from app.domain.agent_identity import (
            AgentIdentity, CrossChainMapping, AgentWallet,
            IdentityStatus, VerificationType, ChainType
        )
        from app.agent_identity.core import AgentIdentityCore
        from app.agent_identity.registry import CrossChainRegistry
        from app.agent_identity.wallet_adapter import MultiChainWalletAdapter
        from app.agent_identity.manager import AgentIdentityManager
        print("✅ All core components imported successfully")
    except Exception as e:
        print(f"❌ Core import error: {e}")
        return False
    
    # Test 2: Test SDK client
    print("\n2. Testing SDK client...")
    try:
        from app.agent_identity.sdk.client import AgentIdentityClient
        from app.agent_identity.sdk.models import (
            AgentIdentity as SDKAgentIdentity,
            IdentityStatus as SDKIdentityStatus,
            VerificationType as SDKVerificationType
        )
        from app.agent_identity.sdk.exceptions import (
            AgentIdentityError,
            ValidationError
        )
        
        # Test client creation
        client = AgentIdentityClient(
            base_url="http://localhost:8000/v1",
            api_key="test_key"
        )
        print("✅ SDK client created successfully")
        print(f"   Base URL: {client.base_url}")
        print(f"   Timeout: {client.timeout.total}s")
        print(f"   Max retries: {client.max_retries}")
        
    except Exception as e:
        print(f"❌ SDK client error: {e}")
        return False
    
    # Test 3: Test model creation
    print("\n3. Testing model creation...")
    try:
        from datetime import datetime, timezone
        
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
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
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
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
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
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        print("✅ AgentWallet model created")
        
    except Exception as e:
        print(f"❌ Model creation error: {e}")
        return False
    
    # Test 4: Test wallet adapter
    print("\n4. Testing wallet adapter...")
    try:
        # Test chain configuration
        adapter = MultiChainWalletAdapter(None)  # Mock session
        chains = adapter.get_supported_chains()
        print(f"✅ Wallet adapter created with {len(chains)} supported chains")
        
        for chain in chains[:3]:  # Show first 3 chains
            print(f"   - {chain['name']} (ID: {chain['chain_id']})")
        
    except Exception as e:
        print(f"❌ Wallet adapter error: {e}")
        return False
    
    # Test 5: Test SDK models
    print("\n5. Testing SDK models...")
    try:
        from app.agent_identity.sdk.models import (
            CreateIdentityRequest, TransactionRequest,
            SearchRequest, ChainConfig
        )
        
        # Test CreateIdentityRequest
        request = CreateIdentityRequest(
            owner_address="0x123...",
            chains=[1, 137],
            display_name="Test Agent",
            description="Test description"
        )
        print("✅ CreateIdentityRequest model created")
        
        # Test TransactionRequest
        tx_request = TransactionRequest(
            to_address="0x456...",
            amount=0.1,
            data={"purpose": "test"}
        )
        print("✅ TransactionRequest model created")
        
        # Test ChainConfig
        chain_config = ChainConfig(
            chain_id=1,
            chain_type=ChainType.ETHEREUM,
            name="Ethereum Mainnet",
            rpc_url="https://mainnet.infura.io/v3/test",
            block_explorer_url="https://etherscan.io",
            native_currency="ETH",
            decimals=18
        )
        print("✅ ChainConfig model created")
        
    except Exception as e:
        print(f"❌ SDK models error: {e}")
        return False
    
    print("\n🎉 All integration tests passed!")
    return True

def test_configuration():
    """Test configuration and setup"""
    print("\n🔧 Testing configuration...")
    
    # Check if configuration file exists
    config_file = "/home/oib/windsurf/aitbc/apps/coordinator-api/.env.agent-identity.example"
    if os.path.exists(config_file):
        print("✅ Configuration example file exists")
        
        # Read and display configuration
        with open(config_file, 'r') as f:
            config_lines = f.readlines()
        
        print("   Configuration sections:")
        for line in config_lines:
            if line.strip() and not line.startswith('#'):
                print(f"   - {line.strip()}")
    else:
        print("❌ Configuration example file missing")
        return False
    
    return True

def main():
    """Run all integration tests"""
    
    tests = [
        test_basic_functionality,
        test_configuration
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        else:
            print(f"\n❌ Test {test.__name__} failed")
    
    print(f"\n📊 Integration Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎊 All integration tests passed!")
        print("\n✅ Agent Identity SDK is ready for:")
        print("   - Database migration")
        print("   - API server startup")
        print("   - SDK client usage")
        print("   - Integration testing")
        return True
    else:
        print("\n❌ Some tests failed - check the errors above")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
