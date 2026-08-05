"""Blockchain client for pool-hub reward distribution (v0.6.7 §B2).

Wraps BlockchainRPCClient (from v0.6.6) with pool-hub-specific logic:
- Submit reward transactions on job completion
- Register miners on blockchain via GPU registration endpoint
- Track reward payouts to prevent duplicates via RewardPolicy

Reward transactions are signed with secp256k1 (Ethereum-style) over the
canonical JSON of the signed fields, matching the blockchain node's verifier
(see ``aitbc.crypto.transaction_service``).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aitbc.constants import BLOCKCHAIN_RPC_URL
from aitbc.marketplace import BlockchainRPCClient
from aitbc.rewards import REWARD_PER_SHARE, RewardPolicy

from ..models import RewardPayout

logger = logging.getLogger(__name__)

# Transaction fields covered by the signature — must match the node verifier.
_SIGNED_FIELDS = ("from", "to", "amount", "fee", "nonce", "payload", "type", "chain_id")


def _canonical_signing_message(tx: dict[str, Any]) -> bytes:
    """Return the exact bytes that are hashed and signed for a transaction."""
    signed = {k: tx[k] for k in _SIGNED_FIELDS if k in tx}
    return json.dumps(signed, sort_keys=True, separators=(",", ":")).encode()


class PoolHubBlockchainClient:
    """Blockchain client for pool-hub reward distribution and miner registration.

    Wraps BlockchainRPCClient (from v0.6.6) with pool-hub-specific logic:
    - Submit reward transactions on job completion
    - Register miners on blockchain via agent-coordinator
    - Track reward payouts to prevent duplicates
    """

    def __init__(
        self,
        rpc_url: str = BLOCKCHAIN_RPC_URL,
        chain_id: str = "ait-hub",
        coordinator_url: str = "http://localhost:8107",
        signer_address: str | None = None,
        signer_private_key: str | None = None,
    ) -> None:
        self._rpc = BlockchainRPCClient(rpc_url=rpc_url)
        self._chain_id = chain_id
        self._coordinator_url = coordinator_url
        self._reward_policy = RewardPolicy()
        self._signer_address = signer_address or os.getenv("POOL_REWARD_ADDRESS")
        self._signer_private_key = signer_private_key or os.getenv("POOL_REWARD_PRIVATE_KEY")

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
        """Submit a signed reward transaction to the blockchain.

        Args:
            miner_address: Miner's wallet address (recipient)
            amount: Reward amount in compute-seconds (smallest unit)
            job_id: Job ID for tracking (included in payload)

        Returns:
            Blockchain response dict with tx_hash

        Raises:
            ValueError: If reward signer key/address is not configured or mismatched.
        """
        if not self._signer_private_key or not self._signer_address:
            raise ValueError("Reward signer not configured; set POOL_REWARD_PRIVATE_KEY and POOL_REWARD_ADDRESS")

        from eth_keys import keys
        from eth_utils import keccak

        pk = keys.PrivateKey(bytes.fromhex(self._signer_private_key.removeprefix("0x")))
        derived_address = pk.public_key.to_checksum_address()
        if self._signer_address.lower() != derived_address.lower():
            raise ValueError(
                f"POOL_REWARD_ADDRESS {self._signer_address} does not match address derived from key ({derived_address})"
            )

        # Canonical tx includes the mining-reward payload; payload is part of the signed fields.
        tx_data: dict[str, Any] = {
            "from": self._signer_address,
            "to": miner_address,
            "amount": amount,
            "fee": 36,
            "nonce": await self._rpc.get_nonce(self._signer_address, self._chain_id),
            "payload": {"purpose": "mining_reward", "job_id": job_id},
            "type": "TRANSFER",
            "chain_id": self._chain_id,
        }

        signature = pk.sign_msg_hash(keccak(_canonical_signing_message(tx_data)))
        tx_data["signature"] = signature.to_bytes().hex()

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

    async def distribute_rewards(self, block_height: int, session: AsyncSession | None = None) -> list[dict[str, Any]]:
        """Distribute rewards for the current epoch.

        Args:
            block_height: Current block height
            session: Optional async DB session. When provided, ``RewardPayout``
                records are checked before submission and persisted after, making
                the idempotency guarantee survive restarts and replicas.

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

            if session is not None:
                existing = await session.execute(
                    select(RewardPayout).where(
                        RewardPayout.miner_id == contrib.miner_id,
                        RewardPayout.epoch_number == epoch.epoch_number,
                        RewardPayout.chain_id == self._chain_id,
                    )
                )
                record = existing.scalar_one_or_none()
                if record is not None and record.status == "paid":
                    logger.info("Skipping already-paid reward for %s epoch %s", contrib.miner_id, epoch.epoch_number)
                    payouts.append(
                        {
                            "miner_id": contrib.miner_id,
                            "amount": contrib.reward_amount,
                            "tx_hash": record.tx_hash or "",
                            "epoch": epoch.epoch_number,
                            "status": "already_paid",
                        }
                    )
                    continue

            try:
                result = await self.submit_reward_transaction(
                    miner_address=contrib.miner_id,
                    amount=contrib.reward_amount,
                    job_id=f"epoch-{epoch.epoch_number}",
                )
                tx_hash = result.get("tx_hash", "")
                self._reward_policy.mark_paid(contrib.miner_id, tx_hash)

                if session is not None:
                    payout_record = RewardPayout(
                        miner_id=contrib.miner_id,
                        chain_id=self._chain_id,
                        epoch_number=epoch.epoch_number,
                        amount=contrib.reward_amount,
                        tx_hash=tx_hash,
                        status="paid",
                    )
                    session.add(payout_record)
                    await session.commit()  # type: ignore[misc, func-returns-value]

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
                if session is not None:
                    failed_record = RewardPayout(
                        miner_id=contrib.miner_id,
                        chain_id=self._chain_id,
                        epoch_number=epoch.epoch_number,
                        amount=contrib.reward_amount,
                        status="failed",
                    )
                    session.add(failed_record)
                    await session.commit()  # type: ignore[misc, func-returns-value]

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
