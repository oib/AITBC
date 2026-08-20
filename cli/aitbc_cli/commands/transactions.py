"""
Transaction commands for AITBC CLI
"""

import json
import os
import sys
from decimal import Decimal
from pathlib import Path

import click
from eth_keys import keys
from eth_utils import keccak

from aitbc import ValidationError
from aitbc.utils import ait_to_seconds, format_ait
from aitbc.utils.validation import validate_address_strict

from ..config import get_config
from ..utils import DECIMAL, error, success
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger
from ..utils.wallet import decrypt_private_key

logger = get_logger(__name__)

DEFAULT_RPC_URL = "http://127.0.0.1:8202"
# The chain settles in integer compute-seconds (3600 = 1 AIT), so the default fee is
# expressed in those units too: 36 seconds = 0.01 AIT.
DEFAULT_FEE_SECONDS = 36
# Use the same wallet directory as wallet create command
DEFAULT_KEYSTORE_DIR = Path.home() / ".aitbc" / "wallets"


@click.group()
def transactions():
    """Transaction management commands"""
    pass


def _send_transaction_impl(
    from_wallet: str,
    to_address: str,
    amount: Decimal,
    fee: Decimal,
    password: str,
    keystore_dir: Path | None = None,
    rpc_url: str | None = None,
) -> str | None:
    """Send a secp256k1-signed transaction from one wallet to another."""
    keystore_dir = keystore_dir or DEFAULT_KEYSTORE_DIR
    rpc_url = rpc_url or DEFAULT_RPC_URL

    # Validate recipient address
    try:
        validate_address_strict(to_address)
    except ValidationError as e:
        logger.error("Invalid recipient address: %s", e)
        error(f"Invalid recipient address: {e}")
        return None

    # Validate amount/fee
    if amount <= 0:
        logger.error("Invalid amount: %s must be positive", amount)
        error("Amount must be positive")
        return None

    # Get sender wallet info
    sender_keystore = keystore_dir / f"{from_wallet}.json"
    if not sender_keystore.exists():
        error(f"Wallet '{from_wallet}' not found")
        return None

    with open(sender_keystore) as f:
        sender_data = json.load(f)

    sender_address = sender_data["address"]

    # Decrypt private key if wallet is encrypted, otherwise use directly
    try:
        if sender_data.get("encrypted") and isinstance(sender_data.get("private_key"), dict):
            private_key_hex = decrypt_private_key(sender_keystore, password)
        elif sender_data.get("encrypted_private_key"):
            private_key_hex = decrypt_private_key(sender_keystore, password)
        else:
            # Unencrypted wallet (created with --no-encrypt)
            private_key_hex = sender_data.get("private_key")
            if not private_key_hex:
                error("Wallet does not contain private key")
                return None

        # Strip 0x prefix if present
        if isinstance(private_key_hex, str) and private_key_hex.startswith("0x"):
            private_key_hex = private_key_hex[2:]

        private_key = keys.PrivateKey(bytes.fromhex(private_key_hex))
    except Exception as e:
        logger.error("Error loading private key: %s", e)
        error(f"Error loading private key: {e}")
        return None

    # Resolve chain_id and nonce from the blockchain node
    from ..utils.chain_id import get_chain_id

    chain_id = get_chain_id(rpc_url, override=None, timeout=5)

    actual_nonce = 0
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=5)
        account_data = http_client.get(f"/rpc/account/{sender_address}")
        actual_nonce = account_data.get("nonce", 0)
    except Exception:
        actual_nonce = 0

    # Convert AIT to compute-seconds (chain unit)
    amount_seconds = ait_to_seconds(amount)
    fee_seconds = ait_to_seconds(fee)

    # The TransactionRequest model adds to/amount to payload, so we include them up front
    # and sign over the exact dict the verifier will hash.
    transaction = {
        "chain_id": chain_id,
        "from": sender_address,
        "to": to_address,
        "amount": amount_seconds,
        "fee": fee_seconds,
        "nonce": actual_nonce,
        "type": "TRANSFER",
        "payload": {"to": to_address, "amount": amount_seconds},
    }

    # Sign the canonical JSON (sort_keys, compact) of all fields except the signature.
    message = json.dumps(transaction, sort_keys=True, separators=(",", ":")).encode()
    signature = private_key.sign_msg_hash(keccak(message))
    transaction["signature"] = signature.to_bytes().hex()

    # Submit to blockchain
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.post("/rpc/transaction", json=transaction)
        tx_hash = result.get("transaction_hash")
        success(f"Transaction submitted: {tx_hash}")
        logger.info("Transaction submitted: %s from %s to %s", tx_hash, from_wallet, to_address)
        return tx_hash
    except NetworkError as e:
        logger.error("Network error submitting transaction: %s", e)
        error(f"Error submitting transaction: {e}")
        return None
    except Exception as e:
        logger.error("Error submitting transaction: %s", e)
        error(f"Error: {e}")
        return None


