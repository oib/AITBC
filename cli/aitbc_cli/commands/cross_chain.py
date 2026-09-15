"""Cross-chain trading commands for AITBC CLI (GAP-47).

``swap`` and ``bridge`` submit a real, wallet-signed bridge lock to the
blockchain RPC — the same signing convention as ``transactions send`` and
``/rpc/bridge/lock`` (canonical JSON, keccak256, secp256k1). The returned
``source_tx_hash``/``from_tx_hash`` is the real hash of the on-chain
``BRIDGE_LOCK`` transaction, which is also the bridge ``transfer_id``.

Statuses come from the persisted ``CrossChainTransfer`` lifecycle:
``pending`` → ``confirmed`` → ``completed`` (or ``failed``/``refunded``).
``--wait`` polls the real status endpoint until a terminal state; when the
release path is fenced or no relayer/validator infrastructure is available,
the command reports the honest intermediate state instead of claiming
settlement.
"""

import json
import time
from decimal import Decimal
from typing import Any

import click
from tabulate import tabulate

from aitbc.utils import ait_to_units, format_ait

from ..utils import DECIMAL, error, output, success
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger
from ..utils.wallet_loader import load_wallet_for_payment
from .transactions import _resolve_transaction_rpc_url

logger = get_logger(__name__)

TERMINAL_STATES = {"completed", "failed", "refunded"}

_STATUS_MESSAGES = {
    "pending": "⏳ pending — lock submitted, awaiting block seal/finality",
    "locked": "🔒 locked — funds locked on source chain",
    "confirmed": "✓ confirmed — release recorded on target chain, awaiting seal",
    "completed": "✅ completed — released on target chain",
    "failed": "❌ failed",
    "refunded": "💰 refunded — locked funds returned to sender",
}


def _resolve_password(password: str | None, password_file: str | None) -> str | None:
    """Resolve an explicit wallet password (flag > file > env handled by loader)."""
    if password is not None:
        return password
    if password_file:
        with open(password_file) as f:
            return f.read().strip()
    return None  # load_wallet_for_payment checks keyring/env and prompts on a TTY


def _sign_request(sign_data: dict[str, Any], private_key: str) -> str:
    """Sign a request payload exactly the way the RPC verifies it.

    Canonical JSON (sorted keys, compact separators) → keccak256 → secp256k1
    sign_msg_hash — identical to ``transactions send`` and ``/rpc/bridge/lock``.
    """
    from eth_keys import keys
    from eth_utils import keccak

    message = json.dumps(sign_data, sort_keys=True, separators=(",", ":")).encode()
    pk = keys.PrivateKey(bytes.fromhex(private_key.removeprefix("0x")))
    return pk.sign_msg_hash(keccak(message)).to_hex()


def _load_signing_wallet(ctx, wallet: str | None, password: str | None, password_file: str | None):
    """Load the wallet that will sign the cross-chain request."""
    from pathlib import Path

    resolved_password = _resolve_password(password, password_file)
    wallet_path = wallet if wallet and (Path(wallet).exists() or "/" in wallet) else None
    wallet_name = None if wallet_path else wallet
    address, private_key, resolved_name = load_wallet_for_payment(
        ctx, wallet_name, wallet_path=wallet_path, password=resolved_password
    )
    if not private_key:
        abort(ctx, f"Wallet '{resolved_name}' has no usable private key; use a file wallet with --wallet")
    return address, private_key


def _wait_for_terminal_status(client: AITBCHTTPClient, path: str, timeout_seconds: int, label: str) -> dict[str, Any] | None:
    """Poll a status endpoint until a terminal bridge state or timeout.

    Prints every real status transition. Returns the last payload; on timeout
    the payload still carries the honest non-terminal state.
    """
    deadline = time.monotonic() + timeout_seconds
    last_status: str | None = None
    last_data: dict[str, Any] | None = None
    while True:
        try:
            last_data = client.get(path)
        except NetworkError as e:
            error(f"Status poll failed: {e}")
            return last_data
        status = last_data.get("status")
        if status != last_status:
            last_status = status
            message = _STATUS_MESSAGES.get(str(status), str(status))
            click.echo(f"{label} status: {message}")
        if status in TERMINAL_STATES:
            return last_data
        if time.monotonic() >= deadline:
            output(f"Timed out after {timeout_seconds}s — last known status: {status}")
            return last_data
        time.sleep(5)


