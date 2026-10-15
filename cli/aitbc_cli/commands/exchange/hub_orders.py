"""Signed orders on the hub exchange — ETH-11 phase 2 (design: eth8-exchange-page).

Command tree:

    aitbc exchange order place  --side BUY|SELL --amount AIT --price ETH/AIT
    aitbc exchange order cancel <order_id>
    aitbc exchange order fund   <order_id> [--print]
    aitbc exchange order my     [--address 0x… | --wallet name]
    aitbc exchange node register [--label NAME]
    aitbc exchange node set-payout --eth-address 0x…
    aitbc exchange node list

Wallet sovereignty (design sovereignty check, decided 14 Oct): every command
that produces a signature calls ``load_wallet_for_payment`` — the node's own
local keystore on this host. No code path here reads, requests, or signs with
another node's key, password, mnemonic, or keystore, and none needs SSH
between nodes. The hub verifies signatures; keys never leave the node.

Envelope shapes must match
``apps/exchange/simple_exchange/handlers/exchange.py`` exactly — the exchange
verifies ``keccak256(canonical JSON)`` over the pinned field set.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import click

from ...utils import DECIMAL, info, output, resolve_output_format, success
from ...utils.error_handling import abort
from ...utils.http_client import AITBCHTTPClient, NetworkError, http_error_detail, http_response_status
from ...utils.chain_id import resolve_chain_id
from ...utils.island_credentials import get_rpc_endpoint
from ...utils.wallet_loader import load_wallet_for_payment
from ...utils.wallet_paths import wallet_dir
from ...utils.wallet_secret import resolve_wallet_password, wallet_password_options
from ..transactions import _send_transaction_impl

TICKS_PER_UNIT = 100_000_000  # 8 decimal places — mirrors db.py
PAIR = "AIT/ETH"
_ORDER_ACTION = "exchange_cancel"
_REGISTER_ACTION = "exchange_register"
_PAYOUT_ACTION = "exchange_set_payout"
DEFAULT_EXPIRES_IN = 1440  # blocks (~4 h at 10 s/block)


def _to_ticks(ctx, value: Decimal, what: str) -> int:
    """Exact Decimal -> integer ticks; refuses anything not representable."""
    try:
        ticks = value * TICKS_PER_UNIT
    except (InvalidOperation, ValueError) as e:
        abort(ctx, f"Invalid {what}: {value}", from_exception=e)
        return 0
    if ticks != ticks.to_integral_value():
        abort(ctx, f"{what} {value} exceeds 8-decimal precision")
        return 0
    return int(ticks)


def _exchange_base_url(ctx, override: str | None) -> str:
    """The exchange service base URL — refuses the blockchain-RPC fallback."""
    from ...config import get_config

    base = (override or get_config().exchange_service_url or "").rstrip("/")
    if not base:
        abort(ctx, "Exchange URL unresolved — set exchange_service_url or HUB_EXCHANGE_URL")
    elif base.endswith("/rpc"):
        abort(
            ctx,
            "exchange_service_url resolved to the blockchain RPC — set HUB_EXCHANGE_URL "
            "(or aitbc config set exchange_service_url …) to the exchange service base",
        )
    return base


def _exchange_client(ctx, override: str | None) -> AITBCHTTPClient:
    return AITBCHTTPClient(base_url=_exchange_base_url(ctx, override), timeout=15)


def _chain_head(ctx) -> int:
    """Local node's chain head — the same chain the hub exchange validates against."""
    client = AITBCHTTPClient(base_url=get_rpc_endpoint(), timeout=10)
    try:
        head = client.get("/head")
    except NetworkError as e:
        abort(ctx, f"Cannot reach local blockchain RPC for chain head: {e}", from_exception=e)
        return 0
    height = head.get("height") if isinstance(head, dict) else None
    if not isinstance(height, int):
        abort(ctx, "Local blockchain RPC returned no chain height")
        return 0
    return height


def _envelope_chain_id(ctx, override: str | None) -> str:
    """The envelope chain_id: explicit flag, else resolved against this node's
    own RPC — fail-closed (resolve_chain_id probes strictly on signing paths),
    never a silent default: a guessed chain_id signs an unverifiable envelope."""
    if override:
        return override
    return resolve_chain_id(ctx, get_rpc_endpoint())


