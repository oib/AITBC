"""aitbc exchange prepay — the hub exchange's prepaid-ETH lane (design: eth8-exchange-page §2).

    aitbc exchange prepay deposit --amount-eth X --wallet NAME [--send]

A BUY order is backed by a prepaid ETH balance on the hub exchange. The
balance is credited by a Sepolia ETH deposit to the hub's bridge deposit
address whose input data carries the tag ``EXCHANGE_DEPOSIT:<node
address>`` — UTF-8 bytes, exactly what
``wallet_app.bridge.bridge_monitor._parse_exchange_deposit_tag`` accepts
(prefix case-insensitive, address text verbatim, canonicalized at credit).

``--print`` (the default) builds and shows the unsigned transaction —
no password, no key read. ``--send`` signs and broadcasts it once with
the node's own wallet through the same decrypt path ``wallet bridge
deposit`` uses. Signing never retries a failed broadcast; the error is
reported and the operator decides.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import click

from ...utils import DECIMAL, evm_rpc, info, output, resolve_output_format, success
from ...utils.address import to_canonical
from ...utils.error_handling import abort
from ...utils.wallet_secret import resolve_wallet_password, wallet_password_options  # noqa: F401  (patch surface for tests)
from .hub_orders import _exchange_client, _fund_wallet_address

SEPOLIA_CHAIN_ID = 11155111
# Fixed ceiling like `wallet bridge deposit`'s tx — a tagged data field adds
# only calldata gas over a plain transfer; estimation overrides it when the
# RPC answers.
FALLBACK_GAS_LIMIT = 100_000
DEFAULT_MAX_ETH = Decimal("0.01")


def _prepay_tag(node_address: str) -> str:
    """The tag the deposit monitor parses — verbatim UTF-8 in tx input."""
    return f"EXCHANGE_DEPOSIT:{node_address}"


def _prepay_data_hex(tag: str) -> str:
    """Hex-encoded UTF-8 tag for the tx ``data`` field."""
    return "0x" + tag.encode("utf-8").hex()


def _short(address: str | None) -> str | None:
    """The participants board's shortened form — same rule as the
    exchange's ``_short_addr`` so registry fields compare equal."""
    if not address:
        return None
    return address[:6] + "…" + address[-4:] if len(address) > 12 else address


def _is_eth_address(value: str | None) -> bool:
    if not value or not value.startswith("0x") or len(value) != 42:
        return False
    try:
        int(value[2:], 16)
    except ValueError:
        return False
    return True


def _bridge_deposit_address(ctx, client) -> str:
    """The hub's ETH deposit destination, advertised by the wallet service's
    bridge status (mounted on the exchange). Never user input — a mistyped
    recipient would strand the deposit outside the monitored float."""
    try:
        status = client.get("/v1/bridge/status")
    except Exception as e:
        abort(ctx, f"Cannot read /v1/bridge/status for the deposit address: {e}", from_exception=e)
        raise AssertionError("unreachable: abort always raises") from e
    address = str(status.get("deposit_address") or "") if isinstance(status, dict) else ""
    if not _is_eth_address(address):
        abort(ctx, "bridge status advertises no usable deposit_address — is the exchange settled up?")
    return to_canonical(address)


def _node_row(ctx, client, address: str) -> dict[str, Any] | None:
    """The wallet's participants-board row, matched on the board's
    shortened address form."""
    try:
        doc = client.get("/api/exchange/nodes")
    except Exception as e:
        abort(ctx, f"Cannot read /api/exchange/nodes for the registry check: {e}", from_exception=e)
        raise AssertionError("unreachable: abort always raises") from e
    short = _short(address)
    for row in (doc.get("nodes") or []) if isinstance(doc, dict) else []:
        if isinstance(row, dict) and row.get("address") == short:
            return row
    return None


def _rpc_call(ctx, rpc_url: str, method: str, params: list[Any]) -> Any:
    """One synchronous JSON-RPC call — shared EVM helper (tests patch this name)."""
    return evm_rpc.rpc_call(ctx, rpc_url, method, params)


def _rpc_try(ctx, rpc_url: str, method: str, params: list[Any]) -> Any:
    """Best-effort variant of ``_rpc_call`` for --print display fields —
    returns None instead of aborting so an unsigned preview still prints."""
    return evm_rpc.rpc_try(ctx, rpc_url, method, params)


def _eth_rpc(ctx, override: str | None) -> str:
    return evm_rpc.resolve_rpc_url(ctx, override)