@click.group(
    epilog="""Examples:

  aitbc crosschain swap --from-chain ait-mainnet --to-chain ait-side --from-token AIT --to-token AIT --amount 10 --wallet wallet-1

  aitbc crosschain bridge --source-chain ait-mainnet --target-chain ait-side --token AIT --amount 10 --wallet wallet-1 --wait"""
)
def cross_chain():
    """Create and inspect cross-chain swaps and bridge transfers between AITBC chains.

    Swaps and bridges lock real funds via a wallet-signed BRIDGE_LOCK
    transaction and settle through the persistent bridge lifecycle.
    """
    pass


@cross_chain.command(
    epilog="""Examples:

  aitbc crosschain rates

  aitbc crosschain rates --from-chain ait-mainnet --to-chain ait-side"""
)
@click.option("--from-chain", help="Source chain ID")
@click.option("--to-chain", help="Target chain ID")
@click.option("--from-token", help="Source token symbol")
@click.option("--to-token", help="Target token symbol")
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.pass_context
def rates(
    ctx,
    from_chain: str | None,
    to_chain: str | None,
    from_token: str | None,
    to_token: str | None,
    rpc_url: str | None,
):
    """Get configured cross-chain swap rates between chains."""
    try:
        client = AITBCHTTPClient(base_url=_resolve_transaction_rpc_url(rpc_url), timeout=10)
        params = {}
        if from_chain and to_chain:
            params = {"from_chain": from_chain, "to_chain": to_chain}
        rates_data = client.get("/rpc/cross-chain/rates", params=params or None)
        rates = rates_data.get("rates", {})

        if from_chain and to_chain:
            pair_key = f"{from_chain}::{to_chain}"
            if pair_key in rates:
                success(f"Swap rate {from_chain} → {to_chain}: {rates[pair_key]}")
            elif from_token == to_token or (not from_token and not to_token):
                success(f"Swap rate {from_chain} → {to_chain}: 1.0 (same-asset parity)")
            else:
                output(rates_data.get("detail") or f"No configured rate for {from_chain} → {to_chain}")
        else:
            success("Cross-chain swap rates (operator-configured):")
            rate_table = []
            for pair, rate in rates.items():
                chains = pair.split("::")
                rate_table.append([chains[0], chains[-1], f"{rate:.6f}"])
            if rate_table:
                click.echo(tabulate(rate_table, headers=["From Chain", "To Chain", "Rate"], tablefmt="grid"))
            else:
                output("No configured swap rates; same-asset pairs settle at parity (1.0)")
    except Exception as e:
        error(f"Network error: {e}")


