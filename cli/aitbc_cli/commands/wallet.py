"""Wallet commands for AITBC CLI"""

import click
import httpx
import json
import os
import shutil
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from ..utils import output, error, success


@click.group()
@click.option("--wallet-name", help="Name of the wallet to use")
@click.option("--wallet-path", help="Direct path to wallet file (overrides --wallet-name)")
@click.pass_context
def wallet(ctx, wallet_name: Optional[str], wallet_path: Optional[str]):
    """Manage your AITBC wallets and transactions"""
    # Ensure wallet object exists
    ctx.ensure_object(dict)
    
    # If direct wallet path is provided, use it
    if wallet_path:
        wp = Path(wallet_path)
        wp.parent.mkdir(parents=True, exist_ok=True)
        ctx.obj['wallet_name'] = wp.stem
        ctx.obj['wallet_dir'] = wp.parent
        ctx.obj['wallet_path'] = wp
        return
    
    # Set wallet directory
    wallet_dir = Path.home() / ".aitbc" / "wallets"
    wallet_dir.mkdir(parents=True, exist_ok=True)
    
    # Set active wallet
    if not wallet_name:
        # Try to get from config or use 'default'
        config_file = Path.home() / ".aitbc" / "config.yaml"
        if config_file.exists():
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
                if config:
                    wallet_name = config.get('active_wallet', 'default')
                else:
                    wallet_name = 'default'
        else:
            wallet_name = 'default'
    
    ctx.obj['wallet_name'] = wallet_name
    ctx.obj['wallet_dir'] = wallet_dir
    ctx.obj['wallet_path'] = wallet_dir / f"{wallet_name}.json"


@wallet.command()
@click.argument('name')
@click.option('--type', 'wallet_type', default='hd', help='Wallet type (hd, simple)')
@click.pass_context
def create(ctx, name: str, wallet_type: str):
    """Create a new wallet"""
    wallet_dir = ctx.obj['wallet_dir']
    wallet_path = wallet_dir / f"{name}.json"
    
    if wallet_path.exists():
        error(f"Wallet '{name}' already exists")
        return
    
    # Generate new wallet
    if wallet_type == 'hd':
        # Hierarchical Deterministic wallet
        import secrets
        seed = secrets.token_hex(32)
        address = f"aitbc1{seed[:40]}"
        private_key = f"0x{seed}"
        public_key = f"0x{secrets.token_hex(32)}"
    else:
        # Simple wallet
        import secrets
        private_key = f"0x{secrets.token_hex(32)}"
        public_key = f"0x{secrets.token_hex(32)}"
        address = f"aitbc1{secrets.token_hex(20)}"
    
    wallet_data = {
        "wallet_id": name,
        "type": wallet_type,
        "address": address,
        "public_key": public_key,
        "private_key": private_key,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "balance": 0,
        "transactions": []
    }
    
    # Save wallet
    with open(wallet_path, 'w') as f:
        json.dump(wallet_data, f, indent=2)
    
    success(f"Wallet '{name}' created successfully")
    output({
        "name": name,
        "type": wallet_type,
        "address": address,
        "path": str(wallet_path)
    }, ctx.obj.get('output_format', 'table'))


@wallet.command()
@click.pass_context
def list(ctx):
    """List all wallets"""
    wallet_dir = ctx.obj['wallet_dir']
    config_file = Path.home() / ".aitbc" / "config.yaml"
    
    # Get active wallet
    active_wallet = 'default'
    if config_file.exists():
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
            active_wallet = config.get('active_wallet', 'default')
    
    wallets = []
    for wallet_file in wallet_dir.glob("*.json"):
        with open(wallet_file, 'r') as f:
            wallet_data = json.load(f)
            wallets.append({
                "name": wallet_data['wallet_id'],
                "type": wallet_data.get('type', 'simple'),
                "address": wallet_data['address'],
                "created_at": wallet_data['created_at'],
                "active": wallet_data['wallet_id'] == active_wallet
            })
    
    output(wallets, ctx.obj.get('output_format', 'table'))


@wallet.command()
@click.argument('name')
@click.pass_context
def switch(ctx, name: str):
    """Switch to a different wallet"""
    wallet_dir = ctx.obj['wallet_dir']
    wallet_path = wallet_dir / f"{name}.json"
    
    if not wallet_path.exists():
        error(f"Wallet '{name}' does not exist")
        return
    
    # Update config
    config_file = Path.home() / ".aitbc" / "config.yaml"
    config = {}
    
    if config_file.exists():
        import yaml
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f) or {}
    
    config['active_wallet'] = name
    
    # Save config
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    
    success(f"Switched to wallet '{name}'")
    output({
        "active_wallet": name,
        "address": json.load(open(wallet_path))['address']
    }, ctx.obj.get('output_format', 'table'))


