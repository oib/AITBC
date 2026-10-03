"""Escrow signing and payment helpers for AITBC CLI.

This module holds the transaction-building and signing logic that is shared
between ``aitbc ai`` (coordinator-backed jobs) and ``aitbc market run``
(direct-provider market jobs).
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any, cast

from aitbc.crypto.crypto import sign_transaction_hash
from eth_utils import keccak

from aitbc.utils import DEFAULT_TX_FEE_UNITS, ait_to_units

from .address import to_canonical
from .error_handling import abort
from .http_client import AITBCHTTPClient, NetworkError


# ``node_wallet`` is advertised only at a blockchain RPC's own root ``/health``.
# A public hub endpoint proxies just ``/rpc/*`` to the blockchain RPC and
# answers ``/health`` with a different service (the agent-coordinator), so a
# ``blockchain_rpc_url`` pointed at the public URL cannot discover the wallet —
# the failure names the config key to repoint.
_NODE_WALLET_URL_HINT = (
    "node_wallet is advertised only at a blockchain RPC's own /health; the public "
    "hub endpoint proxies /rpc/* only and serves a different service at /health. "
    "Set blockchain_rpc_url (config key / BLOCKCHAIN_RPC_URL) to a blockchain RPC "
    "that serves /health directly, e.g. http://127.0.0.1:8202 on the node itself"
)


def get_node_wallet(ctx, rpc_url: str) -> str:
    """Return the canonical node wallet that custodies escrow, from RPC /health.

    The escrow route validates the ESCROW_LOCK ``to`` against the node
    ``NODE_WALLET_ADDRESS``, which is a different account from the consensus
    ``proposer_id``: the proposer signs blocks and differs per node, while the
    node wallet holds escrow and is shared across a chain settling nodes.
    Locking against ``proposer_id`` is rejected with "lock_tx to must be the
    node wallet". Nodes that predate the ``node_wallet`` field report only
    ``proposer_id``, so fall back to it there.
    """
    client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
    try:
        health = client.get("/health")
    except NetworkError as e:
        abort(
            ctx,
            f"Cannot determine the escrow node wallet from {rpc_url}: /health request failed: {e}. {_NODE_WALLET_URL_HINT}",
            from_exception=e,
        )
        raise AssertionError("unreachable: abort always raises") from e
    node_wallet = health.get("node_wallet") or health.get("proposer_id")
    if not node_wallet:
        abort(
            ctx,
            f"Cannot determine the escrow node wallet from {rpc_url}: /health answered without "
            f"node_wallet/proposer_id — a different service answered. {_NODE_WALLET_URL_HINT}",
        )
        raise AssertionError("unreachable: abort always raises")
    return to_canonical(cast(str, node_wallet))


def get_buyer_nonce(ctx, rpc_url: str, buyer: str) -> int:
    """Fetch the current on-chain nonce for ``buyer``; abort on any failure.

    A failed lookup must not mean nonce 0 — the wrong nonce produces an
    already-signed transaction the chain refuses.
    """
    client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
    try:
        account = client.get(f"/rpc/account/{buyer}")
        nonce = account.get("nonce")
        if nonce is None:
            raise ValueError(f"/rpc/account/{buyer} response carried no nonce")
        return int(nonce)
    except Exception as e:
        abort(
            ctx,
            f"Nonce lookup for {buyer} via {rpc_url} failed: {e}. Check the node is serving this account or pass --rpc-url",
            from_exception=e,
        )
        raise AssertionError("unreachable: abort always raises") from e


def build_escrow_lock_tx(
    ctx,
    job_id: str,
    buyer: str,
    provider: str,
    node_wallet: str,
    amount_ait: Decimal,
    nonce: int,
    fee: int | None = None,
    chain_id: str | None = None,
    *,
    energy_quote_id: str | None = None,
    energy_quote_digest: str | None = None,
    settlement_route: str | None = None,
    settlement_asset: str | None = None,
    settlement_unit_scale: int | None = None,
) -> dict[str, Any]:
    """Build an unsigned ESCROW_LOCK transaction dict for the given job."""
    if not chain_id:
        abort(
            ctx,
            "No chain id for the escrow lock transaction — an explicit chain_id, "
            "CHAIN_ID or a serving --rpc-url is required; never sign a silent default",
        )
        raise AssertionError("unreachable: abort always raises")
    buyer_canon = to_canonical(buyer)
    provider_canon = to_canonical(provider)
    node_canon = to_canonical(node_wallet)
    amount_units = ait_to_units(amount_ait)
    if fee is None:
        fee = max(DEFAULT_TX_FEE_UNITS, amount_units // 100)
    payload: dict[str, Any] = {
        "action": "escrow_lock",
        "job_id": job_id,
        "provider": provider_canon,
    }
    if energy_quote_id:
        payload["energy_quote_id"] = energy_quote_id
    if energy_quote_digest:
        payload["energy_quote_digest"] = energy_quote_digest
    if settlement_route:
        payload["settlement_route"] = settlement_route
    if settlement_asset:
        payload["settlement_asset"] = settlement_asset
    if settlement_unit_scale is not None:
        payload["settlement_unit_scale"] = settlement_unit_scale
    return {
        "from": buyer_canon,
        "to": node_canon,
        "amount": amount_units,
        "fee": fee,
        "nonce": nonce,
        "type": "ESCROW_LOCK",
        "chain_id": chain_id,
        "payload": payload,
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
    *,
    energy_quote_id: str | None = None,
    energy_quote_digest: str | None = None,
    settlement_route: str | None = None,
    settlement_asset: str | None = None,
    settlement_unit_scale: int | None = None,
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
    # The chain id comes from the RPC the transaction is submitted to: an
    # explicit argument or CHAIN_ID wins, otherwise probe ``rpc_url``
    # strictly — never sign a silent default the node may not serve.
    if not chain_id:
        chain_id = os.getenv("CHAIN_ID") or ""
    if not chain_id:
        try:
            from .chain_id import get_chain_id

            chain_id = get_chain_id(rpc_url, override=None, timeout=5, strict=True)
        except Exception as e:
            abort(
                ctx,
                f"Chain ID lookup via {rpc_url} failed: {e}. Set CHAIN_ID or point --rpc-url at a serving node",
                from_exception=e,
            )
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
        chain_id=chain_id,
        energy_quote_id=energy_quote_id,
        energy_quote_digest=energy_quote_digest,
        settlement_route=settlement_route,
        settlement_asset=settlement_asset,
        settlement_unit_scale=settlement_unit_scale,
    )
    signature = sign_escrow_lock_tx(lock_tx, private_key)
    return lock_tx, signature
