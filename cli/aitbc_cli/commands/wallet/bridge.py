"""Bridge commands for AITBC CLI (ETH <-> AITBC swaps)."""

from __future__ import annotations

import asyncio
import json
import os
from decimal import Decimal

import click

from ...config import get_config
from ...utils import DECIMAL, error, output, success
from ...utils.address import to_eip55
from ...utils.chain_id import resolve_chain_id
from ...utils.wallet_paths import find_wallet_file_report, wallet_not_found_message
from ...utils.wallet_secret import resolve_wallet_password, wallet_password_options
from ...utils.http_client import AITBCHTTPClient, http_error_detail
from . import _load_wallet, get_wallet_client, wallet
from .eth_common import resolve_wallet_path


@wallet.group(invoke_without_command=False)
def bridge():
    """ETH <-> AITBC bridge commands."""
    pass


@bridge.command(
    epilog="""Examples:

  aitbc wallet bridge deposit --amount 0.005

  aitbc wallet bridge deposit --wallet-name test --amount 0.01"""
)
@click.option("--amount", "amount", required=True, type=DECIMAL, help="ETH amount to deposit.")
@click.option("--wallet-name", "wallet_name", required=False, help="Source wallet name for ETH signing.")
@click.option("--eth-rpc-url", "eth_rpc_url", required=False, help="Ethereum RPC URL.")
@wallet_password_options
@click.pass_context
def deposit(
    ctx,
    amount: Decimal,
    wallet_name: str | None,
    eth_rpc_url: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
):
    """Deposit ETH to the bridge and receive AITBC on the hub."""
    wallet_name = wallet_name or ctx.obj["wallet_name"]
    wallet_path = resolve_wallet_path(ctx, wallet_name)

    if not wallet_path.exists():
        error(wallet_not_found_message(find_wallet_file_report(wallet_name)))
        raise click.Abort()

    password = resolve_wallet_password(
        wallet_name,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        allow_unencrypted=True,
        wallet_path=wallet_path,
        ctx=ctx,
    )
    wallet_data = _load_wallet(wallet_path, wallet_name, password=password)
    ait_address = to_eip55(wallet_data["address"])
    eth_private_key = wallet_data.get("private_key")
    if not eth_private_key:
        error("Wallet does not contain a private key")
        raise click.Abort()

    config = get_config()
    wallet_client = get_wallet_client()

    try:
        deposit_info = wallet_client.post(
            "/v1/bridge/deposit",
            json={"eth_amount": str(amount), "ait_address": ait_address},
        )
    except Exception as e:
        error(f"Failed to get deposit instructions: {e}")
        raise click.Abort() from e

    if not (deposit_info.get("success") or deposit_info.get("status") == "ready"):
        error(deposit_info.get("error", "Wallet service returned an error"))
        raise click.Abort()

    instructions = deposit_info.get("instructions", {})
    estimate = deposit_info.get("estimate", {})
    bridge_eth_address = instructions.get("send_eth_to", "")
    eth_amount = Decimal(instructions.get("amount_eth", 0))
    hex_data = instructions.get("transaction_data_hex", "")
    estimated_ait = estimate.get("estimated_ait_amount", 0)

    success(f"Deposit {eth_amount} ETH to {bridge_eth_address}")
    output(
        {
            "from_address": ait_address,
            "bridge_address": bridge_eth_address,
            "eth_amount": str(eth_amount),
            "hex_data": hex_data,
            "estimated_ait": estimated_ait,
        },
        ctx.obj.get("output_format", "table"),
    )

    # Sign and send the ETH transaction
    rpc_url = eth_rpc_url or os.getenv("ETH_RPC_URL") or getattr(config, "eth_rpc_url", None) or "https://eth.llamarpc.com"
    try:
        from eth_account import Account as EthAccount

        account = EthAccount.from_key(eth_private_key)
        derived_address = account.address

        from aitbc.crypto.signature_recovery import canonical_address

        if canonical_address(derived_address).lower() != canonical_address(ait_address).lower():
            error(
                f"Wallet address {ait_address} does not match the private key's address {derived_address}. "
                "The CLI does not support signing for a different wallet."
            )
            raise click.Abort()

        # Fetch chain id, nonce, gas price
        import httpx

        async def _send() -> str:
            network = os.getenv("ETH_NETWORK", "sepolia")
            try:
                chain_id = int(network)
            except Exception:
                chain_id = {"mainnet": 1, "sepolia": 11155111, "goerli": 5, "holesky": 17000}.get(network.lower(), 11155111)

            async with httpx.AsyncClient(timeout=15.0) as client:
                rpc_body = {
                    "jsonrpc": "2.0",
                    "method": "eth_getTransactionCount",
                    "params": [derived_address, "pending"],
                    "id": 1,
                }
                resp = await client.post(rpc_url, json=rpc_body)
                resp.raise_for_status()
                nonce = int(resp.json()["result"], 16)

                rpc_body = {"jsonrpc": "2.0", "method": "eth_gasPrice", "params": [], "id": 1}
                resp = await client.post(rpc_url, json=rpc_body)
                resp.raise_for_status()
                gas_price = int(resp.json()["result"], 16)

            value_wei = int(eth_amount * Decimal(10**18))
            tx = {
                "to": canonical_address(bridge_eth_address),
                "value": value_wei,
                "gas": 100000,
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": chain_id,
                "data": hex_data,
            }
            signed = account.sign_transaction(tx)
            raw = signed.raw_transaction
            if isinstance(raw, bytes):
                raw = "0x" + raw.hex()

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    rpc_url, json={"jsonrpc": "2.0", "method": "eth_sendRawTransaction", "params": [raw], "id": 1}
                )
                resp.raise_for_status()
                result = resp.json()
                if "error" in result:
                    raise RuntimeError(result["error"])
                return str(result["result"])

        eth_tx_hash = asyncio.get_event_loop().run_until_complete(_send())
        success(f"ETH deposit transaction submitted: {eth_tx_hash}")
        output(
            {
                "eth_tx_hash": eth_tx_hash,
                "bridge_address": bridge_eth_address,
                "eth_amount": str(eth_amount),
                "estimated_ait": estimated_ait,
                "ait_address": ait_address,
            },
            ctx.obj.get("output_format", "table"),
        )
    except Exception as e:
        error(f"Failed to send ETH deposit: {e}")
        raise click.Abort() from e