@wallet.command()
@click.argument('name')
@click.option('--confirm', is_flag=True, help='Skip confirmation prompt')
@click.pass_context
def delete(ctx, name: str, confirm: bool):
    """Delete a wallet"""
    wallet_dir = ctx.obj['wallet_dir']
    wallet_path = wallet_dir / f"{name}.json"
    
    if not wallet_path.exists():
        error(f"Wallet '{name}' does not exist")
        return
    
    if not confirm:
        if not click.confirm(f"Are you sure you want to delete wallet '{name}'? This cannot be undone."):
            return
    
    wallet_path.unlink()
    success(f"Wallet '{name}' deleted")
    
    # If deleted wallet was active, reset to default
    config_file = Path.home() / ".aitbc" / "config.yaml"
    if config_file.exists():
        import yaml
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f) or {}
        
        if config.get('active_wallet') == name:
            config['active_wallet'] = 'default'
            with open(config_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)


@wallet.command()
@click.argument('name')
@click.option('--destination', help='Destination path for backup file')
@click.pass_context
def backup(ctx, name: str, destination: Optional[str]):
    """Backup a wallet"""
    wallet_dir = ctx.obj['wallet_dir']
    wallet_path = wallet_dir / f"{name}.json"
    
    if not wallet_path.exists():
        error(f"Wallet '{name}' does not exist")
        return
    
    if not destination:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = f"{name}_backup_{timestamp}.json"
    
    # Copy wallet file
    shutil.copy2(wallet_path, destination)
    success(f"Wallet '{name}' backed up to '{destination}'")
    output({
        "wallet": name,
        "backup_path": destination,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })


@wallet.command()
@click.argument('backup_path')
@click.argument('name')
@click.option('--force', is_flag=True, help='Override existing wallet')
@click.pass_context
def restore(ctx, backup_path: str, name: str, force: bool):
    """Restore a wallet from backup"""
    wallet_dir = ctx.obj['wallet_dir']
    wallet_path = wallet_dir / f"{name}.json"
    
    if wallet_path.exists() and not force:
        error(f"Wallet '{name}' already exists. Use --force to override.")
        return
    
    if not Path(backup_path).exists():
        error(f"Backup file '{backup_path}' not found")
        return
    
    # Load and verify backup
    with open(backup_path, 'r') as f:
        wallet_data = json.load(f)
    
    # Update wallet name if needed
    wallet_data['wallet_id'] = name
    wallet_data['restored_at'] = datetime.utcnow().isoformat() + "Z"
    
    # Save restored wallet
    with open(wallet_path, 'w') as f:
        json.dump(wallet_data, f, indent=2)
    
    success(f"Wallet '{name}' restored from backup")
    output({
        "wallet": name,
        "restored_from": backup_path,
        "address": wallet_data['address']
    })


@wallet.command()
@click.pass_context
def info(ctx):
    """Show current wallet information"""
    wallet_name = ctx.obj['wallet_name']
    wallet_path = ctx.obj['wallet_path']
    config_file = Path.home() / ".aitbc" / "config.yaml"
    
    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found. Use 'aitbc wallet create' to create one.")
        return
    
    with open(wallet_path, 'r') as f:
        wallet_data = json.load(f)
    
    # Get active wallet from config
    active_wallet = 'default'
    if config_file.exists():
        import yaml
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
            active_wallet = config.get('active_wallet', 'default')
    
    wallet_info = {
        "name": wallet_data['wallet_id'],
        "type": wallet_data.get('type', 'simple'),
        "address": wallet_data['address'],
        "public_key": wallet_data['public_key'],
        "created_at": wallet_data['created_at'],
        "active": wallet_data['wallet_id'] == active_wallet,
        "path": str(wallet_path)
    }
    
    if 'balance' in wallet_data:
        wallet_info['balance'] = wallet_data['balance']
    
    output(wallet_info, ctx.obj.get('output_format', 'table'))


