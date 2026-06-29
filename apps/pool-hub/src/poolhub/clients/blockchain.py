"""Blockchain client for pool-hub reward distribution (v0.6.7 §B2).

Wraps BlockchainRPCClient (from v0.6.6) with pool-hub-specific logic:
- Submit reward transactions on job completion
- Register miners on blockchain via GPU registration endpoint
- Track reward payouts to prevent duplicates via RewardPolicy
"""

from __future__ import annotations

import logging
from typing import Any

from aitbc.marketplace import BlockchainRPCClient
from aitbc.rewards import REWARD_PER_SHARE, RewardPolicy

logger = logging.getLogger(__name__)


class PoolHubBlockchainClient:
    """Blockchain client for pool-hub reward distribution and miner registration.

    Wraps BlockchainRPCClient (from v0.6.6) with pool-hub-specific logic:
    - Submit reward transactions on job completion
    - Register miners on blockchain via agent-coordinator
    - Track reward payouts to prevent duplicates
    """

    def __init__(
        self,
        rpc_url: str = "http://localhost:8202",
        chain_id: str = "ait-hub",
        coordinator_url: str = "http://localhost:8107",
    ) -> None:
        self._rpc = BlockchainRPCClient(rpc_url=rpc_url)
        self._chain_id = chain_id
        self._coordinator_url = coordinator_url
        self._reward_policy = RewardPolicy()

    @property
    def chain_id(self) -> str:
        return self._chain_id

    @property
    def reward_policy(self) -> RewardPolicy:
        return self._reward_policy

    @property
    def rpc_client(self) -> BlockchainRPCClient:
        return self._rpc

    async def submit_reward_transaction(self, miner_address: str, amount: int, job_id: str) -> dict[str, Any]:
        """Submit a reward transaction to the blockchain.

        Args:
            miner_address: Miner's wallet address (recipient)
            amount: Reward amount in compute-seconds (smallest unit)
            job_id: Job ID for tracking (included in payload)

        Returns:
            Blockchain response dict with tx_hash
        """
        tx_data = {
            "chain_id": self._chain_id,
            "from": "genesis",  # pool operator / genesis account
            "to": miner_address,
            "amount": amount,
            "type": "TRANSFER",
            "payload": {"purpose": "mining_reward", "job_id": job_id},
            "signature": "",  # will be signed by blockchain node or TransactionService
        }
        # Note: In production, this would be signed by the pool operator's key
        # using TransactionService.generate_signed_transaction(). For v0.6.7,
        # we submit unsigned transactions (the blockchain node may reject them
        # unless running in test mode). The signing integration is deferred to
        # v0.7.1 (Bridge Security).
        result = await self._rpc.submit_transaction(tx_data)
        logger.info("Reward tx submitted: miner=%s, amount=%d, job=%s", miner_address, amount, job_id)
        return result

    async def register_miner_on_chain(self, miner_id: str, gpu_info: dict[str, Any], address: str) -> dict[str, Any]:
        """Register a miner on the blockchain via GPU registration endpoint.

        Args:
            miner_id: Miner ID
            gpu_info: GPU specifications (model, memory, etc.)
            address: Miner's wallet address

        Returns:
            Blockchain response dict
        """
        registration_data = {
            "chain_id": self._chain_id,
            "gpu_id": miner_id,
            "miner_id": address,
            "model": gpu_info.get("model", "Unknown"),
            "memory_gb": gpu_info.get("memory_gb", 0),
            "region": gpu_info.get("region", ""),
            "registered_by": address,
        }
        result = await self._rpc.register_gpu(registration_data)
        logger.info("Miner registered on-chain: miner_id=%s, chain=%s", miner_id, self._chain_id)
        return result

    async def distribute_rewards(self, block_height: int) -> list[dict[str, Any]]:
        """Distribute rewards for the current epoch.

        Args:
            block_height: Current block height

        Returns:
            List of payout results (one per miner)
        """
        self._reward_policy.update_block_height(block_height)
        epoch = self._reward_policy.calculate_payouts()
        unpaid = self._reward_policy.get_unpaid_miners()

        payouts: list[dict[str, Any]] = []
        for contrib in unpaid:
            if not self._reward_policy.is_eligible_for_payout(contrib.miner_id):
                continue
            try:
                result = await self.submit_reward_transaction(
                    miner_address=contrib.miner_id,
                    amount=contrib.reward_amount,
                    job_id=f"epoch-{epoch.epoch_number}",
                )
                tx_hash = result.get("tx_hash", "")
                self._reward_policy.mark_paid(contrib.miner_id, tx_hash)
                payouts.append(
                    {
                        "miner_id": contrib.miner_id,
                        "amount": contrib.reward_amount,
                        "tx_hash": tx_hash,
                        "epoch": epoch.epoch_number,
                    }
                )
            except Exception as e:
                logger.error("Failed to distribute reward to %s: %s", contrib.miner_id, e)
                payouts.append(
                    {
                        "miner_id": contrib.miner_id,
                        "amount": contrib.reward_amount,
                        "error": str(e),
                        "epoch": epoch.epoch_number,
                    }
                )
        return payouts

    def record_contribution(self, miner_id: str, score: float, shares: int | None = None) -> None:
        """Record a miner's contribution for the current epoch.

        Args:
            miner_id: Miner ID
            score: Contribution score (0-100)
            shares: Compute-seconds contributed (defaults to REWARD_PER_SHARE)
        """
        self._reward_policy.record_contribution(
            miner_id=miner_id,
            score=score,
            shares=shares if shares is not None else REWARD_PER_SHARE,
        )