@bridge.command(
    epilog="""Examples:

  aitbc wallet bridge withdraw --amount 42 --eth-address 0xAbc...

  aitbc wallet bridge withdraw --wallet-name shop --amount 100 --eth-address 0xAbc..."""
)
@click.option("--amount", "amount", required=True, type=DECIMAL, help="AIT amount to withdraw.")
@click.option("--eth-address", "eth_address", required=True, help="Destination Ethereum address.")
@click.option("--wallet-name", "wallet_name", required=False, help="Source wallet name for AIT signing.")
@wallet_password_options
@click.pass_context
def withdraw(
    ctx,
    amount: Decimal,
    eth_address: str,
    wallet_name: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
):
    """Burn AITBC on the hub to receive ETH at the given Ethereum address."""
    wallet_name = wallet_name or ctx.obj["wallet_name"]
    wallet_path = resolve_wallet_path(ctx, wallet_name)

    if not wallet_path.exists():
        error(wallet_not_found_message(find_wallet_file_report(wallet_name)))
        raise click.Abort()

    password = resolve_wallet_password(
        wallet_name,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        allow_unencrypted=True,
        wallet_path=wallet_path,
        ctx=ctx,
    )
    wallet_data = _load_wallet(wallet_path, wallet_name, password=password)
    from_address = to_eip55(wallet_data["address"])
    private_key_hex = wallet_data.get("private_key")
    if not private_key_hex:
        error("Wallet does not contain a private key")
        raise click.Abort()

    from aitbc.crypto.signature_recovery import canonical_address

    try:
        eth_address = canonical_address(eth_address)
    except Exception as e:
        error(f"Invalid eth_address: {e}")
        raise click.Abort() from e

    config = get_config()
    wallet_client = get_wallet_client()
    rpc_url = config.blockchain_rpc_url or "http://localhost:8202"

    try:
        build_info = wallet_client.post(
            "/v1/bridge/withdraw/build",
            json={"ait_amount": str(amount), "eth_address": eth_address, "from_address": from_address},
        )
    except Exception as e:
        error(f"Failed to get withdrawal build info: {e}")
        raise click.Abort() from e

    if build_info.get("status") != "ready":
        error(build_info.get("error", "Wallet service did not return ready status"))
        raise click.Abort()

    unsigned_tx = build_info["instructions"]["body"]
    estimate = build_info.get("estimate", {})
    eth_amount = estimate.get("eth_amount", "unknown")

    success(f"Withdrawing {amount} AIT -> {eth_amount} ETH to {eth_address}")

    # Sign the BRIDGE_WITHDRAW transaction with eth_keys
    from eth_keys import keys as eth_keys
    from eth_utils import keccak

    if private_key_hex.startswith("0x"):
        private_key_hex = private_key_hex[2:]
    private_key = eth_keys.PrivateKey(bytes.fromhex(private_key_hex))

    unsigned_fields = {k: v for k, v in unsigned_tx.items() if k != "signature"}
    message = json.dumps(unsigned_fields, sort_keys=True, separators=(",", ":")).encode()
    signature = private_key.sign_msg_hash(keccak(message))
    signed_tx = dict(unsigned_tx)
    signed_tx["signature"] = signature.to_bytes().hex()

    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.post("/rpc/transaction", json=signed_tx)
        ait_tx_hash = result.get("transaction_hash") or ""
        success(f"BRIDGE_WITHDRAW transaction submitted: {ait_tx_hash}")
        output(
            {
                "ait_tx_hash": ait_tx_hash,
                "from_address": from_address,
                "eth_address": eth_address,
                "ait_amount": str(amount),
                "eth_amount": eth_amount,
                "bridge_fee_ait": estimate.get("fee_ait"),
                "net_ait": estimate.get("net_ait"),
            },
            ctx.obj.get("output_format", "table"),
        )
    except Exception as e:
        error(f"Failed to submit BRIDGE_WITHDRAW transaction: {e}")
        raise click.Abort() from e


