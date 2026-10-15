"""aitbc wallet eth-send — send plain Sepolia ETH to an explicit recipient (CLI-8).

    aitbc wallet eth-send --to 0x… --amount-eth 0.005 --chain-id 11155111

The default is a DRY RUN: it prints the unsigned transfer (from, to, wei,
chain id, nonce, gas estimate, fee estimate, current balance) reading only
the wallet's plaintext address — no password resolution, no key
decryption, no signature, no broadcast. ``--confirm`` resolves the wallet
password through the standard sources, signs once and broadcasts once;
``--wait`` then polls the receipt and prints status and block.
``--max-gas-gwei`` caps the fee: when ``eth_gasPrice`` comes back above
the ceiling the command refuses before any key is decrypted or signed —
raise it explicitly to send into a gas spike. ``--to`` is checked with
``eth_getCode``: a recipient holding contract bytecode refuses under
``--confirm`` unless ``--allow-contract`` is passed (a plain value
transfer to a contract that does not expect it burns gas or locks the
funds); the dry run shows the ``eth_getCode`` result either way.

Testnet only until v1: ``--chain-id`` must be 11155111 — every other id,
mainnet's 1 included, refuses before the wallet file is even opened, and
the RPC's own ``eth_chainId`` is cross-checked the same way. The signing
leg reuses the wallet-file + ``eth_account`` path ``wallet bridge
deposit`` established; key and password material never reach stdout,
stderr, logs or an argument vector. For bridge deposits use
``aitbc wallet bridge deposit`` instead — it carries the input-data tag
the deposit monitor needs; a plain ``eth-send`` to the deposit address
would strand the funds.
"""

from __future__ import annotations

import json
import os
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import click

from ...utils import DECIMAL, info, output, resolve_output_format, success
from ...utils.address import to_eip55
from ...utils.error_handling import abort
from ...utils.evm_rpc import broadcast_raw, hex_to_int, resolve_rpc_url, rpc_call
from ...utils.wallet_secret import wallet_password_options
from . import _load_signing_key, wallet
from .bridge import _resolve_wallet_path

SEPOLIA_CHAIN_ID = 11155111
DEFAULT_MAX_ETH = Decimal("0.1")
# 50 gwei mirrors the "acceptable" bound in contracts/scripts/check-gas-price.js;
# Sepolia's usual price is far below it, so the default only binds on a spike.
DEFAULT_MAX_GAS_GWEI = Decimal("50")
RECEIPT_POLL_SECONDS = 3.0
RECEIPT_TIMEOUT_SECONDS = 120.0


def _send_wallet(ctx, wallet: str | None) -> tuple[str | None, Path]:
    """``--wallet`` names a wallet (standard search order) or gives a wallet
    file path — which is only ever opened locally; remote fetch does not
    exist, so a file on another host cannot be signed with."""
    name = wallet or (ctx.obj or {}).get("wallet_name")
    if name and (os.sep in name or name.endswith(".json")):
        path = Path(name)
        if not path.is_file():
            abort(ctx, f"wallet file not found: {path}")
        return Path(name).stem, path
    if not name:
        abort(ctx, "no wallet selected — pass --wallet <name|path> or the group --wallet-name")
    return name, _resolve_wallet_path(ctx, str(name))


def _wallet_address_only(ctx, wallet_path: Path) -> str:
    """The wallet file's plaintext ``address`` — a raw JSON read, no
    decryption, no password resolution. Used by the dry run."""
    try:
        with open(wallet_path) as f:
            data: dict[str, Any] = json.load(f)
    except OSError as e:
        abort(ctx, f"cannot read wallet file {wallet_path}: {e}", from_exception=e)
        raise AssertionError("unreachable: abort always raises") from e
    address = data.get("address")
    if not address:
        abort(ctx, f"wallet file {wallet_path} has no address field")
    return to_eip55(str(address))