@transactions.command()
@click.option("--from", "from_wallet", required=True, help="From wallet name")
@click.option("--to", "to_address", required=True, help="To address")
@click.option("--amount", type=DECIMAL, required=True, help="Amount to send")
@click.option("--fee", type=DECIMAL, default="0.001", help="Transaction fee")
@click.option("--password", help="Wallet password")
@click.option("--password-file", help="File containing wallet password")
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.option("--use-explorer", is_flag=True, help="Use Explorer API for status checks")
def send(
    from_wallet: str,
    to_address: str,
    amount: Decimal,
    fee: Decimal,
    password: str | None,
    password_file: str | None,
    rpc_url: str | None,
    use_explorer: bool,
):
    """Send transaction from one wallet to another"""
    # Password resolution priority:
    # 1. --password flag
    # 2. --password-file flag
    # 3. AITBC_WALLET_PASSWORD environment variable
    # 4. Check if wallet is unencrypted (skip password)
    # 5. Interactive getpass prompt (only if TTY)

    if password is not None:
        # Password provided via flag (even if empty string)
        pass
    elif password_file:
        with open(password_file) as f:
            password = f.read().strip()
    elif "AITBC_WALLET_PASSWORD" in os.environ:
        # Environment variable is set (even if empty)
        password = os.environ["AITBC_WALLET_PASSWORD"]
    else:
        # Check if wallet is unencrypted
        keystore_dir = DEFAULT_KEYSTORE_DIR
        sender_keystore = keystore_dir / f"{from_wallet}.json"
        if sender_keystore.exists():
            with open(sender_keystore) as f:
                sender_data = json.load(f)
            # If wallet has no encrypted_private_key, it's unencrypted
            if not sender_data.get("encrypted_private_key"):
                password = ""  # Empty password for unencrypted wallets
            else:
                # Wallet is encrypted, need password
                if not sys.stdin.isatty():
                    abort(
                        None,
                        "No TTY available for password prompt. Use --password or --password-file, or set AITBC_WALLET_PASSWORD environment variable.",
                    )
                else:
                    import getpass

                    try:
                        password = getpass.getpass("Enter wallet password: ")
                    except Exception as e:
                        abort(None, f"Password prompt failed: {e}", from_exception=e)
        else:
            # Wallet file doesn't exist, will fail later in _send_transaction_impl
            if not sys.stdin.isatty():
                abort(
                    None,
                    "No TTY available for password prompt. Use --password or --password-file, or set AITBC_WALLET_PASSWORD environment variable.",
                )
            else:
                import getpass

                try:
                    password = getpass.getpass("Enter wallet password: ")
                except Exception as e:
                    abort(None, f"Password prompt failed: {e}", from_exception=e)

    if not rpc_url:
        config = get_config()
        rpc_url = getattr(config, "blockchain_rpc_url", DEFAULT_RPC_URL) or DEFAULT_RPC_URL

    if password is None:
        error("Password is required for transaction")
        return

    tx_hash = _send_transaction_impl(from_wallet, to_address, amount, fee, password, rpc_url=rpc_url)
    if tx_hash:
        success(f"Transaction sent: {tx_hash}")

        # Optionally check status via Explorer API
        if use_explorer:
            try:
                config = get_config()
                http_client = AITBCHTTPClient(base_url=config.explorer_api_url, timeout=30)
                result = http_client.get(f"/api/transactions/by-hash/{tx_hash}")
                success("Transaction status (via Explorer):")
                click.echo(json.dumps(result, indent=2))
            except NetworkError as e:
                error(f"Explorer API unavailable: {e}")
            except Exception as e:
                error(f"Error checking status via Explorer: {e}")


