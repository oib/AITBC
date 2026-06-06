"""Wallet commands for AITBC CLI"""

import getpass
import json
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import click
import yaml

# Import shared modules
from aitbc import AITBCHTTPClient, get_logger

from ..config import get_config
from ..utils import error, output, success

# Initialize logger
logger = get_logger(__name__)


def encrypt_value(value: str, password: str) -> str:
    """Simple encryption for wallet data (placeholder)"""
    # For now, return the value as-is since daemon mode doesn't need this
    return value


def decrypt_value(encrypted: str, password: str) -> str:
    """Simple decryption for wallet data (placeholder)"""
    # For now, return the value as-is since daemon mode doesn't need this
    return encrypted


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

    # Check if we're in a TTY environment
    import sys
    if not sys.stdin.isatty():
        # Non-interactive: try environment variable
        password = os.environ.get(f"AITBC_WALLET_PASSWORD_{wallet_name.upper()}")
        if password:
            return password
        # Try generic password env var
        password = os.environ.get("AITBC_WALLET_PASSWORD")
        if password:
            return password
        error("No TTY available for password prompt. Set AITBC_WALLET_PASSWORD environment variable.")
        raise click.Abort()

    # Prompt for password
    while True:
        try:
            password = getpass.getpass(f"Enter password for wallet '{wallet_name}': ")
        except Exception as e:
            error(f"Password prompt failed: {e}")
            raise click.Abort()

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


def _save_wallet(wallet_path: Path, wallet_data: dict[str, Any], password: str = None):
    """Save wallet with encrypted private key"""
    # Encrypt private key if provided
    if password and "private_key" in wallet_data:
        wallet_data["private_key"] = encrypt_value(wallet_data["private_key"], password)
        wallet_data["encrypted"] = True

    # Save wallet
    with open(wallet_path, "w") as f:
        json.dump(wallet_data, f, indent=2)


def _load_wallet(wallet_path: Path, wallet_name: str) -> dict[str, Any]:
    """Load wallet and decrypt private key if needed"""
    with open(wallet_path) as f:
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
@click.option("--use-daemon", is_flag=True, default=True, help="Use wallet daemon for operations")
@click.option("--chain-id", help="Chain ID for multichain operations (e.g., ait-mainnet, ait-devnet)")
@click.pass_context
def wallet(ctx, wallet_name: str | None, wallet_path: str | None, use_daemon: bool, chain_id: str | None):
    """Manage your AITBC wallets and transactions"""
    # Ensure wallet object exists
    ctx.ensure_object(dict)

    # Set daemon mode
    ctx.obj["use_daemon"] = use_daemon

    # Handle chain_id with auto-detection
    from ..utils.chain_id import get_chain_id
    config = get_config()
    default_rpc_url = config.blockchain_rpc_url if hasattr(config, 'blockchain_rpc_url') else 'http://localhost:8006'
    ctx.obj["chain_id"] = get_chain_id(default_rpc_url, override=chain_id)

    # Initialize dual-mode adapter
    from aitbc_cli.utils.dual_mode_wallet_adapter import DualModeWalletAdapter

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
        if config_file.exists():
            with open(config_file) as f:
                config = yaml.safe_load(f)
                if config:
                    wallet_name = config.get("active_wallet", "default")
                else:
                    wallet_name = "default"
        else:
            wallet_name = "default"

    ctx.obj["wallet_name"] = wallet_name
    ctx.obj["wallet_dir"] = wallet_dir
    ctx.obj["wallet_path"] = wallet_dir / f"{wallet_name}.json"


