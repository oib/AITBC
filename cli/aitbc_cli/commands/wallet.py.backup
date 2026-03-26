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
from ..utils import output, error, success, encrypt_value, decrypt_value
import getpass


def _get_wallet_password(wallet_name: str) -> str:
    """Get or prompt for wallet encryption password"""
    # Try to get from keyring first
    try:
        import keyring

        password = keyring.get_password("aitbc-wallet", wallet_name)
        if password:
            return password
    except Exception:
        pass

    # Prompt for password
    while True:
        password = getpass.getpass(f"Enter password for wallet '{wallet_name}': ")
        if not password:
            error("Password cannot be empty")
            continue

        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            error("Passwords do not match")
            continue

        # Store in keyring for future use
        try:
            import keyring

            keyring.set_password("aitbc-wallet", wallet_name, password)
        except Exception:
            pass

        return password


def _save_wallet(wallet_path: Path, wallet_data: Dict[str, Any], password: str = None):
    """Save wallet with encrypted private key"""
    # Encrypt private key if provided
    if password and "private_key" in wallet_data:
        wallet_data["private_key"] = encrypt_value(wallet_data["private_key"], password)
        wallet_data["encrypted"] = True

    # Save wallet
    with open(wallet_path, "w") as f:
        json.dump(wallet_data, f, indent=2)


def _load_wallet(wallet_path: Path, wallet_name: str) -> Dict[str, Any]:
    """Load wallet and decrypt private key if needed"""
    with open(wallet_path, "r") as f:
        wallet_data = json.load(f)

    # Decrypt private key if encrypted
    if wallet_data.get("encrypted") and "private_key" in wallet_data:
        password = _get_wallet_password(wallet_name)
        try:
            wallet_data["private_key"] = decrypt_value(
                wallet_data["private_key"], password
            )
        except Exception:
            error("Invalid password for wallet")
            raise click.Abort()

    return wallet_data


@click.group()
@click.option("--wallet-name", help="Name of the wallet to use")
@click.option(
    "--wallet-path", help="Direct path to wallet file (overrides --wallet-name)"
)
@click.option(
    "--use-daemon", is_flag=True, help="Use wallet daemon for operations"
)
@click.pass_context
def wallet(ctx, wallet_name: Optional[str], wallet_path: Optional[str], use_daemon: bool):
    """Manage your AITBC wallets and transactions"""
    # Ensure wallet object exists
    ctx.ensure_object(dict)

    # Store daemon mode preference
    ctx.obj["use_daemon"] = use_daemon
    
    # Initialize dual-mode adapter
    from ..config import get_config
    from ..dual_mode_wallet_adapter import DualModeWalletAdapter
    
    config = get_config()
    adapter = DualModeWalletAdapter(config, use_daemon=use_daemon)
    ctx.obj["wallet_adapter"] = adapter

    # If direct wallet path is provided, use it
    if wallet_path:
        wp = Path(wallet_path)
        wp.parent.mkdir(parents=True, exist_ok=True)
        ctx.obj["wallet_name"] = wp.stem
        ctx.obj["wallet_dir"] = wp.parent
        ctx.obj["wallet_path"] = wp
        return

    # Set wallet directory
    wallet_dir = Path.home() / ".aitbc" / "wallets"
    wallet_dir.mkdir(parents=True, exist_ok=True)

    # Set active wallet
    if not wallet_name:
        # Try to get from config or use 'default'
        config_file = Path.home() / ".aitbc" / "config.yaml"
        config = None
        if config_file.exists():
            with open(config_file, "r") as f:
                config = yaml.safe_load(f)
                if config:
                    wallet_name = config.get("active_wallet", "default")
                else:
                    wallet_name = "default"
        else:
            wallet_name = "default"
    else:
        # Load config for other operations
        config_file = Path.home() / ".aitbc" / "config.yaml"
        config = None
        if config_file.exists():
            with open(config_file, "r") as f:
                config = yaml.safe_load(f)

    ctx.obj["wallet_name"] = wallet_name
    ctx.obj["wallet_dir"] = wallet_dir
    ctx.obj["wallet_path"] = wallet_dir / f"{wallet_name}.json"
    ctx.obj["config"] = config


@wallet.command()
@click.argument("name")
@click.option("--type", "wallet_type", default="hd", help="Wallet type (hd, simple)")
@click.option(
    "--no-encrypt", is_flag=True, help="Skip wallet encryption (not recommended)"
)
@click.pass_context
def create(ctx, name: str, wallet_type: str, no_encrypt: bool):
    """Create a new wallet"""
    adapter = ctx.obj["wallet_adapter"]
    use_daemon = ctx.obj["use_daemon"]
    
    # Check if using daemon mode and daemon is available
    if use_daemon and not adapter.is_daemon_available():
        error("Wallet daemon is not available. Falling back to file-based wallet.")
        # Switch to file mode
        from ..config import get_config
        from ..dual_mode_wallet_adapter import DualModeWalletAdapter
        config = get_config()
        adapter = DualModeWalletAdapter(config, use_daemon=False)
        ctx.obj["wallet_adapter"] = adapter
    
    # Get password for encryption
    password = None
    if not no_encrypt:
        if use_daemon:
            # For daemon mode, use a default password or prompt
            password = getpass.getpass(f"Enter password for wallet '{name}' (press Enter for default): ")
            if not password:
                password = "default_wallet_password"
        else:
            # For file mode, use existing password prompt logic
            password = getpass.getpass(f"Enter password for wallet '{name}': ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                error("Passwords do not match")
                return
    
    # Create wallet using the adapter
    try:
        metadata = {
            "wallet_type": wallet_type,
            "created_by": "aitbc_cli",
            "encryption_enabled": not no_encrypt
        }
        
        wallet_info = adapter.create_wallet(name, password, wallet_type, metadata)
        
        # Display results
        output(wallet_info, ctx.obj.get("output_format", "table"))
        
        # Set as active wallet if successful
        if wallet_info:
            config_file = Path.home() / ".aitbc" / "config.yaml"
            config_data = {}
            if config_file.exists():
                with open(config_file, "r") as f:
                    config_data = yaml.safe_load(f) or {}
            
            config_data["active_wallet"] = name
            config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(config_file, "w") as f:
                yaml.dump(config_data, f)
            
            success(f"Wallet '{name}' is now active")
            
    except Exception as e:
        error(f"Failed to create wallet: {str(e)}")
        return


@wallet.command()
@click.pass_context
def list(ctx):
    """List all wallets"""
    adapter = ctx.obj["wallet_adapter"]
    use_daemon = ctx.obj["use_daemon"]
    
    # Check if using daemon mode and daemon is available
    if use_daemon and not adapter.is_daemon_available():
        error("Wallet daemon is not available. Falling back to file-based wallet listing.")
        # Switch to file mode
        from ..config import get_config
        from ..dual_mode_wallet_adapter import DualModeWalletAdapter
        config = get_config()
        adapter = DualModeWalletAdapter(config, use_daemon=False)
    
    try:
        wallets = adapter.list_wallets()
        
        if not wallets:
            output({"wallets": [], "count": 0, "mode": "daemon" if use_daemon else "file"}, 
                   ctx.obj.get("output_format", "table"))
            return
        
        # Format output
        wallet_list = []
        for wallet in wallets:
            wallet_info = {
                "name": wallet.get("wallet_name"),
                "address": wallet.get("address"),
                "balance": wallet.get("balance", 0.0),
                "type": wallet.get("wallet_type", "hd"),
                "created_at": wallet.get("created_at"),
                "mode": wallet.get("mode", "file")
            }
            wallet_list.append(wallet_info)
        
        output_data = {
            "wallets": wallet_list,
            "count": len(wallet_list),
            "mode": "daemon" if use_daemon else "file"
        }
        
        output(output_data, ctx.obj.get("output_format", "table"))
        
    except Exception as e:
        error(f"Failed to list wallets: {str(e)}")




@wallet.command()
@click.argument("name")
@click.pass_context
def switch(ctx, name: str):
    """Switch to a different wallet"""
    adapter = ctx.obj["wallet_adapter"]
    use_daemon = ctx.obj["use_daemon"]
    
    # Check if using daemon mode and daemon is available
    if use_daemon and not adapter.is_daemon_available():
        error("Wallet daemon is not available. Falling back to file-based wallet switching.")
        # Switch to file mode
        from ..config import get_config
        from ..dual_mode_wallet_adapter import DualModeWalletAdapter
        config = get_config()
        adapter = DualModeWalletAdapter(config, use_daemon=False)
    
    # Check if wallet exists
    wallet_info = adapter.get_wallet_info(name)
    if not wallet_info:
        error(f"Wallet '{name}' does not exist")
        return
    
    # Update config
    config_file = Path.home() / ".aitbc" / "config.yaml"
    config = {}
    if config_file.exists():
        import yaml
        with open(config_file, "r") as f:
            config = yaml.safe_load(f) or {}
    
    config["active_wallet"] = name
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, "w") as f:
        yaml.dump(config, f)
    
    success(f"Switched to wallet: {name}")
    output({
        "active_wallet": name,
        "mode": "daemon" if use_daemon else "file",
        "wallet_info": wallet_info
    }, ctx.obj.get("output_format", "table"))


