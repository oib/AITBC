"""
Tests for BridgeManager settlement lifecycle and BlockchainService staking methods.

These are the methods added during v1.0.0 production readiness:
- BridgeManager.create_settlement / process_settlement / get_settlement / list_settlements / cancel_settlement
- BlockchainService.add_to_stake / unbond_stake / complete_unbonding / distribute_earnings / claim_rewards
"""

from unittest.mock import patch

import pytest

from coordinator_api.settlement.bridges.base import BridgeStatus
from coordinator_api.settlement.manager import BridgeManager
from coordinator_api.settlement.storage import InMemorySettlementStorage


@pytest.mark.unit
class TestBridgeManagerSettlementLifecycle:
    """Test the create → process → get → list → cancel lifecycle."""

    @pytest.fixture
    def manager(self) -> BridgeManager:
        storage = InMemorySettlementStorage()
        mgr = BridgeManager(storage)
        mgr._initialized = True  # bypass initialize() so we don't need real adapters
        return mgr

    async def test_create_settlement_returns_id_and_stores_pending(self, manager: BridgeManager) -> None:
        sid = await manager.create_settlement(
            source_chain_id="1000",
            target_chain_id="1001",
            amount=42.0,
            asset_type="AITBC",
            recipient_address="ait1abc",
        )
        assert isinstance(sid, str) and len(sid) > 0
        record = await manager.storage.get_settlement(sid)
        assert record is not None
        assert record["status"] == BridgeStatus.PENDING.value
        assert record["payment_amount"] == 42.0

    async def test_get_settlement_returns_namespace(self, manager: BridgeManager) -> None:
        sid = await manager.create_settlement(
            source_chain_id="1", target_chain_id="2", amount=10.0, asset_type="AITBC", recipient_address="r"
        )
        result = await manager.get_settlement(sid)
        assert result is not None
        assert result.status == BridgeStatus.PENDING.value

    async def test_get_settlement_returns_none_for_missing(self, manager: BridgeManager) -> None:
        assert await manager.get_settlement("nonexistent") is None

    async def test_list_settlements_paginates(self, manager: BridgeManager) -> None:
        for i in range(5):
            await manager.create_settlement(
                source_chain_id="1", target_chain_id="2", amount=float(i), asset_type="AITBC", recipient_address="r"
            )
        page1 = await manager.list_settlements(api_key="k", limit=2, offset=0)
        page2 = await manager.list_settlements(api_key="k", limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        assert page1[0]["payment_amount"] != page2[0]["payment_amount"]

    async def test_cancel_pending_settlement_succeeds(self, manager: BridgeManager) -> None:
        sid = await manager.create_settlement(
            source_chain_id="1", target_chain_id="2", amount=5.0, asset_type="AITBC", recipient_address="r"
        )
        cancelled = await manager.cancel_settlement(sid, user_id="u")
        assert cancelled is True
        record = await manager.storage.get_settlement(sid)
        assert record is not None
        assert record["status"] == BridgeStatus.FAILED.value

    async def test_cancel_missing_settlement_returns_false(self, manager: BridgeManager) -> None:
        assert await manager.cancel_settlement("nope", user_id="u") is False

    async def test_cancel_completed_settlement_returns_false(self, manager: BridgeManager) -> None:
        sid = await manager.create_settlement(
            source_chain_id="1", target_chain_id="2", amount=5.0, asset_type="AITBC", recipient_address="r"
        )
        await manager.storage.update_settlement(sid, status=BridgeStatus.COMPLETED)
        assert await manager.cancel_settlement(sid, user_id="u") is False

    async def test_process_settlement_no_bridges_marks_failed(self, manager: BridgeManager) -> None:
        # manager has no adapters registered
        sid = await manager.create_settlement(
            source_chain_id="1", target_chain_id="2", amount=5.0, asset_type="AITBC", recipient_address="r"
        )
        await manager.process_settlement(sid, user_id="u")
        record = await manager.storage.get_settlement(sid)
        assert record is not None
        assert record["status"] == BridgeStatus.FAILED.value
        assert "No bridges configured" in (record.get("error_message") or "")


@pytest.mark.unit
class TestBlockchainServiceStakingMethods:
    """V23-42: chain-first means the service now raises on chain failure.

    The operator key must be set, otherwise signing raises before the HTTP call.
    """

    @pytest.fixture(autouse=True)
    def _operator_key(self, monkeypatch):
        from coordinator_api.config import settings

        monkeypatch.setattr(settings, "agent_economics_operator_key", "0x" + "11" * 32)
        monkeypatch.setattr(settings, "agent_economics_operator_address", "0x" + "aa" * 20)

    async def test_add_to_stake_raises_network_error(self) -> None:
        from coordinator_api.contexts.blockchain.services.blockchain import BlockchainService
        from aitbc.exceptions import NetworkError

        svc = BlockchainService()
        with patch("coordinator_api.contexts.blockchain.services.blockchain.AITBCHTTPClient") as mock_client_cls:
            mock_client_cls.return_value.post.side_effect = NetworkError("connection refused")
            with pytest.raises(NetworkError):
                await svc.add_to_stake("stake_1", "0x" + "aa" * 20, 100.0)

    async def test_unbond_stake_raises_network_error(self) -> None:
        from coordinator_api.contexts.blockchain.services.blockchain import BlockchainService
        from aitbc.exceptions import NetworkError

        svc = BlockchainService()
        with patch("coordinator_api.contexts.blockchain.services.blockchain.AITBCHTTPClient") as mock_client_cls:
            mock_client_cls.return_value.post.side_effect = NetworkError("connection refused")
            with pytest.raises(NetworkError):
                await svc.unbond_stake("stake_1", "0x" + "aa" * 20)

    async def test_complete_unbonding_raises_network_error(self) -> None:
        from coordinator_api.contexts.blockchain.services.blockchain import BlockchainService
        from aitbc.exceptions import NetworkError

        svc = BlockchainService()
        with patch("coordinator_api.contexts.blockchain.services.blockchain.AITBCHTTPClient") as mock_client_cls:
            mock_client_cls.return_value.post.side_effect = NetworkError("connection refused")
            with pytest.raises(NetworkError):
                await svc.complete_unbonding("stake_1", "0x" + "aa" * 20)

    async def test_distribute_earnings_raises_network_error(self) -> None:
        from coordinator_api.contexts.blockchain.services.blockchain import BlockchainService
        from aitbc.exceptions import NetworkError

        svc = BlockchainService()
        with patch("coordinator_api.contexts.blockchain.services.blockchain.AITBCHTTPClient") as mock_client_cls:
            mock_client_cls.return_value.post.side_effect = NetworkError("connection refused")
            with pytest.raises(NetworkError):
                await svc.distribute_earnings("ait1agent", 500.0)

    async def test_claim_rewards_raises_network_error(self) -> None:
        from coordinator_api.contexts.blockchain.services.blockchain import BlockchainService
        from aitbc.exceptions import NetworkError

        svc = BlockchainService()
        with patch("coordinator_api.contexts.blockchain.services.blockchain.AITBCHTTPClient") as mock_client_cls:
            mock_client_cls.return_value.post.side_effect = NetworkError("connection refused")
            with pytest.raises(NetworkError):
                await svc.claim_rewards(["stake_1", "stake_2"])

    async def test_mint_tokens_is_awaitable(self) -> None:
        """Verify mint_tokens is an async function (the exchange.py bug was it wasn't awaited)."""
        from coordinator_api.contexts.blockchain.services.blockchain import mint_tokens

        import inspect

        assert inspect.iscoroutinefunction(mint_tokens)
