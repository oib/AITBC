"""
Transaction commands for AITBC CLI
"""

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import click
from eth_utils import keccak

from aitbc import ValidationError
from aitbc.config.hub import normalize_hub_base
from aitbc.utils import ait_to_units, format_ait
from aitbc.utils.units import DEFAULT_TX_FEE_AIT, DEFAULT_TX_FEE_UNITS
from aitbc.utils.validation import validate_address_strict

from ..config import get_config
from ..utils import DECIMAL, error, info, success, warning
from ..utils.error_handling import CLIError, abort
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger, http_response_status
from ..utils.wallet import decrypt_private_key
from ..utils.wallet_paths import (
    WalletSearchResult,
    ambiguous_wallet_note,
    find_wallet_file_report,
    service_dir_wallet_note,
    wallet_not_found_message,
)
from ..utils.wallet_secret import resolve_wallet_password, wallet_password_options

logger = get_logger(__name__)

DEFAULT_RPC_URL = "http://127.0.0.1:8202"

# Transaction types whose apply path rejects any nonzero value — mirrors
# aitbc_chain.state.state_transition._ZERO_VALUE_TX_TYPES (the node package
# is not a CLI dependency, so the set is duplicated here).
_ZERO_VALUE_TX_TYPES = frozenset({"MESSAGE", "GOVERNANCE_EXECUTE", "GPU_REGISTER", "GPU_ALLOCATE", "GPU_MARKET"})


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
        hub_rpc = getattr(config, "hub_blockchain_rpc_url", None) or normalize_hub_base(
            config.hub_discovery_url or "hub.aitbc.invalid"
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

        from eth_keys import keys

        return keys.PrivateKey(bytes.fromhex(private_key_hex))
    except Exception as e:
        logger.error("Error loading private key: %s", e)
        abort(None, f"Error loading private key: {e}")
        return None


def _resolve_nonce(rpc_url: str, sender_address: str) -> int:
    """Fetch the sender's on-chain nonce; abort the command on failure.

    A failed lookup must not mean nonce 0 — the wrong nonce produces an
    already-signed transaction the chain refuses.
    """
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=5)
        account_data = http_client.get(f"/rpc/account/{sender_address}")
        nonce = account_data.get("nonce")
        if nonce is None:
            raise ValueError(f"/rpc/account/{sender_address} response carried no nonce")
        return int(nonce)
    except Exception as e:
        abort(
            None,
            f"Nonce lookup for {sender_address} via {rpc_url} failed: {e}. "
            "Check the node is serving this account or pass --rpc-url",
            from_exception=e,
        )
        raise AssertionError("unreachable: abort always raises") from e


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
    rpc_url = _resolve_transaction_rpc_url(rpc_url)

    # Validate recipient address
    try:
        validate_address_strict(to_address)
    except ValidationError as e:
        logger.error("Invalid recipient address: %s", e)
        abort(None, f"Invalid recipient address: {e}")
        return None

    # Validate amount/fee. Zero-value types (mirrors
    # aitbc_chain.state.state_transition._ZERO_VALUE_TX_TYPES — no shared
    # constants package exists) are REJECTED by apply when value != 0, so
    # they need --amount 0; for every other type a zero amount is a no-op
    # that only burns the fee, kept an error.
    if tx_type.upper() in _ZERO_VALUE_TX_TYPES:
        if amount != 0:
            error(f"{tx_type.upper()} transactions must have amount=0")
            return None
    elif amount <= 0:
        logger.error("Invalid amount: %s must be positive", amount)
        error("Amount must be positive")
        return None

    # Get sender wallet info. An explicit keystore_dir wins outright; otherwise
    # the shared search order applies (configured wallet dir, then the service
    # wallet dir — a wallet that only exists under /var/lib/aitbc/wallets is
    # still found by name).
    report: WalletSearchResult | None = None
    sender_keystore: Path | None
    if keystore_dir is not None:
        sender_keystore = keystore_dir / f"{from_wallet}.json"
    else:
        report = find_wallet_file_report(from_wallet)
        sender_keystore = report.path
        note = ambiguous_wallet_note(report)
        if note:
            warning(note)
        service_note = service_dir_wallet_note(report)
        if service_note:
            info(service_note)
    if sender_keystore is None or not sender_keystore.exists():
        if report is not None:
            error(wallet_not_found_message(report))
        else:
            error(f"Wallet '{from_wallet}' not found at {sender_keystore}")
        return None

    with open(sender_keystore) as f:
        sender_data = json.load(f)

    sender_address = sender_data["address"]

    # Decrypt private key if wallet is encrypted, otherwise use directly
    private_key = _load_sender_private_key(sender_keystore, sender_data, password)
    if private_key is None:
        return None

    # Resolve chain_id and nonce from the blockchain node this transaction
    # will be submitted to. An explicit CHAIN_ID wins; otherwise the node
    # must advertise one — a silent default signs a transaction no node
    # serves. (No ctx here: the send/batch commands carry no --chain-id.)
    from ..utils.chain_id import get_chain_id

    chain_id = os.getenv("CHAIN_ID") or ""
    if not chain_id:
        try:
            chain_id = get_chain_id(rpc_url, override=None, timeout=5, strict=True)
        except Exception as e:
            abort(
                None,
                f"Chain ID lookup via {rpc_url} failed: {e}. Set CHAIN_ID or point --rpc-url at a serving node",
                from_exception=e,
            )
            raise AssertionError("unreachable: abort always raises") from e

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
        success(f"Transaction submitted, not confirmed: {tx_hash}")
        logger.info("Transaction submitted (unconfirmed): %s from %s to %s", tx_hash, from_wallet, to_address)
        return tx_hash
    except NetworkError as e:
        logger.error("Network error submitting transaction: %s", e)
        abort(None, f"Error submitting transaction: {e}")
        return None
    except Exception as e:
        logger.error("Error submitting transaction: %s", e)
        abort(None, f"Error: {e}")
        return None


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
        abort(None, f"Invalid payload JSON: {e}")
        return None


