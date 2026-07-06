"""Bridge protocol and security level enums.

These enums are used by the cross-chain integration router and the
deprecated ``CrossChainBridgeService`` (``bridge_enhanced.py``).  They
are extracted here so that new code can import them without pulling in
the deprecated service class.
"""

from __future__ import annotations

from enum import StrEnum


class BridgeProtocol(StrEnum):
    """Bridge protocol types"""

    ATOMIC_SWAP = "atomic_swap"
    HTLC = "htlc"
    LIQUIDITY_POOL = "liquidity_pool"
    WRAPPED_TOKEN = "wrapped_token"


class BridgeSecurityLevel(StrEnum):
    """Bridge security levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAXIMUM = "maximum"