@cross_chain.command(
    epilog="""Examples:

  aitbc crosschain swap --from-chain ait-mainnet --to-chain ait-side --from-token AIT --to-token AIT --amount 10 --wallet wallet-1

  aitbc crosschain swap --from-chain ait-mainnet --to-chain ait-side --from-token AIT --to-token AIT --amount 10 --recipient 0x... --wait"""
)
@click.option("--from-chain", required=True, help="Source chain ID")
@click.option("--to-chain", required=True, help="Target chain ID")
@click.option("--from-token", required=True, help="Source token symbol")
@click.option("--to-token", required=True, help="Target token symbol")
@click.option("--amount", type=DECIMAL, required=True, help="Amount to swap (AIT)")
@click.option("--min-amount", type=DECIMAL, help="Minimum amount to receive on target chain (AIT)")
@click.option("--slippage", type=float, default=0.01, help="Slippage tolerance (0-0.1)")
@click.option("--recipient", help="Recipient address on the target chain (defaults to the sender)")
@click.option("--wallet", "wallet", default=None, help="Wallet name or file path for signing")
@click.option("--password", help="Wallet password")
@click.option("--password-file", help="File containing wallet password")
@click.option("--rpc-url", help="Blockchain RPC URL (source-chain producer)")
@click.option("--wait", is_flag=True, help="Poll status until the transfer reaches a terminal state")
@click.option("--timeout", type=int, default=300, help="Seconds to wait with --wait (default 300)")
@click.pass_context
def swap(
    ctx,
    from_chain: str,
    to_chain: str,
    from_token: str,
    to_token: str,
    amount: Decimal,
    min_amount: Decimal | None,
    slippage: float,
    recipient: str | None,
    wallet: str | None,
    password: str | None,
    password_file: str | None,
    rpc_url: str | None,
    wait: bool,
    timeout: int,
):
    """Create a cross-chain token swap via a real signed bridge lock.

    The wallet signs the swap request; the node locks ``amount`` on the
    source chain and the bridge releases ``amount * rate`` on the target
    chain once the lock reaches finality. The reported ``from_tx_hash`` is
    the real hash of the on-chain BRIDGE_LOCK transaction.
    """
    if from_chain == to_chain:
        error("Source and target chains must be different")
        return
    if amount <= 0:
        error("Amount must be greater than 0")
        return

    rpc_url = _resolve_transaction_rpc_url(rpc_url)
    address, private_key = _load_signing_wallet(ctx, wallet, password, password_file)
    recipient = recipient or address

    amount_units = ait_to_units(amount)
    min_amount_units = ait_to_units(min_amount) if min_amount is not None else 0

    sign_data = {
        "from_chain": from_chain,
        "to_chain": to_chain,
        "from_token": from_token,
        "to_token": to_token,
        "sender": address,
        "recipient": recipient,
        "amount": amount_units,
        "min_amount": min_amount_units,
        "slippage_tolerance": slippage,
    }
    swap_data = dict(sign_data)
    swap_data["signature"] = _sign_request(sign_data, private_key)

    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        swap_result = http_client.post("/rpc/swap", json=swap_data)
        success("Cross-chain swap locked on the source chain")
        output(
            {
                "Swap ID": swap_result.get("swap_id"),
                "Transfer ID": swap_result.get("transfer_id"),
                "From Chain": swap_result.get("from_chain"),
                "To Chain": swap_result.get("to_chain"),
                "Amount": swap_result.get("amount"),
                "Expected Amount": swap_result.get("expected_amount"),
                "Rate": swap_result.get("rate"),
                "Total Fees": swap_result.get("total_fees"),
                "Status": swap_result.get("status"),
                "Source Tx Hash": swap_result.get("from_tx_hash"),
            },
            ctx.obj["output_format"],
        )
        swap_id = swap_result.get("swap_id")
        success(f"Track swap with: aitbc crosschain status --swap-id {swap_id}")
        if wait and swap_id:
            _wait_for_terminal_status(http_client, f"/rpc/cross-chain/swap/{swap_id}", timeout, "Swap")
    except Exception as e:
        error(f"Swap failed: {e}")


@cross_chain.command(
    epilog="""Examples:

  aitbc crosschain status --swap-id swap-123

  aitbc crosschain status --swap-id swap-123 --output json"""
)
@click.option("--swap-id", "swap_id", required=True, help="The swap ID (or transfer ID).")
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.option("--wait", is_flag=True, help="Poll status until a terminal state")
@click.option("--timeout", type=int, default=300, help="Seconds to wait with --wait")
@click.pass_context
def status(ctx, swap_id: str, rpc_url: str | None, wait: bool, timeout: int):
    """Get the real status of a cross-chain swap."""
    try:
        http_client = AITBCHTTPClient(base_url=_resolve_transaction_rpc_url(rpc_url), timeout=10)
        swap_data = http_client.get(f"/rpc/cross-chain/swap/{swap_id}")
        if wait and swap_data.get("status") not in TERMINAL_STATES:
            swap_data = (
                _wait_for_terminal_status(http_client, f"/rpc/cross-chain/swap/{swap_id}", timeout, "Swap") or swap_data
            )
        current = swap_data.get("status", "unknown")
        click.echo(_STATUS_MESSAGES.get(str(current), f"Swap status: {current}"))

        details = {
            "Swap ID": swap_data.get("swap_id"),
            "Transfer ID": swap_data.get("transfer_id"),
            "From Chain": swap_data.get("from_chain"),
            "To Chain": swap_data.get("to_chain"),
            "From Token": swap_data.get("from_token"),
            "To Token": swap_data.get("to_token"),
            "Amount": swap_data.get("amount"),
            "Expected Amount": swap_data.get("expected_amount"),
            "Actual Amount": swap_data.get("actual_amount"),
            "Status": swap_data.get("status"),
            "Lock Block Height": swap_data.get("lock_block_height"),
            "Created At": swap_data.get("created_at"),
            "Completed At": swap_data.get("completed_at"),
            "Bridge Fee": swap_data.get("total_fees"),
            "From Tx Hash": swap_data.get("from_tx_hash"),
            "To Tx Hash": swap_data.get("to_tx_hash"),
        }
        output(details, ctx.obj["output_format"])
        if swap_data.get("error"):
            error(f"Error: {swap_data['error']}")
    except Exception as e:
        error(f"Network error: {e}")


