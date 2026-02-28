#!/usr/bin/env python3
"""
AITBC Agent Identity SDK Example
Demonstrates basic usage of the Agent Identity SDK
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any

# Import SDK components
# Note: In a real installation, this would be:
# from aitbc_agent_identity_sdk import AgentIdentityClient, VerificationType
# For this example, we'll use relative imports
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from app.agent_identity.sdk.client import AgentIdentityClient
from app.agent_identity.sdk.models import VerificationType, IdentityStatus


async def basic_identity_example():
    """Basic identity creation and management example"""
    
    print("🚀 AITBC Agent Identity SDK - Basic Example")
    print("=" * 50)
    
    # Initialize the client
    async with AgentIdentityClient(
        base_url="http://localhost:8000/v1",
        api_key="demo_api_key"
    ) as client:
        
        try:
            # 1. Create a new agent identity
            print("\n1. Creating agent identity...")
            identity = await client.create_identity(
                owner_address="0x1234567890123456789012345678901234567890",
                chains=[1, 137, 56],  # Ethereum, Polygon, BSC
                display_name="Demo AI Agent",
                description="A demonstration AI agent for cross-chain operations",
                metadata={
                    "version": "1.0.0",
                    "capabilities": ["inference", "training", "data_processing"],
                    "created_by": "aitbc-sdk-example"
                },
                tags=["demo", "ai", "cross-chain"]
            )
            
            print(f"✅ Created identity: {identity.agent_id}")
            print(f"   Display name: {identity.display_name}")
            print(f"   Supported chains: {identity.supported_chains}")
            print(f"   Primary chain: {identity.primary_chain}")
            
            # 2. Get comprehensive identity details
            print("\n2. Getting identity details...")
            details = await client.get_identity(identity.agent_id)
            
            print(f"   Status: {details['identity']['status']}")
            print(f"   Verification level: {details['identity']['verification_level']}")
            print(f"   Reputation score: {details['identity']['reputation_score']}")
            print(f"   Total transactions: {details['identity']['total_transactions']}")
            print(f"   Success rate: {details['identity']['success_rate']:.2%}")
            
            # 3. Create wallets on each chain
            print("\n3. Creating agent wallets...")
            wallet_results = identity.wallet_results
            
            for wallet_result in wallet_results:
                if wallet_result.get('success', False):
                    print(f"   ✅ Chain {wallet_result['chain_id']}: {wallet_result['wallet_address']}")
                else:
                    print(f"   ❌ Chain {wallet_result['chain_id']}: {wallet_result.get('error', 'Unknown error')}")
            
            # 4. Get wallet balances
            print("\n4. Checking wallet balances...")
            for chain_id in identity.supported_chains:
                try:
                    balance = await client.get_wallet_balance(identity.agent_id, int(chain_id))
                    print(f"   Chain {chain_id}: {balance} tokens")
                except Exception as e:
                    print(f"   Chain {chain_id}: Error getting balance - {e}")
            
            # 5. Verify identity on all chains
            print("\n5. Verifying identity on all chains...")
            mappings = await client.get_cross_chain_mappings(identity.agent_id)
            
            for mapping in mappings:
                try:
                    # Generate mock proof data
                    proof_data = {
                        "agent_id": identity.agent_id,
                        "chain_id": mapping.chain_id,
                        "chain_address": mapping.chain_address,
                        "timestamp": datetime.utcnow().isoformat(),
                        "verification_method": "demo"
                    }
                    
                    # Generate simple proof hash
                    proof_string = json.dumps(proof_data, sort_keys=True)
                    import hashlib
                    proof_hash = hashlib.sha256(proof_string.encode()).hexdigest()
                    
                    verification = await client.verify_identity(
                        agent_id=identity.agent_id,
                        chain_id=mapping.chain_id,
                        verifier_address="0xverifier12345678901234567890123456789012345678",
                        proof_hash=proof_hash,
                        proof_data=proof_data,
                        verification_type=VerificationType.BASIC
                    )
                    
                    print(f"   ✅ Chain {mapping.chain_id}: Verified (ID: {verification.verification_id})")
                    
                except Exception as e:
                    print(f"   ❌ Chain {mapping.chain_id}: Verification failed - {e}")
            
            # 6. Search for identities
            print("\n6. Searching for identities...")
            search_results = await client.search_identities(
                query="demo",
                limit=10,
                min_reputation=0.0
            )
            
            print(f"   Found {search_results.total_count} identities")
            for result in search_results.results[:3]:  # Show first 3
                print(f"   - {result['display_name']} (Reputation: {result['reputation_score']})")
            
            # 7. Sync reputation across chains
            print("\n7. Syncing reputation across chains...")
            reputation_sync = await client.sync_reputation(identity.agent_id)
            
            print(f"   Aggregated reputation: {reputation_sync.aggregated_reputation}")
            print(f"   Chain reputations: {reputation_sync.chain_reputations}")
            print(f"   Verified chains: {reputation_sync.verified_chains}")
            
            # 8. Export identity data
            print("\n8. Exporting identity data...")
            export_data = await client.export_identity(identity.agent_id)
            
            print(f"   Export version: {export_data['export_version']}")
            print(f"   Agent ID: {export_data['agent_id']}")
            print(f"   Export timestamp: {export_data['export_timestamp']}")
            print(f"   Cross-chain mappings: {len(export_data['cross_chain_mappings'])}")
            
            # 9. Get registry health
            print("\n9. Checking registry health...")
            health = await client.get_registry_health()
            
            print(f"   Registry status: {health.status}")
            print(f"   Total identities: {health.registry_statistics.total_identities}")
            print(f"   Total mappings: {health.registry_statistics.total_mappings}")
            print(f"   Verification rate: {health.registry_statistics.verification_rate:.2%}")
            print(f"   Supported chains: {len(health.supported_chains)}")
            
            if health.issues:
                print(f"   Issues: {', '.join(health.issues)}")
            else:
                print("   No issues detected ✅")
            
            print("\n🎉 Example completed successfully!")
            
        except Exception as e:
            print(f"\n❌ Error during example: {e}")
            import traceback
            traceback.print_exc()


async def advanced_transaction_example():
    """Advanced transaction and wallet management example"""
    
    print("\n🔧 AITBC Agent Identity SDK - Advanced Transaction Example")
    print("=" * 60)
    
    async with AgentIdentityClient(
        base_url="http://localhost:8000/v1",
        api_key="demo_api_key"
    ) as client:
        
        try:
            # Use existing agent or create new one
            agent_id = "demo_agent_123"
            
            # 1. Get all wallets
            print("\n1. Getting all agent wallets...")
            wallets = await client.get_all_wallets(agent_id)
            
            print(f"   Total wallets: {wallets['statistics']['total_wallets']}")
            print(f"   Active wallets: {wallets['statistics']['active_wallets']}")
            print(f"   Total balance: {wallets['statistics']['total_balance']}")
            
            # 2. Execute a transaction
            print("\n2. Executing transaction...")
            try:
                tx = await client.execute_transaction(
                    agent_id=agent_id,
                    chain_id=1,
                    to_address="0x4567890123456789012345678901234567890123",
                    amount=0.01,
                    data={"purpose": "demo_transaction", "type": "payment"}
                )
                
                print(f"   ✅ Transaction executed: {tx.transaction_hash}")
                print(f"   From: {tx.from_address}")
                print(f"   To: {tx.to_address}")
                print(f"   Amount: {tx.amount} ETH")
                print(f"   Gas used: {tx.gas_used}")
                print(f"   Status: {tx.status}")
                
            except Exception as e:
                print(f"   ❌ Transaction failed: {e}")
            
            # 3. Get transaction history
            print("\n3. Getting transaction history...")
            try:
                history = await client.get_transaction_history(agent_id, 1, limit=5)
                
                print(f"   Found {len(history)} recent transactions:")
                for tx in history:
                    print(f"   - {tx.hash[:10]}... {tx.amount} ETH to {tx.to_address[:10]}...")
                    print(f"     Status: {tx.status}, Block: {tx.block_number}")
                
            except Exception as e:
                print(f"   ❌ Failed to get history: {e}")
            
            # 4. Update identity
            print("\n4. Updating agent identity...")
            try:
                updates = {
                    "display_name": "Updated Demo Agent",
                    "description": "Updated description with new capabilities",
                    "metadata": {
                        "version": "1.1.0",
                        "last_updated": datetime.utcnow().isoformat()
                    },
                    "tags": ["demo", "ai", "updated"]
                }
                
                result = await client.update_identity(agent_id, updates)
                print(f"   ✅ Identity updated: {result.identity_id}")
                print(f"   Updated fields: {', '.join(result.updated_fields)}")
                
            except Exception as e:
                print(f"   ❌ Update failed: {e}")
            
            print("\n🎉 Advanced example completed!")
            
        except Exception as e:
            print(f"\n❌ Error during advanced example: {e}")
            import traceback
            traceback.print_exc()


async def search_and_discovery_example():
    """Search and discovery example"""
    
    print("\n🔍 AITBC Agent Identity SDK - Search and Discovery Example")
    print("=" * 65)
    
    async with AgentIdentityClient(
        base_url="http://localhost:8000/v1",
        api_key="demo_api_key"
    ) as client:
        
        try:
            # 1. Search by query
            print("\n1. Searching by query...")
            results = await client.search_identities(
                query="ai",
                limit=10,
                min_reputation=50.0
            )
            
            print(f"   Found {results.total_count} identities matching 'ai'")
            print(f"   Query: '{results.query}'")
            print(f"   Filters: {results.filters}")
            
            for result in results.results[:5]:
                print(f"   - {result['display_name']}")
                print(f"     Agent ID: {result['agent_id']}")
                print(f"     Reputation: {result['reputation_score']}")
                print(f"     Success rate: {result['success_rate']:.2%}")
                print(f"     Chains: {len(result['supported_chains'])}")
            
            # 2. Search by chains
            print("\n2. Searching by chains...")
            chain_results = await client.search_identities(
                chains=[1, 137],  # Ethereum and Polygon only
                verification_level=VerificationType.ADVANCED,
                limit=5
            )
            
            print(f"   Found {chain_results.total_count} identities on Ethereum/Polygon with Advanced verification")
            
            # 3. Get supported chains
            print("\n3. Getting supported chains...")
            chains = await client.get_supported_chains()
            
            print(f"   Supported chains ({len(chains)}):")
            for chain in chains:
                print(f"   - {chain.name} (ID: {chain.chain_id}, Type: {chain.chain_type})")
                print(f"     RPC: {chain.rpc_url}")
                print(f"     Currency: {chain.native_currency}")
            
            # 4. Resolve identity to address
            print("\n4. Resolving identity to chain addresses...")
            test_agent_id = "demo_agent_123"
            
            for chain_id in [1, 137, 56]:
                try:
                    address = await client.resolve_identity(test_agent_id, chain_id)
                    print(f"   Chain {chain_id}: {address}")
                except Exception as e:
                    print(f"   Chain {chain_id}: Not found - {e}")
            
            # 5. Resolve address to agent
            print("\n5. Resolving addresses to agent IDs...")
            test_addresses = [
                ("0x1234567890123456789012345678901234567890", 1),
                ("0x4567890123456789012345678901234567890123", 137)
            ]
            
            for address, chain_id in test_addresses:
                try:
                    agent_id = await client.resolve_address(address, chain_id)
                    print(f"   {address[:10]}... on chain {chain_id}: {agent_id}")
                except Exception as e:
                    print(f"   {address[:10]}... on chain {chain_id}: Not found - {e}")
            
            print("\n🎉 Search and discovery example completed!")
            
        except Exception as e:
            print(f"\n❌ Error during search example: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """Run all examples"""
    
    print("🎯 AITBC Agent Identity SDK - Complete Example Suite")
    print("=" * 70)
    print("This example demonstrates the full capabilities of the Agent Identity SDK")
    print("including identity management, cross-chain operations, and search functionality.")
    print()
    print("Note: This example requires a running Agent Identity API server.")
    print("Make sure the API is running at http://localhost:8000/v1")
    print()
    
    try:
        # Run basic example
        await basic_identity_example()
        
        # Run advanced transaction example
        await advanced_transaction_example()
        
        # Run search and discovery example
        await search_and_discovery_example()
        
        print("\n🎊 All examples completed successfully!")
        print("\nNext steps:")
        print("1. Explore the SDK documentation")
        print("2. Integrate the SDK into your application")
        print("3. Customize for your specific use case")
        print("4. Deploy to production with proper error handling")
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Example interrupted by user")
    except Exception as e:
        print(f"\n\n💥 Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Run the example suite
    asyncio.run(main())
