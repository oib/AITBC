"""Coverage for cross-chain bridge_types enums (#1289 residual).

Pins the wire values the cross-chain router and BridgeClientAdapter
depend on — a silent value change would break serialized contracts.
"""

from __future__ import annotations

from coordinator_api.contexts.cross_chain.services.cross_chain.bridge_types import (
    BridgeProtocol,
    BridgeSecurityLevel,
)


def test_bridge_protocol_values():
    assert BridgeProtocol.ATOMIC_SWAP == "atomic_swap"
    assert BridgeProtocol.HTLC == "htlc"
    assert BridgeProtocol.LIQUIDITY_POOL == "liquidity_pool"
    assert BridgeProtocol.WRAPPED_TOKEN == "wrapped_token"
    assert len(BridgeProtocol) == 4


def test_bridge_security_level_values():
    assert BridgeSecurityLevel.LOW == "low"
    assert BridgeSecurityLevel.MEDIUM == "medium"
    assert BridgeSecurityLevel.HIGH == "high"
    assert BridgeSecurityLevel.MAXIMUM == "maximum"
    assert len(BridgeSecurityLevel) == 4


def test_enums_are_str_subclasses():
    # StrEnum members must interoperate with plain str comparisons/JSON
    assert BridgeProtocol.HTLC.value == "htlc"
    assert isinstance(BridgeProtocol.HTLC, str)
    assert BridgeSecurityLevel.MAXIMUM == "maximum"