@bridge.command(
    epilog="""Examples:

  aitbc wallet bridge status --ait-tx-hash 0x...
  aitbc wallet bridge status --today     # releases since 00:00 host-local time on the hub
  aitbc wallet bridge status --24h       # rolling 24h — the sell day-cap window"""
)
@click.option("--ait-tx-hash", "ait_tx_hash", required=False, help="AIT withdrawal transaction hash.")
@click.option(
    "--today",
    "today",
    is_flag=True,
    default=False,
    help="Aggregate releases since host-local midnight on the hub (the zone named in the window's timezone field).",
)
@click.option(
    "--24h",
    "last_24h",
    is_flag=True,
    default=False,
    help="Aggregate releases over the rolling 24h window (the sell day-cap basis).",
)
@click.option(
    "--hub-url",
    "hub_url",
    default=None,
    help="Hub wallet-service base URL — bare origin, path is stripped (default: configured wallet daemon)",
)
@click.pass_context
def status(ctx, ait_tx_hash: str | None, today: bool, last_24h: bool, hub_url: str | None):
    """Check an AIT->ETH withdrawal, or aggregate ETH released over a
    window for day-cap reconciliation (--today / --24h, read-only)."""
    chosen = [bool(ait_tx_hash), today, last_24h]
    if sum(chosen) != 1:
        error("status needs exactly one of --ait-tx-hash, --today, --24h")
        raise click.Abort()

    if ait_tx_hash:
        wallet_client = get_wallet_client()
        try:
            info = wallet_client.get(f"/v1/bridge/withdraw/{ait_tx_hash}")
        except Exception as e:
            error(f"Failed to get withdrawal status: {e}")
            raise click.Abort() from e
        output(info, ctx.obj.get("output_format", "table"))
        return

    client = _hub_bridge_client(hub_url)
    try:
        doc = client.get("/v1/bridge/float")
    except Exception as e:
        error(f"Failed to read bridge float: {e}")
        raise click.Abort() from e
    window = doc.get("windows", {}).get("today" if today else "last_24h", {})
    label = "today (since 00:00 host-local)" if today else "last 24h (rolling)"
    output(
        {
            "window": label,
            "timezone": window.get("timezone", ""),
            "since": window.get("since", ""),
            "withdrawals_eth": window.get("withdrawals_eth", ""),
            "sell_eth": window.get("sell_eth", ""),
            "exchange_eth": window.get("exchange_eth", ""),
            "total_eth": window.get("total_eth", ""),
            "sell_daily_cap": doc.get("sell_daily_cap", {}),
        },
        ctx.obj.get("output_format", "table"),
    )