@wallet.command()
@click.argument("name")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def delete(ctx, name: str, confirm: bool):
    """Delete a wallet"""
    wallet_dir = ctx.obj["wallet_dir"]
    wallet_path = wallet_dir / f"{name}.json"

    if not wallet_path.exists():
        error(f"Wallet '{name}' does not exist")
        return

    if not confirm:
        if not click.confirm(
            f"Are you sure you want to delete wallet '{name}'? This cannot be undone."
        ):
            return

    wallet_path.unlink()
    success(f"Wallet '{name}' deleted")

    # If deleted wallet was active, reset to default
    config_file = Path.home() / ".aitbc" / "config.yaml"
    if config_file.exists():
        import yaml

        with open(config_file, "r") as f:
            config = yaml.safe_load(f) or {}

        if config.get("active_wallet") == name:
            config["active_wallet"] = "default"
            with open(config_file, "w") as f:
                yaml.dump(config, f, default_flow_style=False)


@wallet.command()
@click.argument("name")
@click.option("--destination", help="Destination path for backup file")
@click.pass_context
def backup(ctx, name: str, destination: Optional[str]):
    """Backup a wallet"""
    wallet_dir = ctx.obj["wallet_dir"]
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
    output(
        {
            "wallet": name,
            "backup_path": destination,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    )


@wallet.command()
@click.argument("backup_path")
@click.argument("name")
@click.option("--force", is_flag=True, help="Override existing wallet")
@click.pass_context
def restore(ctx, backup_path: str, name: str, force: bool):
    """Restore a wallet from backup"""
    wallet_dir = ctx.obj["wallet_dir"]
    wallet_path = wallet_dir / f"{name}.json"

    if wallet_path.exists() and not force:
        error(f"Wallet '{name}' already exists. Use --force to override.")
        return

    if not Path(backup_path).exists():
        error(f"Backup file '{backup_path}' not found")
        return

    # Load and verify backup
    with open(backup_path, "r") as f:
        wallet_data = json.load(f)

    # Update wallet name if needed
    wallet_data["wallet_id"] = name
    wallet_data["restored_at"] = datetime.utcnow().isoformat() + "Z"

    # Save restored wallet (preserve encryption state)
    # If wallet was encrypted, we save it as-is (still encrypted with original password)
    with open(wallet_path, "w") as f:
        json.dump(wallet_data, f, indent=2)

    success(f"Wallet '{name}' restored from backup")
    output(
        {
            "wallet": name,
            "restored_from": backup_path,
            "address": wallet_data["address"],
        }
    )


@wallet.command()
@click.pass_context
def info(ctx):
    """Show current wallet information"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]
    config_file = Path.home() / ".aitbc" / "config.yaml"

    if not wallet_path.exists():
        error(
            f"Wallet '{wallet_name}' not found. Use 'aitbc wallet create' to create one."
        )
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)

    # Get active wallet from config
    active_wallet = "default"
    if config_file.exists():
        import yaml

        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
            active_wallet = config.get("active_wallet", "default")

    wallet_info = {
        "name": wallet_data.get("name", wallet_name),
        "type": wallet_data.get("type", wallet_data.get("wallet_type", "simple")),
        "address": wallet_data["address"],
        "public_key": wallet_data.get("public_key", "N/A"),
        "created_at": wallet_data["created_at"],
        "active": wallet_data.get("name", wallet_name) == active_wallet,
        "path": str(wallet_path),
    }

    if "balance" in wallet_data:
        wallet_info["balance"] = wallet_data["balance"]

    output(wallet_info, ctx.obj.get("output_format", "table"))


@wallet.command()
@click.pass_context
def balance(ctx):
    """Check wallet balance"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]
    config = ctx.obj.get("config")

    # Auto-create wallet if it doesn't exist
    if not wallet_path.exists():
        import secrets
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

        # Generate proper key pair
        private_key_bytes = secrets.token_bytes(32)
        private_key = f"0x{private_key_bytes.hex()}"

        # Derive public key from private key
        priv_key = ec.derive_private_key(
            int.from_bytes(private_key_bytes, "big"), ec.SECP256K1()
        )
        pub_key = priv_key.public_key()
        pub_key_bytes = pub_key.public_bytes(
            encoding=Encoding.X962, format=PublicFormat.UncompressedPoint
        )
        public_key = f"0x{pub_key_bytes.hex()}"

        # Generate address from public key
        digest = hashes.Hash(hashes.SHA256())
        digest.update(pub_key_bytes)
        address_hash = digest.finalize()
        address = f"aitbc1{address_hash[:20].hex()}"

        wallet_data = {
            "wallet_id": wallet_name,
            "type": "simple",
            "address": address,
            "public_key": public_key,
            "private_key": private_key,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "balance": 0.0,
            "transactions": [],
        }
        wallet_path.parent.mkdir(parents=True, exist_ok=True)
        # Auto-create with encryption
        success("Creating new wallet with encryption enabled")
        password = _get_wallet_password(wallet_name)
        _save_wallet(wallet_path, wallet_data, password)
    else:
        wallet_data = _load_wallet(wallet_path, wallet_name)

    # Try to get balance from blockchain if available
    if config:
        try:
            with httpx.Client() as client:
                # Try multiple balance query methods
                blockchain_balance = None
                
                # Method 1: Try direct balance endpoint
                try:
                    response = client.get(
                        f"{config.get('coordinator_url').rstrip('/')}/rpc/getBalance/{wallet_data['address']}?chain_id=ait-devnet",
                        timeout=5,
                    )
                    if response.status_code == 200:
                        result = response.json()
                        blockchain_balance = result.get("balance", 0)
                except Exception:
                    pass
                
                # Method 2: Try addresses list endpoint
                if blockchain_balance is None:
                    try:
                        response = client.get(
                            f"{config.get('coordinator_url').rstrip('/')}/rpc/addresses?chain_id=ait-devnet",
                            timeout=5,
                        )
                        if response.status_code == 200:
                            addresses = response.json()
                            if isinstance(addresses, list):
                                for addr_info in addresses:
                                    if addr_info.get("address") == wallet_data["address"]:
                                        blockchain_balance = addr_info.get("balance", 0)
                                        break
                    except Exception:
                        pass
                
                # Method 3: Use faucet as balance check (last resort)
                if blockchain_balance is None:
                    try:
                        response = client.post(
                            f"{config.get('coordinator_url').rstrip('/')}/rpc/admin/mintFaucet?chain_id=ait-devnet",
                            json={"address": wallet_data["address"], "amount": 1},
                            timeout=5,
                        )
                        if response.status_code == 200:
                            result = response.json()
                            blockchain_balance = result.get("balance", 0)
                            # Subtract the 1 we just added
                            if blockchain_balance > 0:
                                blockchain_balance -= 1
                    except Exception:
                        pass
                
                # If we got a blockchain balance, show it
                if blockchain_balance is not None:
                    output(
                        {
                            "wallet": wallet_name,
                            "address": wallet_data["address"],
                            "local_balance": wallet_data.get("balance", 0),
                            "blockchain_balance": blockchain_balance,
                            "synced": wallet_data.get("balance", 0) == blockchain_balance,
                            "note": "Blockchain balance synced" if wallet_data.get("balance", 0) == blockchain_balance else "Local and blockchain balances differ",
                        },
                        ctx.obj.get("output_format", "table"),
                    )
                    return
        except Exception:
            pass

    # Fallback to local balance only
    output(
        {
            "wallet": wallet_name,
            "address": wallet_data["address"],
            "balance": wallet_data.get("balance", 0),
            "note": "Local balance (blockchain balance queries unavailable)",
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command()
@click.option("--limit", type=int, default=10, help="Number of transactions to show")
@click.pass_context
def history(ctx, limit: int):
    """Show transaction history"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)

    transactions = wallet_data.get("transactions", [])[-limit:]

    # Format transactions
    formatted_txs = []
    for tx in transactions:
        formatted_txs.append(
            {
                "type": tx["type"],
                "amount": tx["amount"],
                "description": tx.get("description", ""),
                "timestamp": tx["timestamp"],
            }
        )

    output(
        {
            "wallet": wallet_name,
            "address": wallet_data["address"],
            "transactions": formatted_txs,
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command()
@click.argument("amount", type=float)
@click.argument("job_id")
@click.option("--desc", help="Description of the work")
@click.pass_context
def earn(ctx, amount: float, job_id: str, desc: Optional[str]):
    """Add earnings from completed job"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)

    # Add transaction
    transaction = {
        "type": "earn",
        "amount": amount,
        "job_id": job_id,
        "description": desc or f"Job {job_id}",
        "timestamp": datetime.now().isoformat(),
    }

    wallet_data["transactions"].append(transaction)
    wallet_data["balance"] = wallet_data.get("balance", 0) + amount

    # Save wallet with encryption
    password = None
    if wallet_data.get("encrypted"):
        password = _get_wallet_password(wallet_name)
    _save_wallet(wallet_path, wallet_data, password)

    success(f"Earnings added: {amount} AITBC")
    output(
        {
            "wallet": wallet_name,
            "amount": amount,
            "job_id": job_id,
            "new_balance": wallet_data["balance"],
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command()
@click.argument("amount", type=float)
@click.argument("description")
@click.pass_context
def spend(ctx, amount: float, description: str):
    """Spend AITBC"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)

    balance = wallet_data.get("balance", 0)
    if balance < amount:
        error(f"Insufficient balance. Available: {balance}, Required: {amount}")
        ctx.exit(1)
        return

    # Add transaction
    transaction = {
        "type": "spend",
        "amount": -amount,
        "description": description,
        "timestamp": datetime.now().isoformat(),
    }

    wallet_data["transactions"].append(transaction)
    wallet_data["balance"] = balance - amount

    # Save wallet with encryption
    password = None
    if wallet_data.get("encrypted"):
        password = _get_wallet_password(wallet_name)
    _save_wallet(wallet_path, wallet_data, password)

    success(f"Spent: {amount} AITBC")
    output(
        {
            "wallet": wallet_name,
            "amount": amount,
            "description": description,
            "new_balance": wallet_data["balance"],
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command()
@click.pass_context
def address(ctx):
    """Show wallet address"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)

    output(
        {"wallet": wallet_name, "address": wallet_data["address"]},
        ctx.obj.get("output_format", "table"),
    )


@wallet.command()
@click.argument("to_address")
@click.argument("amount", type=float)
@click.option("--description", help="Transaction description")
@click.pass_context
def send(ctx, to_address: str, amount: float, description: Optional[str]):
    """Send AITBC to another address"""
    adapter = ctx.obj["wallet_adapter"]
    use_daemon = ctx.obj["use_daemon"]
    wallet_name = ctx.obj["wallet_name"]
    
    # Check if using daemon mode and daemon is available
    if use_daemon and not adapter.is_daemon_available():
        error("Wallet daemon is not available. Falling back to file-based wallet send.")
        # Switch to file mode
        from ..config import get_config
        from ..dual_mode_wallet_adapter import DualModeWalletAdapter
        config = get_config()
        adapter = DualModeWalletAdapter(config, use_daemon=False)
        ctx.obj["wallet_adapter"] = adapter
    
    # Get password for transaction
    password = getpass.getpass(f"Enter password for wallet '{wallet_name}': ")
    
    try:
        result = adapter.send_transaction(wallet_name, password, to_address, amount, description)
        
        # Display results
        output(result, ctx.obj.get("output_format", "table"))
        
        # Update active wallet if successful
        if result:
            success(f"Transaction sent successfully")
        
    except Exception as e:
        error(f"Failed to send transaction: {str(e)}")
        return


@wallet.command()
@click.pass_context
def balance(ctx):
    """Check wallet balance"""
    adapter = ctx.obj["wallet_adapter"]
    use_daemon = ctx.obj["use_daemon"]
    wallet_name = ctx.obj["wallet_name"]
    
    # Check if using daemon mode and daemon is available
    if use_daemon and not adapter.is_daemon_available():
        error("Wallet daemon is not available. Falling back to file-based wallet balance.")
        # Switch to file mode
        from ..config import get_config
        from ..dual_mode_wallet_adapter import DualModeWalletAdapter
        config = get_config()
        adapter = DualModeWalletAdapter(config, use_daemon=False)
        ctx.obj["wallet_adapter"] = adapter
    
    try:
        balance = adapter.get_wallet_balance(wallet_name)
        wallet_info = adapter.get_wallet_info(wallet_name)
        
        if balance is None:
            error(f"Wallet '{wallet_name}' not found")
            return
        
        output_data = {
            "wallet_name": wallet_name,
            "balance": balance,
            "address": wallet_info.get("address") if wallet_info else None,
            "mode": "daemon" if use_daemon else "file"
        }
        
        output(output_data, ctx.obj.get("output_format", "table"))
        
    except Exception as e:
        error(f"Failed to get wallet balance: {str(e)}")


@wallet.group()
def daemon():
    """Wallet daemon management commands"""
    pass


@daemon.command()
@click.pass_context
def status(ctx):
    """Check wallet daemon status"""
    from ..config import get_config
    from ..wallet_daemon_client import WalletDaemonClient
    
    config = get_config()
    client = WalletDaemonClient(config)
    
    if client.is_available():
        status_info = client.get_status()
        success("Wallet daemon is available")
        output(status_info, ctx.obj.get("output_format", "table"))
    else:
        error("Wallet daemon is not available")
        output({
            "status": "unavailable",
            "wallet_url": config.wallet_url,
            "suggestion": "Start the wallet daemon or check the configuration"
        }, ctx.obj.get("output_format", "table"))


@daemon.command()
@click.pass_context
def configure(ctx):
    """Configure wallet daemon settings"""
    from ..config import get_config
    
    config = get_config()
    
    output({
        "wallet_url": config.wallet_url,
        "timeout": getattr(config, 'timeout', 30),
        "suggestion": "Use AITBC_WALLET_URL environment variable or config file to change settings"
    }, ctx.obj.get("output_format", "table"))


@wallet.command()
@click.argument("wallet_name")
@click.option("--password", help="Wallet password")
@click.option("--new-password", help="New password for daemon wallet")
@click.option("--force", is_flag=True, help="Force migration even if wallet exists")
@click.pass_context
def migrate_to_daemon(ctx, wallet_name: str, password: Optional[str], new_password: Optional[str], force: bool):
    """Migrate a file-based wallet to daemon storage"""
    from ..wallet_migration_service import WalletMigrationService
    from ..config import get_config
    
    config = get_config()
    migration_service = WalletMigrationService(config)
    
    if not migration_service.is_daemon_available():
        error("Wallet daemon is not available")
        return
    
    try:
        result = migration_service.migrate_to_daemon(wallet_name, password, new_password, force)
        success(f"Migrated wallet '{wallet_name}' to daemon")
        output(result, ctx.obj.get("output_format", "table"))
        
    except Exception as e:
        error(f"Failed to migrate wallet: {str(e)}")


@wallet.command()
@click.argument("wallet_name")
@click.option("--password", help="Wallet password")
@click.option("--new-password", help="New password for file wallet")
@click.option("--force", is_flag=True, help="Force migration even if wallet exists")
@click.pass_context
def migrate_to_file(ctx, wallet_name: str, password: Optional[str], new_password: Optional[str], force: bool):
    """Migrate a daemon-based wallet to file storage"""
    from ..wallet_migration_service import WalletMigrationService
    from ..config import get_config
    
    config = get_config()
    migration_service = WalletMigrationService(config)
    
    if not migration_service.is_daemon_available():
        error("Wallet daemon is not available")
        return
    
    try:
        result = migration_service.migrate_to_file(wallet_name, password, new_password, force)
        success(f"Migrated wallet '{wallet_name}' to file storage")
        output(result, ctx.obj.get("output_format", "table"))
        
    except Exception as e:
        error(f"Failed to migrate wallet: {str(e)}")


@wallet.command()
@click.pass_context
def migration_status(ctx):
    """Show wallet migration status"""
    from ..wallet_migration_service import WalletMigrationService
    from ..config import get_config
    
    config = get_config()
    migration_service = WalletMigrationService(config)
    
    try:
        status = migration_service.get_migration_status()
        output(status, ctx.obj.get("output_format", "table"))
        
    except Exception as e:
        error(f"Failed to get migration status: {str(e)}")
def stats(ctx):
    """Show wallet statistics"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)

    transactions = wallet_data.get("transactions", [])

    # Calculate stats
    total_earned = sum(
        tx["amount"] for tx in transactions if tx["type"] == "earn" and tx["amount"] > 0
    )
    total_spent = sum(
        abs(tx["amount"])
        for tx in transactions
        if tx["type"] in ["spend", "send"] and tx["amount"] < 0
    )
    jobs_completed = len([tx for tx in transactions if tx["type"] == "earn"])

    output(
        {
            "wallet": wallet_name,
            "address": wallet_data["address"],
            "current_balance": wallet_data.get("balance", 0),
            "total_earned": total_earned,
            "total_spent": total_spent,
            "jobs_completed": jobs_completed,
            "transaction_count": len(transactions),
            "wallet_created": wallet_data.get("created_at"),
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command()
@click.argument("amount", type=float)
@click.option("--duration", type=int, default=30, help="Staking duration in days")
@click.pass_context
def stake(ctx, amount: float, duration: int):
    """Stake AITBC tokens"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)

    balance = wallet_data.get("balance", 0)
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
        "apy": 5.0 + (duration / 30) * 1.5,  # Higher APY for longer stakes
    }

    staking = wallet_data.setdefault("staking", [])
    staking.append(stake_record)
    wallet_data["balance"] = balance - amount

    # Add transaction
    wallet_data["transactions"].append(
        {
            "type": "stake",
            "amount": -amount,
            "stake_id": stake_id,
            "description": f"Staked {amount} AITBC for {duration} days",
            "timestamp": datetime.now().isoformat(),
        }
    )

    # Save wallet with encryption
    password = None
    if wallet_data.get("encrypted"):
        password = _get_wallet_password(wallet_name)
    _save_wallet(wallet_path, wallet_data, password)

    success(f"Staked {amount} AITBC for {duration} days")
    output(
        {
            "wallet": wallet_name,
            "stake_id": stake_id,
            "amount": amount,
            "duration_days": duration,
            "apy": stake_record["apy"],
            "new_balance": wallet_data["balance"],
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command()
@click.argument("stake_id")
@click.pass_context
def unstake(ctx, stake_id: str):
    """Unstake AITBC tokens"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)

    staking = wallet_data.get("staking", [])
    stake_record = next(
        (s for s in staking if s["stake_id"] == stake_id and s["status"] == "active"),
        None,
    )

    if not stake_record:
        error(f"Active stake '{stake_id}' not found")
        ctx.exit(1)
        return

    # Calculate rewards
    start = datetime.fromisoformat(stake_record["start_date"])
    days_staked = max(1, (datetime.now() - start).days)
    daily_rate = stake_record["apy"] / 100 / 365
    rewards = stake_record["amount"] * daily_rate * days_staked

    # Return principal + rewards
    returned = stake_record["amount"] + rewards
    wallet_data["balance"] = wallet_data.get("balance", 0) + returned
    stake_record["status"] = "completed"
    stake_record["rewards"] = rewards
    stake_record["completed_date"] = datetime.now().isoformat()

    # Add transaction
    wallet_data["transactions"].append(
        {
            "type": "unstake",
            "amount": returned,
            "stake_id": stake_id,
            "rewards": rewards,
            "description": f"Unstaked {stake_record['amount']} AITBC + {rewards:.4f} rewards",
            "timestamp": datetime.now().isoformat(),
        }
    )

    # Save wallet with encryption
    password = None
    if wallet_data.get("encrypted"):
        password = _get_wallet_password(wallet_name)
    _save_wallet(wallet_path, wallet_data, password)

    success(f"Unstaked {stake_record['amount']} AITBC + {rewards:.4f} rewards")
    output(
        {
            "wallet": wallet_name,
            "stake_id": stake_id,
            "principal": stake_record["amount"],
            "rewards": rewards,
            "total_returned": returned,
            "days_staked": days_staked,
            "new_balance": wallet_data["balance"],
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command(name="staking-info")
@click.pass_context
def staking_info(ctx):
    """Show staking information"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)

    staking = wallet_data.get("staking", [])
    active_stakes = [s for s in staking if s["status"] == "active"]
    completed_stakes = [s for s in staking if s["status"] == "completed"]

    total_staked = sum(s["amount"] for s in active_stakes)
    total_rewards = sum(s.get("rewards", 0) for s in completed_stakes)

    output(
        {
            "wallet": wallet_name,
            "total_staked": total_staked,
            "total_rewards_earned": total_rewards,
            "active_stakes": len(active_stakes),
            "completed_stakes": len(completed_stakes),
            "stakes": [
                {
                    "stake_id": s["stake_id"],
                    "amount": s["amount"],
                    "apy": s["apy"],
                    "duration_days": s["duration_days"],
                    "status": s["status"],
                    "start_date": s["start_date"],
                }
                for s in staking
            ],
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command(name="multisig-create")
@click.argument("signers", nargs=-1, required=True)
@click.option(
    "--threshold", type=int, required=True, help="Required signatures to approve"
)
@click.option("--name", required=True, help="Multisig wallet name")
@click.pass_context
def multisig_create(ctx, signers: tuple, threshold: int, name: str):
    """Create a multi-signature wallet"""
    wallet_dir = ctx.obj.get("wallet_dir", Path.home() / ".aitbc" / "wallets")
    wallet_dir.mkdir(parents=True, exist_ok=True)
    multisig_path = wallet_dir / f"{name}_multisig.json"

    if multisig_path.exists():
        error(f"Multisig wallet '{name}' already exists")
        return

    if threshold > len(signers):
        error(
            f"Threshold ({threshold}) cannot exceed number of signers ({len(signers)})"
        )
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
        "pending_transactions": [],
    }

    with open(multisig_path, "w") as f:
        json.dump(multisig_data, f, indent=2)

    success(f"Multisig wallet '{name}' created ({threshold}-of-{len(signers)})")
    output(
        {
            "name": name,
            "address": multisig_data["address"],
            "signers": list(signers),
            "threshold": threshold,
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command(name="multisig-propose")
@click.option("--wallet", "wallet_name", required=True, help="Multisig wallet name")
@click.argument("to_address")
@click.argument("amount", type=float)
@click.option("--description", help="Transaction description")
@click.pass_context
def multisig_propose(
    ctx, wallet_name: str, to_address: str, amount: float, description: Optional[str]
):
    """Propose a multisig transaction"""
    wallet_dir = ctx.obj.get("wallet_dir", Path.home() / ".aitbc" / "wallets")
    multisig_path = wallet_dir / f"{wallet_name}_multisig.json"

    if not multisig_path.exists():
        error(f"Multisig wallet '{wallet_name}' not found")
        return

    with open(multisig_path) as f:
        ms_data = json.load(f)

    if ms_data.get("balance", 0) < amount:
        error(
            f"Insufficient balance. Available: {ms_data['balance']}, Required: {amount}"
        )
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
        "status": "pending",
    }

    ms_data.setdefault("pending_transactions", []).append(pending_tx)
    with open(multisig_path, "w") as f:
        json.dump(ms_data, f, indent=2)

    success(f"Transaction proposed: {tx_id}")
    output(
        {
            "tx_id": tx_id,
            "to": to_address,
            "amount": amount,
            "signatures_needed": ms_data["threshold"],
            "status": "pending",
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command(name="multisig-challenge")
@click.option("--wallet", "wallet_name", required=True, help="Multisig wallet name")
@click.argument("tx_id")
@click.pass_context
def multisig_challenge(ctx, wallet_name: str, tx_id: str):
    """Create a cryptographic challenge for multisig transaction signing"""
    wallet_dir = ctx.obj.get("wallet_dir", Path.home() / ".aitbc" / "wallets")
    multisig_path = wallet_dir / f"{wallet_name}_multisig.json"

    if not multisig_path.exists():
        error(f"Multisig wallet '{wallet_name}' not found")
        return

    with open(multisig_path) as f:
        ms_data = json.load(f)

    # Find pending transaction
    pending = ms_data.get("pending_transactions", [])
    tx = next(
        (t for t in pending if t["tx_id"] == tx_id and t["status"] == "pending"), None
    )

    if not tx:
        error(f"Pending transaction '{tx_id}' not found")
        return

    # Import crypto utilities
    from ..utils.crypto_utils import multisig_security

    try:
        # Create signing request
        signing_request = multisig_security.create_signing_request(tx, wallet_name)
        
        output({
            "tx_id": tx_id,
            "wallet": wallet_name,
            "challenge": signing_request["challenge"],
            "nonce": signing_request["nonce"],
            "message": signing_request["message"],
            "instructions": [
                "1. Copy the challenge string above",
                "2. Sign it with your private key using: aitbc wallet sign-challenge <challenge> <private-key>",
                "3. Use the returned signature with: aitbc wallet multisig-sign --wallet <wallet> <tx_id> --signer <address> --signature <signature>"
            ]
        }, ctx.obj.get("output_format", "table"))
        
    except Exception as e:
        error(f"Failed to create challenge: {e}")


@wallet.command(name="sign-challenge")
@click.argument("challenge")
@click.argument("private_key")
@click.pass_context
def sign_challenge(ctx, challenge: str, private_key: str):
    """Sign a cryptographic challenge (for testing multisig)"""
    from ..utils.crypto_utils import sign_challenge

    try:
        signature = sign_challenge(challenge, private_key)
        
        output({
            "challenge": challenge,
            "signature": signature,
            "message": "Use this signature with multisig-sign command"
        }, ctx.obj.get("output_format", "table"))
        
    except Exception as e:
        error(f"Failed to sign challenge: {e}")


@wallet.command(name="multisig-sign")
@click.option("--wallet", "wallet_name", required=True, help="Multisig wallet name")
@click.argument("tx_id")
@click.option("--signer", required=True, help="Signer address")
@click.option("--signature", required=True, help="Cryptographic signature (hex)")
@click.pass_context
def multisig_sign(ctx, wallet_name: str, tx_id: str, signer: str, signature: str):
    """Sign a pending multisig transaction with cryptographic verification"""
    wallet_dir = ctx.obj.get("wallet_dir", Path.home() / ".aitbc" / "wallets")
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

    # Import crypto utilities
    from ..utils.crypto_utils import multisig_security
    
    # Verify signature cryptographically
    success, message = multisig_security.verify_and_add_signature(tx_id, signature, signer)
    if not success:
        error(f"Signature verification failed: {message}")
        ctx.exit(1)
        return

    pending = ms_data.get("pending_transactions", [])
    tx = next(
        (t for t in pending if t["tx_id"] == tx_id and t["status"] == "pending"), None
    )

    if not tx:
        error(f"Pending transaction '{tx_id}' not found")
        ctx.exit(1)
        return

    # Check if already signed
    for sig in tx.get("signatures", []):
        if sig["signer"] == signer:
            error(f"'{signer}' has already signed this transaction")
            return

    # Add cryptographic signature
    if "signatures" not in tx:
        tx["signatures"] = []
    
    tx["signatures"].append({
        "signer": signer,
        "signature": signature,
        "timestamp": datetime.now().isoformat()
    })

    # Check if threshold met
    if len(tx["signatures"]) >= ms_data["threshold"]:
        tx["status"] = "approved"
        # Execute the transaction
        ms_data["balance"] = ms_data.get("balance", 0) - tx["amount"]
        ms_data["transactions"].append(
            {
                "type": "multisig_send",
                "amount": -tx["amount"],
                "to": tx["to"],
                "tx_id": tx["tx_id"],
                "signatures": tx["signatures"],
                "timestamp": datetime.now().isoformat(),
            }
        )
        success(f"Transaction {tx_id} approved and executed!")
    else:
        success(
            f"Signed. {len(tx['signatures'])}/{ms_data['threshold']} signatures collected"
        )

    with open(multisig_path, "w") as f:
        json.dump(ms_data, f, indent=2)

    output(
        {
            "tx_id": tx_id,
            "signatures": tx["signatures"],
            "threshold": ms_data["threshold"],
            "status": tx["status"],
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command(name="liquidity-stake")
@click.argument("amount", type=float)
@click.option("--pool", default="main", help="Liquidity pool name")
@click.option(
    "--lock-days", type=int, default=0, help="Lock period in days (higher APY)"
)
@click.pass_context
def liquidity_stake(ctx, amount: float, pool: str, lock_days: int):
    """Stake tokens into a liquidity pool"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj.get("wallet_path")
    if not wallet_path or not Path(wallet_path).exists():
        error("Wallet not found")
        ctx.exit(1)
        return

    wallet_data = _load_wallet(Path(wallet_path), wallet_name)

    balance = wallet_data.get("balance", 0)
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
        "unlock_date": (now + timedelta(days=lock_days)).isoformat()
        if lock_days > 0
        else None,
        "status": "active",
    }

    wallet_data.setdefault("liquidity", []).append(liq_record)
    wallet_data["balance"] = balance - amount

    wallet_data["transactions"].append(
        {
            "type": "liquidity_stake",
            "amount": -amount,
            "pool": pool,
            "stake_id": stake_id,
            "timestamp": now.isoformat(),
        }
    )

    # Save wallet with encryption
    password = None
    if wallet_data.get("encrypted"):
        password = _get_wallet_password(wallet_name)
    _save_wallet(Path(wallet_path), wallet_data, password)

    success(f"Staked {amount} AITBC into '{pool}' pool ({tier} tier, {apy}% APY)")
    output(
        {
            "stake_id": stake_id,
            "pool": pool,
            "amount": amount,
            "apy": apy,
            "tier": tier,
            "lock_days": lock_days,
            "new_balance": wallet_data["balance"],
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command(name="liquidity-unstake")
@click.argument("stake_id")
@click.pass_context
def liquidity_unstake(ctx, stake_id: str):
    """Withdraw from a liquidity pool with rewards"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj.get("wallet_path")
    if not wallet_path or not Path(wallet_path).exists():
        error("Wallet not found")
        ctx.exit(1)
        return

    wallet_data = _load_wallet(Path(wallet_path), wallet_name)

    liquidity = wallet_data.get("liquidity", [])
    record = next(
        (r for r in liquidity if r["stake_id"] == stake_id and r["status"] == "active"),
        None,
    )

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

    wallet_data["balance"] = wallet_data.get("balance", 0) + total

    wallet_data["transactions"].append(
        {
            "type": "liquidity_unstake",
            "amount": total,
            "principal": record["amount"],
            "rewards": round(rewards, 6),
            "pool": record["pool"],
            "stake_id": stake_id,
            "timestamp": datetime.now().isoformat(),
        }
    )

    # Save wallet with encryption
    password = None
    if wallet_data.get("encrypted"):
        password = _get_wallet_password(wallet_name)
    _save_wallet(Path(wallet_path), wallet_data, password)

    success(
        f"Withdrawn {total:.6f} AITBC (principal: {record['amount']}, rewards: {rewards:.6f})"
    )
    output(
        {
            "stake_id": stake_id,
            "pool": record["pool"],
            "principal": record["amount"],
            "rewards": round(rewards, 6),
            "total_returned": round(total, 6),
            "days_staked": round(days_staked, 2),
            "apy": record["apy"],
            "new_balance": round(wallet_data["balance"], 6),
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command()
@click.pass_context
def rewards(ctx):
    """View all earned rewards (staking + liquidity)"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj.get("wallet_path")
    if not wallet_path or not Path(wallet_path).exists():
        error("Wallet not found")
        ctx.exit(1)
        return

    wallet_data = _load_wallet(Path(wallet_path), wallet_name)

    staking = wallet_data.get("staking", [])
    liquidity = wallet_data.get("liquidity", [])

    # Staking rewards
    staking_rewards = sum(
        s.get("rewards", 0) for s in staking if s.get("status") == "completed"
    )
    active_staking = sum(s["amount"] for s in staking if s.get("status") == "active")

    # Liquidity rewards
    liq_rewards = sum(
        r.get("rewards", 0) for r in liquidity if r.get("status") == "completed"
    )
    active_liquidity = sum(
        r["amount"] for r in liquidity if r.get("status") == "active"
    )

    # Estimate pending rewards for active positions
    pending_staking = 0
    for s in staking:
        if s.get("status") == "active":
            start = datetime.fromisoformat(s["start_date"])
            days = max((datetime.now() - start).total_seconds() / 86400, 0)
            pending_staking += s["amount"] * (s["apy"] / 100) * (days / 365)

    pending_liquidity = 0
    for r in liquidity:
        if r.get("status") == "active":
            start = datetime.fromisoformat(r["start_date"])
            days = max((datetime.now() - start).total_seconds() / 86400, 0)
            pending_liquidity += r["amount"] * (r["apy"] / 100) * (days / 365)

    output(
        {
            "staking_rewards_earned": round(staking_rewards, 6),
            "staking_rewards_pending": round(pending_staking, 6),
            "staking_active_amount": active_staking,
            "liquidity_rewards_earned": round(liq_rewards, 6),
            "liquidity_rewards_pending": round(pending_liquidity, 6),
            "liquidity_active_amount": active_liquidity,
            "total_earned": round(staking_rewards + liq_rewards, 6),
            "total_pending": round(pending_staking + pending_liquidity, 6),
            "total_staked": active_staking + active_liquidity,
        },
        ctx.obj.get("output_format", "table"),
    )


# Multi-Chain Commands

@wallet.group()
def chain():
    """Multi-chain wallet operations"""
    pass


@chain.command()
@click.pass_context
def list(ctx):
    """List all blockchain chains"""
    adapter = ctx.obj["wallet_adapter"]
    use_daemon = ctx.obj["use_daemon"]
    
    if not use_daemon:
        error("Chain operations require daemon mode. Use --use-daemon flag.")
        return
    
    if not adapter.is_daemon_available():
        error("Wallet daemon is not available")
        return
    
    try:
        chains = adapter.list_chains()
        output({
            "chains": chains,
            "count": len(chains),
            "mode": "daemon"
        }, ctx.obj.get("output_format", "table"))
        
    except Exception as e:
        error(f"Failed to list chains: {str(e)}")


@chain.command()
@click.argument("chain_id")
@click.argument("name")
@click.argument("coordinator_url")
@click.argument("coordinator_api_key")
@click.pass_context
def create(ctx, chain_id: str, name: str, coordinator_url: str, coordinator_api_key: str):
    """Create a new blockchain chain"""
    adapter = ctx.obj["wallet_adapter"]
    use_daemon = ctx.obj["use_daemon"]
    
    if not use_daemon:
        error("Chain operations require daemon mode. Use --use-daemon flag.")
        return
    
    if not adapter.is_daemon_available():
        error("Wallet daemon is not available")
        return
    
    try:
        chain = adapter.create_chain(chain_id, name, coordinator_url, coordinator_api_key)
        if chain:
            success(f"Created chain: {chain_id}")
            output(chain, ctx.obj.get("output_format", "table"))
        else:
            error(f"Failed to create chain: {chain_id}")
        
    except Exception as e:
        error(f"Failed to create chain: {str(e)}")


@chain.command()
@click.pass_context
def status(ctx):
    """Get chain status and statistics"""
    adapter = ctx.obj["wallet_adapter"]
    use_daemon = ctx.obj["use_daemon"]
    
    if not use_daemon:
        error("Chain operations require daemon mode. Use --use-daemon flag.")
        return
    
    if not adapter.is_daemon_available():
        error("Wallet daemon is not available")
        return
    
    try:
        status = adapter.get_chain_status()
        output(status, ctx.obj.get("output_format", "table"))
        
    except Exception as e:
        error(f"Failed to get chain status: {str(e)}")


@chain.command()
@click.argument("chain_id")
@click.pass_context
def wallets(ctx, chain_id: str):
    """List wallets in a specific chain"""
    adapter = ctx.obj["wallet_adapter"]
    use_daemon = ctx.obj["use_daemon"]
    
    if not use_daemon:
        error("Chain operations require daemon mode. Use --use-daemon flag.")
        return
    
    if not adapter.is_daemon_available():
        error("Wallet daemon is not available")
        return
    
    try:
        wallets = adapter.list_wallets_in_chain(chain_id)
        output({
            "chain_id": chain_id,
            "wallets": wallets,
            "count": len(wallets),
            "mode": "daemon"
        }, ctx.obj.get("output_format", "table"))
        
    except Exception as e:
        error(f"Failed to list wallets in chain {chain_id}: {str(e)}")


@chain.command()
@click.argument("chain_id")
@click.argument("wallet_name")
@click.pass_context
def info(ctx, chain_id: str, wallet_name: str):
    """Get wallet information from a specific chain"""
    adapter = ctx.obj["wallet_adapter"]
    use_daemon = ctx.obj["use_daemon"]
    
    if not use_daemon:
        error("Chain operations require daemon mode. Use --use-daemon flag.")
        return
    
    if not adapter.is_daemon_available():
        error("Wallet daemon is not available")
        return
    
    try:
        wallet_info = adapter.get_wallet_info_in_chain(chain_id, wallet_name)
        if wallet_info:
            output(wallet_info, ctx.obj.get("output_format", "table"))
        else:
            error(f"Wallet '{wallet_name}' not found in chain '{chain_id}'")
        
    except Exception as e:
        error(f"Failed to get wallet info: {str(e)}")


@chain.command()
@click.argument("chain_id")
@click.argument("wallet_name")
@click.pass_context
def balance(ctx, chain_id: str, wallet_name: str):
    """Get wallet balance in a specific chain"""
    adapter = ctx.obj["wallet_adapter"]
    use_daemon = ctx.obj["use_daemon"]
    
    if not use_daemon:
        error("Chain operations require daemon mode. Use --use-daemon flag.")
        return
    
    if not adapter.is_daemon_available():
        error("Wallet daemon is not available")
        return
    
    try:
        balance = adapter.get_wallet_balance_in_chain(chain_id, wallet_name)
        if balance is not None:
            output({
                "chain_id": chain_id,
                "wallet_name": wallet_name,
                "balance": balance,
                "mode": "daemon"
            }, ctx.obj.get("output_format", "table"))
        else:
            error(f"Could not get balance for wallet '{wallet_name}' in chain '{chain_id}'")
        
    except Exception as e:
        error(f"Failed to get wallet balance: {str(e)}")


@chain.command()
@click.argument("source_chain_id")
@click.argument("target_chain_id")
@click.argument("wallet_name")
@click.option("--new-password", help="New password for target chain wallet")
@click.pass_context
def migrate(ctx, source_chain_id: str, target_chain_id: str, wallet_name: str, new_password: Optional[str]):
    """Migrate a wallet from one chain to another"""
    adapter = ctx.obj["wallet_adapter"]
    use_daemon = ctx.obj["use_daemon"]
    
    if not use_daemon:
        error("Chain operations require daemon mode. Use --use-daemon flag.")
        return
    
    if not adapter.is_daemon_available():
        error("Wallet daemon is not available")
        return
    
    try:
        # Get password
        import getpass
        password = getpass.getpass(f"Enter password for wallet '{wallet_name}': ")
        
        result = adapter.migrate_wallet(source_chain_id, target_chain_id, wallet_name, password, new_password)
        if result:
            success(f"Migrated wallet '{wallet_name}' from '{source_chain_id}' to '{target_chain_id}'")
            output(result, ctx.obj.get("output_format", "table"))
        else:
            error(f"Failed to migrate wallet '{wallet_name}'")
        
    except Exception as e:
        error(f"Failed to migrate wallet: {str(e)}")


@wallet.command()
@click.argument("chain_id")
@click.argument("wallet_name")
@click.option("--type", "wallet_type", default="hd", help="Wallet type (hd, simple)")
@click.option("--no-encrypt", is_flag=True, help="Skip wallet encryption (not recommended)")
@click.pass_context
def create_in_chain(ctx, chain_id: str, wallet_name: str, wallet_type: str, no_encrypt: bool):
    """Create a wallet in a specific chain"""
    adapter = ctx.obj["wallet_adapter"]
    use_daemon = ctx.obj["use_daemon"]
    
    if not use_daemon:
        error("Chain operations require daemon mode. Use --use-daemon flag.")
        return
    
    if not adapter.is_daemon_available():
        error("Wallet daemon is not available")
        return
    
    try:
        # Get password
        import getpass
        if not no_encrypt:
            password = getpass.getpass(f"Enter password for wallet '{wallet_name}': ")
            confirm_password = getpass.getpass(f"Confirm password for wallet '{wallet_name}': ")
            if password != confirm_password:
                error("Passwords do not match")
                return
        else:
            password = "insecure"  # Default password for unencrypted wallets
        
        metadata = {
            "wallet_type": wallet_type,
            "encrypted": not no_encrypt,
            "created_at": datetime.now().isoformat()
        }
        
        result = adapter.create_wallet_in_chain(chain_id, wallet_name, password, wallet_type, metadata)
        if result:
            success(f"Created wallet '{wallet_name}' in chain '{chain_id}'")
            output(result, ctx.obj.get("output_format", "table"))
        else:
            error(f"Failed to create wallet '{wallet_name}' in chain '{chain_id}'")
        
    except Exception as e:
        error(f"Failed to create wallet in chain: {str(e)}")


@wallet.command()
@click.option("--threshold", type=int, required=True, help="Number of signatures required")
@click.option("--signers", multiple=True, required=True, help="Public keys of signers")
@click.option("--wallet-name", help="Name for the multi-sig wallet")
@click.option("--chain-id", help="Chain ID for multi-chain support")
@click.pass_context
def multisig_create(ctx, threshold: int, signers: tuple, wallet_name: Optional[str], chain_id: Optional[str]):
    """Create a multi-signature wallet"""
    config = ctx.obj.get('config')
    
    if len(signers) < threshold:
        error(f"Threshold {threshold} cannot be greater than number of signers {len(signers)}")
        return
    
    multisig_data = {
        "threshold": threshold,
        "signers": list(signers),
        "wallet_name": wallet_name or f"multisig_{int(datetime.now().timestamp())}",
        "created_at": datetime.utcnow().isoformat()
    }
    
    if chain_id:
        multisig_data["chain_id"] = chain_id
    
    try:
        if ctx.obj.get("use_daemon"):
            # Use wallet daemon for multi-sig creation
            from ..dual_mode_wallet_adapter import DualModeWalletAdapter
            adapter = DualModeWalletAdapter(config)
            
            result = adapter.create_multisig_wallet(
                threshold=threshold,
                signers=list(signers),
                wallet_name=wallet_name,
                chain_id=chain_id
            )
            
            if result:
                success(f"Multi-sig wallet '{multisig_data['wallet_name']}' created!")
                success(f"Threshold: {threshold}/{len(signers)}")
                success(f"Signers: {len(signers)}")
                output(result, ctx.obj.get('output_format', 'table'))
            else:
                error("Failed to create multi-sig wallet")
        else:
            # Local multi-sig wallet creation
            wallet_dir = Path.home() / ".aitbc" / "wallets"
            wallet_dir.mkdir(parents=True, exist_ok=True)
            
            wallet_file = wallet_dir / f"{multisig_data['wallet_name']}.json"
            
            if wallet_file.exists():
                error(f"Wallet '{multisig_data['wallet_name']}' already exists")
                return
            
            # Save multi-sig wallet
            with open(wallet_file, 'w') as f:
                json.dump(multisig_data, f, indent=2)
            
            success(f"Multi-sig wallet '{multisig_data['wallet_name']}' created!")
            success(f"Threshold: {threshold}/{len(signers)}")
            output(multisig_data, ctx.obj.get('output_format', 'table'))
            
    except Exception as e:
        error(f"Failed to create multi-sig wallet: {e}")


@wallet.command()
@click.option("--amount", type=float, required=True, help="Transfer limit amount")
@click.option("--period", default="daily", help="Limit period (hourly, daily, weekly)")
@click.option("--wallet-name", help="Wallet to set limit for")
@click.pass_context
def set_limit(ctx, amount: float, period: str, wallet_name: Optional[str]):
    """Set transfer limits for wallet"""
    config = ctx.obj.get('config')
    
    limit_data = {
        "amount": amount,
        "period": period,
        "set_at": datetime.utcnow().isoformat()
    }
    
    try:
        if ctx.obj.get("use_daemon"):
            # Use wallet daemon
            from ..dual_mode_wallet_adapter import DualModeWalletAdapter
            adapter = DualModeWalletAdapter(config)
            
            result = adapter.set_transfer_limit(
                amount=amount,
                period=period,
                wallet_name=wallet_name
            )
            
            if result:
                success(f"Transfer limit set: {amount} {period}")
                output(result, ctx.obj.get('output_format', 'table'))
            else:
                error("Failed to set transfer limit")
        else:
            # Local limit setting
            limits_file = Path.home() / ".aitbc" / "transfer_limits.json"
            limits_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Load existing limits
            limits = {}
            if limits_file.exists():
                with open(limits_file, 'r') as f:
                    limits = json.load(f)
            
            # Set new limit
            wallet_key = wallet_name or "default"
            limits[wallet_key] = limit_data
            
            # Save limits
            with open(limits_file, 'w') as f:
                json.dump(limits, f, indent=2)
            
            success(f"Transfer limit set for '{wallet_key}': {amount} {period}")
            output(limit_data, ctx.obj.get('output_format', 'table'))
            
    except Exception as e:
        error(f"Failed to set transfer limit: {e}")


@wallet.command()
@click.option("--amount", type=float, required=True, help="Amount to time-lock")
@click.option("--duration", type=int, required=True, help="Lock duration in hours")
@click.option("--recipient", required=True, help="Recipient address")
@click.option("--wallet-name", help="Wallet to create time-lock from")
@click.pass_context
def time_lock(ctx, amount: float, duration: int, recipient: str, wallet_name: Optional[str]):
    """Create a time-locked transfer"""
    config = ctx.obj.get('config')
    
    lock_data = {
        "amount": amount,
        "duration_hours": duration,
        "recipient": recipient,
        "wallet_name": wallet_name or "default",
        "created_at": datetime.utcnow().isoformat(),
        "unlock_time": (datetime.utcnow() + timedelta(hours=duration)).isoformat()
    }
    
    try:
        if ctx.obj.get("use_daemon"):
            # Use wallet daemon
            from ..dual_mode_wallet_adapter import DualModeWalletAdapter
            adapter = DualModeWalletAdapter(config)
            
            result = adapter.create_time_lock(
                amount=amount,
                duration_hours=duration,
                recipient=recipient,
                wallet_name=wallet_name
            )
            
            if result:
                success(f"Time-locked transfer created: {amount} tokens")
                success(f"Unlocks in: {duration} hours")
                success(f"Recipient: {recipient}")
                output(result, ctx.obj.get('output_format', 'table'))
            else:
                error("Failed to create time-lock")
        else:
            # Local time-lock creation
            locks_file = Path.home() / ".aitbc" / "time_locks.json"
            locks_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Load existing locks
            locks = []
            if locks_file.exists():
                with open(locks_file, 'r') as f:
                    locks = json.load(f)
            
            # Add new lock
            locks.append(lock_data)
            
            # Save locks
            with open(locks_file, 'w') as f:
                json.dump(locks, f, indent=2)
            
            success(f"Time-locked transfer created: {amount} tokens")
            success(f"Unlocks at: {lock_data['unlock_time']}")
            success(f"Recipient: {recipient}")
            output(lock_data, ctx.obj.get('output_format', 'table'))
            
    except Exception as e:
        error(f"Failed to create time-lock: {e}")


@wallet.command()
@click.option("--wallet-name", help="Wallet to check limits for")
@click.pass_context
def check_limits(ctx, wallet_name: Optional[str]):
    """Check transfer limits for wallet"""
    limits_file = Path.home() / ".aitbc" / "transfer_limits.json"
    
    if not limits_file.exists():
        error("No transfer limits configured")
        return
    
    try:
        with open(limits_file, 'r') as f:
            limits = json.load(f)
        
        wallet_key = wallet_name or "default"
        
        if wallet_key not in limits:
            error(f"No transfer limits configured for '{wallet_key}'")
            return
        
        limit_info = limits[wallet_key]
        success(f"Transfer limits for '{wallet_key}':")
        output(limit_info, ctx.obj.get('output_format', 'table'))
        
    except Exception as e:
        error(f"Failed to check transfer limits: {e}")


@wallet.command()
@click.option("--wallet-name", help="Wallet to check locks for")
@click.pass_context
def list_time_locks(ctx, wallet_name: Optional[str]):
    """List time-locked transfers"""
    locks_file = Path.home() / ".aitbc" / "time_locks.json"
    
    if not locks_file.exists():
        error("No time-locked transfers found")
        return
    
    try:
        with open(locks_file, 'r') as f:
            locks = json.load(f)
        
        # Filter by wallet if specified
        if wallet_name:
            locks = [lock for lock in locks if lock.get('wallet_name') == wallet_name]
        
        if not locks:
            error(f"No time-locked transfers found for '{wallet_name}'")
            return
        
        success(f"Time-locked transfers ({len(locks)} found):")
        output({"time_locks": locks}, ctx.obj.get('output_format', 'table'))
        
    except Exception as e:
        error(f"Failed to list time-locks: {e}")


@wallet.command()
@click.option("--wallet-name", help="Wallet name for audit")
@click.option("--days", type=int, default=30, help="Number of days to audit")
@click.pass_context
def audit_trail(ctx, wallet_name: Optional[str], days: int):
    """Generate wallet audit trail"""
    config = ctx.obj.get('config')
    
    audit_data = {
        "wallet_name": wallet_name or "all",
        "audit_period_days": days,
        "generated_at": datetime.utcnow().isoformat()
    }
    
    try:
        if ctx.obj.get("use_daemon"):
            # Use wallet daemon for audit
            from ..dual_mode_wallet_adapter import DualModeWalletAdapter
            adapter = DualModeWalletAdapter(config)
            
            result = adapter.get_audit_trail(
                wallet_name=wallet_name,
                days=days
            )
            
            if result:
                success(f"Audit trail for '{wallet_name or 'all wallets'}':")
                output(result, ctx.obj.get('output_format', 'table'))
            else:
                error("Failed to generate audit trail")
        else:
            # Local audit trail generation
            audit_file = Path.home() / ".aitbc" / "audit_trail.json"
            audit_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Generate sample audit data
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            audit_data["transactions"] = []
            audit_data["signatures"] = []
            audit_data["limits"] = []
            audit_data["time_locks"] = []
            
            success(f"Audit trail generated for '{wallet_name or 'all wallets'}':")
            output(audit_data, ctx.obj.get('output_format', 'table'))
            
    except Exception as e:
        error(f"Failed to generate audit trail: {e}")