@transactions.command(
    epilog="""Examples:

  aitbc transactions send --from wallet-1 --to 0x... --amount 10

  aitbc transactions send --from wallet-1 --to 0x... --amount 10 --fee 0.01"""
)
@click.option("--from", "from_wallet", required=True, help="From wallet name")
@click.option("--to", "to_address", required=True, help="To address")
@click.option("--amount", type=DECIMAL, required=True, help="Amount to send")
@click.option(
    "--fee", type=DECIMAL, default=DEFAULT_TX_FEE_AIT, show_default=True, help="Transaction fee (standard chain fee)"
)
@wallet_password_options
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
    password_stdin: bool,
    rpc_url: str | None,
    tx_type: str,
    payload: str | None,
    use_explorer: bool,
):
    """Send a transaction from one wallet to another."""
    password = resolve_wallet_password(
        from_wallet,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        allow_unencrypted=True,
    )

    if not rpc_url:
        rpc_url = _resolve_transaction_rpc_url(None)

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
                if http_response_status(e) == 404:
                    error(f"Transaction {tx_hash} not found")
                else:
                    error(f"Explorer API unavailable: {e}")
            except Exception as e:
                abort(None, f"Error checking status via Explorer: {e}")

    # Check if first wallet is unencrypted


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
        # default fee matches `send --fee` (standard chain fee), not the old 10 AIT
        fee = Decimal(str(tx.get("fee", DEFAULT_TX_FEE_AIT)))
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
                abort(None, f"Transaction produced a duplicate hash: {tx['from_wallet']} → {tx['to_address']}")
            seen_hashes.add(tx_hash)
        results.append({"transaction": tx, "hash": tx_hash, "success": tx_hash is not None})

        if tx_hash:
            success(f"Transaction sent: {tx['from_wallet']} → {tx['to_address']} ({tx['amount']} AIT)")
        else:
            error(f"Transaction failed: {tx['from_wallet']} → {tx['to_address']}")

    except CLIError:
        # Lookup failures abort the batch. A chain-id failure is systemic
        # (same rpc_url for every entry); a nonce 404 is per sender — but
        # either way there is nothing valid to sign with, so the caller
        # prints a partial summary and the command exits non-zero.
        raise
    except Exception as e:
        results.append({"transaction": tx, "hash": None, "success": False, "error": str(e)})
        abort(None, f"Transaction error: {e}")