@cross_chain.command(
    epilog="""Examples:

  aitbc crosschain swaps

  aitbc crosschain swaps --user-address 0x... --status completed --limit 20"""
)
@click.option("--user-address", help="Filter by user address")
@click.option("--status", help="Filter by status")
@click.option("--limit", type=int, default=10, help="Number of swaps to show")
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.pass_context
def swaps(ctx, user_address: str | None, status: str | None, limit: int, rpc_url: str | None):
    """List persisted cross-chain swaps, optionally filtered."""
    params: dict[str, Any] = {}
    if user_address:
        params["user_address"] = user_address
    if status:
        params["status"] = status

    try:
        http_client = AITBCHTTPClient(base_url=_resolve_transaction_rpc_url(rpc_url), timeout=10)
        swaps_data = http_client.get("/rpc/cross-chain/swaps", params=params)
        swaps = swaps_data.get("swaps", [])

        if swaps:
            success(f"Found {len(swaps)} cross-chain swaps:")
            swap_table = []
            for swap in swaps[:limit]:
                swap_table.append(
                    [
                        str(swap.get("swap_id", ""))[:16] + "...",
                        swap.get("from_chain", ""),
                        swap.get("to_chain", ""),
                        swap.get("amount", 0),
                        swap.get("status", ""),
                        str(swap.get("created_at", ""))[:19],
                    ]
                )
            click.echo(tabulate(swap_table, headers=["ID", "From", "To", "Amount", "Status", "Created"], tablefmt="grid"))
            if len(swaps) > limit:
                success(f"Showing {limit} of {len(swaps)} total swaps")
        else:
            success("No cross-chain swaps found")
    except Exception as e:
        error(f"Network error: {e}")


@cross_chain.command(
    epilog="""Examples:

  aitbc crosschain bridge --source-chain ait-mainnet --target-chain ait-side --token AIT --amount 10 --wallet wallet-1

  aitbc crosschain bridge --source-chain ait-mainnet --target-chain ait-side --token AIT --amount 10 --recipient 0x... --wait"""
)
@click.option("--source-chain", required=True, help="Source chain ID")
@click.option("--target-chain", required=True, help="Target chain ID")
@click.option("--token", required=True, help="Token to bridge")
@click.option("--amount", type=DECIMAL, required=True, help="Amount to bridge (AIT)")
@click.option("--recipient", help="Recipient address on the target chain (defaults to the sender)")
@click.option("--wallet", "wallet", default=None, help="Wallet name or file path for signing")
@click.option("--password", help="Wallet password")
@click.option("--password-file", help="File containing wallet password")
@click.option("--rpc-url", help="Blockchain RPC URL (source-chain producer)")
@click.option("--wait", is_flag=True, help="Poll status until the transfer reaches a terminal state")
@click.option("--timeout", type=int, default=300, help="Seconds to wait with --wait (default 300)")
@click.pass_context
def bridge(
    ctx,
    source_chain: str,
    target_chain: str,
    token: str,
    amount: Decimal,
    recipient: str | None,
    wallet: str | None,
    password: str | None,
    password_file: str | None,
    rpc_url: str | None,
    wait: bool,
    timeout: int,
):
    """Bridge tokens to a target chain via a real signed bridge lock.

    The wallet signs the lock request (same payload as ``/rpc/bridge/lock``);
    the node creates a real BRIDGE_LOCK transaction. ``bridge_id`` equals
    the transfer ID and the source-chain transaction hash.
    """
    if source_chain == target_chain:
        error("Source and target chains must be different")
        return
    if amount <= 0:
        error("Amount must be greater than 0")
        return

    rpc_url = _resolve_transaction_rpc_url(rpc_url)
    address, private_key = _load_signing_wallet(ctx, wallet, password, password_file)
    recipient = recipient or address
    amount_units = ait_to_units(amount)

    sign_data = {
        "source_chain": source_chain,
        "target_chain": target_chain,
        "sender": address,
        "recipient": recipient,
        "amount": amount_units,
        "asset": token,
    }
    bridge_data = dict(sign_data)
    bridge_data["signature"] = _sign_request(sign_data, private_key)

    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        bridge_result = http_client.post("/rpc/cross-chain/bridge", json=bridge_data)
        success("Cross-chain bridge lock submitted")
        output(
            {
                "Bridge ID": bridge_result.get("bridge_id"),
                "Source Chain": bridge_result.get("source_chain"),
                "Target Chain": bridge_result.get("target_chain"),
                "Token": bridge_result.get("token"),
                "Amount": bridge_result.get("amount"),
                "Bridge Fee": bridge_result.get("bridge_fee"),
                "Status": bridge_result.get("status"),
                "Source Tx Hash": bridge_result.get("source_tx_hash"),
            },
            ctx.obj["output_format"],
        )
        bridge_id = bridge_result.get("bridge_id")
        success(f"Track bridge with: aitbc crosschain bridge-status --bridge-id {bridge_id}")
        if wait and bridge_id:
            _wait_for_terminal_status(http_client, f"/rpc/cross-chain/bridge/{bridge_id}", timeout, "Bridge")
    except Exception as e:
        error(f"Bridge failed: {e}")


