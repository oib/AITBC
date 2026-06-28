"""Basic wallet commands for AITBC CLI"""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import click

from ...config import get_config
from ...utils import error, output, success
from ...utils.http_client import AITBCHTTPClient
from aitbc.utils import ait_to_seconds, format_ait
from . import _get_wallet_password, _load_wallet, _save_wallet, get_wallet_client, wallet


@wallet.command()
@click.argument("name")
@click.option("--type", "wallet_type", default="hd", help="Wallet type (hd, simple)")
@click.option("--no-encrypt", is_flag=True, help="Skip wallet encryption (not recommended)")
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
        # Hierarchical Deterministic wallet (secp256k1 / Ethereum-style)
        from eth_account import Account
        from eth_keys import keys

        account = Account.create()
        private_key = account.key.hex()
        public_key = keys.PrivateKey(bytes(account.key)).public_key.to_hex()
        address = account.address
    else:
        # Simple wallet (secp256k1 / Ethereum-style)
        from eth_account import Account
        from eth_keys import keys

        account = Account.create()
        private_key = account.key.hex()
        public_key = keys.PrivateKey(bytes(account.key)).public_key.to_hex()
        address = account.address

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
        success("Wallet encryption is enabled. Your private key will be encrypted at rest.")
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

        from ...config import get_config

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
        if not click.confirm(f"Are you sure you want to delete wallet '{name}'? This cannot be undone."):
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
        error(f"Wallet '{wallet_name}' not found. Use 'aitbc wallet create' to create one.")
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
        wallet_info["balance"] = format_ait(wallet_data["balance"])

    output(wallet_info, ctx.obj.get("output_format", "table"))


@wallet.command()
@click.argument("name", required=False)
@click.pass_context
def balance(ctx, name: str | None):
    """Check wallet balance from wallet service"""
    wallet_name = name or ctx.obj["wallet_name"]
    if not wallet_name:
        error("No wallet specified. Use --wallet-name or provide wallet name as argument")
        return

    try:
        client = get_wallet_client()
        balance_data = client.get(f"/v1/wallets/{wallet_name}/balance")
        # Format balance as AIT if it's a raw seconds value
        if "balance" in balance_data and isinstance(balance_data["balance"], int):
            balance_data["balance"] = format_ait(balance_data["balance"])
        output(balance_data, ctx.obj.get("output_format", "table"), title=f"Wallet: {wallet_name}")
    except Exception as e:
        error(f"Error getting wallet balance: {e}")
        raise click.Abort() from e


