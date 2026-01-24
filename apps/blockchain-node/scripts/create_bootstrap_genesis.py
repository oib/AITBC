#!/usr/bin/env python3
"""Generate a genesis file with initial distribution for the exchange economy."""

import json
import time
from pathlib import Path

# Genesis configuration with initial token distribution
GENESIS_CONFIG = {
    "chain_id": "ait-mainnet",
    "timestamp": None,  # populated at runtime
    "params": {
        "mint_per_unit": 1000,
        "coordinator_ratio": 0.05,
        "base_fee": 10,
        "fee_per_byte": 1,
    },
    "accounts": [
        # Exchange Treasury - 10 million AITBC for liquidity
        {
            "address": "aitbcexchange00000000000000000000000000000000",
            "balance": 10_000_000_000_000,  # 10 million AITBC (in smallest units)
            "nonce": 0,
        },
        # Community Faucet - 1 million AITBC for airdrop
        {
            "address": "aitbcfaucet0000000000000000000000000000000000",
            "balance": 1_000_000_000_000,  # 1 million AITBC
            "nonce": 0,
        },
        # Team/Dev Fund - 2 million AITBC
        {
            "address": "aitbcteamfund00000000000000000000000000000000",
            "balance": 2_000_000_000_000,  # 2 million AITBC
            "nonce": 0,
        },
        # Early Investor Fund - 5 million AITBC
        {
            "address": "aitbcearlyinvest000000000000000000000000000000",
            "balance": 5_000_000_000_000,  # 5 million AITBC
            "nonce": 0,
        },
        # Ecosystem Fund - 3 million AITBC
        {
            "address": "aitbecosystem000000000000000000000000000000000",
            "balance": 3_000_000_000_000,  # 3 million AITBC
            "nonce": 0,
        }
    ],
    "authorities": [
        {
            "address": "aitbcvalidator00000000000000000000000000000000",
            "weight": 1,
        }
    ],
}

def create_genesis_with_bootstrap():
    """Create genesis file with initial token distribution"""
    
    # Set timestamp
    GENESIS_CONFIG["timestamp"] = int(time.time())
    
    # Calculate total initial distribution
    total_supply = sum(account["balance"] for account in GENESIS_CONFIG["accounts"])
    
    print("=" * 60)
    print("AITBC GENESIS BOOTSTRAP DISTRIBUTION")
    print("=" * 60)
    print(f"Total Initial Supply: {total_supply / 1_000_000:,.0f} AITBC")
    print("\nInitial Distribution:")
    
    for account in GENESIS_CONFIG["accounts"]:
        balance_aitbc = account["balance"] / 1_000_000
        percent = (balance_aitbc / 21_000_000) * 100
        print(f"  {account['address']}: {balance_aitbc:,.0f} AITBC ({percent:.1f}%)")
    
    print("\nPurpose of Funds:")
    print("  - Exchange Treasury: Provides liquidity for trading")
    print("  - Community Faucet: Airdrop to early users")
    print("  - Team Fund: Development incentives")
    print("  - Early Investors: Initial backers")
    print("  - Ecosystem Fund: Partnerships and growth")
    print("=" * 60)
    
    return GENESIS_CONFIG

def write_genesis_file(genesis_data, output_path="data/genesis_with_bootstrap.json"):
    """Write genesis to file"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, 'w') as f:
        json.dump(genesis_data, f, indent=2, sort_keys=True)
    
    print(f"\nGenesis file written to: {path}")
    return path

if __name__ == "__main__":
    # Create genesis with bootstrap distribution
    genesis = create_genesis_with_bootstrap()
    
    # Write to file
    genesis_path = write_genesis_file(genesis)
    
    print("\nTo apply this genesis:")
    print("1. Stop the blockchain node")
    print("2. Replace the genesis.json file")
    print("3. Reset the blockchain database")
    print("4. Restart the node")