@transactions.command()
@click.option("--transactions-file", required=True, help="JSON file with batch transactions")
@click.option("--password", help="Wallet password")
@click.option("--password-file", help="File containing wallet password")
@click.option("--rpc-url", help="Blockchain RPC URL")
def batch(transactions_file: str, password: str | None, password_file: str | None, rpc_url: str | None):
    """Send batch transactions"""
    # Password resolution priority:
    # 1. --password flag
    # 2. --password-file flag
    # 3. AITBC_WALLET_PASSWORD environment variable
    # 4. Check if wallet is unencrypted (skip password)
    # 5. Interactive getpass prompt (only if TTY)

    if password is not None:
        # Password provided via flag (even if empty string)
        pass
    elif password_file:
        with open(password_file) as f:
            password = f.read().strip()
    elif "AITBC_WALLET_PASSWORD" in os.environ:
        # Environment variable is set (even if empty)
        password = os.environ["AITBC_WALLET_PASSWORD"]
    else:
        # Check if first wallet is unencrypted
        with open(transactions_file) as f:
            transactions_data = json.load(f)
        if transactions_data:
            first_wallet = transactions_data[0].get("from_wallet")
            keystore_dir = DEFAULT_KEYSTORE_DIR
            sender_keystore = keystore_dir / f"{first_wallet}.json"
            if sender_keystore.exists():
                with open(sender_keystore) as f:
                    sender_data = json.load(f)
                # If wallet has no encrypted_private_key, it's unencrypted
                if not sender_data.get("encrypted_private_key"):
                    password = ""  # Empty password for unencrypted wallets
                else:
                    # Wallet is encrypted, need password
                    if not sys.stdin.isatty():
                        abort(
                            None,
                            "No TTY available for password prompt. Use --password or --password-file, or set AITBC_WALLET_PASSWORD environment variable.",
                        )
                    else:
                        import getpass

                        try:
                            password = getpass.getpass("Enter wallet password: ")
                        except Exception as e:
                            abort(None, f"Password prompt failed: {e}", from_exception=e)
            else:
                # Wallet file doesn't exist
                if not sys.stdin.isatty():
                    abort(
                        None,
                        "No TTY available for password prompt. Use --password or --password-file, or set AITBC_WALLET_PASSWORD environment variable.",
                    )
                else:
                    import getpass

                    try:
                        password = getpass.getpass("Enter wallet password: ")
                    except Exception as e:
                        abort(None, f"Password prompt failed: {e}", from_exception=e)
        else:
            # Empty transactions file
            if not sys.stdin.isatty():
                abort(
                    None,
                    "No TTY available for password prompt. Use --password or --password-file, or set AITBC_WALLET_PASSWORD environment variable.",
                )
            else:
                import getpass

                try:
                    password = getpass.getpass("Enter wallet password: ")
                except Exception as e:
                    abort(None, f"Password prompt failed: {e}", from_exception=e)

    if not rpc_url:
        config = get_config()
        rpc_url = getattr(config, "blockchain_rpc_url", DEFAULT_RPC_URL) or DEFAULT_RPC_URL

    if password is None:
        error("Password is required for batch transactions")
        return

    with open(transactions_file) as f:
        transactions_data = json.load(f)

    results = []
    for tx in transactions_data:
        try:
            # amounts come out of a JSON batch file as numbers; convert at the boundary
            tx_hash = _send_transaction_impl(
                tx["from_wallet"],
                tx["to_address"],
                Decimal(str(tx["amount"])),
                Decimal(str(tx.get("fee", 10))),
                password,
                rpc_url=rpc_url,
            )
            results.append({"transaction": tx, "hash": tx_hash, "success": tx_hash is not None})

            if tx_hash:
                success(f"Transaction sent: {tx['from_wallet']} → {tx['to_address']} ({tx['amount']} AIT)")
            else:
                error(f"Transaction failed: {tx['from_wallet']} → {tx['to_address']}")

        except Exception as e:
            results.append({"transaction": tx, "hash": None, "success": False, "error": str(e)})
            error(f"Transaction error: {e}")

    success(f"Batch completed: {len([r for r in results if r['success']])}/{len(results)} successful")


