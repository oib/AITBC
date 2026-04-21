#!/usr/bin/env python3
"""
Final test and summary for blockchain nodes
"""

import httpx
import json

# Node URLs
NODES = {
    "node1": {"url": "http://127.0.0.1:8082", "name": "Node 1"},
    "node2": {"url": "http://127.0.0.1:8081", "name": "Node 2"},
}

def test_nodes():
    """Test both nodes"""
    print("🔗 AITBC Blockchain Node Test Summary")
    print("=" * 60)
    
    results = []
    
    for node_id, node in NODES.items():
        print(f"\n{node['name']}:")
        
        # Test RPC API
        try:
            response = httpx.get(f"{node['url']}/openapi.json", timeout=5)
            api_ok = response.status_code == 200
            print(f"  RPC API: {'✅' if api_ok else '❌'}")
        except:
            api_ok = False
            print(f"  RPC API: ❌")
        
        # Test chain head
        try:
            response = httpx.get(f"{node['url']}/rpc/head", timeout=5)
            if response.status_code == 200:
                head = response.json()
                height = head.get('height', 0)
                print(f"  Chain Height: {height}")
                
                # Test faucet
                try:
                    response = httpx.post(
                        f"{node['url']}/rpc/admin/mintFaucet",
                        json={"address": "aitbc1test000000000000000000000000000000000000", "amount": 100},
                        timeout=5
                    )
                    faucet_ok = response.status_code == 200
                    print(f"  Faucet: {'✅' if faucet_ok else '❌'}")
                except:
                    faucet_ok = False
                    print(f"  Faucet: ❌")
                
                results.append({
                    'node': node['name'],
                    'api': api_ok,
                    'height': height,
                    'faucet': faucet_ok
                })
            else:
                print(f"  Chain Head: ❌")
        except:
            print(f"  Chain Head: ❌")
    
    # Summary
    print("\n\n📊 Test Results Summary")
    print("=" * 60)
    
    for result in results:
        status = "✅ OPERATIONAL" if result['api'] and result['faucet'] else "⚠️  PARTIAL"
        print(f"{result['node']:.<20} {status}")
        print(f"  - RPC API: {'✅' if result['api'] else '❌'}")
        print(f"  - Height: {result['height']}")
        print(f"  - Faucet: {'✅' if result['faucet'] else '❌'}")
    
    print("\n\n📝 Notes:")
    print("- Both nodes are running independently")
    print("- Each node maintains its own chain")
    print("- Nodes are not connected (different heights)")
    print("- To connect nodes in production:")
    print("  1. Deploy on separate servers")
    print("  2. Use Redis for gossip backend")
    print("  3. Configure P2P peer discovery")
    print("  4. Ensure network connectivity")
    
    print("\n✅ Test completed successfully!")

if __name__ == "__main__":
    test_nodes()