@cross_chain.command(
    epilog="""Examples:

  aitbc crosschain bridge-status --bridge-id 0x...

  aitbc crosschain bridge-status --bridge-id 0x... --output json"""
)
@click.option("--bridge-id", "--transfer-id", "bridge_id", required=True, help="The bridge/transfer ID.")
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.option("--wait", is_flag=True, help="Poll status until a terminal state")
@click.option("--timeout", type=int, default=300, help="Seconds to wait with --wait")
@click.pass_context
def bridge_status(ctx, bridge_id: str, rpc_url: str | None, wait: bool, timeout: int):
    """Check the real status of a cross-chain bridge transfer."""
    try:
        http_client = AITBCHTTPClient(base_url=_resolve_transaction_rpc_url(rpc_url), timeout=10)
        bridge_data = http_client.get(f"/rpc/cross-chain/bridge/{bridge_id}")
        if wait and bridge_data.get("status") not in TERMINAL_STATES:
            bridge_data = (
                _wait_for_terminal_status(http_client, f"/rpc/cross-chain/bridge/{bridge_id}", timeout, "Bridge")
                or bridge_data
            )
        current = bridge_data.get("status", "unknown")
        click.echo(_STATUS_MESSAGES.get(str(current), f"Bridge status: {current}"))

        details = {
            "Bridge ID": bridge_data.get("bridge_id"),
            "Source Chain": bridge_data.get("source_chain"),
            "Target Chain": bridge_data.get("target_chain"),
            "Asset": bridge_data.get("asset"),
            "Amount": format_ait(bridge_data.get("amount", 0))
            if isinstance(bridge_data.get("amount"), int)
            else bridge_data.get("amount"),
            "Sender": bridge_data.get("sender"),
            "Recipient Address": bridge_data.get("recipient_address"),
            "Status": bridge_data.get("status"),
            "Lock Sealed": bridge_data.get("lock_sealed"),
            "Lock Block Height": bridge_data.get("lock_block_height"),
            "Created At": bridge_data.get("created_at"),
            "Completed At": bridge_data.get("completed_at"),
            "Source Tx Hash": bridge_data.get("source_tx_hash"),
            "Target Tx Hash": bridge_data.get("target_tx_hash"),
        }
        output(details, ctx.obj["output_format"])
    except Exception as e:
        error(f"Network error: {e}")