@bridge.command(
    "float",
    epilog="""Examples:

  aitbc wallet bridge float
  aitbc wallet bridge float --hub-url https://hub.example   # from a shop node""",
)
@click.option(
    "--hub-url",
    "hub_url",
    default=None,
    help="Hub wallet-service base URL — bare origin, path is stripped (default: configured wallet daemon)",
)
@click.pass_context
def float_cmd(ctx, hub_url: str | None):
    """Show the bridge ETH float: wallet balance, pending reserve across
    all three release lanes, and today/24h release windows (read-only)."""
    client = _hub_bridge_client(hub_url)
    try:
        doc = client.get("/v1/bridge/float")
    except Exception as e:
        error(f"Failed to read bridge float: {e}")
        raise click.Abort() from e
    output(doc, ctx.obj.get("output_format", "table"))


@bridge.command(
    "settlements",
    epilog="""Examples:

  aitbc wallet bridge settlements
  aitbc wallet bridge settlements --state needs_review --kind order_refund
  aitbc wallet bridge settlements --hub-url https://hub.example   # from a shop node""",
)
@click.option("--state", "state", default=None, help="Filter by settlement status (needs_review, settled, refunded, ...)")
@click.option("--kind", "kind", type=click.Choice(["trade", "order_refund"]), default=None, help="Filter by settlement kind")
@click.option("--limit", "limit", type=int, default=50, show_default=True, help="Max rows (server caps at 500)")
@click.option(
    "--hub-url",
    "hub_url",
    default=None,
    help="Hub wallet-service base URL — bare origin, path is stripped (default: configured wallet daemon)",
)
@click.pass_context
def settlements(ctx, state, kind, limit, hub_url):
    """List exchange-settlement ledger rows on the hub wallet service
    (admin-keyed — CLI-1)."""
    client = _hub_bridge_client(hub_url)
    try:
        doc = client.get(
            "/v1/bridge/settlements",
            params={k: v for k, v in (("status", state), ("kind", kind), ("limit", limit)) if v is not None},
        )
    except Exception as e:
        error(f"Failed to list settlements: {e}")
        raise click.Abort() from e
    output(doc, ctx.obj.get("output_format", "table"))


@bridge.group(invoke_without_command=False)
def sell():
    """Escrowed AIT -> ETH sell commands (quote / lock / status)."""
    pass


def _normalize_hub_url(hub_url: str) -> str:
    """Normalize ``--hub-url`` to the bare origin ``scheme://host[:port]``.

    The hub's nginx mounts ``/v1/bridge/*`` at the origin root — a path-
    suffixed URL (e.g. ``https://hub.example``) silently 404s, so any
    path/query/fragment is stripped. A scheme-less value gets ``https://``.
    """
    from urllib.parse import urlsplit

    raw = hub_url.strip()
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    return f"{parts.scheme}://{parts.netloc}"


def _hub_bridge_client(hub_url: str | None) -> AITBCHTTPClient:
    """HTTP client for the hub's wallet service carrying the sell routes.

    Defaults to the configured wallet daemon; on a shop node pass
    ``--hub-url`` for the hub's bridge mount (the hub wallet daemon itself is
    loopback-only). An explicit ``--hub-url`` is normalized to its bare
    origin — the bridge routes live at the root, not under a path prefix.
    """
    config = get_config()
    base_url = _normalize_hub_url(hub_url) if hub_url else config.wallet_daemon_url.rstrip("/")
    return AITBCHTTPClient(base_url=base_url, timeout=30, max_retries=0, api_key=config.wallet_api_key)


def _resolve_wallet(
    ctx,
    wallet_name: str | None,
    password: str | None = None,
    password_file: str | None = None,
    password_stdin: bool = False,
):
    """Load the active wallet file on this node — the key never leaves it."""
    wallet_name = wallet_name or ctx.obj["wallet_name"]
    wallet_path = resolve_wallet_path(ctx, wallet_name)
    if not wallet_path.exists():
        error(wallet_not_found_message(find_wallet_file_report(wallet_name)))
        raise click.Abort()
    return _load_wallet(
        wallet_path, wallet_name, password=password, password_file=password_file, password_stdin=password_stdin
    )