@transactions.command(
    epilog="""Examples:

  aitbc transactions batch --transactions-file /tmp/txs.json

  aitbc transactions batch --transactions-file /tmp/txs.json --password-file /tmp/pass

  The batch file is a JSON list of objects with keys:
    from_wallet  — sender wallet name (required)
    to_address   — recipient 0x address (required)
    amount       — AIT amount to send (required)
    fee          — AIT fee (optional, defaults to the standard chain fee like `send --fee`)"""
)
@click.option("--transactions-file", required=True, help="JSON file with batch transactions")
@wallet_password_options
@click.option("--rpc-url", help="Blockchain RPC URL")
def batch(transactions_file: str, password: str | None, password_file: str | None, password_stdin: bool, rpc_url: str | None):
    """Send multiple transactions from a JSON batch file.

    Entries are objects ``{"from_wallet", "to_address", "amount", "fee"?}``
    with amounts in AIT. Identical entries are rejected as duplicates instead
    of being reported as two successes for the same on-chain hash.
    """
    with open(transactions_file) as f:
        transactions_data = json.load(f)
    first_wallet = transactions_data[0].get("from_wallet") if transactions_data else None
    password = resolve_wallet_password(
        first_wallet,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        allow_unencrypted=True,
    )

    if not rpc_url:
        rpc_url = _resolve_transaction_rpc_url(None)

    # The chain's account nonce does not move while earlier batch transactions
    # sit in the mempool, so entries from the same wallet sign with per-entry
    # nonce offsets — otherwise identical entries produce the same tx hash and
    # the mempool silently dedupes them while the CLI reported "2/2 successful".
    seen_entries: set[tuple[str, str, Decimal, Decimal]] = set()
    seen_hashes: set[str] = set()
    nonce_offsets: dict[str, int] = {}

    results: list[dict[str, Any]] = []
    for index, tx in enumerate(transactions_data, start=1):
        try:
            _process_batch_entry(tx, password, rpc_url, seen_entries, seen_hashes, nonce_offsets, results)
        except CLIError:
            # Say what already went out before aborting: earlier entries were
            # submitted to the node and their hashes are the only receipt.
            submitted = [r["hash"] for r in results if r.get("hash")]
            error(
                f"Batch aborted at entry {index}/{len(transactions_data)} "
                f"(from_wallet={tx.get('from_wallet', '?')}): {len(submitted)} "
                f"transaction(s) already submitted: {', '.join(str(h) for h in submitted) or 'none'}"
            )
            raise

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
            if http_response_status(e) == 404:
                abort(None, f"Transaction {tx_hash} not found", from_exception=e)
            else:
                abort(None, f"Explorer API unavailable: {e}", from_exception=e)
        except Exception as e:
            abort(None, f"Error: {e}", from_exception=e)
    else:
        if not rpc_url:
            rpc_url = _resolve_transaction_rpc_url(None)

        try:
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
            result = http_client.get(f"/rpc/transaction/{tx_hash}")
            success(f"Transaction status for {tx_hash}")
            click.echo(json.dumps(result, indent=2))
        except NetworkError as e:
            abort(None, f"Error getting transaction status: {e}", from_exception=e)
        except Exception as e:
            abort(None, f"Error: {e}", from_exception=e)