@wallet.command()
@click.pass_context
def balance(ctx):
    """Check wallet balance"""
    wallet_name = ctx.obj['wallet_name']
    wallet_path = ctx.obj['wallet_path']
    config = ctx.obj.get('config')
    
    # Auto-create wallet if it doesn't exist
    if not wallet_path.exists():
        import secrets
        wallet_data = {
            "wallet_id": wallet_name,
            "type": "simple",
            "address": f"aitbc1{secrets.token_hex(20)}",
            "public_key": f"0x{secrets.token_hex(32)}",
            "private_key": f"0x{secrets.token_hex(32)}",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "balance": 0.0,
            "transactions": []
        }
        wallet_path.parent.mkdir(parents=True, exist_ok=True)
        with open(wallet_path, 'w') as f:
            json.dump(wallet_data, f, indent=2)
    else:
        with open(wallet_path, 'r') as f:
            wallet_data = json.load(f)
    
    # Try to get balance from blockchain if available
    if config:
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{config.coordinator_url.replace('/api', '')}/rpc/balance/{wallet_data['address']}",
                    timeout=5
                )
                
                if response.status_code == 200:
                    blockchain_balance = response.json().get('balance', 0)
                    output({
                        "wallet": wallet_name,
                        "address": wallet_data['address'],
                        "local_balance": wallet_data.get('balance', 0),
                        "blockchain_balance": blockchain_balance,
                        "synced": wallet_data.get('balance', 0) == blockchain_balance
                    }, ctx.obj.get('output_format', 'table'))
                    return
        except:
            pass
    
    # Fallback to local balance only
    output({
        "wallet": wallet_name,
        "address": wallet_data['address'],
        "balance": wallet_data.get('balance', 0),
        "note": "Local balance only (blockchain not accessible)"
    }, ctx.obj.get('output_format', 'table'))


@wallet.command()
@click.option("--limit", type=int, default=10, help="Number of transactions to show")
@click.pass_context
def history(ctx, limit: int):
    """Show transaction history"""
    wallet_name = ctx.obj['wallet_name']
    wallet_path = ctx.obj['wallet_path']
    
    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return
    
    with open(wallet_path, 'r') as f:
        wallet_data = json.load(f)
    
    transactions = wallet_data.get('transactions', [])[-limit:]
    
    # Format transactions
    formatted_txs = []
    for tx in transactions:
        formatted_txs.append({
            "type": tx['type'],
            "amount": tx['amount'],
            "description": tx.get('description', ''),
            "timestamp": tx['timestamp']
        })
    
    output({
        "wallet": wallet_name,
        "address": wallet_data['address'],
        "transactions": formatted_txs
    }, ctx.obj.get('output_format', 'table'))


@wallet.command()
@click.argument("amount", type=float)
@click.argument("job_id")
@click.option("--desc", help="Description of the work")
@click.pass_context
def earn(ctx, amount: float, job_id: str, desc: Optional[str]):
    """Add earnings from completed job"""
    wallet_name = ctx.obj['wallet_name']
    wallet_path = ctx.obj['wallet_path']
    
    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return
    
    with open(wallet_path, 'r') as f:
        wallet_data = json.load(f)
    
    # Add transaction
    transaction = {
        "type": "earn",
        "amount": amount,
        "job_id": job_id,
        "description": desc or f"Job {job_id}",
        "timestamp": datetime.now().isoformat()
    }
    
    wallet_data['transactions'].append(transaction)
    wallet_data['balance'] = wallet_data.get('balance', 0) + amount
    
    # Save wallet
    with open(wallet_path, 'w') as f:
        json.dump(wallet_data, f, indent=2)
    
    success(f"Earnings added: {amount} AITBC")
    output({
        "wallet": wallet_name,
        "amount": amount,
        "job_id": job_id,
        "new_balance": wallet_data['balance']
    }, ctx.obj.get('output_format', 'table'))


@wallet.command()
@click.argument("amount", type=float)
@click.argument("description")
@click.pass_context
def spend(ctx, amount: float, description: str):
    """Spend AITBC"""
    wallet_name = ctx.obj['wallet_name']
    wallet_path = ctx.obj['wallet_path']
    
    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return
    
    with open(wallet_path, 'r') as f:
        wallet_data = json.load(f)
    
    balance = wallet_data.get('balance', 0)
    if balance < amount:
        error(f"Insufficient balance. Available: {balance}, Required: {amount}")
        ctx.exit(1)
        return
    
    # Add transaction
    transaction = {
        "type": "spend",
        "amount": -amount,
        "description": description,
        "timestamp": datetime.now().isoformat()
    }
    
    wallet_data['transactions'].append(transaction)
    wallet_data['balance'] = balance - amount
    
    # Save wallet
    with open(wallet_path, 'w') as f:
        json.dump(wallet_data, f, indent=2)
    
    success(f"Spent: {amount} AITBC")
    output({
        "wallet": wallet_name,
        "amount": amount,
        "description": description,
        "new_balance": wallet_data['balance']
    }, ctx.obj.get('output_format', 'table'))