def _registry_check(ctx, client, address: str) -> tuple[bool, str]:
    """(ok, reason) — the pre-flight rule ``--send`` enforces and ``--print``
    reports: the sending wallet must be a *registered* exchange node whose
    declared ``eth_address`` is itself. Registered + matching means the
    tagged deposit credits the right node and any uncommitted prepaid
    remainder pays back to the same key."""
    row = _node_row(ctx, client, address)
    if row is None:
        return False, f"{address} has no row on the participants board"
    if row.get("status") != "registered":
        return False, (f"node status is '{row.get('status')}', not 'registered' — run 'aitbc exchange node register' first")
    if row.get("eth_address") != _short(address):
        return False, (
            f"registry payout eth_address {row.get('eth_address')!r} does not match "
            f"the sending wallet — run 'aitbc exchange node set-payout --eth-address {address}' first"
        )
    return True, "registered, payout address matches"


@click.group(name="prepay")
def prepay():
    """Prepaid-ETH lane — node-tagged Sepolia deposits credit the exchange float."""


@prepay.command(
    "deposit",
    epilog="""Examples:

  aitbc exchange prepay deposit --amount-eth 0.0002 --wallet sepolia

  aitbc exchange prepay deposit --amount-eth 0.0002 --wallet sepolia --send --password-stdin

  aitbc exchange prepay deposit --amount-eth 0.05 --wallet sepolia --max-eth 0.1 --send""",
)
@click.option("--amount-eth", "amount_eth", type=DECIMAL, required=True, help="Sepolia ETH to deposit")
@click.option("--wallet", default=None, help="Wallet name or file path — the node's own registered wallet")
@wallet_password_options
@click.option("--send", is_flag=True, help="Sign and broadcast once (default: print the unsigned tx)")
@click.option(
    "--max-eth",
    "max_eth",
    type=DECIMAL,
    default=DEFAULT_MAX_ETH,
    show_default=True,
    help="Per-call deposit cap — raise explicitly for larger deposits",
)
@click.option("--exchange-url", default=None, help="Override exchange service base URL")
@click.option("--eth-rpc-url", default=None, help="Sepolia JSON-RPC endpoint (default: ETH_RPC_URL env/config)")
@click.pass_context
def deposit(ctx, amount_eth, wallet, password, password_file, password_stdin, send, max_eth, exchange_url, eth_rpc_url):
    """Deposit Sepolia ETH into this node's prepaid exchange balance.

    Sends to the hub's bridge deposit address with the
    ``EXCHANGE_DEPOSIT:<node address>`` input-data tag; the deposit monitor
    records it 'exchange_prepay' and the settlement monitor credits the
    prepaid balance (and auto-funds any open unfunded BUYs, in id order).
    """
    if amount_eth <= 0:
        abort(ctx, "--amount-eth must be positive")
        return
    if max_eth <= 0:
        abort(ctx, "--max-eth must be positive")
        return
    if amount_eth > max_eth:
        abort(
            ctx,
            f"--amount-eth {amount_eth} exceeds the per-call cap {max_eth} ETH — pass --max-eth to raise it",
        )
        return

    address, wallet_id, wallet_path = _fund_wallet_address(ctx, wallet)
    client = _exchange_client(ctx, exchange_url)
    to_address = _bridge_deposit_address(ctx, client)
    ok, reason = _registry_check(ctx, client, address)
    if not ok:
        abort(ctx, f"registry check failed: {reason}")
        return

    rpc_url = _eth_rpc(ctx, eth_rpc_url)
    chain_id = _rpc_try(ctx, rpc_url, "eth_chainId", [])
    try:
        chain_id_int = int(chain_id, 16) if isinstance(chain_id, str) else None
    except (TypeError, ValueError):
        chain_id_int = None  # malformed result — same path as a missing one
    if chain_id_int is not None and chain_id_int != SEPOLIA_CHAIN_ID:
        abort(ctx, f"RPC chain id {chain_id_int} is not Sepolia ({SEPOLIA_CHAIN_ID}) — refusing")
        return

    tag = _prepay_tag(address)
    data_hex = _prepay_data_hex(tag)
    value_wei = int(amount_eth * Decimal(10**18))
    if value_wei <= 0:
        abort(ctx, f"amount {amount_eth} ETH is below 1 wei — refusing a zero-value deposit")
        return
    nonce = _rpc_try(ctx, rpc_url, "eth_getTransactionCount", [address, "pending"])
    gas_price = _rpc_try(ctx, rpc_url, "eth_gasPrice", [])
    gas_estimate = _rpc_try(
        ctx,
        rpc_url,
        "eth_estimateGas",
        [{"from": address, "to": to_address, "value": hex(value_wei), "data": data_hex}],
    )
    gas_limit = int(gas_estimate, 16) if isinstance(gas_estimate, str) else FALLBACK_GAS_LIMIT

    tx_view = {
        "chain_id": SEPOLIA_CHAIN_ID if chain_id_int is None else chain_id_int,
        "chain_id_verified": chain_id_int == SEPOLIA_CHAIN_ID,
        "from": address,
        "to": to_address,
        "amount_eth": str(amount_eth),
        "value_wei": value_wei,
        "tag": tag,
        "data_hex": data_hex,
        "nonce": int(nonce, 16) if isinstance(nonce, str) else None,
        "gas_limit": gas_limit,
        "gas_price_wei": int(gas_price, 16) if isinstance(gas_price, str) else None,
        "per_call_cap_eth": str(max_eth),
        "registry_check": reason,
    }
    if not send:
        info("Not broadcasting — unsigned tx (re-run with --send to sign and submit once):")
        output(tx_view, resolve_output_format(ctx))
        return

    _send_deposit(
        ctx,
        rpc_url=rpc_url,
        wallet_id=wallet_id,
        wallet_path=wallet_path,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        address=address,
        to_address=to_address,
        amount_eth=amount_eth,
        value_wei=value_wei,
        tag=tag,
        data_hex=data_hex,
        chain_id_int=chain_id_int,
        nonce=nonce,
        gas_price=gas_price,
        gas_limit=gas_limit,
    )