def _node_state(client: AITBCHTTPClient, ctx, address: str) -> tuple[int, dict[str, Any]]:
    """Exchange-scoped nonce + the node's registry/orders row via my-orders."""
    try:
        info_doc = client.get("/api/exchange/my-orders", params={"addr": address})
    except NetworkError as e:
        abort(ctx, f"Cannot reach exchange: {http_error_detail(e) or e}", from_exception=e)
        return 0, {}
    nonce = info_doc.get("next_nonce", 0)
    return (nonce if isinstance(nonce, int) else 0), info_doc


def _sign_envelope(envelope: dict[str, Any], private_key: str) -> str:
    """keccak256(canonical JSON) + secp256k1 — the repo's canonical signing."""
    from aitbc.crypto.crypto import sign_transaction_data

    return sign_transaction_data(envelope, private_key)


def _post_signed(
    client: AITBCHTTPClient, ctx, path: str, envelope: dict[str, Any], signature: str, address: str
) -> dict[str, Any]:
    """POST a signed action; the signature doubles as the dedupe idempotency key."""
    try:
        return client.post(
            path,
            json={"envelope": envelope, "signature": signature, "user_address": address},
            idempotency_key=signature,
        )
    except NetworkError as e:
        status = http_response_status(e)
        detail = http_error_detail(e)
        if detail:
            abort(ctx, f"Exchange answered {status}: {detail}", from_exception=e)
        else:
            abort(ctx, f"Exchange request failed: {e}", from_exception=e)
        return {}


def _load_signer(ctx, wallet, password, password_file, password_stdin) -> tuple[str, str, str]:
    """This node's own wallet — (address, private_key, wallet_id)."""
    address, private_key, wallet_id = load_wallet_for_payment(
        ctx,
        wallet_name=wallet,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        require_private_key=True,
    )
    if private_key is None:  # unreachable under require_private_key; narrows the type
        abort(ctx, "Wallet has no private key available for signing")
        raise AssertionError("unreachable: abort always raises")
    return address, private_key, wallet_id


@click.group(name="order")
def order():
    """Signed AIT/ETH orders on the hub exchange — funded under
    EXCHANGE_SETTLEMENT_ENABLED (flag-off: unfunded, settlement-free)."""


@click.group(name="node")
def node():
    """Node registration on the hub exchange."""


def _funding_hint(result: dict[str, Any]) -> None:
    """Render the funding instruction attached to an unfunded order
    (EXCHANGE_SETTLEMENT_ENABLED on the hub). Flag-off responses carry no
    'funding' key — nothing is printed, byte-identical to before."""
    funding = result.get("funding")
    if not isinstance(funding, dict) or funding.get("state") != "unfunded":
        return
    if funding.get("type") == "eth_prepay":
        info(
            f"To fund: send {funding.get('needed_eth')} ETH (Sepolia) to "
            f"{funding.get('bridge_eth_address')} with the input-data tag "
            f"'{funding.get('tag')}' — the deposit monitor records it "
            "exchange_prepay and the settlement monitor credits your "
            "prepaid balance."
        )
    elif funding.get("type") == "ait_lock":
        payload = funding.get("payload") or f"sell_quote={result.get('id')}"
        info(
            f"To fund: send a TRANSFER of at least {funding.get('required_ait')} "
            f"AIT to {funding.get('escrow')} with payload '{payload}' from "
            "this wallet — stranger locks are refunded, never credited."
        )


