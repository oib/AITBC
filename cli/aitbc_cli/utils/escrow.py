"""Escrow signing and payment helpers for AITBC CLI.

This module holds the transaction-building and signing logic that is shared
between ``aitbc ai`` (coordinator-backed jobs) and ``aitbc market run``
(direct-provider marketplace jobs).
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from aitbc.crypto.crypto import sign_transaction_hash
from eth_utils import keccak

from aitbc.utils import DEFAULT_TX_FEE_UNITS, ait_to_units

from .address import to_canonical
from .error_handling import abort
from .http_client import AITBCHTTPClient, NetworkError


def get_node_wallet(ctx, rpc_url: str) -> str:
    """Return the canonical node wallet/proposer address from the RPC /health endpoint."""
    client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
    try:
        health = client.get("/health")
    except NetworkError as e:
        abort(ctx, f"Cannot reach blockchain RPC at {rpc_url}: {e}")
    proposer_id = health.get("proposer_id")
    if not proposer_id:
        abort(ctx, "Blockchain RPC /health did not return proposer_id (node wallet)")
    return to_canonical(proposer_id)


def get_buyer_nonce(ctx, rpc_url: str, buyer: str) -> int:
    """Fetch the current on-chain nonce for ``buyer``; return 0 on any error."""
    client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
    try:
        account = client.get(f"/rpc/account/{buyer}")
    except Exception:
        return 0
    return int(account.get("nonce", 0))


def build_escrow_lock_tx(
    ctx,
    job_id: str,
    buyer: str,
    provider: str,
    node_wallet: str,
    amount_ait: Decimal,
    nonce: int,
    fee: int | None = None,
    chain_id: str = "ait-hub.aitbc.bubuit.net",
) -> dict[str, Any]:
    """Build an unsigned ESCROW_LOCK transaction dict for the given job."""
    buyer_canon = to_canonical(buyer)
    provider_canon = to_canonical(provider)
    node_canon = to_canonical(node_wallet)
    amount_units = ait_to_units(amount_ait)
    if fee is None:
        fee = max(DEFAULT_TX_FEE_UNITS, amount_units // 100)
    return {
        "from": buyer_canon,
        "to": node_canon,
        "amount": amount_units,
        "fee": fee,
        "nonce": nonce,
        "type": "ESCROW_LOCK",
        "chain_id": chain_id,
        "payload": {
            "action": "escrow_lock",
            "job_id": job_id,
            "provider": provider_canon,
        },
    }


def sign_escrow_lock_tx(lock_tx: dict[str, Any], private_key: str) -> str:
    """Sign an ESCROW_LOCK transaction and return the signature hex string."""
    has_amount = "amount" in lock_tx
    tx_for_sign = {k: v for k, v in lock_tx.items() if k not in ("signature", "sig") and not (has_amount and k == "value")}
    canonical = json.dumps(tx_for_sign, sort_keys=True, separators=(",", ":")).encode()
    tx_hash = "0x" + keccak(canonical).hex()
    return sign_transaction_hash(tx_hash, private_key)


def create_signed_escrow_lock(
    ctx,
    rpc_url: str,
    job_id: str,
    buyer: str,
    provider: str,
    amount_ait: Decimal,
    private_key: str,
    chain_id: str | None = None,
    fee: int | None = None,
    node_wallet: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Build and sign a complete ESCROW_LOCK transaction.

    Returns the unsigned lock transaction dict and the buyer's signature.
    If ``node_wallet`` is not provided, it is read from the RPC /health endpoint.
    """
    buyer_canon = to_canonical(buyer)
    provider_canon = to_canonical(provider)
    if not node_wallet:
        node_wallet = get_node_wallet(ctx, rpc_url)
    node_canon = to_canonical(node_wallet)
    nonce = get_buyer_nonce(ctx, rpc_url, buyer_canon)
    lock_tx = build_escrow_lock_tx(
        ctx,
        job_id,
        buyer_canon,
        provider_canon,
        node_canon,
        amount_ait,
        nonce,
        fee=fee,
        chain_id=chain_id or "ait-hub.aitbc.bubuit.net",
    )
    signature = sign_escrow_lock_tx(lock_tx, private_key)
    return lock_tx, signature
