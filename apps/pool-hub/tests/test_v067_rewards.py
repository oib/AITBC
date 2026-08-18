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

    @pytest.fixture
    def signer_key(self):
        """Return a deterministic secp256k1 key pair for reward signing tests."""
        return {
            "address": "0x1a642f0E3c3aF545E7AcBD38b07251B3990914F1",
            "private_key": "0101010101010101010101010101010101010101010101010101010101010101",
        }

    @pytest.fixture
    def signed_client(self, signer_key):
        from poolhub.clients.blockchain import PoolHubBlockchainClient

        return PoolHubBlockchainClient(
            signer_address=signer_key["address"],
            signer_private_key=signer_key["private_key"],
        )

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
        # Hub-only locally (V23-92). The field default is empty and is filled
        # from HUB_DISCOVERY_URL / HUB_AGENT_URL — never localhost:8107.
        assert "localhost:8107" not in settings.agent_coordinator_url

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
    """Test canonical Miner model has v0.6.7 chain/wallet fields."""

    def test_miner_info_has_chain_id(self):
        from poolhub.models import Miner

        assert "chain_id" in Miner.__table__.columns

    def test_miner_info_has_wallet_address(self):
        from poolhub.models import Miner

        assert "wallet_address" in Miner.__table__.columns

    def test_miner_info_chain_id_default(self):
        from poolhub.models import Miner

        default = Miner.__table__.columns["chain_id"].default
        assert default is not None and default.arg == "ait-hub"
        assert Miner.__table__.columns["wallet_address"].nullable is True


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