def _validated_wei(ctx, amount_eth: Decimal, max_eth: Decimal) -> int:
    """Positive, at most 18 decimals, and within the per-call cap."""
    if max_eth <= 0:
        abort(ctx, "--max-eth must be positive")
    elif amount_eth <= 0:
        abort(ctx, "--amount-eth must be positive")
    elif amount_eth > max_eth:
        abort(ctx, f"--amount-eth {amount_eth} exceeds the per-call cap {max_eth} ETH — pass --max-eth to raise it")
    scaled = amount_eth * Decimal(10**18)
    if scaled != scaled.to_integral_value():
        abort(ctx, f"--amount-eth {amount_eth} has more than 18 decimals — not representable in wei")
    return int(scaled)


def _validated_gas_ceiling(ctx, max_gas_gwei: Decimal) -> int:
    """Positive gwei ceiling, returned as wei for the exact integer compare."""
    if max_gas_gwei <= 0:
        abort(ctx, "--max-gas-gwei must be positive")
    scaled = max_gas_gwei * Decimal(10**9)
    if scaled != scaled.to_integral_value():
        abort(ctx, f"--max-gas-gwei {max_gas_gwei} has more than 9 decimals — not representable in wei")
    return int(scaled)


def _check_rpc_chain(ctx, rpc_url: str) -> None:
    rpc_chain = hex_to_int(ctx, rpc_call(ctx, rpc_url, "eth_chainId", []), "chain id")
    if rpc_chain != SEPOLIA_CHAIN_ID:
        abort(ctx, f"RPC at {rpc_url} reports chain id {rpc_chain}, not Sepolia ({SEPOLIA_CHAIN_ID}) — refusing")


def _validated_recipient(ctx, to_address: str, from_address: str) -> str:
    """EIP-55 checksummed recipient. Mixed-case input whose checksum does not
    verify refuses — ``to_eip55`` would otherwise silently "fix" a typo into
    a real address. Refuses the zero address and self-sends."""
    hex_part = to_address.strip()[2:]
    mixed_case = not (hex_part.islower() or hex_part.isupper())
    try:
        checksummed = to_eip55(to_address.strip())
    except ValueError as e:
        abort(ctx, f"invalid --to address: {e}", from_exception=e)
        raise AssertionError("unreachable: abort always raises") from e
    if mixed_case and checksummed != to_address.strip():
        abort(ctx, "--to fails its EIP-55 checksum — re-check the address rather than trusting a mixed-case typo")
    if int(hex_part, 16) == 0:
        abort(ctx, "--to is the zero address")
    if checksummed.lower() == from_address.lower():
        abort(ctx, "--to is the wallet's own address — a self-send only burns gas")
    return checksummed


def _receipt_view(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": receipt.get("status"),
        "block": int(receipt["blockNumber"], 16) if isinstance(receipt.get("blockNumber"), str) else None,
        "gas_used": int(receipt["gasUsed"], 16) if isinstance(receipt.get("gasUsed"), str) else None,
    }


def _wait_for_receipt(ctx, rpc_url: str, tx_hash: str) -> dict[str, Any]:
    """Poll eth_getTransactionReceipt until sealed or the timeout lapses;
    the submission already landed, so a timeout is reported, not an error."""
    deadline = time.monotonic() + RECEIPT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        receipt = rpc_call(ctx, rpc_url, "eth_getTransactionReceipt", [tx_hash])
        if isinstance(receipt, dict) and receipt.get("status") is not None:
            return _receipt_view(receipt)
        time.sleep(RECEIPT_POLL_SECONDS)
    return {"status": "pending", "note": f"no receipt after {RECEIPT_TIMEOUT_SECONDS:.0f}s — check {tx_hash} on the explorer"}


