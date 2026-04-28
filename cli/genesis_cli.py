#!/usr/bin/env python3
"""
Genesis CLI - Standalone genesis block and wallet generation commands
"""

import argparse
import subprocess
import sys
import json
import sqlite3
from pathlib import Path


def handle_genesis_init(args):
    """Initialize genesis block and wallet"""
    # Use new genesis-init.py script for basic genesis initialization
    new_script_path = Path("/opt/aitbc/scripts/utils/genesis-init.py")
    old_script_path = Path("/opt/aitbc/apps/blockchain-node/scripts/unified_genesis.py")
    
    # Prefer new script if it exists and we're not doing wallet creation
    if new_script_path.exists() and not args.create_wallet:
        script_path = new_script_path
        use_new_script = True
    elif old_script_path.exists():
        script_path = old_script_path
        use_new_script = False
    else:
        print(f"Error: Genesis generation script not found")
        return 1
    
    if use_new_script:
        # Use new simpler script
        cmd = [sys.executable, str(script_path), "--chain-id", args.chain_id]
        if args.proposer:
            cmd.extend(["--proposer", args.proposer])
        else:
            print("Error: --proposer is required for genesis initialization")
            return 1
    else:
        # Use old comprehensive script for wallet creation
        cmd = [sys.executable, str(script_path), "--chain-id", args.chain_id]
        if args.create_wallet:
            cmd.append("--create-wallet")
        if args.password:
            cmd.extend(["--password", args.password])
        if args.proposer:
            cmd.extend(["--proposer", args.proposer])
        if args.force:
            cmd.append("--force")
        if args.register_service:
            cmd.append("--register-service")
            cmd.extend(["--service-url", args.service_url])
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        return 0
    except subprocess.CalledProcessError as e:
        print(f"Error: Genesis generation failed: {e.stderr}")
        return 1


def handle_genesis_verify(args):
    """Verify genesis block and wallet configuration"""
    chain_id = args.chain_id
    
    # Check genesis config file
    genesis_path = Path(f"/var/lib/aitbc/data/{chain_id}/genesis.json")
    if not genesis_path.exists():
        print(f"Error: Genesis config not found: {genesis_path}")
        return 1
    
    try:
        with open(genesis_path) as f:
            genesis_data = json.load(f)
        
        print(f"✓ Genesis config found: {genesis_path}")
        print(f"  Chain ID: {genesis_data.get('chain_id')}")
        print(f"  Genesis Hash: {genesis_data.get('block', {}).get('hash')}")
        print(f"  Proposer: {genesis_data.get('block', {}).get('proposer')}")
        print(f"  Allocations: {len(genesis_data.get('allocations', []))}")
    except Exception as e:
        print(f"Error: Failed to read genesis config: {e}")
        return 1
    
    # Check database
    db_path = Path("/var/lib/aitbc/data/chain.db")
    if not db_path.exists():
        print(f"Error: Database not found: {db_path}")
        return 1
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM block WHERE height=0 AND chain_id=?", (chain_id,))
        genesis_block = cursor.fetchone()
        
        if genesis_block:
            print(f"✓ Genesis block found in database")
            print(f"  Height: {genesis_block[1]}")
            print(f"  Hash: {genesis_block[2]}")
            print(f"  Proposer: {genesis_block[4]}")
        else:
            print(f"Error: Genesis block not found in database for chain {chain_id}")
        
        cursor.execute("SELECT COUNT(*) FROM account WHERE chain_id=?", (chain_id,))
        account_count = cursor.fetchone()[0]
        
        if account_count > 0:
            print(f"✓ Found {account_count} accounts in database")
        else:
            print(f"Error: No accounts found in database for chain {chain_id}")
        
        conn.close()
    except Exception as e:
        print(f"Error: Failed to verify database: {e}")
        return 1
    
    # Check genesis wallet
    wallet_path = Path("/var/lib/aitbc/keystore/genesis.json")
    if wallet_path.exists():
        print(f"✓ Genesis wallet found: {wallet_path}")
        try:
            with open(wallet_path) as f:
                wallet_data = json.load(f)
            print(f"  Address: {wallet_data.get('address')}")
            print(f"  Public Key: {wallet_data.get('public_key')[:16]}..." if wallet_data.get('public_key') else "N/A")
        except Exception as e:
            print(f"Error: Failed to read genesis wallet: {e}")
    else:
        print(f"Error: Genesis wallet not found: {wallet_path}")
    
    return 0


def handle_genesis_info(args):
    """Show genesis block information"""
    chain_id = args.chain_id
    genesis_path = Path(f"/var/lib/aitbc/data/{chain_id}/genesis.json")
    
    if not genesis_path.exists():
        print(f"Error: Genesis config not found: {genesis_path}")
        return 1
    
    try:
        with open(genesis_path) as f:
            genesis_data = json.load(f)
        
        block = genesis_data.get("block", {})
        allocations = genesis_data.get("allocations", [])
        
        print(f"Genesis Information for {chain_id}:")
        print(f"  Chain ID: {genesis_data.get('chain_id')}")
        print(f"  Block Height: {block.get('height')}")
        print(f"  Block Hash: {block.get('hash')}")
        print(f"  Parent Hash: {block.get('parent_hash')}")
        print(f"  Proposer: {block.get('proposer')}")
        print(f"  Timestamp: {block.get('timestamp')}")
        print(f"  Transaction Count: {block.get('tx_count')}")
        print(f"  Total Allocations: {len(allocations)}")
        print(f"\n  Top Allocations:")
        for i, alloc in enumerate(allocations[:5], 1):
            print(f"    {i}. {alloc.get('address')}: {alloc.get('balance')} AIT")
        
    except Exception as e:
        print(f"Error: Failed to read genesis info: {e}")
        return 1
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="AITBC Genesis CLI - Genesis block and wallet generation",
        epilog="Examples: genesis-cli init --create-wallet | genesis-cli verify | genesis-cli info"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Genesis commands")
    
    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize genesis block and wallet")
    init_parser.add_argument("--chain-id", default="ait-mainnet", help="Chain ID for genesis")
    init_parser.add_argument("--create-wallet", action="store_true", help="Create genesis wallet with secure random key")
    init_parser.add_argument("--password", help="Wallet password (auto-generated if not provided)")
    init_parser.add_argument("--proposer", help="Proposer address (defaults to genesis wallet)")
    init_parser.add_argument("--force", action="store_true", help="Force overwrite existing genesis")
    init_parser.add_argument("--register-service", action="store_true", help="Register genesis wallet with wallet service")
    init_parser.add_argument("--service-url", default="http://localhost:8003", help="Wallet service URL")
    init_parser.set_defaults(handler=handle_genesis_init)
    
    # Verify command
    verify_parser = subparsers.add_parser("verify", help="Verify genesis block and wallet configuration")
    verify_parser.add_argument("--chain-id", default="ait-mainnet", help="Chain ID to verify")
    verify_parser.set_defaults(handler=handle_genesis_verify)
    
    # Info command
    info_parser = subparsers.add_parser("info", help="Show genesis block information")
    info_parser.add_argument("--chain-id", default="ait-mainnet", help="Chain ID to show info for")
    info_parser.set_defaults(handler=handle_genesis_info)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
