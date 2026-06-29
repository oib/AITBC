"""Integration tests for v0.6.7 Pool Hub reward distribution features.

Tests cover:
- Reward policy constants exported from aitbc.rewards
- PoolHubBlockchainClient initialization and chain_id
- Pool-hub settings (blockchain_rpc_url, default_chain_id, agent_coordinator_url, reward flag)
- MinerInfo dataclass with chain_id and wallet_address fields
- RewardPayout model existence and fields
- Submit reward transaction (mocked BlockchainRPCClient)
- Register miner on-chain (mocked)
- Distribute rewards (mocked)
- Distribute rewards skips ineligible miners
- Distribute rewards handles errors gracefully
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Set required env var before importing poolhub settings
os.environ.setdefault("POOLHUB_COORDINATOR_SHARED_SECRET", "test-secret")

# Add src directories to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ---------------------------------------------------------------------------
# Reward policy constants tests
# ---------------------------------------------------------------------------


class TestRewardPolicyConstants:
    """Test reward policy constants are exported from aitbc.rewards."""

    def test_reward_policy_constants_exist(self):
        from aitbc.rewards import (
            BASE_BLOCK_REWARD,
            HALVING_INTERVAL,
            MAX_REWARD_PER_EPOCH,
            MINIMUM_PAYOUT,
            REWARD_EPOCH_LENGTH,
            REWARD_PER_SHARE,
        )

        assert REWARD_PER_SHARE == 1000
        assert HALVING_INTERVAL == 210_000
        assert REWARD_EPOCH_LENGTH == 1_000
        assert MAX_REWARD_PER_EPOCH == 100_000
        assert MINIMUM_PAYOUT == 3_600
        assert BASE_BLOCK_REWARD == 50_000

    def test_reward_policy_class_exists(self):
        from aitbc.rewards import RewardPolicy

        policy = RewardPolicy()
        assert policy.current_epoch_number == 0

    def test_reward_epoch_class_exists(self):
        from aitbc.rewards import RewardEpoch

        epoch = RewardEpoch(epoch_number=0, block_start=0, block_end=1000)
        assert epoch.epoch_number == 0
        assert epoch.total_shares == 0


# ---------------------------------------------------------------------------
# PoolHubBlockchainClient tests
# ---------------------------------------------------------------------------


class TestPoolHubBlockchainClient:
    """Test PoolHubBlockchainClient (v0.6.7)."""

    def test_client_init_defaults(self):
        from poolhub.clients.blockchain import PoolHubBlockchainClient

        client = PoolHubBlockchainClient()
        assert client.chain_id == "ait-hub"
        assert "8202" in client.rpc_client.rpc_url

    def test_client_init_custom(self):
        from poolhub.clients.blockchain import PoolHubBlockchainClient

        client = PoolHubBlockchainClient(
            rpc_url="http://node.example:9000",
            chain_id="test-chain",
            coordinator_url="http://coordinator:8107",
        )
        assert client.chain_id == "test-chain"
        assert "9000" in client.rpc_client.rpc_url

    def test_client_has_reward_policy(self):
        from poolhub.clients.blockchain import PoolHubBlockchainClient

        client = PoolHubBlockchainClient()
        assert client.reward_policy is not None
        assert client.reward_policy.current_epoch_number == 0

    @pytest.mark.asyncio
    async def test_submit_reward_transaction_mock(self):
        from poolhub.clients.blockchain import PoolHubBlockchainClient

        client = PoolHubBlockchainClient()

        mock_response = {"tx_hash": "abc123", "status": "accepted"}
        with patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock, return_value=mock_response):
            result = await client.submit_reward_transaction(miner_address="0xminer1", amount=1000, job_id="job-001")

        assert result["tx_hash"] == "abc123"

    @pytest.mark.asyncio
    async def test_register_miner_on_chain_mock(self):
        from poolhub.clients.blockchain import PoolHubBlockchainClient

        client = PoolHubBlockchainClient()

        mock_response = {"gpu_id": "miner-1", "status": "registered"}
        with patch.object(client._rpc, "register_gpu", new_callable=AsyncMock, return_value=mock_response):
            result = await client.register_miner_on_chain(
                miner_id="miner-1",
                gpu_info={"model": "RTX 4090", "memory_gb": 24},
                address="0xminer1",
            )

        assert result["gpu_id"] == "miner-1"

    @pytest.mark.asyncio
    async def test_distribute_rewards_mock(self):
        from poolhub.clients.blockchain import PoolHubBlockchainClient

        client = PoolHubBlockchainClient()
        # Record contributions for two miners
        client.record_contribution("miner-1", score=90.0, shares=5000)
        client.record_contribution("miner-2", score=80.0, shares=3000)

        mock_response = {"tx_hash": "tx-abc", "status": "accepted"}
        with patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock, return_value=mock_response):
            payouts = await client.distribute_rewards(block_height=100)

        assert len(payouts) == 2
        assert all(p["tx_hash"] == "tx-abc" for p in payouts)

    @pytest.mark.asyncio
    async def test_distribute_rewards_skips_ineligible(self):
        from poolhub.clients.blockchain import PoolHubBlockchainClient

        client = PoolHubBlockchainClient()
        # Record contribution for one miner
        client.record_contribution("miner-1", score=90.0, shares=5000)

        # Mark the miner as paid (makes them ineligible)
        client.reward_policy.mark_paid("miner-1", "existing-tx")

        mock_response = {"tx_hash": "tx-new", "status": "accepted"}
        with patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock, return_value=mock_response):
            payouts = await client.distribute_rewards(block_height=100)

        # Miner-1 was already paid, so no new payouts
        assert len(payouts) == 0

    @pytest.mark.asyncio
    async def test_distribute_rewards_handles_errors(self):
        from poolhub.clients.blockchain import PoolHubBlockchainClient

        client = PoolHubBlockchainClient()
        client.record_contribution("miner-1", score=90.0, shares=5000)

        with patch.object(client._rpc, "submit_transaction", new_callable=AsyncMock, side_effect=Exception("Network error")):
            payouts = await client.distribute_rewards(block_height=100)

        # Should not crash — should record the error
        assert len(payouts) == 1
        assert "error" in payouts[0]
        assert "Network error" in payouts[0]["error"]


# ---------------------------------------------------------------------------
# Pool-hub settings tests
# ---------------------------------------------------------------------------


class TestPoolHubSettings:
    """Test pool-hub settings (v0.6.7)."""

    def test_settings_blockchain_rpc_url(self):
        from poolhub.settings import Settings

        settings = Settings()
        assert settings.blockchain_rpc_url == "http://localhost:8202"
        assert "8006" not in settings.blockchain_rpc_url

    def test_settings_default_chain_id(self):
        from poolhub.settings import Settings

        settings = Settings()
        assert settings.default_chain_id == "ait-hub"

    def test_settings_agent_coordinator_url(self):
        from poolhub.settings import Settings

        settings = Settings()
        assert "8107" in settings.agent_coordinator_url

    def test_settings_enable_reward_distribution(self):
        from poolhub.settings import Settings

        settings = Settings()
        assert settings.enable_reward_distribution is False

    def test_settings_reward_sync_interval_blocks(self):
        from poolhub.settings import Settings

        settings = Settings()
        assert settings.reward_sync_interval_blocks == 100


# ---------------------------------------------------------------------------
# MinerInfo dataclass tests
# ---------------------------------------------------------------------------


class TestMinerInfoFields:
    """Test MinerInfo dataclass has v0.6.7 fields."""

    def test_miner_info_has_chain_id(self):
        from app.registry.miner_registry import MinerInfo

        # Check the dataclass field exists
        import dataclasses

        fields = {f.name for f in dataclasses.fields(MinerInfo)}
        assert "chain_id" in fields

    def test_miner_info_has_wallet_address(self):
        from app.registry.miner_registry import MinerInfo

        import dataclasses

        fields = {f.name for f in dataclasses.fields(MinerInfo)}
        assert "wallet_address" in fields

    def test_miner_info_chain_id_default(self):
        from app.registry.miner_registry import MinerInfo

        miner = MinerInfo(
            miner_id="m1",
            pool_id="p1",
            capabilities=["llm"],
            gpu_info={},
            endpoint=None,
            max_concurrent_jobs=1,
        )
        assert miner.chain_id == "ait-hub"
        assert miner.wallet_address is None


# ---------------------------------------------------------------------------
# RewardPayout model tests
# ---------------------------------------------------------------------------


class TestRewardPayoutModel:
    """Test RewardPayout SQLModel (v0.6.7)."""

    def test_reward_payout_model_exists(self):
        from poolhub.models import RewardPayout

        assert RewardPayout is not None
        assert RewardPayout.__tablename__ == "reward_payouts"

    def test_reward_payout_has_chain_id(self):
        from poolhub.models import RewardPayout

        assert "chain_id" in RewardPayout.__table__.columns
        assert RewardPayout.__table__.columns["chain_id"].index

    def test_reward_payout_has_epoch_number(self):
        from poolhub.models import RewardPayout

        assert "epoch_number" in RewardPayout.__table__.columns
        assert RewardPayout.__table__.columns["epoch_number"].index

    def test_reward_payout_has_miner_id(self):
        from poolhub.models import RewardPayout

        assert "miner_id" in RewardPayout.__table__.columns
        assert RewardPayout.__table__.columns["miner_id"].index

    def test_reward_payout_has_tx_hash(self):
        from poolhub.models import RewardPayout

        assert "tx_hash" in RewardPayout.__table__.columns

    def test_miner_model_has_chain_id(self):
        from poolhub.models import Miner

        assert "chain_id" in Miner.__table__.columns
        assert Miner.__table__.columns["chain_id"].index

    def test_miner_model_has_wallet_address(self):
        from poolhub.models import Miner

        assert "wallet_address" in Miner.__table__.columns