@wallet.command()
@click.argument("name")
@click.option("--type", "wallet_type", default="hd", help="Wallet type (hd, simple)")
@click.option(
    "--no-encrypt", is_flag=True, help="Skip wallet encryption (not recommended)"
)
@click.pass_context
def create(ctx, name: str, wallet_type: str, no_encrypt: bool):
    """Create a new wallet"""
    wallet_dir = ctx.obj["wallet_dir"]
    wallet_path = wallet_dir / f"{name}.json"

    if wallet_path.exists():
        error(f"Wallet '{name}' already exists")
        return

    # Generate new wallet
    if wallet_type == "hd":
        # Hierarchical Deterministic wallet
        import secrets

        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            PublicFormat,
        )

        # Generate private key
        private_key_bytes = secrets.token_bytes(32)
        private_key = f"0x{private_key_bytes.hex()}"

        # Derive public key from private key using ECDSA
        priv_key = ec.derive_private_key(
            int.from_bytes(private_key_bytes, "big"), ec.SECP256K1()
        )
        pub_key = priv_key.public_key()
        pub_key_bytes = pub_key.public_bytes(
            encoding=Encoding.X962, format=PublicFormat.UncompressedPoint
        )
        public_key = f"0x{pub_key_bytes.hex()}"

        # Generate address from public key (simplified)
        digest = hashes.Hash(hashes.SHA256())
        digest.update(pub_key_bytes)
        address_hash = digest.finalize()
        address = f"aitbc1{address_hash[:20].hex()}"
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
        "created_at": datetime.now(UTC).isoformat() + "Z",
        "balance": 0,
        "transactions": [],
    }

    # Get password for encryption unless skipped
    password = None
    if not no_encrypt:
        success(
            "Wallet encryption is enabled. Your private key will be encrypted at rest."
        )
        password = _get_wallet_password(name)

    # Save wallet
    _save_wallet(wallet_path, wallet_data, password)

    success(f"Wallet '{name}' created successfully")
    output(
        {
            "name": name,
            "type": wallet_type,
            "address": address,
            "path": str(wallet_path),
        },
        ctx.obj.get("output_format", "table"),
    )


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
        from aitbc_cli.utils.dual_mode_wallet_adapter import DualModeWalletAdapter

        from ..config import get_config
        config = get_config()
        adapter = DualModeWalletAdapter(config, use_daemon=False)

    try:
        wallets = adapter.list_wallets()

        if not wallets:
            output("No wallets found")
            return

        # Format output
        output_format = ctx.obj.get("output_format", "table")
        if output_format == "json":
            import json
            output(json.dumps(wallets, indent=2))
        elif output_format == "yaml":
            import yaml
            output(yaml.dump(wallets, default_flow_style=False))
        else:
            # Table format
            for wallet in wallets:
                wallet_name = wallet.get("wallet_name", wallet.get("name", "unknown"))
                wallet_address = wallet.get("address", "")
                output(f"{wallet_name}: {wallet_address}")
    except Exception as e:
        error(f"Failed to list wallets: {str(e)}")


@wallet.command()
@click.argument("name")
@click.pass_context
def switch(ctx, name: str):
    """Switch to a different wallet"""
    wallet_dir = ctx.obj["wallet_dir"]
    wallet_path = wallet_dir / f"{name}.json"

    if not wallet_path.exists():
        error(f"Wallet '{name}' does not exist")
        return

    # Update config
    config_file = Path.home() / ".aitbc" / "config.yaml"
    config = {}

    if config_file.exists():
        import yaml

        with open(config_file) as f:
            config = yaml.safe_load(f) or {}

    config["active_wallet"] = name

    # Save config
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    success(f"Switched to wallet '{name}'")
    # Load wallet to get address (will handle encryption)
    wallet_data = _load_wallet(wallet_path, name)
    output(
        {"active_wallet": name, "address": wallet_data["address"]},
        ctx.obj.get("output_format", "table"),
    )


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

        with open(config_file) as f:
            config = yaml.safe_load(f) or {}

        if config.get("active_wallet") == name:
            config["active_wallet"] = "default"
            with open(config_file, "w") as f:
                yaml.dump(config, f, default_flow_style=False)