@sell.command(
    name="quote",
    epilog="""Examples:

  aitbc wallet bridge sell quote --amount 10 --eth-address 0xAbc... --hub-url https://hub.example

  aitbc wallet bridge sell quote --amount 10 --eth-address 0xAbc...   # on the hub itself""",
)
@click.option("--amount", "amount", required=True, type=DECIMAL, help="AIT amount to sell.")
@click.option("--eth-address", "eth_address", required=True, help="Ethereum address to receive ETH.")
@click.option("--wallet-name", "wallet_name", required=False, help="Shop wallet name (AIT source).")
@click.option("--hub-url", "hub_url", required=False, help="Hub wallet-service base URL — bare origin, path is stripped.")
@wallet_password_options
@click.pass_context
def sell_quote(
    ctx,
    amount: Decimal,
    eth_address: str,
    wallet_name: str | None,
    hub_url: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
):
    """Request an AIT->ETH sell quote from the hub escrow."""
    wallet_data = _resolve_wallet(
        ctx, wallet_name, password=password, password_file=password_file, password_stdin=password_stdin
    )
    ait_address = to_eip55(wallet_data["address"])

    client = _hub_bridge_client(hub_url)
    try:
        quote = client.post(
            "/v1/bridge/sell/quote",
            json={"ait_amount": str(amount), "eth_address": eth_address, "ait_address": ait_address},
        )
    except Exception as e:
        error(f"Failed to get sell quote: {http_error_detail(e) or e}")
        raise click.Abort() from e

    if quote.get("detail") or quote.get("error"):
        error(quote.get("detail") or quote.get("error") or "Sell quote rejected")
        raise click.Abort()

    success(f"Quote {quote.get('quote_id')}: {amount} AIT -> {quote.get('eth_amount')} ETH")
    output(
        {
            "quote_id": quote.get("quote_id"),
            "rate": quote.get("rate"),
            "fee_ait": quote.get("fee_ait"),
            "eth_amount": quote.get("eth_amount"),
            "expires_at": quote.get("expires_at"),
            "escrow_address": quote.get("escrow_address"),
            "next": f"aitbc wallet bridge sell lock --quote-id {quote.get('quote_id')}",
        },
        ctx.obj.get("output_format", "table"),
    )


