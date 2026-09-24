"""
Transaction commands for AITBC CLI
"""

import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import click
from eth_keys import keys
from eth_utils import keccak

from aitbc import ValidationError
from aitbc.utils import ait_to_units, format_ait
from aitbc.utils.units import DEFAULT_TX_FEE_UNITS
from aitbc.utils.validation import validate_address_strict

from ..config import get_config
from ..utils import DECIMAL, error, success
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger
from ..utils.wallet import decrypt_private_key
from ..utils.wallet_paths import wallet_dir

logger = get_logger(__name__)

DEFAULT_RPC_URL = "http://127.0.0.1:8202"


def _resolve_transaction_rpc_url(rpc_url: str | None) -> str:
    """Return the RPC URL to submit a transaction from.

    Follower/customer nodes run a local blockchain RPC, but it cannot on its own
    propagate transactions to the proposer. When the default local RPC is used,
    prefer the hub's public blockchain RPC URL instead.
    """
    if rpc_url:
        return rpc_url
    config = get_config()
    rpc_url = getattr(config, "blockchain_rpc_url", DEFAULT_RPC_URL) or DEFAULT_RPC_URL
    if "localhost" in rpc_url or "127.0.0.1" in rpc_url:
        hub_rpc = (
            getattr(config, "hub_blockchain_rpc_url", None) or f"https://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        )
        if hub_rpc:
            hub_rpc = hub_rpc.rstrip("/")
            if hub_rpc.endswith("/rpc"):
                hub_rpc = hub_rpc[:-4]
            if hub_rpc:
                return hub_rpc
    return rpc_url


# The chain settles in integer compute-units (1 AIT = 36_000_000), so the default fee is
# expressed in those units too: 360_000 compute-units = 0.01 AIT.
DEFAULT_FEE_UNITS = DEFAULT_TX_FEE_UNITS
# Use the same wallet directory as wallet create command


@click.group(
    epilog="""Examples:

  aitbc transactions send --from wallet-1 --to 0x... --amount 10

  aitbc transactions pending"""
)
def transactions():
    """Send, batch, estimate fees, and query transactions."""
    pass


def _prompt_wallet_password() -> str:
    """Prompt for a wallet password on a TTY, or abort when none is available."""
    if not sys.stdin.isatty():
        abort(
            None,
            "No TTY available for password prompt. Use --password or --password-file, or set AITBC_WALLET_PASSWORD environment variable.",
        )
    import getpass

    try:
        return getpass.getpass("Enter wallet password: ")
    except Exception as e:
        abort(None, f"Password prompt failed: {e}", from_exception=e)
        raise  # unreachable: abort always raises


def _load_sender_private_key(sender_keystore: Path, sender_data: dict[str, Any], password: str):
    """Decrypt the wallet's private key, or read it for unencrypted wallets."""
    private_key_hex: str | None
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

        return keys.PrivateKey(bytes.fromhex(private_key_hex))
    except Exception as e:
        logger.error("Error loading private key: %s", e)
        error(f"Error loading private key: {e}")
        return None


def _resolve_nonce(rpc_url: str, sender_address: str) -> int:
    """Fetch the sender's on-chain nonce, defaulting to 0 when unreachable."""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=5)
        account_data = http_client.get(f"/rpc/account/{sender_address}")
        nonce: int = account_data.get("nonce", 0)
        return nonce
    except Exception:
        return 0


