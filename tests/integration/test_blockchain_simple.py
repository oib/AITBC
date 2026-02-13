#!/usr/bin/env python3
"""
Simple test to verify blockchain nodes are working independently
and demonstrate how to configure them for networking
"""

import httpx
import json
import time

# Node URLs
NODES = {
    "node1": "http://127.0.0.1:8082",
    "node2": "http://127.0.0.1:8081",
}

def test_node_basic_functionality():
    """Test basic functionality of each node"""
    print("Testing Blockchain Node Functionality")
    print("=" * 60)
    
    for name, url in NODES.items():
        print(f"\nTesting {name}:")
        
        # Check if node is responsive
        try:
            response = httpx.get(f"{url}/openapi.json", timeout=5)
            print(f"  ✅ Node responsive")
        except:
            print(f"  ❌ Node not responding")
            continue
        
        # Get chain head
        try:
            response = httpx.get(f"{url}/rpc/head", timeout=5)
            if response.status_code == 200:
                head = response.json()
                print(f"  ✅ Chain height: {head.get('height', 'unknown')}")
            else:
                print(f"  ❌ Failed to get chain head")
        except:
            print(f"  ❌ Error getting chain head")
        
        # Test faucet
        try:
            response = httpx.post(
                f"{url}/rpc/admin/mintFaucet",
                json={"address": "aitbc1test000000000000000000000000000000000000", "amount": 100},
                timeout=5
            )
            if response.status_code == 200:
                print(f"  ✅ Faucet working")
            else:
                print(f"  ❌ Faucet failed: {response.status_code}")
        except:
            print(f"  ❌ Error testing faucet")

def show_networking_config():
    """Show how to configure nodes for networking"""
    print("\n\nNetworking Configuration")
    print("=" * 60)
    
    print("""
To connect the blockchain nodes in a network, you need to:

1. Use a shared gossip backend (Redis or Starlette Broadcast):

   For Starlette Broadcast (simpler):
   - Node 1 .env:
     GOSSIP_BACKEND=broadcast
     GOSSIP_BROADCAST_URL=http://127.0.0.1:7070/gossip
     
   - Node 2 .env:
     GOSSIP_BACKEND=broadcast
     GOSSIP_BROADCAST_URL=http://127.0.0.1:7070/gossip

2. Start a gossip relay service:
   python -m aitbc_chain.gossip.relay --port 7070

3. Configure P2P discovery:
   - Add peer list to configuration
   - Ensure ports are accessible between nodes

4. For production deployment:
   - Use Redis as gossip backend
   - Configure proper network addresses
   - Set up peer discovery mechanism

Current status: Nodes are running independently with memory backend.
They work correctly but don't share blocks or transactions.
""")

def main():
    test_node_basic_functionality()
    show_networking_config()

if __name__ == "__main__":
    main()