@cross_chain.command(
    epilog="""Examples:

  aitbc crosschain confirm --transfer-id 0x... --wallet wallet-1

  Manually relays a pending transfer: fetches the real Merkle proof for the
  sealed lock and submits it to /rpc/bridge/confirm. Normally the node's
  bridge relayer does this automatically once the lock reaches finality."""
)
@click.option("--transfer-id", required=True, help="The bridge transfer ID")
@click.option("--source-chain", help="Source chain ID (defaults to the node's chain)")
@click.option("--wallet", "wallet", default=None, help="Wallet name or file path for signing the confirm")
@click.option("--password", help="Wallet password")
@click.option("--password-file", help="File containing wallet password")
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.pass_context
def confirm(
    ctx,
    transfer_id: str,
    source_chain: str | None,
    wallet: str | None,
    password: str | None,
    password_file: str | None,
    rpc_url: str | None,
):
    """Confirm a pending bridge transfer with its real Merkle proof."""
    rpc_url = _resolve_transaction_rpc_url(rpc_url)
    address, private_key = _load_signing_wallet(ctx, wallet, password, password_file)

    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        params = {"source_chain": source_chain} if source_chain else None
        proof_result = http_client.get(f"/rpc/bridge/transfer/{transfer_id}/proof", params=params)
        proof = proof_result.get("proof")
        if not proof:
            error("No proof returned — the lock may not be sealed in a block yet")
            return

        sign_data = {"transfer_id": transfer_id, "confirmer": address}
        confirm_payload = {
            "transfer_id": transfer_id,
            "proof": proof,
            "confirmer": address,
            "signature": _sign_request(sign_data, private_key),
        }
        result = http_client.post("/rpc/bridge/confirm", json=confirm_payload)
        success("Bridge confirm submitted")
        output(
            {
                "Transfer ID": result.get("transfer_id"),
                "Status": result.get("status"),
                "Target Tx Hash": result.get("target_tx_hash"),
            },
            ctx.obj["output_format"],
        )
    except Exception as e:
        error(f"Confirm failed: {e}")


@cross_chain.command(
    epilog="""Examples:

  aitbc crosschain pools

  aitbc crosschain pools --output json"""
)
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.pass_context
def pools(ctx, rpc_url: str | None):
    """Show cross-chain liquidity pools (none exist — swaps settle via bridge locks)."""
    try:
        http_client = AITBCHTTPClient(base_url=_resolve_transaction_rpc_url(rpc_url), timeout=10)
        pools_data = http_client.get("/rpc/cross-chain/pools")
        pools = pools_data.get("pools", [])

        if pools:
            pool_table = []
            for pool in pools:
                pool_table.append(
                    [
                        pool.get("pool_id", ""),
                        pool.get("token_a", ""),
                        pool.get("token_b", ""),
                        pool.get("chain_a", ""),
                        pool.get("chain_b", ""),
                        f"{pool.get('reserve_a', 0):.2f}",
                        f"{pool.get('reserve_b', 0):.2f}",
                    ]
                )
            click.echo(
                tabulate(
                    pool_table,
                    headers=["Pool ID", "Token A", "Token B", "Chain A", "Chain B", "Reserve A", "Reserve B"],
                    tablefmt="grid",
                )
            )
        else:
            output(pools_data.get("detail") or "No cross-chain liquidity pools found")
    except Exception as e:
        error(f"Network error: {e}")


@cross_chain.command(
    epilog="""Examples:

  aitbc crosschain stats

  aitbc crosschain stats --output json"""
)
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.pass_context
def stats(ctx, rpc_url: str | None):
    """Show cross-chain trading statistics from real persisted records."""
    try:
        http_client = AITBCHTTPClient(base_url=_resolve_transaction_rpc_url(rpc_url), timeout=10)
        stats_data = http_client.get("/rpc/cross-chain/stats")

        success("Cross-Chain Trading Statistics:")

        for key, label in (("swap_stats", "Swap"), ("bridge_stats", "Bridge")):
            rows = stats_data.get(key, [])
            if rows:
                success(f"{label} Statistics:")
                table = [[s.get("status", ""), s.get("count", 0), format_ait(s.get("volume", 0))] for s in rows]
                click.echo(tabulate(table, headers=["Status", "Count", "Volume (AIT)"], tablefmt="grid"))

        output(
            {
                "Total Volume": f"{stats_data.get('total_volume', 0)} AIT",
                "Supported Chains": ", ".join(stats_data.get("supported_chains", [])),
                "Bridge Chains": ", ".join(stats_data.get("bridge_supported_chains", [])),
                "Release Enabled": stats_data.get("release_enabled"),
                "Relayer Enabled": stats_data.get("relayer_enabled"),
                "Last Updated": stats_data.get("timestamp", ""),
            },
            ctx.obj["output_format"],
        )
    except Exception as e:
        error(f"Network error: {e}")
