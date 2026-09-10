"""GPU-onchain transaction builders and submission helpers.

Turns `aitbc gpu-onchain register/allocate` into signed blockchain transactions
so they are broadcast through the mempool, included in blocks, and replicated
across all validators instead of being written to one node's local DB.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from aitbc.crypto.crypto import sign_transaction_hash
from aitbc.utils import DEFAULT_TX_FEE_UNITS
from eth_utils import keccak

from .escrow import get_buyer_nonce
from .error_handling import abort
from .http_client import AITBCHTTPClient, NetworkError
from .wallet_loader import load_wallet_for_payment


def _sign_tx(tx: dict[str, Any], private_key: str) -> str:
    """Sign a transaction dict and return the hex signature."""
    has_amount = "amount" in tx
    tx_for_sign = {k: v for k, v in tx.items() if k not in ("signature", "sig") and not (has_amount and k == "value")}
    canonical = json.dumps(tx_for_sign, sort_keys=True, separators=(",", ":")).encode()
    tx_hash = "0x" + keccak(canonical).hex()
    return sign_transaction_hash(tx_hash, private_key)


def _build_gpu_tx(
    ctx: Any,
    rpc_url: str,
    chain_id: str,
    wallet: str,
    password: str | None,
    tx_type: str,
    payload: dict[str, Any],
    fee: int | None = None,
) -> tuple[dict[str, Any], str]:
    """Build a GPU_REGISTER or GPU_ALLOCATE transaction and return (tx, private_key)."""
    address, private_key, _ = load_wallet_for_payment(ctx, wallet_name=wallet, password=password, require_private_key=True)
    if not private_key:
        abort(ctx, f"Wallet '{wallet}' has no private key for signing")
        raise AssertionError("unreachable after abort")

    nonce = get_buyer_nonce(ctx, rpc_url, address)
    if fee is None:
        fee = DEFAULT_TX_FEE_UNITS

    tx: dict[str, Any] = {
        "from": address,
        "to": address,
        "amount": 0,
        "fee": fee,
        "nonce": nonce,
        "type": tx_type,
        "chain_id": chain_id,
        "payload": payload,
    }
    return tx, private_key


def _submit_signed_tx(rpc_url: str, tx: dict[str, Any]) -> dict[str, Any]:
    client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
    return client.post("/rpc/transaction", json=tx)


def submit_gpu_register(
    ctx: Any,
    rpc_url: str,
    chain_id: str,
    wallet: str,
    password: str | None,
    gpu_id: str,
    miner_id: str,
    model: str,
    memory_gb: int,
    cuda_version: str,
    region: str,
    capabilities: tuple,
    price_per_hour: Decimal,
    fee: int | None = None,
) -> dict[str, Any]:
    """Build, sign and submit a GPU_REGISTER transaction."""
    payload = {
        "gpu_id": gpu_id,
        "miner_id": miner_id,
        "model": model,
        "memory_gb": memory_gb,
        "cuda_version": cuda_version,
        "region": region,
        "capabilities": list(capabilities),
        "price_per_hour": str(price_per_hour),
    }
    tx, private_key = _build_gpu_tx(ctx, rpc_url, chain_id, wallet, password, "GPU_REGISTER", payload, fee=fee)
    tx["signature"] = _sign_tx(tx, private_key)
    return _submit_signed_tx(rpc_url, tx)


def submit_gpu_allocate(
    ctx: Any,
    rpc_url: str,
    chain_id: str,
    wallet: str,
    password: str | None,
    gpu_id: str,
    client_id: str,
    duration_hours: float,
    total_cost: Decimal,
    fee: int | None = None,
) -> dict[str, Any]:
    """Build, sign and submit a GPU_ALLOCATE transaction."""
    payload = {
        "gpu_id": gpu_id,
        "client_id": client_id,
        "duration_hours": duration_hours,
        "total_cost": str(total_cost),
    }
    tx, private_key = _build_gpu_tx(ctx, rpc_url, chain_id, wallet, password, "GPU_ALLOCATE", payload, fee=fee)
    tx["signature"] = _sign_tx(tx, private_key)
    return _submit_signed_tx(rpc_url, tx)


def wait_for_tx(rpc_url: str, tx_hash: str, timeout: float = 30.0, poll_interval: float = 2.0) -> dict[str, Any] | None:
    """Poll /rpc/transaction/{tx_hash} until the tx is mined or timeout."""
    import time

    client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = client.get(f"/rpc/transaction/{tx_hash}")
            if isinstance(result, dict) and result.get("block_height") is not None:
                return result
        except NetworkError:
            pass
        time.sleep(poll_interval)
    return None