@wallet.command()
@click.argument("name", required=False)
@click.option("--limit", type=int, default=10, help="Number of transactions to show")
@click.pass_context
def transactions(ctx, name: str | None, limit: int):
    """Show blockchain transactions for wallet"""
    wallet_name = name or ctx.obj["wallet_name"]
    if not wallet_name:
        error("No wallet specified. Use --wallet-name or provide wallet name as argument")
        return

    try:
        # Get wallet address from wallet service
        client = get_wallet_client()
        wallets_data = client.get("/v1/wallets")

        # Find wallet by wallet_id
        wallet_info = None
        for item in wallets_data.get("items", []):
            if item.get("wallet_id") == wallet_name:
                wallet_info = item
                break

        if not wallet_info:
            error(f"Wallet '{wallet_name}' not found")
            return

        address = wallet_info.get("metadata", {}).get("address")
        if not address:
            error(f"Could not get address for wallet '{wallet_name}'")
            return

        # Get transactions from blockchain RPC
        config = get_config()
        rpc_client = AITBCHTTPClient(base_url=config.blockchain_rpc_url, timeout=30)
        transactions = rpc_client.get(f"/transactions?address={address}&limit={limit}")

        if isinstance(transactions, dict):
            transactions = transactions.get("transactions", [])

        # Format transactions
        formatted_txs = []
        for tx in transactions:
            formatted_txs.append(
                {
                    "tx_id": tx.get("transaction_id"),
                    "tx_hash": tx.get("tx_hash", "")[:16] + "...",
                    "sender": tx.get("sender", "")[:20] + "...",
                    "recipient": tx.get("recipient", "")[:20] + "...",
                    "value": format_ait(tx.get("value", 0)) if tx.get("value") else 0,
                    "fee": format_ait(tx.get("fee", 0)) if tx.get("fee") else 0,
                    "status": tx.get("status"),
                    "timestamp": tx.get("created_at", "")[:19],
                }
            )

        output(
            {"wallet": wallet_name, "address": address, "count": len(formatted_txs), "transactions": formatted_txs},
            ctx.obj.get("output_format", "table"),
            title=f"Transactions: {wallet_name}",
        )
    except Exception as e:
        error(f"Error getting transactions: {e}")
        raise click.Abort() from e


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
            "amount": format_ait(amount),
            "job_id": job_id,
            "new_balance": format_ait(wallet_data["balance"]),
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
            "amount": format_ait(amount),
            "description": description,
            "new_balance": format_ait(wallet_data["balance"]),
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
@click.option("--fee", type=float, default=0.01, help="Transaction fee in AIT")
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
        from ...config import get_config

        config = get_config()
        rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")
        # Use hub RPC for cross-node transaction propagation
        rpc_url = rpc_url.replace("localhost", config.hub_discovery_url or "hub.aitbc.bubuit.net")

    # Get chain_id from RPC
    try:
        from ...utils.chain_id import get_chain_id

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
        from eth_keys import keys

        private_key_hex = wallet_data.get("private_key")
        if not private_key_hex:
            error("Wallet does not contain private key")
            return

        # Remove 0x prefix if present for eth_keys
        if private_key_hex.startswith("0x"):
            private_key_hex = private_key_hex[2:]
        private_key = keys.PrivateKey(bytes.fromhex(private_key_hex))
    except Exception as e:
        error(f"Error loading private key: {e}")
        return

    # Create transaction with modern payload format
    # Convert AIT to seconds for blockchain
    amount_seconds = ait_to_seconds(amount)
    fee_seconds = ait_to_seconds(fee)

    transaction = {
        "type": "TRANSFER",
        "chain_id": chain_id,
        "from": sender_address,
        "to": to_address,
        "amount": amount_seconds,
        "nonce": actual_nonce,
        "fee": fee_seconds,
        "payload": {"amount": amount_seconds},
    }

    # Sign transaction (secp256k1, matching the node verifier — see A1 wire format)
    import json

    from eth_utils import keccak

    # The node verifier signs over {from, to, amount, fee, nonce, payload, type}
    # with sort_keys=True, separators=(",", ":"). chain_id is excluded (B6 gap).
    signed_fields = {
        k: transaction[k] for k in ("from", "to", "amount", "fee", "nonce", "payload", "type") if k in transaction
    }
    message = json.dumps(signed_fields, sort_keys=True, separators=(",", ":")).encode()
    signature = private_key.sign_msg_hash(keccak(message))
    transaction["signature"] = signature.to_bytes().hex()

    # Submit to blockchain
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.post("/rpc/transaction", json=transaction)
        tx_hash = result.get("transaction_hash")
        success(f"Transaction submitted: {tx_hash}")
        output(
            {
                "transaction_hash": tx_hash,
                "from": sender_address,
                "to": to_address,
                "amount": f"{amount} AIT",
                "fee": f"{fee} AIT",
                "chain_id": chain_id,
            },
            ctx.obj.get("output_format", "table"),
        )
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
    total_earned = sum(tx["amount"] for tx in transactions if tx["type"] == "earn" and tx["amount"] > 0)
    total_spent = sum(abs(tx["amount"]) for tx in transactions if tx["type"] in ["spend", "send"] and tx["amount"] < 0)
    jobs_completed = len([tx for tx in transactions if tx["type"] == "earn"])

    output(
        {
            "wallet": wallet_name,
            "address": wallet_data["address"],
            "current_balance": format_ait(wallet_data.get("balance", 0)),
            "total_earned": format_ait(total_earned),
            "total_spent": format_ait(total_spent),
            "jobs_completed": jobs_completed,
            "transaction_count": len(transactions),
            "wallet_created": wallet_data.get("created_at"),
        },
        ctx.obj.get("output_format", "table"),
    )