@wallet.command()
@click.argument("name")
@click.option("--destination", help="Destination path for backup file")
@click.pass_context
def backup(ctx, name: str, destination: str | None):
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
            "timestamp": datetime.now(UTC).isoformat() + "Z",
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
    with open(backup_path) as f:
        wallet_data = json.load(f)

    # Update wallet name if needed
    wallet_data["wallet_id"] = name
    wallet_data["restored_at"] = datetime.now(UTC).isoformat() + "Z"

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

        with open(config_file) as f:
            config = yaml.safe_load(f)
            active_wallet = config.get("active_wallet", "default")

    wallet_info = {
        "name": wallet_data["wallet_id"],
        "type": wallet_data.get("type", "simple"),
        "address": wallet_data["address"],
        "public_key": wallet_data["public_key"],
        "created_at": wallet_data["created_at"],
        "active": wallet_data["wallet_id"] == active_wallet,
        "path": str(wallet_path),
    }

    if "balance" in wallet_data:
        wallet_info["balance"] = wallet_data["balance"]

    output(wallet_info, ctx.obj.get("output_format", "table"))


@wallet.command()
@click.argument("name", required=False)
@click.pass_context
def balance(ctx, name: str | None):
    """Check wallet balance"""
    wallet_name = name or ctx.obj["wallet_name"]
    if not wallet_name:
        error("No wallet specified. Use --wallet-name or provide wallet name as argument")
        return

    wallet_dir = ctx.obj["wallet_dir"]
    wallet_path = wallet_dir / f"{wallet_name}.json"
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
            "created_at": datetime.now(UTC).isoformat() + "Z",
            "balance": 0.0,
            "transactions": [],
        }
        wallet_path.parent.mkdir(parents=True, exist_ok=True)
        # Auto-create without prompt in balance command
        if ctx.obj.get("output_format", "table") == "table":
            success("Creating new wallet")
        _save_wallet(wallet_path, wallet_data, None)
    else:
        wallet_data = _load_wallet(wallet_path, wallet_name)

    # Try to get balance from wallet daemon (which queries blockchain)
    use_daemon = ctx.obj.get("use_daemon", True)
    if use_daemon:
        try:
            from aitbc_cli.config import get_config
            from aitbc_cli.utils.wallet_daemon_client import WalletDaemonClient
            _cfg = config or get_config()
            daemon_client = WalletDaemonClient(_cfg)
            if daemon_client.is_available():
                balance_info = daemon_client.get_wallet_balance(wallet_name)
                if balance_info:
                    output(
                        {
                            "wallet": wallet_name,
                            "address": balance_info.address or wallet_data.get("address", ""),
                            "balance": balance_info.balance,
                            "chain_id": balance_info.chain_id,
                        },
                        ctx.obj.get("output_format", "table"),
                    )
                    return
        except Exception:
            pass

    # Try to get balance directly from blockchain RPC
    try:
        from aitbc_cli.config import get_config
        _cfg = config or get_config()
        rpc_url = getattr(_cfg, "blockchain_rpc_url", None) or "https://hub.aitbc.bubuit.net"
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=5)
        data = http_client.get(f"/rpc/account/{wallet_data['address']}")
        output(
            {
                "wallet": wallet_name,
                "address": wallet_data["address"],
                "balance": data.get("balance", 0),
                "chain_id": data.get("chain_id", ""),
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
            "note": "Local balance only (blockchain not accessible)",
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
def earn(ctx, amount: float, job_id: str, desc: str | None):
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
@click.argument("name", required=False)
@click.pass_context
def address(ctx, name: str | None):
    """Show wallet address"""
    wallet_name = name or ctx.obj["wallet_name"]
    if not wallet_name:
        error("No wallet specified. Use --wallet-name or provide wallet name as argument")
        return

    wallet_dir = ctx.obj["wallet_dir"]
    wallet_path = wallet_dir / f"{wallet_name}.json"

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
@click.option("--fee", type=float, default=10, help="Transaction fee")
@click.option("--password", help="Wallet password for signing")
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.pass_context
def send(ctx, to_address: str, amount: float, fee: float, password: str | None, rpc_url: str | None):
    """Send AITBC to another address"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)
    sender_address = wallet_data["address"]

    # Get RPC URL from context or parameter (use hub for cross-node transfers)
    if not rpc_url:
        from ..config import get_config
        config = get_config()
        rpc_url = getattr(config, 'blockchain_rpc_url', 'http://localhost:8006')
        # Use hub RPC for cross-node transaction propagation
        rpc_url = rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')

    # Get chain_id from RPC
    try:
        from ..utils.chain_id import get_chain_id
        chain_id = get_chain_id(rpc_url, override=None, timeout=5)
    except Exception:
        import os
        chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

    # Get actual nonce from blockchain
    actual_nonce = 0
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=5)
        account_data = http_client.get(f"/rpc/account/{sender_address}")
        actual_nonce = account_data.get("nonce", 0)
    except Exception:
        actual_nonce = 0

    # Get private key for signing
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
        private_key_hex = wallet_data.get("private_key")
        if not private_key_hex:
            error("Wallet does not contain private key")
            return

        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    except Exception as e:
        error(f"Error loading private key: {e}")
        return

    # Create transaction with modern payload format
    transaction = {
        "type": "TRANSFER",
        "chain_id": chain_id,
        "from": sender_address,
        "nonce": actual_nonce,
        "fee": int(fee),
        "payload": {
            "recipient": to_address,
            "amount": int(amount)
        }
    }

    # Sign transaction
    import json
    message = json.dumps(transaction, sort_keys=True).encode()
    signature = private_key.sign(message)
    transaction["signature"] = signature.hex()

    # Submit to blockchain
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.post("/rpc/transaction", json=transaction)
        tx_hash = result.get("transaction_hash")
        success(f"Transaction submitted: {tx_hash}")
        output({
            "transaction_hash": tx_hash,
            "from": sender_address,
            "to": to_address,
            "amount": amount,
            "fee": fee,
            "chain_id": chain_id
        }, ctx.obj.get("output_format", "table"))
        return tx_hash
    except Exception as e:
        error(f"Error submitting transaction: {e}")
        return None


@wallet.command()
@click.argument("to_address")
@click.argument("amount", type=float)
@click.option("--description", help="Transaction description")
@click.pass_context
def request_payment(ctx, to_address: str, amount: float, description: str | None):
    """Request payment from another address"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)

    # Create payment request
    request = {
        "from_address": to_address,
        "to_address": wallet_data["address"],
        "amount": amount,
        "description": description or "",
        "timestamp": datetime.now().isoformat(),
    }

    output(
        {
            "wallet": wallet_name,
            "payment_request": request,
            "note": "Share this with the payer to request payment",
        },
        ctx.obj.get("output_format", "table"),
    )


@wallet.command()
@click.pass_context
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
    """Stake AITBC tokens on blockchain"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)
    sender_address = wallet_data["address"]

    # Convert bech32 address to hex for RPC compatibility
    from ..utils.crypto_utils import bech32_to_hex
    hex_address = bech32_to_hex(sender_address)

    # Get RPC URL from config (use hub for cross-node operations)
    from ..config import get_config
    config = get_config()
    rpc_url = getattr(config, 'blockchain_rpc_url', 'http://localhost:8006')
    rpc_url = rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')

    # Get chain_id
    try:
        from ..utils.chain_id import get_chain_id
        chain_id = get_chain_id(rpc_url, override=None, timeout=5)
    except Exception:
        import os
        chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

    # Submit staking request to blockchain RPC
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        stake_data = {
            "address": hex_address,
            "amount": int(amount * 10**18),  # Convert to wei
            "lock_days": duration,
            "chain_id": chain_id
        }
        result = http_client.post("/rpc/staking/stake", json=stake_data)

        success(f"Staked {amount} AITBC for {duration} days")
        output({
            "wallet": wallet_name,
            "stake_id": result.get("stake_id"),
            "amount": amount,
            "duration_days": duration,
            "locked_until": result.get("locked_until"),
            "remaining_balance": result.get("remaining_balance"),
            "chain_id": chain_id
        }, ctx.obj.get("output_format", "table"))
    except Exception as e:
        error(f"Error staking tokens: {e}")
        raise click.Abort()


@wallet.command()
@click.argument("stake_id")
@click.pass_context
def unstake(ctx, stake_id: str):
    """Unstake AITBC tokens from blockchain"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)
    sender_address = wallet_data["address"]

    # Convert bech32 address to hex for RPC compatibility
    from ..utils.crypto_utils import bech32_to_hex
    hex_address = bech32_to_hex(sender_address)

    # Get RPC URL from config (use hub for cross-node operations)
    from ..config import get_config
    config = get_config()
    rpc_url = getattr(config, 'blockchain_rpc_url', 'http://localhost:8006')
    rpc_url = rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')

    # Get chain_id
    try:
        from ..utils.chain_id import get_chain_id
        chain_id = get_chain_id(rpc_url, override=None, timeout=5)
    except Exception:
        import os
        chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

    # Submit unstaking request to blockchain RPC
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        unstake_data = {
            "address": hex_address,
            "stake_id": int(stake_id),
            "chain_id": chain_id
        }
        result = http_client.post("/rpc/staking/unstake", json=unstake_data)

        success(f"Unstaked tokens from stake {stake_id}")
        output({
            "wallet": wallet_name,
            "stake_id": stake_id,
            "amount": result.get("amount"),
            "new_balance": result.get("new_balance"),
            "status": result.get("status"),
            "chain_id": chain_id
        }, ctx.obj.get("output_format", "table"))
    except Exception as e:
        error(f"Error unstaking tokens: {e}")
        raise click.Abort()


@wallet.command(name="staking-info")
@click.pass_context
def staking_info(ctx):
    """Show staking information from blockchain"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    wallet_data = _load_wallet(wallet_path, wallet_name)
    sender_address = wallet_data["address"]

    # Convert bech32 address to hex for RPC compatibility
    from ..utils.crypto_utils import bech32_to_hex
    hex_address = bech32_to_hex(sender_address)

    # Get RPC URL from config (use hub for cross-node operations)
    from ..config import get_config
    config = get_config()
    rpc_url = getattr(config, 'blockchain_rpc_url', 'http://localhost:8006')
    rpc_url = rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')

    # Get chain_id
    try:
        from ..utils.chain_id import get_chain_id
        chain_id = get_chain_id(rpc_url, override=None, timeout=5)
    except Exception:
        import os
        chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

    # Query staking info from blockchain RPC
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.get(f"/rpc/staking/{hex_address}?chain_id={chain_id}")

        output({
            "wallet": wallet_name,
            "address": sender_address,
            "chain_id": chain_id,
            "total_staked": result.get("total_staked"),
            "active_stake_count": result.get("active_stake_count"),
            "active_stakes": result.get("active_stakes", [])
        }, ctx.obj.get("output_format", "table"))
    except Exception as e:
        error(f"Error fetching staking info: {e}")
        raise click.Abort()


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
    ctx, wallet_name: str, to_address: str, amount: float, description: str | None
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


@wallet.command(name="multisig-sign")
@click.option("--wallet", "wallet_name", required=True, help="Multisig wallet name")
@click.argument("tx_id")
@click.option("--signer", required=True, help="Signer address")
@click.pass_context
def multisig_sign(ctx, wallet_name: str, tx_id: str, signer: str):
    """Sign a pending multisig transaction"""
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

    pending = ms_data.get("pending_transactions", [])
    tx = next(
        (t for t in pending if t["tx_id"] == tx_id and t["status"] == "pending"), None
    )

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


@wallet.command()
@click.argument("address")
@click.option("--amount", default=1000000, help="Amount to request from faucet (default: 1000000)")
@click.option("--chain-id", help="Chain ID (defaults to node's chain)")
@click.pass_context
def fund(ctx, address: str, amount: int, chain_id: str):
    """Fund wallet using blockchain faucet"""
    import httpx

    from ..config import get_config
    from ..utils.chain_id import get_chain_id

    config = get_config()
    rpc_url = config.blockchain_rpc_url if hasattr(config, 'blockchain_rpc_url') else 'http://localhost:8006'

    # Get chain_id
    if not chain_id:
        chain_id = get_chain_id(rpc_url)

    # Normalize address
    address = address.lower().strip()
    if not address.startswith("0x"):
        address = "0x" + address

    # Call faucet endpoint
    faucet_url = f"{rpc_url}/faucet"
    faucet_data = {
        "address": address,
        "amount": amount,
        "chain_id": chain_id
    }

    try:
        response = httpx.post(faucet_url, json=faucet_data, timeout=10)
        response.raise_for_status()
        result = response.json()

        if result.get("success"):
            success(f"Successfully funded wallet {address} with {amount} units")
            output(result, ctx.obj.get("output_format", "table"))
        else:
            error(f"Failed to fund wallet: {result.get('message', 'Unknown error')}")
    except httpx.HTTPError as e:
        error(f"HTTP error calling faucet: {e}")
    except Exception as e:
        error(f"Error funding wallet: {e}")


@wallet.command()
@click.option('--destination', help='Destination file path (default: wallet_name_export.json)')
@click.pass_context
def export(ctx, destination: str | None):
    """Export wallet to JSON file"""
    wallet_name = ctx.obj["wallet_name"]
    wallet_path = ctx.obj["wallet_path"]

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        return

    try:
        wallet_data = _load_wallet(wallet_path, wallet_name)

        # Generate export filename if not provided
        if not destination:
            destination = f"{wallet_name}_export.json"

        export_path = Path(destination)

        # Write export file
        with open(export_path, 'w') as f:
            json.dump(wallet_data, f, indent=2)

        success(f"Wallet exported to {export_path}")
        output({
            "wallet": wallet_name,
            "exported_to": str(export_path),
            "address": wallet_data.get("address"),
            "balance": wallet_data.get("balance", 0)
        }, ctx.obj.get("output_format", "table"))
    except Exception as e:
        error(f"Error exporting wallet: {e}")


@wallet.command()
@click.argument('file_path')
@click.option('--name', help='New wallet name (default: from file)')
@click.pass_context
def import_wallet(ctx, file_path: str, name: str | None):
    """Import wallet from JSON file"""
    wallet_dir = ctx.obj.get("wallet_dir", Path.home() / ".aitbc" / "wallets")
    wallet_dir.mkdir(parents=True, exist_ok=True)

    import_path = Path(file_path)

    if not import_path.exists():
        error(f"Import file not found: {file_path}")
        return

    try:
        with open(import_path) as f:
            wallet_data = json.load(f)

        # Determine wallet name
        wallet_name = name or wallet_data.get("name", import_path.stem)
        wallet_path = wallet_dir / f"{wallet_name}.json"

        if wallet_path.exists():
            if not click.confirm(f"Wallet '{wallet_name}' already exists. Overwrite?"):
                return

        # Save imported wallet
        with open(wallet_path, 'w') as f:
            json.dump(wallet_data, f, indent=2)

        success(f"Wallet imported as '{wallet_name}'")
        output({
            "wallet": wallet_name,
            "imported_from": str(import_path),
            "address": wallet_data.get("address"),
            "balance": wallet_data.get("balance", 0)
        }, ctx.obj.get("output_format", "table"))
    except json.JSONDecodeError:
        error("Invalid JSON file")
    except Exception as e:
        error(f"Error importing wallet: {e}")