@order.command(
    "place",
    epilog="""Examples:

  aitbc exchange order place --side SELL --amount 10 --price 0.000083 --wallet node2

  aitbc exchange order place --side BUY --amount 5 --price 0.000083 \\
      --expires-in 720 --wallet node2 --password-stdin""",
)
@click.option("--side", type=click.Choice(["BUY", "SELL"]), required=True, help="Order side")
@click.option("--amount", "amount", type=DECIMAL, required=True, help="AIT amount (8-decimal exact)")
@click.option("--price", "price", type=DECIMAL, required=True, help="ETH price per AIT (within the oracle band)")
@click.option(
    "--expires-in",
    type=int,
    default=DEFAULT_EXPIRES_IN,
    show_default=True,
    help="Blocks until the order envelope expires",
)
@click.option("--wallet", default=None, help="Wallet name or file path (this node's own wallet)")
@wallet_password_options
@click.option("--chain-id", default=None, help="Envelope chain_id (default: island credentials)")
@click.option("--exchange-url", default=None, help="Override exchange service base URL")
@click.pass_context
def order_place(ctx, side, amount, price, expires_in, wallet, password, password_file, password_stdin, chain_id, exchange_url):
    """Sign and place an AIT/ETH order. Under settlement the response
    carries the funding instruction — rendered as a hint above the JSON."""
    if amount <= 0 or price <= 0:
        abort(ctx, "amount and price must be positive")
    address, private_key, _wallet_id = _load_signer(ctx, wallet, password, password_file, password_stdin)
    client = _exchange_client(ctx, exchange_url)
    nonce, info_doc = _node_state(client, ctx, address)
    if not info_doc.get("registered"):
        abort(ctx, f"{address} is not a registered exchange node — run 'aitbc exchange node register' first")
    envelope = {
        "side": side,
        "pair": PAIR,
        "amount_ticks": _to_ticks(ctx, amount, "amount"),
        "price_ticks": _to_ticks(ctx, price, "price"),
        "expiry_height": _chain_head(ctx) + expires_in,
        "account_nonce": nonce,
        "chain_id": _envelope_chain_id(ctx, chain_id),
    }
    signature = _sign_envelope(envelope, private_key)
    result = _post_signed(client, ctx, "/api/orders", envelope, signature, address)
    success(f"Order placed: {side} {amount} AIT @ {price} ETH (id {result.get('id')}, status {result.get('status')})")
    _funding_hint(result)
    output(result, resolve_output_format(ctx))


@order.command(
    "cancel",
    epilog="""Example:

  aitbc exchange order cancel 42 --wallet node2""",
)
@click.argument("order_id", type=int)
@click.option(
    "--expires-in",
    type=int,
    default=120,
    show_default=True,
    help="Blocks until the cancel envelope expires",
)
@click.option("--wallet", default=None, help="Wallet name or file path — must be the order owner's")
@wallet_password_options
@click.option("--chain-id", default=None, help="Envelope chain_id (default: island credentials)")
@click.option("--exchange-url", default=None, help="Override exchange service base URL")
@click.pass_context
def order_cancel(ctx, order_id, expires_in, wallet, password, password_file, password_stdin, chain_id, exchange_url):
    """Sign and submit a cancel for one of this node's own orders."""
    address, private_key, _wallet_id = _load_signer(ctx, wallet, password, password_file, password_stdin)
    client = _exchange_client(ctx, exchange_url)
    nonce, _info_doc = _node_state(client, ctx, address)
    envelope = {
        "action": _ORDER_ACTION,
        "order_id": order_id,
        "expiry_height": _chain_head(ctx) + expires_in,
        "account_nonce": nonce,
        "chain_id": _envelope_chain_id(ctx, chain_id),
    }
    signature = _sign_envelope(envelope, private_key)
    result = _post_signed(client, ctx, f"/api/orders/{order_id}/cancel", envelope, signature, address)
    success(f"Order {order_id}: {result.get('status')}")
    output(result, resolve_output_format(ctx))


@order.command(
    "my",
    epilog="""Examples:

  aitbc exchange order my --wallet node2
  aitbc exchange order my --address 0xF1C8…""",
)
@click.option("--wallet", default=None, help="Wallet name (address only — no signing)")
@click.option("--address", "address_opt", default=None, help="Plain 0x address (no wallet needed)")
@click.option("--exchange-url", default=None, help="Override exchange service base URL")
@click.pass_context
def order_my(ctx, wallet, address_opt, exchange_url):
    """Show this node's orders and next exchange nonce (read-only)."""
    if address_opt:
        address = address_opt
    elif wallet:
        address, _pk, _wid = load_wallet_for_payment(ctx, wallet_name=wallet, require_private_key=False)
    else:
        abort(ctx, "Provide --wallet or --address")
        return
    client = _exchange_client(ctx, exchange_url)
    nonce, info_doc = _node_state(client, ctx, address)
    output(
        {
            "address": info_doc.get("address"),
            "label": info_doc.get("label"),
            "registered": info_doc.get("registered"),
            "next_nonce": nonce,
            "orders": info_doc.get("orders") or [],
        },
        resolve_output_format(ctx),
        title="My exchange orders",
    )


