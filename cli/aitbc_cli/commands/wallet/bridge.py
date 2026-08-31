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
from ...utils.http_client import AITBCHTTPClient
from . import _load_wallet, get_wallet_client, wallet


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
@click.option("--password", help="Wallet password for signing")
@click.pass_context
def deposit(ctx, amount: Decimal, wallet_name: str | None, eth_rpc_url: str | None, password: str | None):
    """Deposit ETH to the bridge and receive AITBC on the hub."""
    wallet_name = wallet_name or ctx.obj["wallet_name"]
    wallet_dir = ctx.obj["wallet_dir"]
    if wallet_name != ctx.obj.get("wallet_name"):
        wallet_path = wallet_dir / f"{wallet_name}.json"
    else:
        wallet_path = ctx.obj.get("wallet_path") or wallet_dir / f"{wallet_name}.json"

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        raise click.Abort()

    wallet_data = _load_wallet(wallet_path, wallet_name)
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
@click.option("--password", help="Wallet password for signing")
@click.pass_context
def withdraw(ctx, amount: Decimal, eth_address: str, wallet_name: str | None, password: str | None):
    """Burn AITBC on the hub to receive ETH at the given Ethereum address."""
    wallet_name = wallet_name or ctx.obj["wallet_name"]
    wallet_dir = ctx.obj["wallet_dir"]
    if wallet_name != ctx.obj.get("wallet_name"):
        wallet_path = wallet_dir / f"{wallet_name}.json"
    else:
        wallet_path = ctx.obj.get("wallet_path") or wallet_dir / f"{wallet_name}.json"

    if not wallet_path.exists():
        error(f"Wallet '{wallet_name}' not found")
        raise click.Abort()

    wallet_data = _load_wallet(wallet_path, wallet_name)
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

  aitbc wallet bridge status --ait-tx-hash 0x..."""
)
@click.option("--ait-tx-hash", "ait_tx_hash", required=True, help="AIT withdrawal transaction hash.")
@click.pass_context
def status(ctx, ait_tx_hash: str):
    """Check the status of an AIT->ETH withdrawal."""
    wallet_client = get_wallet_client()
    try:
        info = wallet_client.get(f"/v1/bridge/withdraw/{ait_tx_hash}")
    except Exception as e:
        error(f"Failed to get withdrawal status: {e}")
        raise click.Abort() from e

    output(info, ctx.obj.get("output_format", "table"))