def _send_transaction_impl(
    from_wallet: str,
    to_address: str,
    amount: Decimal,
    fee: Decimal,
    password: str,
    keystore_dir: Path | None = None,
    rpc_url: str | None = None,
    tx_type: str = "TRANSFER",
    payload: dict[str, Any] | None = None,
    nonce_offset: int = 0,
) -> str | None:
    """Send a secp256k1-signed transaction from one wallet to another."""
    keystore_dir = keystore_dir or wallet_dir()
    rpc_url = _resolve_transaction_rpc_url(rpc_url)

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
    private_key = _load_sender_private_key(sender_keystore, sender_data, password)
    if private_key is None:
        return None

    # Resolve chain_id and nonce from the blockchain node
    from ..utils.chain_id import get_chain_id

    chain_id = get_chain_id(rpc_url, override=None, timeout=5)

    # Batch callers pass a per-sender offset: the chain's account nonce does not
    # move while earlier batch transactions sit in the mempool, so every entry
    # would otherwise sign with the same nonce and only the first could be mined.
    actual_nonce = _resolve_nonce(rpc_url, sender_address) + nonce_offset

    # Convert AIT to compute-units (chain unit)
    amount_seconds = ait_to_units(amount)
    fee_seconds = ait_to_units(fee)

    # The TransactionRequest model adds to/amount to payload, so we include them up front
    # and sign over the exact dict the verifier will hash.
    tx_payload = dict(payload) if payload else {}
    if "to" not in tx_payload:
        tx_payload["to"] = to_address
    if "amount" not in tx_payload:
        tx_payload["amount"] = amount_seconds
    transaction = {
        "chain_id": chain_id,
        "from": sender_address,
        "to": to_address,
        "amount": amount_seconds,
        "fee": fee_seconds,
        "nonce": actual_nonce,
        "type": tx_type,
        "payload": tx_payload,
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


def _resolve_send_password(from_wallet: str, password: str | None, password_file: str | None) -> str | None:
    """Resolve the wallet password: flag, file, env, empty for unencrypted, else prompt."""
    if password is not None:
        # Password provided via flag (even if empty string)
        return password
    if password_file:
        with open(password_file) as f:
            return f.read().strip()
    if "AITBC_WALLET_PASSWORD" in os.environ:
        # Environment variable is set (even if empty)
        return os.environ["AITBC_WALLET_PASSWORD"]

    # Check if wallet is unencrypted
    sender_keystore = wallet_dir() / f"{from_wallet}.json"
    if sender_keystore.exists():
        with open(sender_keystore) as f:
            sender_data = json.load(f)
        # If wallet has no encrypted_private_key, it's unencrypted
        if not sender_data.get("encrypted_private_key"):
            return ""  # Empty password for unencrypted wallets
    # Wallet is encrypted or missing — the prompt fails for a missing file later
    # in _send_transaction_impl, matching the original ordering.
    return _prompt_wallet_password()


def _parse_payload_json(payload: str | None) -> dict[str, Any] | None:
    """Parse the --payload JSON object, reporting errors instead of raising."""
    if not payload:
        return None
    try:
        parsed_payload = json.loads(payload)
        if not isinstance(parsed_payload, dict):
            error("Payload must be a JSON object")
            return None
        return parsed_payload
    except json.JSONDecodeError as e:
        error(f"Invalid payload JSON: {e}")
        return None


@transactions.command(
    epilog="""Examples:

  aitbc transactions send --from wallet-1 --to 0x... --amount 10

  aitbc transactions send --from wallet-1 --to 0x... --amount 10 --fee 0.001"""
)
@click.option("--from", "from_wallet", required=True, help="From wallet name")
@click.option("--to", "to_address", required=True, help="To address")
@click.option("--amount", type=DECIMAL, required=True, help="Amount to send")
@click.option("--fee", type=DECIMAL, default="0.001", help="Transaction fee")
@click.option("--password", help="Wallet password")
@click.option("--password-file", help="File containing wallet password")
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.option("--type", "tx_type", default="TRANSFER", help="Transaction type (default TRANSFER)")
@click.option("--payload", help="JSON payload for non-standard transaction types")
@click.option("--use-explorer", is_flag=True, help="Use Explorer API for status checks")
def send(
    from_wallet: str,
    to_address: str,
    amount: Decimal,
    fee: Decimal,
    password: str | None,
    password_file: str | None,
    rpc_url: str | None,
    tx_type: str,
    payload: str | None,
    use_explorer: bool,
):
    """Send a transaction from one wallet to another."""
    # Password resolution priority:
    # 1. --password flag
    # 2. --password-file flag
    # 3. AITBC_WALLET_PASSWORD environment variable
    # 4. Check if wallet is unencrypted (skip password)
    # 5. Interactive getpass prompt (only if TTY)

    password = _resolve_send_password(from_wallet, password, password_file)

    if not rpc_url:
        rpc_url = _resolve_transaction_rpc_url(None)

    if password is None:
        error("Password is required for transaction")
        return

    parsed_payload: dict[str, Any] | None = None
    if payload:
        parsed_payload = _parse_payload_json(payload)
        if parsed_payload is None:
            return

    tx_hash = _send_transaction_impl(
        from_wallet,
        to_address,
        amount,
        fee,
        password,
        rpc_url=rpc_url,
        tx_type=tx_type,
        payload=parsed_payload,
    )
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


def _resolve_batch_password(transactions_file: str, password: str | None, password_file: str | None) -> str | None:
    """Resolve the wallet password: flag, file, env, unencrypted first wallet, else prompt."""
    if password is not None:
        # Password provided via flag (even if empty string)
        return password
    if password_file:
        with open(password_file) as f:
            return f.read().strip()
    if "AITBC_WALLET_PASSWORD" in os.environ:
        # Environment variable is set (even if empty)
        return os.environ["AITBC_WALLET_PASSWORD"]

    # Check if first wallet is unencrypted
    with open(transactions_file) as f:
        transactions_data = json.load(f)
    if transactions_data:
        first_wallet = transactions_data[0].get("from_wallet")
        sender_keystore = wallet_dir() / f"{first_wallet}.json"
        if sender_keystore.exists():
            with open(sender_keystore) as f:
                sender_data = json.load(f)
            # If wallet has no encrypted_private_key, it's unencrypted
            if not sender_data.get("encrypted_private_key"):
                return ""  # Empty password for unencrypted wallets
    # Wallet is encrypted, missing, or the file is empty — prompt.
    return _prompt_wallet_password()


def _process_batch_entry(
    tx: dict[str, Any],
    password: str,
    rpc_url: str,
    seen_entries: set,
    seen_hashes: set,
    nonce_offsets: dict[str, int],
    results: list,
) -> None:
    """Send one batch entry, deduping identical entries and duplicate hashes."""
    try:
        # amounts come out of a JSON batch file as numbers; convert at the boundary
        amount = Decimal(str(tx["amount"]))
        # default fee matches `send --fee` (0.001 AIT), not the old 10 AIT
        fee = Decimal(str(tx.get("fee", "0.001")))
        entry_key = (tx["from_wallet"], str(tx["to_address"]).lower(), amount, fee)
        if entry_key in seen_entries:
            results.append({"transaction": tx, "hash": None, "success": False, "error": "duplicate batch entry"})
            error(f"Duplicate batch entry skipped: {tx['from_wallet']} → {tx['to_address']} ({tx['amount']} AIT)")
            return
        seen_entries.add(entry_key)

        from_wallet = tx["from_wallet"]
        tx_hash = _send_transaction_impl(
            from_wallet,
            tx["to_address"],
            amount,
            fee,
            password,
            rpc_url=rpc_url,
            nonce_offset=nonce_offsets.get(from_wallet, 0),
        )
        if tx_hash:
            nonce_offsets[from_wallet] = nonce_offsets.get(from_wallet, 0) + 1
            if tx_hash in seen_hashes:
                results.append(
                    {
                        "transaction": tx,
                        "hash": tx_hash,
                        "success": False,
                        "error": f"duplicate transaction hash {tx_hash}",
                    }
                )
                error(f"Transaction produced a duplicate hash: {tx['from_wallet']} → {tx['to_address']}")
                return
            seen_hashes.add(tx_hash)
        results.append({"transaction": tx, "hash": tx_hash, "success": tx_hash is not None})

        if tx_hash:
            success(f"Transaction sent: {tx['from_wallet']} → {tx['to_address']} ({tx['amount']} AIT)")
        else:
            error(f"Transaction failed: {tx['from_wallet']} → {tx['to_address']}")

    except Exception as e:
        results.append({"transaction": tx, "hash": None, "success": False, "error": str(e)})
        error(f"Transaction error: {e}")


@transactions.command(
    epilog="""Examples:

  aitbc transactions batch --transactions-file /tmp/txs.json

  aitbc transactions batch --transactions-file /tmp/txs.json --password-file /tmp/pass

  The batch file is a JSON list of objects with keys:
    from_wallet  — sender wallet name (required)
    to_address   — recipient 0x address (required)
    amount       — AIT amount to send (required)
    fee          — AIT fee (optional, defaults to 0.001 like `send --fee`)"""
)
@click.option("--transactions-file", required=True, help="JSON file with batch transactions")
@click.option("--password", help="Wallet password")
@click.option("--password-file", help="File containing wallet password")
@click.option("--rpc-url", help="Blockchain RPC URL")
def batch(transactions_file: str, password: str | None, password_file: str | None, rpc_url: str | None):
    """Send multiple transactions from a JSON batch file.

    Entries are objects ``{"from_wallet", "to_address", "amount", "fee"?}``
    with amounts in AIT. Identical entries are rejected as duplicates instead
    of being reported as two successes for the same on-chain hash.
    """
    # Password resolution priority:
    # 1. --password flag
    # 2. --password-file flag
    # 3. AITBC_WALLET_PASSWORD environment variable
    # 4. Check if wallet is unencrypted (skip password)
    # 5. Interactive getpass prompt (only if TTY)

    password = _resolve_batch_password(transactions_file, password, password_file)

    if not rpc_url:
        rpc_url = _resolve_transaction_rpc_url(None)

    if password is None:
        error("Password is required for batch transactions")
        return

    with open(transactions_file) as f:
        transactions_data = json.load(f)

    # The chain's account nonce does not move while earlier batch transactions
    # sit in the mempool, so entries from the same wallet sign with per-entry
    # nonce offsets — otherwise identical entries produce the same tx hash and
    # the mempool silently dedupes them while the CLI reported "2/2 successful".
    seen_entries: set[tuple[str, str, Decimal, Decimal]] = set()
    seen_hashes: set[str] = set()
    nonce_offsets: dict[str, int] = {}

    results: list[dict[str, Any]] = []
    for tx in transactions_data:
        _process_batch_entry(tx, password, rpc_url, seen_entries, seen_hashes, nonce_offsets, results)

    success(f"Batch completed: {len([r for r in results if r['success']])}/{len(results)} successful")


@transactions.command(
    epilog="""Examples:

  aitbc transactions status --tx-hash 0x...

  aitbc transactions status --tx-hash 0x... --use-explorer"""
)
@click.option("--tx-hash", "tx_hash", required=True, help="The Tx hash.")
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.option("--use-explorer", is_flag=True, help="Use Explorer API instead of RPC")
def status(tx_hash: str, rpc_url: str | None, use_explorer: bool):
    """Get the status of a transaction by its hash."""
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
            rpc_url = _resolve_transaction_rpc_url(None)

        try:
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
            result = http_client.get(f"/rpc/transaction/{tx_hash}")
            success(f"Transaction status for {tx_hash}")
            click.echo(json.dumps(result, indent=2))
        except NetworkError as e:
            error(f"Error getting transaction status: {e}")
        except Exception as e:
            error(f"Error: {e}")


@transactions.command(
    epilog="""Examples:

  aitbc transactions pending

  aitbc transactions pending --rpc-url http://localhost:8202"""
)
@click.option("--rpc-url", help="Blockchain RPC URL")
def pending(rpc_url: str | None):
    """Get the list of pending transactions from the node."""
    if not rpc_url:
        rpc_url = _resolve_transaction_rpc_url(None)

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


@transactions.command(
    epilog="""Examples:

  aitbc transactions estimate-fee --from wallet-1 --to 0x... --amount 10

  aitbc transactions estimate-fee --from wallet-1 --to 0x... --amount 10 --rpc-url http://localhost:8202"""
)
@click.option("--from", "from_wallet", required=True, help="From wallet name")
@click.option("--to", "to_address", required=True, help="To address")
@click.option("--amount", type=DECIMAL, required=True, help="Amount to send")
@click.option("--rpc-url", help="Blockchain RPC URL")
def estimate_fee(from_wallet: str, to_address: str, amount: Decimal, rpc_url: str | None):
    """Estimate the transaction fee for a transfer.

    The node has no fee-estimation endpoint (the old ``/rpc/estimateFee``
    call always 404'd and fell back here), so the estimate is the flat
    default fee applied to every transfer.
    """
    success(f"Estimated fee: {format_ait(DEFAULT_FEE_UNITS)} (default)")


@transactions.command(
    epilog="""Examples:

  aitbc transactions search --address 0x...

  aitbc transactions search --address 0x... --limit 50 --use-explorer"""
)
@click.option("--address", "address", required=True, help="Blockchain address to fund.")
@click.option("--limit", default=100, help="Number of transactions to return")
@click.option("--use-explorer", is_flag=True, help="Use Explorer API instead of RPC")
def search(address: str, limit: int, use_explorer: bool):
    """Search transactions by address or node ID."""
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
