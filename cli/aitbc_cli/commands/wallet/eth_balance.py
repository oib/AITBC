"""aitbc wallet eth-balance — read-only Sepolia ETH balance + nonce (ETH-20b).

    aitbc wallet eth-balance --address 0x…
    aitbc wallet eth-balance --wallet sepolia

Prints the sealed-state (block tag ``latest``) ``eth_getBalance`` and
``eth_getTransactionCount`` for one address — passed directly via
``--address`` or read from a wallet file's plaintext ``address`` field
via ``--wallet``. Exactly one of the two selectors is required.

The command is a pure read: nothing is signed, sent or decrypted and no
password is ever resolved — ``--wallet`` is a raw JSON read of the
``address`` field only. The zero address and the wallet's own address
are valid read targets (those refusals were send-safety only); a
mixed-case ``--address`` whose EIP-55 checksum does not verify still
refuses, same rule as ``eth-send``.

Sepolia only: the resolved RPC's own ``eth_chainId`` must answer
11155111 — a mainnet or other-chain endpoint refuses before the balance
calls. The endpoint resolves ``--eth-rpc-url`` > ``ETH_RPC_URL`` env >
CLI config; error text shows the masked display URL only.
"""

from __future__ import annotations

from decimal import Decimal

import click

from ...utils import output, resolve_output_format
from ...utils.address import to_eip55
from ...utils.error_handling import abort
from ...utils.evm_rpc import display_rpc_url, hex_to_int, resolve_rpc_url, rpc_call
from . import wallet
from .eth_common import check_rpc_chain, resolve_wallet_file, wallet_address_only


def _validated_read_address(ctx, address: str) -> str:
    """EIP-55 checksummed read target. Mixed-case input whose checksum
    does not verify refuses — ``to_eip55`` would otherwise silently
    "fix" a typo into a real address."""
    hex_part = address.strip()[2:]
    mixed_case = not (hex_part.islower() or hex_part.isupper())
    try:
        checksummed = to_eip55(address.strip())
    except ValueError as e:
        abort(ctx, f"invalid --address: {e}", from_exception=e)
        raise AssertionError("unreachable: abort always raises") from e
    if mixed_case and checksummed != address.strip():
        abort(ctx, "--address fails its EIP-55 checksum — re-check the address rather than trusting a mixed-case typo")
    return checksummed


@wallet.command(
    "eth-balance",
    epilog="""Examples:

  aitbc wallet eth-balance --address 0xA556…74C

  aitbc wallet eth-balance --wallet sepolia --eth-rpc-url https://rpc.sepolia.example""",
)
@click.option("--address", "address", default=None, help="0x address to read (EIP-55 or lowercase)")
@click.option("--wallet", "wallet_name", default=None, help="Wallet name or wallet file path on this host")
@click.option("--eth-rpc-url", "eth_rpc_url", default=None, help="Sepolia JSON-RPC endpoint (default: ETH_RPC_URL env/config)")
@click.pass_context
def eth_balance(ctx, address: str | None, wallet_name: str | None, eth_rpc_url: str | None):
    """Read the sealed Sepolia ETH balance and nonce of one address.

    Exactly one of ``--address`` / ``--wallet`` is required; ``--wallet``
    reads only the file's plaintext ``address`` field — no decryption, no
    password. Read-only: nothing is signed or sent.
    """
    if address and wallet_name:
        abort(ctx, "pass exactly one of --address or --wallet, not both")
        return
    if not address and not wallet_name:
        abort(ctx, "one of --address or --wallet is required")
        return

    if address:
        target = _validated_read_address(ctx, address)
    else:
        _name, wallet_path = resolve_wallet_file(ctx, wallet_name)
        target = wallet_address_only(ctx, wallet_path)

    rpc_url = resolve_rpc_url(ctx, eth_rpc_url)
    check_rpc_chain(ctx, rpc_url)
    balance_wei = hex_to_int(ctx, rpc_call(ctx, rpc_url, "eth_getBalance", [target, "latest"]), "balance")
    nonce = hex_to_int(ctx, rpc_call(ctx, rpc_url, "eth_getTransactionCount", [target, "latest"]), "nonce")
    output(
        {
            "address": target,
            "balance_wei": balance_wei,
            "balance_eth": str(Decimal(balance_wei) / Decimal(10**18)),
            "nonce": nonce,
            "rpc": display_rpc_url(rpc_url),
        },
        resolve_output_format(ctx),
    )