@wallet.command(
    "eth-send",
    epilog="""Examples:

  aitbc wallet eth-send --to 0xD701…3D3C --amount-eth 0.005 --chain-id 11155111

  aitbc wallet eth-send --to 0xD701…3D3C --amount-eth 0.005 --chain-id 11155111 \\
      --wallet sepolia --confirm --password-stdin --wait""",
)
@click.option("--to", "to_address", required=True, help="Recipient 0x address (EIP-55 or lowercase)")
@click.option("--amount-eth", "amount_eth", type=DECIMAL, required=True, help="Sepolia ETH to send")
@click.option("--chain-id", "chain_id", type=int, required=True, help="EVM chain id — must be 11155111 (Sepolia)")
@click.option("--eth-rpc-url", "eth_rpc_url", default=None, help="Sepolia JSON-RPC endpoint (default: ETH_RPC_URL env/config)")
@click.option("--wallet", "wallet_name", default=None, help="Wallet name or wallet file path on this host")
@click.option(
    "--max-eth",
    "max_eth",
    type=DECIMAL,
    default=DEFAULT_MAX_ETH,
    show_default=True,
    help="Per-call send cap — raise explicitly for larger transfers",
)
@click.option(
    "--max-gas-gwei",
    "max_gas_gwei",
    type=DECIMAL,
    default=DEFAULT_MAX_GAS_GWEI,
    show_default=True,
    help="Gas-price ceiling in gwei — --confirm refuses to sign above it",
)
@click.option(
    "--allow-contract",
    is_flag=True,
    help="With --confirm: allow --to to hold contract bytecode (default: refuse contracts)",
)
@click.option("--confirm", is_flag=True, help="Sign and broadcast once (default: dry run, prints the unsigned transfer)")
@click.option("--wait", "wait_receipt", is_flag=True, help="With --confirm: poll the receipt and print status and block")
@wallet_password_options
@click.pass_context
def eth_send(
    ctx,
    to_address: str,
    amount_eth: Decimal,
    chain_id: int,
    eth_rpc_url: str | None,
    wallet_name: str | None,
    max_eth: Decimal,
    max_gas_gwei: Decimal,
    allow_contract: bool,
    confirm: bool,
    wait_receipt: bool,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
):
    """Send plain Sepolia ETH from this node's wallet to an explicit address.

    Prints the unsigned transfer by default; ``--confirm`` signs and
    broadcasts once. Sepolia (chain id 11155111) only — every other chain
    id refuses, including mainnet's 1.
    """
    if chain_id != SEPOLIA_CHAIN_ID:
        abort(ctx, f"--chain-id {chain_id} refused — eth-send is Sepolia-only (chain id {SEPOLIA_CHAIN_ID})")
        return
    if wait_receipt and not confirm:
        abort(ctx, "--wait only applies with --confirm — a dry run has no transaction to wait on")
        return
    if allow_contract and not confirm:
        abort(ctx, "--allow-contract only applies with --confirm — a dry run signs nothing either way")
        return
    value_wei = _validated_wei(ctx, amount_eth, max_eth)
    gas_ceiling_wei = _validated_gas_ceiling(ctx, max_gas_gwei)

    wallet_name, wallet_path = _send_wallet(ctx, wallet_name)
    from_address = _wallet_address_only(ctx, wallet_path)
    to = _validated_recipient(ctx, to_address, from_address)

    rpc_url = resolve_rpc_url(ctx, eth_rpc_url)
    _check_rpc_chain(ctx, rpc_url)
    nonce = hex_to_int(ctx, rpc_call(ctx, rpc_url, "eth_getTransactionCount", [from_address, "pending"]), "nonce")
    gas_price_wei = hex_to_int(ctx, rpc_call(ctx, rpc_url, "eth_gasPrice", []), "gas price")
    gas_limit = hex_to_int(
        ctx,
        rpc_call(
            ctx,
            rpc_url,
            "eth_estimateGas",
            [{"from": from_address, "to": to, "value": hex(value_wei)}],
        ),
        "gas estimate",
    )
    balance_wei = hex_to_int(ctx, rpc_call(ctx, rpc_url, "eth_getBalance", [from_address, "latest"]), "balance")
    to_code = rpc_call(ctx, rpc_url, "eth_getCode", [to, "latest"])
    to_is_contract = isinstance(to_code, str) and to_code not in ("0x", "0x0", "")
    fee_wei = gas_limit * gas_price_wei

    tx_view = {
        "from": from_address,
        "to": to,
        "amount_eth": str(amount_eth),
        "value_wei": value_wei,
        "chain_id": SEPOLIA_CHAIN_ID,
        "nonce": nonce,
        "gas_limit": gas_limit,
        "gas_price_wei": gas_price_wei,
        "gas_price_gwei": str(Decimal(gas_price_wei) / Decimal(10**9)),
        "gas_ceiling_gwei": str(max_gas_gwei),
        "over_gas_ceiling": gas_price_wei > gas_ceiling_wei,
        "fee_estimate_wei": fee_wei,
        "fee_estimate_eth": str(Decimal(fee_wei) / Decimal(10**18)),
        "balance_wei": balance_wei,
        "balance_eth": str(Decimal(balance_wei) / Decimal(10**18)),
        "to_code": to_code,
        "to_is_contract": to_is_contract,
        "per_call_cap_eth": str(max_eth),
    }

    if not confirm:
        info("DRY RUN — nothing signed, nothing sent. Re-run with --confirm to sign and broadcast once:")
        output(tx_view, resolve_output_format(ctx))
        return

    _broadcast_transfer(
        ctx,
        rpc_url=rpc_url,
        wallet_name=wallet_name,
        wallet_path=wallet_path,
        from_address=from_address,
        to=to,
        amount_eth=amount_eth,
        value_wei=value_wei,
        nonce=nonce,
        gas_price_wei=gas_price_wei,
        gas_limit=gas_limit,
        gas_ceiling_wei=gas_ceiling_wei,
        balance_wei=balance_wei,
        fee_wei=fee_wei,
        to_is_contract=to_is_contract,
        allow_contract=allow_contract,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        wait_receipt=wait_receipt,
    )