@sell.command(
    name="lock",
    epilog="""Examples:

  aitbc wallet bridge sell lock --quote-id sellq_ab12... --wallet-name sepolia""",
)
@click.option("--quote-id", "quote_id", required=True, help="Sell quote id from `sell quote`.")
@click.option("--wallet-name", "wallet_name", required=False, help="Shop wallet name (signs the lock).")
@click.option("--hub-url", "hub_url", required=False, help="Hub wallet-service base URL — bare origin, path is stripped.")
@wallet_password_options
@click.pass_context
def sell_lock(
    ctx,
    quote_id: str,
    wallet_name: str | None,
    hub_url: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
):
    """Sign and submit the AIT lock to the escrow address.

    The TRANSFER is signed with THIS node's wallet key and submitted to the
    local chain RPC — the hub only ever sees the sealed transaction.
    """
    wallet_data = _resolve_wallet(
        ctx, wallet_name, password=password, password_file=password_file, password_stdin=password_stdin
    )
    from_address = to_eip55(wallet_data["address"])
    private_key_hex = wallet_data.get("private_key")
    if not private_key_hex:
        error("Wallet does not contain a private key")
        raise click.Abort()

    client = _hub_bridge_client(hub_url)
    try:
        quote = client.get(f"/v1/bridge/sell/status/{quote_id}")
    except Exception as e:
        error(f"Failed to fetch quote: {http_error_detail(e) or e}")
        raise click.Abort() from e

    escrow_address = quote.get("escrow_address")
    ait_amount_raw = quote.get("ait_amount")
    if quote.get("kind") != "quote" or not escrow_address or not ait_amount_raw:
        error(f"Quote {quote_id} not found or malformed: {quote.get('detail') or quote}")
        raise click.Abort()
    if quote.get("status") != "quoted":
        error(f"Quote {quote_id} is {quote.get('status')}, not quotable for a lock")
        raise click.Abort()

    from aitbc.crypto.signature_recovery import canonical_address
    from aitbc.utils import ait_to_units

    escrow_address = canonical_address(escrow_address)
    config = get_config()
    rpc_url = config.blockchain_rpc_url or "http://localhost:8202"
    chain_id = resolve_chain_id(ctx, rpc_url)

    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=15)
        account = http_client.get(f"/rpc/account/{from_address}")
        nonce = account.get("nonce", 0)
    except Exception as e:
        error(f"Failed to fetch account nonce: {http_error_detail(e) or e}")
        raise click.Abort() from e

    amount_units = ait_to_units(Decimal(str(ait_amount_raw)))
    fee_units = ait_to_units(Decimal("0.01"))
    unsigned_tx = {
        "type": "TRANSFER",
        "chain_id": chain_id,
        "from": canonical_address(from_address),
        "to": escrow_address,
        "amount": amount_units,
        "fee": fee_units,
        "nonce": nonce,
        "payload": {"amount": amount_units, "sell_quote": quote_id},
    }

    from eth_keys import keys as eth_keys
    from eth_utils import keccak

    if private_key_hex.startswith("0x"):
        private_key_hex = private_key_hex[2:]
    private_key = eth_keys.PrivateKey(bytes.fromhex(private_key_hex))
    unsigned_fields = {k: v for k, v in unsigned_tx.items() if k != "signature"}
    message = json.dumps(unsigned_fields, sort_keys=True, separators=(",", ":")).encode()
    signature = private_key.sign_msg_hash(keccak(message))
    signed_tx = dict(unsigned_tx)
    signed_tx["signature"] = signature.to_bytes().hex()

    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.post("/rpc/transaction", json=signed_tx)
        ait_tx_hash = result.get("transaction_hash") or result.get("tx_hash") or ""
        success(f"Sell lock submitted: {ait_tx_hash}")
        output(
            {
                "ait_tx_hash": ait_tx_hash,
                "quote_id": quote_id,
                "from_address": from_address,
                "escrow_address": escrow_address,
                "ait_amount": str(ait_amount_raw),
                "next": f"aitbc wallet bridge sell status --id {quote_id}",
            },
            ctx.obj.get("output_format", "table"),
        )
    except Exception as e:
        error(f"Failed to submit sell lock: {http_error_detail(e) or e}")
        raise click.Abort() from e


@sell.command(
    name="status",
    epilog="""Examples:

  aitbc wallet bridge sell status --id sellq_ab12...""",
)
@click.option("--id", "identifier", required=True, help="Quote id, lock id, or lock transaction hash.")
@click.option("--hub-url", "hub_url", required=False, help="Hub wallet-service base URL — bare origin, path is stripped.")
@click.pass_context
def sell_status(ctx, identifier: str, hub_url: str | None):
    """Check the status of a sell quote or lock."""
    client = _hub_bridge_client(hub_url)
    try:
        info = client.get(f"/v1/bridge/sell/status/{identifier}")
    except Exception as e:
        error(f"Failed to get sell status: {http_error_detail(e) or e}")
        raise click.Abort() from e

    # The quote row freezes at 'locked' once a lock exists — the live state
    # (releasing/released/settled/refunded) is on the lock row the hub embeds
    # under "lock". Hoist it so the reported status is the lock's.
    lock = info.get("lock")
    if info.get("kind") == "quote" and isinstance(lock, dict):
        out = {k: v for k, v in info.items() if k not in ("kind", "lock")}
        out.update(
            {
                "kind": "lock",
                "quote_status": info.get("status"),
                "status": lock.get("status"),
                "lock_id": lock.get("id"),
                "ait_tx_hash": lock.get("ait_tx_hash"),
                "eth_tx_hash": lock.get("eth_tx_hash"),
                "settle_tx_hash": lock.get("settle_tx_hash"),
                "refund_tx_hash": lock.get("refund_tx_hash"),
                "error": lock.get("error"),
                "settled_at": lock.get("settled_at"),
            }
        )
        info = out

    output(info, ctx.obj.get("output_format", "table"))