@order.command(
    "fund",
    epilog="""Examples:

  aitbc exchange order fund 42 --wallet node2 --password-stdin
  aitbc exchange order fund 42 --wallet node2 --print""",
)
@click.argument("order_id", type=int)
@click.option("--fee", type=DECIMAL, default=Decimal("0.001"), show_default=True, help="AIT chain fee for the lock transfer")
@click.option("--print", "print_only", is_flag=True, help="Emit the equivalent 'transactions send' line; broadcast nothing")
@click.option("--wallet", default=None, help="Wallet name (not a file path) — must be the order owner's")
@wallet_password_options
@click.option("--rpc-url", default=None, help="Blockchain RPC URL for the lock transfer")
@click.option("--exchange-url", default=None, help="Override exchange service base URL")
@click.pass_context
def order_fund(ctx, order_id, fee, print_only, wallet, password, password_file, password_stdin, rpc_url, exchange_url):
    """Fund an unfunded SELL order with its AIT escrow lock.

    Reads the funding instruction from my-orders (escrow address, required
    AIT, sell_quote payload) and sends the lock TRANSFER from this node's
    own wallet — the sender must be the order owner (stranger locks are
    refunded, never credited). --print emits the equivalent
    'transactions send' line without broadcasting anything.

    Operator note (CLI-1): this command was implemented and exercised
    against mocks only — no live exchange, wallet, or chain run has been
    performed. A real transfer is an AIT move the operator names
    explicitly.
    """
    address, _pk, wallet_id = load_wallet_for_payment(ctx, wallet_name=wallet, require_private_key=False)
    client = _exchange_client(ctx, exchange_url)
    _nonce, doc = _node_state(client, ctx, address)
    row = next((o for o in (doc.get("orders") or []) if o.get("id") == order_id), None)
    if row is None:
        abort(ctx, f"Order {order_id} is not among {address}'s orders")
        return
    if row.get("order_type") != "SELL":
        abort(
            ctx, f"Order {order_id} is a BUY — fund it with an ETH prepay tagged EXCHANGE_DEPOSIT:{address}, not an AIT lock"
        )
        return
    funding = row.get("funding")
    if row.get("status") != "open" or row.get("funded_state") != "unfunded" or not isinstance(funding, dict):
        abort(
            ctx,
            f"Order {order_id} is not awaiting a lock (status={row.get('status')}, funded_state={row.get('funded_state')})",
        )
        return
    if funding.get("type") != "ait_lock":
        abort(ctx, f"Order {order_id} expects {funding.get('type')} funding, not an AIT lock")
        return
    escrow = funding.get("escrow") or ""
    if not escrow:
        abort(ctx, "Funding block carries no escrow address — AIT_SELL_ESCROW unset on the exchange")
        return
    try:
        required = Decimal(str(funding.get("required_ait") or "0"))
    except InvalidOperation as e:
        abort(ctx, f"Unparseable required_ait in funding block: {funding.get('required_ait')!r}", from_exception=e)
        return
    if required <= 0:
        abort(ctx, f"Unparseable required_ait in funding block: {funding.get('required_ait')!r}")
        return
    send_line = (
        f"aitbc transactions send --from {wallet_id} --to {escrow} "
        f"--amount {required} --fee {fee} --payload '{{\"sell_quote\": {order_id}}}'"
    )
    if print_only:
        info("Not broadcasting — equivalent raw command:")
        click.echo(send_line)
        return
    pw = resolve_wallet_password(
        wallet_id,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        allow_unencrypted=True,
        wallet_path=wallet_dir() / f"{wallet_id}.json",
    )
    tx_hash = _send_transaction_impl(wallet_id, escrow, required, fee, pw, rpc_url=rpc_url, payload={"sell_quote": order_id})
    if tx_hash:
        success(f"Lock sent for order {order_id}: {tx_hash} — the settlement monitor funds it once it lands")
        output(
            {"order_id": order_id, "ait_tx_hash": tx_hash, "escrow": escrow, "required_ait": str(required)},
            resolve_output_format(ctx),
        )