@wallet.command()
@click.pass_context
def address(ctx):
    """Show wallet address"""
    wallet_name = ctx.obj['wallet_name']
    wallet_path = ctx.obj['wallet_path']
    
    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return
    
    with open(wallet_path, 'r') as f:
        wallet_data = json.load(f)
    
    output({
        "wallet": wallet_name,
        "address": wallet_data['address']
    }, ctx.obj.get('output_format', 'table'))


@wallet.command()
@click.argument("to_address")
@click.argument("amount", type=float)
@click.option("--description", help="Transaction description")
@click.pass_context
def send(ctx, to_address: str, amount: float, description: Optional[str]):
    """Send AITBC to another address"""
    wallet_name = ctx.obj['wallet_name']
    wallet_path = ctx.obj['wallet_path']
    config = ctx.obj.get('config')
    
    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return
    
    with open(wallet_path, 'r') as f:
        wallet_data = json.load(f)
    
    balance = wallet_data.get('balance', 0)
    if balance < amount:
        error(f"Insufficient balance. Available: {balance}, Required: {amount}")
        ctx.exit(1)
        return
    
    # Try to send via blockchain
    if config:
        try:
            with httpx.Client() as client:
                response = client.post(
                    f"{config.coordinator_url.replace('/api', '')}/rpc/transactions",
                    json={
                        "from": wallet_data['address'],
                        "to": to_address,
                        "amount": amount,
                        "description": description or ""
                    },
                    headers={"X-Api-Key": getattr(config, 'api_key', '') or ""}
                )
                
                if response.status_code == 201:
                    tx = response.json()
                    # Update local wallet
                    transaction = {
                        "type": "send",
                        "amount": -amount,
                        "to_address": to_address,
                        "tx_hash": tx.get('hash'),
                        "description": description or "",
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    wallet_data['transactions'].append(transaction)
                    wallet_data['balance'] = balance - amount
                    
                    with open(wallet_path, 'w') as f:
                        json.dump(wallet_data, f, indent=2)
                    
                    success(f"Sent {amount} AITBC to {to_address}")
                    output({
                        "wallet": wallet_name,
                        "tx_hash": tx.get('hash'),
                        "amount": amount,
                        "to": to_address,
                        "new_balance": wallet_data['balance']
                    }, ctx.obj.get('output_format', 'table'))
                    return
        except Exception as e:
            error(f"Network error: {e}")
    
    # Fallback: just record locally
    transaction = {
        "type": "send",
        "amount": -amount,
        "to_address": to_address,
        "description": description or "",
        "timestamp": datetime.now().isoformat(),
        "pending": True
    }
    
    wallet_data['transactions'].append(transaction)
    wallet_data['balance'] = balance - amount
    
    with open(wallet_path, 'w') as f:
        json.dump(wallet_data, f, indent=2)
    
    output({
        "wallet": wallet_name,
        "amount": amount,
        "to": to_address,
        "new_balance": wallet_data['balance'],
        "note": "Transaction recorded locally (pending blockchain confirmation)"
    }, ctx.obj.get('output_format', 'table'))


@wallet.command()
@click.argument("to_address")
@click.argument("amount", type=float)
@click.option("--description", help="Transaction description")
@click.pass_context
def request_payment(ctx, to_address: str, amount: float, description: Optional[str]):
    """Request payment from another address"""
    wallet_name = ctx.obj['wallet_name']
    wallet_path = ctx.obj['wallet_path']
    
    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return
    
    with open(wallet_path, 'r') as f:
        wallet_data = json.load(f)
    
    # Create payment request
    request = {
        "from_address": to_address,
        "to_address": wallet_data['address'],
        "amount": amount,
        "description": description or "",
        "timestamp": datetime.now().isoformat()
    }
    
    output({
        "wallet": wallet_name,
        "payment_request": request,
        "note": "Share this with the payer to request payment"
    }, ctx.obj.get('output_format', 'table'))


@wallet.command()
@click.pass_context
def stats(ctx):
    """Show wallet statistics"""
    wallet_name = ctx.obj['wallet_name']
    wallet_path = ctx.obj['wallet_path']
    
    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return
    
    with open(wallet_path, 'r') as f:
        wallet_data = json.load(f)
    
    transactions = wallet_data.get('transactions', [])
    
    # Calculate stats
    total_earned = sum(tx['amount'] for tx in transactions if tx['type'] == 'earn' and tx['amount'] > 0)
    total_spent = sum(abs(tx['amount']) for tx in transactions if tx['type'] in ['spend', 'send'] and tx['amount'] < 0)
    jobs_completed = len([tx for tx in transactions if tx['type'] == 'earn'])
    
    output({
        "wallet": wallet_name,
        "address": wallet_data['address'],
        "current_balance": wallet_data.get('balance', 0),
        "total_earned": total_earned,
        "total_spent": total_spent,
        "jobs_completed": jobs_completed,
        "transaction_count": len(transactions),
        "wallet_created": wallet_data.get('created_at')
    }, ctx.obj.get('output_format', 'table'))


@wallet.command()
@click.argument("amount", type=float)
@click.option("--duration", type=int, default=30, help="Staking duration in days")
@click.pass_context
def stake(ctx, amount: float, duration: int):
    """Stake AITBC tokens"""
    wallet_name = ctx.obj['wallet_name']
    wallet_path = ctx.obj['wallet_path']

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    with open(wallet_path, 'r') as f:
        wallet_data = json.load(f)

    balance = wallet_data.get('balance', 0)
    if balance < amount:
        error(f"Insufficient balance. Available: {balance}, Required: {amount}")
        ctx.exit(1)
        return

    # Record stake
    stake_id = f"stake_{int(datetime.now().timestamp())}"
    stake_record = {
        "stake_id": stake_id,
        "amount": amount,
        "duration_days": duration,
        "start_date": datetime.now().isoformat(),
        "end_date": (datetime.now() + timedelta(days=duration)).isoformat(),
        "status": "active",
        "apy": 5.0 + (duration / 30) * 1.5  # Higher APY for longer stakes
    }

    staking = wallet_data.setdefault('staking', [])
    staking.append(stake_record)
    wallet_data['balance'] = balance - amount

    # Add transaction
    wallet_data['transactions'].append({
        "type": "stake",
        "amount": -amount,
        "stake_id": stake_id,
        "description": f"Staked {amount} AITBC for {duration} days",
        "timestamp": datetime.now().isoformat()
    })

    with open(wallet_path, 'w') as f:
        json.dump(wallet_data, f, indent=2)

    success(f"Staked {amount} AITBC for {duration} days")
    output({
        "wallet": wallet_name,
        "stake_id": stake_id,
        "amount": amount,
        "duration_days": duration,
        "apy": stake_record['apy'],
        "new_balance": wallet_data['balance']
    }, ctx.obj.get('output_format', 'table'))


@wallet.command()
@click.argument("stake_id")
@click.pass_context
def unstake(ctx, stake_id: str):
    """Unstake AITBC tokens"""
    wallet_name = ctx.obj['wallet_name']
    wallet_path = ctx.obj['wallet_path']

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    with open(wallet_path, 'r') as f:
        wallet_data = json.load(f)

    staking = wallet_data.get('staking', [])
    stake_record = next((s for s in staking if s['stake_id'] == stake_id and s['status'] == 'active'), None)

    if not stake_record:
        error(f"Active stake '{stake_id}' not found")
        ctx.exit(1)
        return

    # Calculate rewards
    start = datetime.fromisoformat(stake_record['start_date'])
    days_staked = max(1, (datetime.now() - start).days)
    daily_rate = stake_record['apy'] / 100 / 365
    rewards = stake_record['amount'] * daily_rate * days_staked

    # Return principal + rewards
    returned = stake_record['amount'] + rewards
    wallet_data['balance'] = wallet_data.get('balance', 0) + returned
    stake_record['status'] = 'completed'
    stake_record['rewards'] = rewards
    stake_record['completed_date'] = datetime.now().isoformat()

    # Add transaction
    wallet_data['transactions'].append({
        "type": "unstake",
        "amount": returned,
        "stake_id": stake_id,
        "rewards": rewards,
        "description": f"Unstaked {stake_record['amount']} AITBC + {rewards:.4f} rewards",
        "timestamp": datetime.now().isoformat()
    })

    with open(wallet_path, 'w') as f:
        json.dump(wallet_data, f, indent=2)

    success(f"Unstaked {stake_record['amount']} AITBC + {rewards:.4f} rewards")
    output({
        "wallet": wallet_name,
        "stake_id": stake_id,
        "principal": stake_record['amount'],
        "rewards": rewards,
        "total_returned": returned,
        "days_staked": days_staked,
        "new_balance": wallet_data['balance']
    }, ctx.obj.get('output_format', 'table'))


@wallet.command(name="staking-info")
@click.pass_context
def staking_info(ctx):
    """Show staking information"""
    wallet_name = ctx.obj['wallet_name']
    wallet_path = ctx.obj['wallet_path']

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    with open(wallet_path, 'r') as f:
        wallet_data = json.load(f)

    staking = wallet_data.get('staking', [])
    active_stakes = [s for s in staking if s['status'] == 'active']
    completed_stakes = [s for s in staking if s['status'] == 'completed']

    total_staked = sum(s['amount'] for s in active_stakes)
    total_rewards = sum(s.get('rewards', 0) for s in completed_stakes)

    output({
        "wallet": wallet_name,
        "total_staked": total_staked,
        "total_rewards_earned": total_rewards,
        "active_stakes": len(active_stakes),
        "completed_stakes": len(completed_stakes),
        "stakes": [
            {
                "stake_id": s['stake_id'],
                "amount": s['amount'],
                "apy": s['apy'],
                "duration_days": s['duration_days'],
                "status": s['status'],
                "start_date": s['start_date']
            }
            for s in staking
        ]
    }, ctx.obj.get('output_format', 'table'))


@wallet.command(name="multisig-create")
@click.argument("signers", nargs=-1, required=True)
@click.option("--threshold", type=int, required=True, help="Required signatures to approve")
@click.option("--name", required=True, help="Multisig wallet name")
@click.pass_context
def multisig_create(ctx, signers: tuple, threshold: int, name: str):
    """Create a multi-signature wallet"""
    wallet_dir = ctx.obj.get('wallet_dir', Path.home() / ".aitbc" / "wallets")
    wallet_dir.mkdir(parents=True, exist_ok=True)
    multisig_path = wallet_dir / f"{name}_multisig.json"

    if multisig_path.exists():
        error(f"Multisig wallet '{name}' already exists")
        return

    if threshold > len(signers):
        error(f"Threshold ({threshold}) cannot exceed number of signers ({len(signers)})")
        return

    import secrets
    multisig_data = {
        "wallet_id": name,
        "type": "multisig",
        "address": f"aitbc1ms{secrets.token_hex(18)}",
        "signers": list(signers),
        "threshold": threshold,
        "created_at": datetime.now().isoformat(),
        "balance": 0.0,
        "transactions": [],
        "pending_transactions": []
    }

    with open(multisig_path, "w") as f:
        json.dump(multisig_data, f, indent=2)

    success(f"Multisig wallet '{name}' created ({threshold}-of-{len(signers)})")
    output({
        "name": name,
        "address": multisig_data["address"],
        "signers": list(signers),
        "threshold": threshold
    }, ctx.obj.get('output_format', 'table'))


@wallet.command(name="multisig-propose")
@click.option("--wallet", "wallet_name", required=True, help="Multisig wallet name")
@click.argument("to_address")
@click.argument("amount", type=float)
@click.option("--description", help="Transaction description")
@click.pass_context
def multisig_propose(ctx, wallet_name: str, to_address: str, amount: float, description: Optional[str]):
    """Propose a multisig transaction"""
    wallet_dir = ctx.obj.get('wallet_dir', Path.home() / ".aitbc" / "wallets")
    multisig_path = wallet_dir / f"{wallet_name}_multisig.json"

    if not multisig_path.exists():
        error(f"Multisig wallet '{wallet_name}' not found")
        return

    with open(multisig_path) as f:
        ms_data = json.load(f)

    if ms_data.get("balance", 0) < amount:
        error(f"Insufficient balance. Available: {ms_data['balance']}, Required: {amount}")
        ctx.exit(1)
        return

    import secrets
    tx_id = f"mstx_{secrets.token_hex(8)}"
    pending_tx = {
        "tx_id": tx_id,
        "to": to_address,
        "amount": amount,
        "description": description or "",
        "proposed_at": datetime.now().isoformat(),
        "proposed_by": os.environ.get("USER", "unknown"),
        "signatures": [],
        "status": "pending"
    }

    ms_data.setdefault("pending_transactions", []).append(pending_tx)
    with open(multisig_path, "w") as f:
        json.dump(ms_data, f, indent=2)

    success(f"Transaction proposed: {tx_id}")
    output({
        "tx_id": tx_id,
        "to": to_address,
        "amount": amount,
        "signatures_needed": ms_data["threshold"],
        "status": "pending"
    }, ctx.obj.get('output_format', 'table'))


@wallet.command(name="multisig-sign")
@click.option("--wallet", "wallet_name", required=True, help="Multisig wallet name")
@click.argument("tx_id")
@click.option("--signer", required=True, help="Signer address")
@click.pass_context
def multisig_sign(ctx, wallet_name: str, tx_id: str, signer: str):
    """Sign a pending multisig transaction"""
    wallet_dir = ctx.obj.get('wallet_dir', Path.home() / ".aitbc" / "wallets")
    multisig_path = wallet_dir / f"{wallet_name}_multisig.json"

    if not multisig_path.exists():
        error(f"Multisig wallet '{wallet_name}' not found")
        return

    with open(multisig_path) as f:
        ms_data = json.load(f)

    if signer not in ms_data.get("signers", []):
        error(f"'{signer}' is not an authorized signer")
        ctx.exit(1)
        return

    pending = ms_data.get("pending_transactions", [])
    tx = next((t for t in pending if t["tx_id"] == tx_id and t["status"] == "pending"), None)

    if not tx:
        error(f"Pending transaction '{tx_id}' not found")
        ctx.exit(1)
        return

    if signer in tx["signatures"]:
        error(f"'{signer}' has already signed this transaction")
        return

    tx["signatures"].append(signer)

    # Check if threshold met
    if len(tx["signatures"]) >= ms_data["threshold"]:
        tx["status"] = "approved"
        # Execute the transaction
        ms_data["balance"] = ms_data.get("balance", 0) - tx["amount"]
        ms_data["transactions"].append({
            "type": "multisig_send",
            "amount": -tx["amount"],
            "to": tx["to"],
            "tx_id": tx["tx_id"],
            "signatures": tx["signatures"],
            "timestamp": datetime.now().isoformat()
        })
        success(f"Transaction {tx_id} approved and executed!")
    else:
        success(f"Signed. {len(tx['signatures'])}/{ms_data['threshold']} signatures collected")

    with open(multisig_path, "w") as f:
        json.dump(ms_data, f, indent=2)

    output({
        "tx_id": tx_id,
        "signatures": tx["signatures"],
        "threshold": ms_data["threshold"],
        "status": tx["status"]
    }, ctx.obj.get('output_format', 'table'))


@wallet.command(name="liquidity-stake")
@click.argument("amount", type=float)
@click.option("--pool", default="main", help="Liquidity pool name")
@click.option("--lock-days", type=int, default=0, help="Lock period in days (higher APY)")
@click.pass_context
def liquidity_stake(ctx, amount: float, pool: str, lock_days: int):
    """Stake tokens into a liquidity pool"""
    wallet_path = ctx.obj.get('wallet_path')
    if not wallet_path or not Path(wallet_path).exists():
        error("Wallet not found")
        ctx.exit(1)
        return

    with open(wallet_path) as f:
        wallet_data = json.load(f)

    balance = wallet_data.get('balance', 0)
    if balance < amount:
        error(f"Insufficient balance. Available: {balance}, Required: {amount}")
        ctx.exit(1)
        return

    # APY tiers based on lock period
    if lock_days >= 90:
        apy = 12.0
        tier = "platinum"
    elif lock_days >= 30:
        apy = 8.0
        tier = "gold"
    elif lock_days >= 7:
        apy = 5.0
        tier = "silver"
    else:
        apy = 3.0
        tier = "bronze"

    import secrets
    stake_id = f"liq_{secrets.token_hex(6)}"
    now = datetime.now()

    liq_record = {
        "stake_id": stake_id,
        "pool": pool,
        "amount": amount,
        "apy": apy,
        "tier": tier,
        "lock_days": lock_days,
        "start_date": now.isoformat(),
        "unlock_date": (now + timedelta(days=lock_days)).isoformat() if lock_days > 0 else None,
        "status": "active"
    }

    wallet_data.setdefault('liquidity', []).append(liq_record)
    wallet_data['balance'] = balance - amount

    wallet_data['transactions'].append({
        "type": "liquidity_stake",
        "amount": -amount,
        "pool": pool,
        "stake_id": stake_id,
        "timestamp": now.isoformat()
    })

    with open(wallet_path, "w") as f:
        json.dump(wallet_data, f, indent=2)

    success(f"Staked {amount} AITBC into '{pool}' pool ({tier} tier, {apy}% APY)")
    output({
        "stake_id": stake_id,
        "pool": pool,
        "amount": amount,
        "apy": apy,
        "tier": tier,
        "lock_days": lock_days,
        "new_balance": wallet_data['balance']
    }, ctx.obj.get('output_format', 'table'))


@wallet.command(name="liquidity-unstake")
@click.argument("stake_id")
@click.pass_context
def liquidity_unstake(ctx, stake_id: str):
    """Withdraw from a liquidity pool with rewards"""
    wallet_path = ctx.obj.get('wallet_path')
    if not wallet_path or not Path(wallet_path).exists():
        error("Wallet not found")
        ctx.exit(1)
        return

    with open(wallet_path) as f:
        wallet_data = json.load(f)

    liquidity = wallet_data.get('liquidity', [])
    record = next((r for r in liquidity if r["stake_id"] == stake_id and r["status"] == "active"), None)

    if not record:
        error(f"Active liquidity stake '{stake_id}' not found")
        ctx.exit(1)
        return

    # Check lock period
    if record.get("unlock_date"):
        unlock = datetime.fromisoformat(record["unlock_date"])
        if datetime.now() < unlock:
            error(f"Stake is locked until {record['unlock_date']}")
            ctx.exit(1)
            return

    # Calculate rewards
    start = datetime.fromisoformat(record["start_date"])
    days_staked = max((datetime.now() - start).total_seconds() / 86400, 0.001)
    rewards = record["amount"] * (record["apy"] / 100) * (days_staked / 365)
    total = record["amount"] + rewards

    record["status"] = "completed"
    record["end_date"] = datetime.now().isoformat()
    record["rewards"] = round(rewards, 6)

    wallet_data['balance'] = wallet_data.get('balance', 0) + total

    wallet_data['transactions'].append({
        "type": "liquidity_unstake",
        "amount": total,
        "principal": record["amount"],
        "rewards": round(rewards, 6),
        "pool": record["pool"],
        "stake_id": stake_id,
        "timestamp": datetime.now().isoformat()
    })

    with open(wallet_path, "w") as f:
        json.dump(wallet_data, f, indent=2)

    success(f"Withdrawn {total:.6f} AITBC (principal: {record['amount']}, rewards: {rewards:.6f})")
    output({
        "stake_id": stake_id,
        "pool": record["pool"],
        "principal": record["amount"],
        "rewards": round(rewards, 6),
        "total_returned": round(total, 6),
        "days_staked": round(days_staked, 2),
        "apy": record["apy"],
        "new_balance": round(wallet_data['balance'], 6)
    }, ctx.obj.get('output_format', 'table'))


@wallet.command()
@click.pass_context
def rewards(ctx):
    """View all earned rewards (staking + liquidity)"""
    wallet_path = ctx.obj.get('wallet_path')
    if not wallet_path or not Path(wallet_path).exists():
        error("Wallet not found")
        ctx.exit(1)
        return

    with open(wallet_path) as f:
        wallet_data = json.load(f)

    staking = wallet_data.get('staking', [])
    liquidity = wallet_data.get('liquidity', [])

    # Staking rewards
    staking_rewards = sum(s.get('rewards', 0) for s in staking if s.get('status') == 'completed')
    active_staking = sum(s['amount'] for s in staking if s.get('status') == 'active')

    # Liquidity rewards
    liq_rewards = sum(r.get('rewards', 0) for r in liquidity if r.get('status') == 'completed')
    active_liquidity = sum(r['amount'] for r in liquidity if r.get('status') == 'active')

    # Estimate pending rewards for active positions
    pending_staking = 0
    for s in staking:
        if s.get('status') == 'active':
            start = datetime.fromisoformat(s['start_date'])
            days = max((datetime.now() - start).total_seconds() / 86400, 0)
            pending_staking += s['amount'] * (s['apy'] / 100) * (days / 365)

    pending_liquidity = 0
    for r in liquidity:
        if r.get('status') == 'active':
            start = datetime.fromisoformat(r['start_date'])
            days = max((datetime.now() - start).total_seconds() / 86400, 0)
            pending_liquidity += r['amount'] * (r['apy'] / 100) * (days / 365)

    output({
        "staking_rewards_earned": round(staking_rewards, 6),
        "staking_rewards_pending": round(pending_staking, 6),
        "staking_active_amount": active_staking,
        "liquidity_rewards_earned": round(liq_rewards, 6),
        "liquidity_rewards_pending": round(pending_liquidity, 6),
        "liquidity_active_amount": active_liquidity,
        "total_earned": round(staking_rewards + liq_rewards, 6),
        "total_pending": round(pending_staking + pending_liquidity, 6),
        "total_staked": active_staking + active_liquidity
    }, ctx.obj.get('output_format', 'table'))
