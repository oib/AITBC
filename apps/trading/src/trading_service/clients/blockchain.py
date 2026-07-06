"""Blockchain RPC client for the trading service (v0.8.0 §B3, v0.10.7 §B2).

Thin wrapper around the shared ``aitbc.blockchain.rpc_client.BlockchainClient``
that adds resilient error handling for chain discovery monitoring (returns 0
on transient failures instead of raising).
"""

from __future__ import annotations

import logging
from typing import Any

from aitbc.blockchain.rpc_client import BlockchainClient as BaseBlockchainClient

logger = logging.getLogger(__name__)


class BlockchainClient(BaseBlockchainClient):
    """Async blockchain RPC client for trading service operations.

    Extends the shared ``aitbc.blockchain.rpc_client.BlockchainClient`` with
    resilient error handling suitable for chain discovery monitoring:
    ``get_block_height`` and ``get_chain_health`` return safe defaults
    (0 / empty) on transient failures instead of raising.
    """

    async def get_block_height(self, chain_id: str | None = None) -> int:
        """Get the current block height for a chain.

        Returns 0 on transient failures (used by chain discovery which
        must not crash when a chain is temporarily unreachable).
        """
        try:
            return await super().get_block_height(chain_id)
        except Exception as e:
            logger.warning("Failed to get block height: %s", e)
            return 0

    async def get_chain_health(self, chain_id: str | None = None) -> dict[str, Any]:
        """Get chain health metrics.

        Returns an empty dict on transient failures.
        """
        try:
            return await super().get_chain_health(chain_id)
        except Exception as e:
            logger.warning("Failed to get chain health: %s", e)
            return {}