@transactions.command()
@click.argument("tx_hash")
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.option("--use-explorer", is_flag=True, help="Use Explorer API instead of RPC")
def status(tx_hash: str, rpc_url: str | None, use_explorer: bool):
    """Get transaction status"""
    if use_explorer:
        try:
            config = get_config()
            http_client = AITBCHTTPClient(base_url=config.explorer_api_url, timeout=30)
            result = http_client.get(f"/api/transactions/by-hash/{tx_hash}")
            success(f"Transaction status for {tx_hash} (via Explorer)")
            click.echo(json.dumps(result, indent=2))
        except NetworkError as e:
            error(f"Explorer API unavailable: {e}")
        except Exception as e:
            error(f"Error: {e}")
    else:
        if not rpc_url:
            rpc_url = DEFAULT_RPC_URL

        try:
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
            result = http_client.get(f"/rpc/transaction/{tx_hash}")
            success(f"Transaction status for {tx_hash}")
            click.echo(json.dumps(result, indent=2))
        except NetworkError as e:
            error(f"Error getting transaction status: {e}")
        except Exception as e:
            error(f"Error: {e}")


@transactions.command()
@click.option("--rpc-url", help="Blockchain RPC URL")
def pending(rpc_url: str | None):
    """Get pending transactions"""
    if not rpc_url:
        rpc_url = DEFAULT_RPC_URL

    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        data = http_client.get("/rpc/pending")
        transactions = data.get("transactions", [])
        success(f"Pending transactions: {len(transactions)}")
        for tx in transactions:
            tx_hash = tx.get("hash") or tx.get("tx_hash") or tx.get("id")
            tx_type = tx.get("type", "TRANSFER")
            amount = tx.get("amount", tx.get("value", 0))
            sender = tx.get("from", "?")
            if tx_hash:
                click.echo(f"  - {tx_hash}: {amount} AIT ({tx_type})")
            else:
                click.echo(f"  - {tx_type} {amount} AIT from {sender[:16]}...")
    except NetworkError as e:
        error(f"Error getting pending transactions: {e}")
    except Exception as e:
        error(f"Error: {e}")


@transactions.command()
@click.option("--from", "from_wallet", required=True, help="From wallet name")
@click.option("--to", "to_address", required=True, help="To address")
@click.option("--amount", type=DECIMAL, required=True, help="Amount to send")
@click.option("--rpc-url", help="Blockchain RPC URL")
def estimate_fee(from_wallet: str, to_address: str, amount: Decimal, rpc_url: str | None):
    """Estimate transaction fee"""
    if not rpc_url:
        rpc_url = DEFAULT_RPC_URL

    try:
        test_tx = {
            "sender": "",
            "recipient": to_address,
            "value": ait_to_seconds(amount),
            "fee": DEFAULT_FEE_SECONDS,
            "nonce": 0,
            "type": "transfer",
            "payload": {},
        }

        try:
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
            fee_data = http_client.post("/rpc/estimateFee", json=test_tx)
            # the node answers in compute-seconds; printing that number next to "AIT"
            # reported the 36-second default -- 0.01 AIT -- as "36.0 AIT".
            estimated_fee = fee_data.get("estimated_fee", DEFAULT_FEE_SECONDS)
            success(f"Estimated fee: {format_ait(estimated_fee)}")
        except NetworkError:
            success(f"Estimated fee: {format_ait(DEFAULT_FEE_SECONDS)} (default)")
    except Exception as e:
        error(f"Error estimating fee: {e}")
        success(f"Estimated fee: {format_ait(DEFAULT_FEE_SECONDS)} (default)")


@transactions.command()
@click.argument("address")
@click.option("--limit", default=100, help="Number of transactions to return")
@click.option("--use-explorer", is_flag=True, help="Use Explorer API instead of RPC")
def search(address: str, limit: int, use_explorer: bool):
    """Search transactions by address or node ID"""
    if use_explorer:
        try:
            config = get_config()
            http_client = AITBCHTTPClient(base_url=config.explorer_api_url, timeout=30)
            params = {"address": address, "limit": limit}
            result = http_client.get("/api/transactions/search", params=params)
            transactions = result.get("transactions", [])
            success(f"Found {len(transactions)} transactions for {address} (via Explorer)")
            click.echo(json.dumps(transactions, indent=2))
        except NetworkError as e:
            error(f"Explorer API unavailable: {e}")
        except Exception as e:
            error(f"Error searching transactions: {e}")
    else:
        # Fallback to RPC method if available
        error("Transaction search via RPC not implemented. Use --use-explorer flag to use Explorer API.")