@transactions.command(
    epilog="""Examples:

  aitbc transactions pending

  aitbc transactions pending --rpc-url http://localhost:8202"""
)
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.pass_context
def pending(ctx, rpc_url: str | None):
    """Get the list of pending transactions from the node."""
    if not rpc_url:
        rpc_url = _resolve_transaction_rpc_url(None)

    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        data = http_client.get("/rpc/pending")
        transactions = data.get("transactions", [])
        if ctx.obj and ctx.obj.get("output_format") == "json":
            click.echo(json.dumps(transactions, indent=2))
            return
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
        abort(None, f"Error getting pending transactions: {e}")
    except Exception as e:
        abort(None, f"Error: {e}")


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

  aitbc transactions search --sender 0x... --limit 50

  aitbc transactions search --address 0x... --limit 50 --use-explorer"""
)
@click.option("--address", "address", help="Blockchain address on either side of the transaction.")
@click.option("--sender", "sender", help="Return only transactions sent by this address.")
@click.option("--recipient", "recipient", help="Return only transactions received by this address.")
@click.option("--limit", default=100, help="Number of transactions to return")
@click.option("--use-explorer", is_flag=True, help="Use Explorer API instead of RPC")
@click.option("--rpc-url", default=None, help="Blockchain RPC base URL (overrides config)")
def search(address: str, sender: str, recipient: str, limit: int, use_explorer: bool, rpc_url: str):
    """Search transactions by address, sender, or recipient."""
    if not address and not sender and not recipient:
        abort(None, "Provide at least one of --address, --sender or --recipient.")
    filters = {k: v for k, v in {"address": address, "sender": sender, "recipient": recipient}.items() if v}
    if use_explorer:
        if sender or recipient:
            abort(None, "The Explorer API cannot filter by sender or recipient. Omit --use-explorer to use the RPC path.")
        _search_via_explorer(address, limit)
    else:
        _search_via_rpc(filters, sender, recipient, limit, rpc_url)


def _search_via_explorer(address: str, limit: int) -> None:
    try:
        config = get_config()
        http_client = AITBCHTTPClient(base_url=config.explorer_api_url, timeout=30)
        params = {"address": address, "limit": limit}
        result = http_client.get("/api/transactions/search", params=params)
        transactions = result.get("transactions", [])
        success(f"Found {len(transactions)} transactions for {address} (via Explorer)")
        click.echo(json.dumps(transactions, indent=2))
    except NetworkError as e:
        abort(None, f"Explorer API unavailable: {e}")
    except Exception as e:  # noqa: BLE001 - CLI boundary — unexpected failure reports cleanly
        abort(None, f"Error searching transactions: {e}")


def _row_matches(row: object, key: str, want: str) -> bool:
    if not isinstance(row, dict):
        return False
    return str(row.get(key, "")).lower() == want.lower()


def _search_via_rpc(filters: dict, sender: str | None, recipient: str | None, limit: int, rpc_url: str | None) -> None:
    try:
        http_client = AITBCHTTPClient(base_url=_resolve_transaction_rpc_url(rpc_url), timeout=30)
        transactions = http_client.get_json("/rpc/transactions", params={**filters, "limit": limit})
        if not isinstance(transactions, list):
            error("Unexpected response shape from /rpc/transactions (expected a JSON array).")
            return

        # A node that has not been restarted since sender/recipient landed
        # silently ignores those params and returns either-side rows —
        # verify locally rather than present a wrong answer confidently.
        if sender or recipient:
            kept = [
                r
                for r in transactions
                if (not sender or _row_matches(r, "sender", sender))
                and (not recipient or _row_matches(r, "recipient", recipient))
            ]
            dropped = len(transactions) - len(kept)
            if dropped:
                warning(
                    f"node returned {dropped} rows that did not match the filter "
                    "(rpc not yet restarted with the sender/recipient filter?); "
                    "results were filtered locally, and `limit` applied before "
                    "the filter, so the list may be incomplete"
                )
            transactions = kept
        names = "+".join(filters)
        success(f"Found {len(transactions)} transactions matching {names} (via RPC)")
        click.echo(json.dumps(transactions, indent=2))
    except NetworkError as e:
        abort(None, f"RPC unavailable: {e}")
    except Exception as e:  # noqa: BLE001 - CLI boundary — unexpected failure reports cleanly
        abort(None, f"Error searching transactions: {e}")
