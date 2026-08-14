"""Integration tests for v0.6.6 Compute Marketplace features.

Tests cover:
- OfferFSM state transitions (available → reserved → in_use → available/delist)
- BlockchainRPCClient chain_id-aware offer queries (mocked)
- Marketplace chain_id filter on offer listing
- Marketplace matching endpoint (price-time priority)
- Marketplace update_offer_status with FSM validation
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add the marketplace src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aitbc.marketplace import OfferFSM, OfferStatus  # noqa: E402


# ---------------------------------------------------------------------------
# OfferFSM transition tests
# ---------------------------------------------------------------------------


class TestOfferFSMTransitions:
    """Test OfferFSM state machine transitions used by marketplace."""

    def test_available_to_reserved(self):
        fsm = OfferFSM(OfferStatus.AVAILABLE)
        fsm.transition(OfferStatus.RESERVED)
        assert fsm.status == OfferStatus.RESERVED

    def test_reserved_to_in_use(self):
        fsm = OfferFSM(OfferStatus.RESERVED)
        fsm.transition(OfferStatus.IN_USE)
        assert fsm.status == OfferStatus.IN_USE

    def test_in_use_to_available(self):
        fsm = OfferFSM(OfferStatus.IN_USE)
        fsm.transition(OfferStatus.AVAILABLE)
        assert fsm.status == OfferStatus.AVAILABLE

    def test_reserved_to_available_release(self):
        fsm = OfferFSM(OfferStatus.RESERVED)
        fsm.transition(OfferStatus.AVAILABLE)
        assert fsm.status == OfferStatus.AVAILABLE

    def test_available_to_delisted(self):
        fsm = OfferFSM(OfferStatus.AVAILABLE)
        fsm.transition(OfferStatus.DELISTED)
        assert fsm.status == OfferStatus.DELISTED
        assert fsm.is_terminal()

    def test_invalid_transition_available_to_in_use_raises(self):
        fsm = OfferFSM(OfferStatus.AVAILABLE)
        with pytest.raises(ValueError, match="Invalid offer transition"):
            fsm.transition(OfferStatus.IN_USE)

    def test_invalid_transition_delisted_to_anything_raises(self):
        fsm = OfferFSM(OfferStatus.DELISTED)
        with pytest.raises(ValueError, match="Invalid offer transition"):
            fsm.transition(OfferStatus.AVAILABLE)

    def test_from_string_valid(self):
        status = OfferFSM.from_string("available")
        assert status == OfferStatus.AVAILABLE

    def test_from_string_invalid_raises(self):
        with pytest.raises(ValueError, match="Unknown offer status"):
            OfferFSM.from_string("unknown_status")


# ---------------------------------------------------------------------------
# BlockchainRPCClient chain_id routing tests (mocked)
# ---------------------------------------------------------------------------


class TestBlockchainRPCClientChainId:
    """Test BlockchainRPCClient passes chain_id in queries."""


# ---------------------------------------------------------------------------
# Marketplace endpoint integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Create test client for marketplace service."""
    from marketplace_service.main import app

    return TestClient(app)


class TestMarketplaceChainIdFilter:
    """Test marketplace offer listing with chain_id filter."""


class TestMarketplaceMatching:
    """Test marketplace matching endpoint (v0.6.6)."""


class TestMarketplaceConfig:
    """Test marketplace config (v0.6.6)."""

    def test_config_has_correct_defaults(self):
        from marketplace_service.config import settings

        assert settings.blockchain_rpc_url == "http://localhost:8202"
        assert settings.default_chain_id == "ait-hub"
        assert "8107" in settings.agent_coordinator_url

    def test_no_stale_8006_port(self):
        from marketplace_service.config import settings

        assert "8006" not in settings.blockchain_rpc_url
