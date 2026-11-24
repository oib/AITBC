"""Blockchain RPC client for the trading service (v0.8.0 §B3, v0.10.7 §B2).

Thin subclass of the shared ``aitbc.blockchain.rpc_client.BlockchainClient``.
It deliberately does NOT swallow transport failures into safe defaults:
``get_block_height``/``get_chain_health`` must raise so callers can mark a
chain ``unreachable`` — returning 0/{} fabricated a healthy-looking
``status='active', block_height=0`` registry entry and kept dead endpoints
in the offer-sync set (#2839).
"""

from __future__ import annotations

from aitbc.blockchain.rpc_client import BlockchainClient as BaseBlockchainClient


class BlockchainClient(BaseBlockchainClient):
    """Async blockchain RPC client for trading service operations.

    Failure semantics are inherited unchanged: ``get_block_height`` and
    ``get_chain_health`` raise on transport/HTTP errors. Chain discovery
    and health reporting rely on that — a swallowed failure would be
    indistinguishable from a reachable chain at height 0.
    """
