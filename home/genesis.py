#!/usr/bin/env python3
"""
Genesis wallet - Distributes initial AITBC from genesis block
"""

import os
import sys
import json
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cli'))
from wallet import AITBCWallet

def main():
    print("🌍 GENESIS BLOCK - Initial AITBC Distribution")
    print("=" * 60)
    
    # Create genesis wallet with large initial balance
    genesis = AITBCWallet("genesis_wallet.json")
    genesis.data["balance"] = 1000000.0  # 1 million AITBC
    genesis.data["transactions"] = [{
        "type": "genesis",
        "amount": 1000000.0,
        "description": "Genesis block creation",
        "timestamp": datetime.now().isoformat()
    }]
    genesis.save()
    
    print(f"💰 Genesis Wallet Created")
    print(f"   Address: {genesis.data['address']}")
    print(f"   Balance: {genesis.data['balance']} AITBC")
    print()
    
    # Distribute to client and miner
    client_wallet = AITBCWallet(os.path.join("client", "client_wallet.json"))
    miner_wallet = AITBCWallet(os.path.join("miner", "miner_wallet.json"))
    
    print("📤 Distributing Initial AITBC")
    print("-" * 40)
    
    # Give client 10,000 AITBC to spend
    client_address = client_wallet.data["address"]
    print(f"💸 Sending 10,000 AITBC to Client ({client_address[:20]}...)")
    client_wallet.add_earnings(10000.0, "genesis_distribution", "Initial funding from genesis block")
    
    # Give miner 1,000 AITBC to start
    miner_address = miner_wallet.data["address"]
    print(f"💸 Sending 1,000 AITBC to Miner ({miner_address[:20]}...)")
    miner_wallet.add_earnings(1000.0, "genesis_distribution", "Initial funding from genesis block")
    
    # Update genesis wallet
    genesis.data["balance"] -= 11000.0
    genesis.data["transactions"].extend([
        {
            "type": "transfer",
            "amount": -10000.0,
            "to": client_address,
            "description": "Initial client funding",
            "timestamp": datetime.now().isoformat()
        },
        {
            "type": "transfer", 
            "amount": -1000.0,
            "to": miner_address,
            "description": "Initial miner funding",
            "timestamp": datetime.now().isoformat()
        }
    ])
    genesis.save()
    
    print()
    print("✅ Distribution Complete!")
    print("=" * 60)
    print(f"Genesis Balance: {genesis.data['balance']} AITBC")
    print(f"Client Balance: {client_wallet.data['balance']} AITBC")
    print(f"Miner Balance: {miner_wallet.data['balance']} AITBC")
    print()
    print("💡 Next Steps:")
    print("   1. Client: Submit jobs and pay for GPU services")
    print("   2. Miner: Process jobs and earn AITBC")
    print("   3. Track everything with the wallet CLI tools")

if __name__ == "__main__":
    main()