@node.command(
    "register",
    epilog="""Example:

  aitbc exchange node register --wallet node2

The label is pinned by the exchange's registry seed; --label must match it.""",
)
@click.option("--wallet", default=None, help="Wallet name or file path — the node's registered AIT wallet")
@click.option("--label", default=None, help="Registry label (must equal the seeded label; default: use seeded)")
@wallet_password_options
@click.option("--chain-id", default=None, help="Envelope chain_id (default: island credentials)")
@click.option("--exchange-url", default=None, help="Override exchange service base URL")
@click.pass_context
def node_register(ctx, wallet, label, password, password_file, password_stdin, chain_id, exchange_url):
    """Claim this node's seeded registry row with a signed envelope."""
    address, private_key, _wallet_id = _load_signer(ctx, wallet, password, password_file, password_stdin)
    client = _exchange_client(ctx, exchange_url)
    nonce, info_doc = _node_state(client, ctx, address)
    seeded_label = info_doc.get("label")
    if label is None:
        if not seeded_label:
            abort(ctx, "No seeded registry row for this address — the hub operator seeds labels")
            return
        label = seeded_label
    if info_doc.get("registered"):
        info(f"{address} is already registered as '{seeded_label}'")
        return
    envelope = {
        "action": _REGISTER_ACTION,
        "address": address,
        "label": label,
        "account_nonce": nonce,
        "chain_id": _envelope_chain_id(ctx, chain_id),
    }
    signature = _sign_envelope(envelope, private_key)
    result = _post_signed(client, ctx, "/api/exchange/nodes/register", envelope, signature, address)
    success(f"Registered on the hub exchange as '{result.get('label')}'")
    output(result, resolve_output_format(ctx))


@node.command(
    "set-payout",
    epilog="""Example:

  aitbc exchange node set-payout --eth-address 0xAbc… --wallet node2 --password-stdin

The address is normalized to EIP-55 checksum form before signing; the
exchange refuses anything else. Applies to orders placed after the claim.""",
)
@click.option(
    "--eth-address", "eth_address", required=True, help="Sepolia ETH payout address (any case — checksummed before signing)"
)
@click.option("--wallet", default=None, help="Wallet name or file path — the node's registered AIT wallet")
@wallet_password_options
@click.option("--chain-id", default=None, help="Envelope chain_id (default: island credentials)")
@click.option("--exchange-url", default=None, help="Override exchange service base URL")
@click.pass_context
def node_set_payout(ctx, eth_address, wallet, password, password_file, password_stdin, chain_id, exchange_url):
    """Claim this node's ETH payout address with a signed envelope
    (dark while EXCHANGE_SETTLEMENT_ENABLED is off — a flag-off exchange
    answers 404, which is surfaced as-is)."""
    from eth_utils import to_checksum_address

    try:
        checksummed = to_checksum_address(eth_address)
    except (ValueError, TypeError) as e:
        abort(ctx, f"Invalid --eth-address: {eth_address!r}", from_exception=e)
        return
    address, private_key, _wallet_id = _load_signer(ctx, wallet, password, password_file, password_stdin)
    client = _exchange_client(ctx, exchange_url)
    nonce, _info_doc = _node_state(client, ctx, address)
    envelope = {
        "action": _PAYOUT_ACTION,
        "eth_address": checksummed,
        "account_nonce": nonce,
        "chain_id": _envelope_chain_id(ctx, chain_id),
    }
    signature = _sign_envelope(envelope, private_key)
    result = _post_signed(client, ctx, "/api/exchange/nodes/payout", envelope, signature, address)
    success(f"Payout address set: {result.get('eth_address')} (previous: {result.get('previous_eth_address') or 'unset'})")
    output(result, resolve_output_format(ctx))


@node.command("list")
@click.option("--exchange-url", default=None, help="Override exchange service base URL")
@click.pass_context
def node_list(ctx, exchange_url):
    """List exchange nodes — the participants board (read-only, no wallet)."""
    client = _exchange_client(ctx, exchange_url)
    try:
        doc = client.get("/api/exchange/nodes")
    except NetworkError as e:
        abort(ctx, f"Cannot reach exchange: {http_error_detail(e) or e}", from_exception=e)
        return
    output({"nodes": doc.get("nodes") or []}, resolve_output_format(ctx), title="Exchange nodes")
