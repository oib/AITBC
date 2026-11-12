"""
Core MarketService mixin: construction and shared helpers.
"""

import time

from sqlalchemy.ext.asyncio import AsyncSession

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.market import BlockchainRPCClient

from ...config import settings


logger = get_logger(__name__)


class _CoreMixin:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._rpc_client = BlockchainRPCClient(
            rpc_url=settings.blockchain_rpc_url,
            api_key=settings.blockchain_rpc_api_key,
        )

    def get_current_timestamp(self) -> int:
        """Get current Unix timestamp"""
        return int(time.time())

    def _canonical_address(self, address: str) -> str:
        """Return the canonical 0x spelling for address comparison.

        The chain stores EIP-55 secp256k1/EVM addresses, so comparing the
        canonical `0x` form produced by :func:`canonical_address` removes
        formatting differences without accepting legacy `ait1`/`aitbc1` spellings.
        """
        return canonical_address(address or "")