def _broadcast_transfer(
    ctx,
    *,
    rpc_url: str,
    wallet_name: str | None,
    wallet_path: Path,
    from_address: str,
    to: str,
    amount_eth: Decimal,
    value_wei: int,
    nonce: int,
    gas_price_wei: int,
    gas_limit: int,
    gas_ceiling_wei: int,
    balance_wei: int,
    fee_wei: int,
    to_is_contract: bool,
    allow_contract: bool,
    password,
    password_file,
    password_stdin,
    wait_receipt: bool,
) -> None:
    """The --confirm leg: contract, gas-ceiling and balance gates, one signature, one broadcast."""
    if to_is_contract and not allow_contract:
        abort(
            ctx,
            "--to holds contract bytecode — a plain value transfer can burn gas or lock funds there; "
            "pass --allow-contract if the recipient is a contract that accepts plain ETH",
        )
        return
    if gas_price_wei > gas_ceiling_wei:
        abort(
            ctx,
            f"eth_gasPrice {Decimal(gas_price_wei) / Decimal(10**9)} gwei exceeds --max-gas-gwei "
            f"{Decimal(gas_ceiling_wei) / Decimal(10**9)} — refusing to sign; raise the flag to send into a gas spike",
        )
        return
    if balance_wei < value_wei + fee_wei:
        abort(
            ctx,
            f"insufficient Sepolia ETH: need {amount_eth} + ~{Decimal(fee_wei) / Decimal(10**18)} gas, "
            f"have {Decimal(balance_wei) / Decimal(10**18)}",
        )
        return

    private_key = _load_signing_key(ctx, wallet_name, wallet_path, password, password_file, password_stdin)

    from eth_account import Account as EthAccount

    from aitbc.crypto.signature_recovery import canonical_address

    account = EthAccount.from_key(private_key)
    if canonical_address(account.address).lower() != canonical_address(from_address).lower():
        abort(
            ctx,
            f"Wallet address {from_address} does not match the key's address {account.address} — "
            "the CLI does not sign for a different wallet",
        )
        return

    signed = account.sign_transaction(
        {
            "to": to,
            "value": value_wei,
            "gas": gas_limit,
            "gasPrice": gas_price_wei,
            "nonce": nonce,
            "chainId": SEPOLIA_CHAIN_ID,
            "data": "0x",
        }
    )
    raw = signed.raw_transaction
    if isinstance(raw, bytes):
        raw = "0x" + raw.hex()

    tx_hash = broadcast_raw(ctx, rpc_url, raw, label="ETH transfer")
    success(f"ETH transfer submitted: {tx_hash}")
    view: dict[str, Any] = {
        "eth_tx_hash": tx_hash,
        "from": from_address,
        "to": to,
        "amount_eth": str(amount_eth),
    }
    if wait_receipt:
        view["receipt"] = _wait_for_receipt(ctx, rpc_url, tx_hash)
    output(view, resolve_output_format(ctx))
    receipt = view.get("receipt")
    if isinstance(receipt, dict) and receipt.get("status") == "0x0":
        abort(ctx, f"transaction {tx_hash} sealed with failure status")