def _load_signing_key(ctx, wallet_id: str, wallet_path, password, password_file, password_stdin) -> str:
    """Decrypt the wallet file through the standard resolver and hand back the
    private key — the shared loader ``wallet bridge deposit``/``eth-send`` use."""
    from ..wallet import _load_signing_key as _shared_load_signing_key

    return _shared_load_signing_key(ctx, wallet_id, wallet_path, password, password_file, password_stdin)


def _broadcast_raw(ctx, rpc_url: str, raw: str) -> str:
    """One eth_sendRawTransaction — a failure is reported, never retried."""
    return evm_rpc.broadcast_raw(ctx, rpc_url, raw, label="ETH deposit")


def _send_deposit(
    ctx,
    *,
    rpc_url: str,
    wallet_id: str,
    wallet_path,
    password,
    password_file,
    password_stdin,
    address: str,
    to_address: str,
    amount_eth: Decimal,
    value_wei: int,
    tag: str,
    data_hex: str,
    chain_id_int: int | None,
    nonce,
    gas_price,
    gas_limit: int,
) -> None:
    """The --send leg: verified-chain + funded-wallet gates, one signature,
    one broadcast."""
    if chain_id_int is None:
        abort(ctx, "cannot verify the RPC chain id — refusing to sign for an unverified chain")
        return

    try:
        gas_price_wei = int(gas_price, 16) if isinstance(gas_price, str) else None
    except ValueError:
        gas_price_wei = None
    if gas_price_wei is None:
        abort(ctx, "no usable gas price from the Sepolia RPC — refusing to sign a zero-price transaction")
        return

    balance = _rpc_call(ctx, rpc_url, "eth_getBalance", [address, "latest"])
    gas_cost_wei = gas_limit * gas_price_wei
    if balance is not None and int(balance, 16) < value_wei + gas_cost_wei:
        abort(
            ctx,
            f"insufficient Sepolia ETH: need {amount_eth} + ~{Decimal(gas_cost_wei) / Decimal(10**18)} gas, "
            f"have {Decimal(int(balance, 16)) / Decimal(10**18)}",
        )
        return

    private_key = _load_signing_key(ctx, wallet_id, wallet_path, password, password_file, password_stdin)

    from eth_account import Account as EthAccount

    from aitbc.crypto.signature_recovery import canonical_address

    account = EthAccount.from_key(private_key)
    if canonical_address(account.address).lower() != canonical_address(address).lower():
        abort(
            ctx,
            f"Wallet address {address} does not match the key's address {account.address} — "
            "the CLI does not sign for a different wallet",
        )
        return

    if nonce is None:
        abort(ctx, "no pending nonce from the RPC — refusing to guess one")
        return
    signed = account.sign_transaction(
        {
            "to": to_address,
            "value": value_wei,
            "gas": gas_limit,
            "gasPrice": gas_price_wei,
            "nonce": int(nonce, 16),
            "chainId": SEPOLIA_CHAIN_ID,
            "data": data_hex,
        }
    )
    raw = signed.raw_transaction
    if isinstance(raw, bytes):
        raw = "0x" + raw.hex()

    tx_hash = _broadcast_raw(ctx, rpc_url, raw)

    success(f"Exchange prepay deposit submitted: {tx_hash}")
    output(
        {
            "eth_tx_hash": tx_hash,
            "from": address,
            "to": to_address,
            "amount_eth": str(amount_eth),
            "tag": tag,
            "note": "the deposit monitor records 'exchange_prepay' — the settlement monitor credits the prepaid balance",
        },
        resolve_output_format(ctx),
    )
