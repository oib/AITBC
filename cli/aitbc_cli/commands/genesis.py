"""Genesis block and wallet generation commands for AITBC CLI"""

import click
from typing import Optional
from ..utils import output, error, success
import subprocess
import sys
from pathlib import Path


@click.group()
def genesis():
    """Genesis block and wallet generation commands"""
    pass


@genesis.command()
@click.option("--chain-id", default="ait-mainnet", help="Chain ID for genesis")
@click.option("--create-wallet", is_flag=True, help="Create genesis wallet with secure random key")
@click.option("--password", help="Wallet password (auto-generated if not provided)")
@click.option("--proposer", help="Proposer address (defaults to genesis wallet)")
@click.option("--force", is_flag=True, help="Force overwrite existing genesis")
@click.option("--register-service", is_flag=True, help="Register genesis wallet with wallet service")
@click.option("--service-url", default="http://localhost:8003", help="Wallet service URL")
@click.pass_context
def init(ctx, chain_id: str, create_wallet: bool, password: Optional[str], proposer: Optional[str], 
          force: bool, register_service: bool, service_url: str):
    """Initialize genesis block and wallet for a blockchain"""
    script_path = Path("/opt/aitbc/apps/blockchain-node/scripts/unified_genesis.py")
    
    if not script_path.exists():
        error(f"Genesis generation script not found: {script_path}")
        return
    
    # Build command
    cmd = [
        sys.executable,
        str(script_path),
        "--chain-id", chain_id
    ]
    
    if create_wallet:
        cmd.append("--create-wallet")
    
    if password:
        cmd.extend(["--password", password])
    
    if proposer:
        cmd.extend(["--proposer", proposer])
    
    if force:
        cmd.append("--force")
    
    if register_service:
        cmd.append("--register-service")
        cmd.extend(["--service-url", service_url])
    
    try:
        success(f"Running genesis generation for {chain_id}...")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        output(result.stdout, ctx.obj.get("output_format", "table"))
        success(f"Genesis generation completed successfully")
    except subprocess.CalledProcessError as e:
        error(f"Genesis generation failed: {e.stderr}")
        return


@genesis.command()
@click.option("--chain-id", default="ait-mainnet", help="Chain ID to verify")
@click.pass_context
def verify(ctx, chain_id: str):
    """Verify genesis block and wallet configuration"""
    import json
    import sqlite3
    
    # Check genesis config file
    genesis_path = Path(f"/var/lib/aitbc/data/{chain_id}/genesis.json")
    if not genesis_path.exists():
        error(f"Genesis config not found: {genesis_path}")
        return
    
    try:
        with open(genesis_path) as f:
            genesis_data = json.load(f)
        
        success(f"✓ Genesis config found: {genesis_path}")
        output({
            "chain_id": genesis_data.get("chain_id"),
            "genesis_hash": genesis_data.get("block", {}).get("hash"),
            "proposer": genesis_data.get("block", {}).get("proposer"),
            "allocations_count": len(genesis_data.get("allocations", []))
        }, ctx.obj.get("output_format", "table"))
    except Exception as e:
        error(f"Failed to read genesis config: {e}")
        return
    
    # Check database
    db_path = Path("/var/lib/aitbc/data/chain.db")
    if not db_path.exists():
        error(f"Database not found: {db_path}")
        return
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Check genesis block
        cursor.execute("SELECT * FROM block WHERE height=0 AND chain_id=?", (chain_id,))
        genesis_block = cursor.fetchone()
        
        if genesis_block:
            success(f"✓ Genesis block found in database")
            output({
                "height": genesis_block[1],
                "hash": genesis_block[2],
                "proposer": genesis_block[4]
            }, ctx.obj.get("output_format", "table"))
        else:
            error(f"Genesis block not found in database for chain {chain_id}")
        
        # Check genesis accounts
        cursor.execute("SELECT COUNT(*) FROM account WHERE chain_id=?", (chain_id,))
        account_count = cursor.fetchone()[0]
        
        if account_count > 0:
            success(f"✓ Found {account_count} accounts in database")
        else:
            error(f"No accounts found in database for chain {chain_id}")
        
        conn.close()
    except Exception as e:
        error(f"Failed to verify database: {e}")
        return
    
    # Check genesis wallet
    wallet_path = Path("/var/lib/aitbc/keystore/genesis.json")
    if wallet_path.exists():
        success(f"✓ Genesis wallet found: {wallet_path}")
        try:
            with open(wallet_path) as f:
                wallet_data = json.load(f)
            output({
                "address": wallet_data.get("address"),
                "public_key": wallet_data.get("public_key")[:16] + "..." if wallet_data.get("public_key") else None
            }, ctx.obj.get("output_format", "table"))
        except Exception as e:
            error(f"Failed to read genesis wallet: {e}")
    else:
        error(f"Genesis wallet not found: {wallet_path}")


@genesis.command()
@click.option("--chain-id", default="ait-mainnet", help="Chain ID to show info for")
@click.pass_context
def info(ctx, chain_id: str):
    """Show genesis block information"""
    import json
    import sqlite3
    
    genesis_path = Path(f"/var/lib/aitbc/data/{chain_id}/genesis.json")
    if not genesis_path.exists():
        error(f"Genesis config not found: {genesis_path}")
        return
    
    try:
        with open(genesis_path) as f:
            genesis_data = json.load(f)
        
        block = genesis_data.get("block", {})
        allocations = genesis_data.get("allocations", [])
        
        output({
            "chain_id": genesis_data.get("chain_id"),
            "genesis_block": {
                "height": block.get("height"),
                "hash": block.get("hash"),
                "parent_hash": block.get("parent_hash"),
                "proposer": block.get("proposer"),
                "timestamp": block.get("timestamp"),
                "tx_count": block.get("tx_count")
            },
            "allocations": [
                {
                    "address": alloc.get("address"),
                    "balance": alloc.get("balance"),
                    "nonce": alloc.get("nonce")
                }
                for alloc in allocations[:5]  # Show first 5
            ],
            "total_allocations": len(allocations)
        }, ctx.obj.get("output_format", "table"))
        
    except Exception as e:
        error(f"Failed to read genesis info: {e}")
