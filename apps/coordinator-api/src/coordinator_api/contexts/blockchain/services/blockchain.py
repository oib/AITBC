"""
Blockchain service for token operations
"""

import re
from decimal import Decimal
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError
from aitbc.network import AITBCHTTPClient

from ....config import settings

logger = get_logger(__name__)

# Blockchain node RPC — default to the canonical port 8202 (see apps/blockchain-node/src/aitbc_chain/main.py).
# Overridable via settings.blockchain_rpc_url.
BLOCKCHAIN_RPC = settings.blockchain_rpc_url

# Basic validation for blockchain addresses (alphanumeric, common prefixes)
ADDRESS_PATTERN = re.compile(r"^[a-zA-Z0-9]{20,50}$")


class BlockchainService:
    """Blockchain service for staking router — fires background RPC calls to the chain node."""

    def __init__(self) -> None:
        self.rpc_url = BLOCKCHAIN_RPC

    async def create_stake_contract(
        self,
        stake_id: str,
        agent_wallet: str,
        amount: Decimal,
        lock_period: int,
        auto_compound: bool,
    ) -> None:
        """Record a stake on-chain (background task, best-effort)."""
        client = AITBCHTTPClient(timeout=10.0)
        try:
            client.post(
                f"{self.rpc_url}/staking/stake",
                json={
                    "stake_id": stake_id,
                    "agent_wallet": agent_wallet,
                    "amount": str(amount),
                    "lock_period": lock_period,
                    "auto_compound": auto_compound,
                },
                headers={"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""},
            )
            logger.info("Stake contract created on-chain for %s", stake_id)
        except NetworkError as e:
            logger.error("Failed to create stake contract on-chain for %s: %s", stake_id, e)

    async def update_agent_performance(self, agent_wallet: str, accuracy: Decimal, successful: bool) -> None:
        """Record agent performance update on-chain (background task, best-effort)."""
        client = AITBCHTTPClient(timeout=10.0)
        try:
            client.post(
                f"{self.rpc_url}/staking/performance",
                json={"agent_wallet": agent_wallet, "accuracy": str(accuracy), "successful": successful},
                headers={"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""},
            )
            logger.info("Agent performance updated on-chain for %s", agent_wallet)
        except NetworkError as e:
            logger.error("Failed to update agent performance on-chain for %s: %s", agent_wallet, e)

    async def add_to_stake(self, stake_id: str, additional_amount: Decimal) -> None:
        """Add tokens to an existing stake on-chain (background task, best-effort)."""
        client = AITBCHTTPClient(timeout=10.0)
        try:
            client.post(
                f"{self.rpc_url}/staking/stake/{stake_id}/add",
                json={"stake_id": stake_id, "additional_amount": str(additional_amount)},
                headers={"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""},
            )
            logger.info("Added %s to stake %s on-chain", additional_amount, stake_id)
        except NetworkError as e:
            logger.error("Failed to add to stake %s on-chain: %s", stake_id, e)

    async def unbond_stake(self, stake_id: str) -> None:
        """Initiate unbonding for a stake on-chain (background task, best-effort)."""
        client = AITBCHTTPClient(timeout=10.0)
        try:
            client.post(
                f"{self.rpc_url}/staking/stake/{stake_id}/unbond",
                json={"stake_id": stake_id},
                headers={"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""},
            )
            logger.info("Unbonding initiated for stake %s on-chain", stake_id)
        except NetworkError as e:
            logger.error("Failed to unbond stake %s on-chain: %s", stake_id, e)

    async def complete_unbonding(self, stake_id: str) -> None:
        """Complete unbonding for a stake on-chain (background task, best-effort)."""
        client = AITBCHTTPClient(timeout=10.0)
        try:
            client.post(
                f"{self.rpc_url}/staking/stake/{stake_id}/complete",
                json={"stake_id": stake_id},
                headers={"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""},
            )
            logger.info("Unbonding completed for stake %s on-chain", stake_id)
        except NetworkError as e:
            logger.error("Failed to complete unbonding for stake %s on-chain: %s", stake_id, e)

    async def distribute_earnings(self, agent_wallet: str, total_earnings: Decimal) -> None:
        """Distribute agent earnings to stakers on-chain (background task, best-effort)."""
        client = AITBCHTTPClient(timeout=10.0)
        try:
            client.post(
                f"{self.rpc_url}/staking/agents/{agent_wallet}/distribute",
                json={"agent_wallet": agent_wallet, "total_earnings": str(total_earnings)},
                headers={"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""},
            )
            logger.info("Distributed %s earnings for agent %s on-chain", total_earnings, agent_wallet)
        except NetworkError as e:
            logger.error("Failed to distribute earnings for agent %s on-chain: %s", agent_wallet, e)

    async def claim_rewards(self, stake_ids: list[str]) -> None:
        """Claim accumulated rewards for multiple stakes on-chain (background task, best-effort)."""
        client = AITBCHTTPClient(timeout=10.0)
        try:
            client.post(
                f"{self.rpc_url}/staking/claim-rewards",
                json={"stake_ids": stake_ids},
                headers={"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""},
            )
            logger.info("Claimed rewards for %d stakes on-chain", len(stake_ids))
        except NetworkError as e:
            logger.error("Failed to claim rewards on-chain: %s", e)

    async def deploy_bounty_contract(self, bounty_id: str, reward_amount: Decimal | Any, tier: Any, deadline: Any) -> None:
        """Deploy a bounty contract on-chain (background task, best-effort)."""
        client = AITBCHTTPClient(timeout=10.0)
        try:
            client.post(
                f"{self.rpc_url}/bounty/deploy",
                json={
                    "bounty_id": bounty_id,
                    "reward_amount": reward_amount,
                    "tier": str(tier),
                    "deadline": deadline.isoformat() if hasattr(deadline, "isoformat") else str(deadline),
                },
                headers={"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""},
            )
            logger.info("Bounty contract deployed on-chain for %s", bounty_id)
        except NetworkError as e:
            logger.error("Failed to deploy bounty contract %s on-chain: %s", bounty_id, e)

    async def submit_bounty_solution(
        self,
        bounty_id: str,
        submission_id: str,
        zk_proof: dict[str, Any] | None,
        performance_hash: str,
        accuracy: float,
        response_time: int | None,
    ) -> None:
        """Submit a bounty solution on-chain (background task, best-effort)."""
        client = AITBCHTTPClient(timeout=10.0)
        try:
            client.post(
                f"{self.rpc_url}/bounty/{bounty_id}/submit",
                json={
                    "submission_id": submission_id,
                    "zk_proof": zk_proof,
                    "performance_hash": performance_hash,
                    "accuracy": accuracy,
                    "response_time": response_time,
                },
                headers={"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""},
            )
            logger.info("Bounty solution submitted on-chain for %s/%s", bounty_id, submission_id)
        except NetworkError as e:
            logger.error("Failed to submit bounty solution %s on-chain: %s", submission_id, e)

    async def verify_submission(self, bounty_id: str, submission_id: str, verified: bool, verifier_address: str) -> None:
        """Verify a bounty submission on-chain (background task, best-effort)."""
        client = AITBCHTTPClient(timeout=10.0)
        try:
            client.post(
                f"{self.rpc_url}/bounty/{bounty_id}/verify",
                json={
                    "submission_id": submission_id,
                    "verified": verified,
                    "verifier_address": verifier_address,
                },
                headers={"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""},
            )
            logger.info("Bounty submission verified on-chain for %s/%s", bounty_id, submission_id)
        except NetworkError as e:
            logger.error("Failed to verify submission %s on-chain: %s", submission_id, e)

    async def dispute_submission(self, bounty_id: str, submission_id: str, disputer_address: str, dispute_reason: str) -> None:
        """Record a submission dispute on-chain (background task, best-effort)."""
        client = AITBCHTTPClient(timeout=10.0)
        try:
            client.post(
                f"{self.rpc_url}/bounty/{bounty_id}/dispute",
                json={
                    "submission_id": submission_id,
                    "disputer_address": disputer_address,
                    "dispute_reason": dispute_reason,
                },
                headers={"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""},
            )
            logger.info("Bounty submission disputed on-chain for %s/%s", bounty_id, submission_id)
        except NetworkError as e:
            logger.error("Failed to dispute submission %s on-chain: %s", submission_id, e)

    async def expire_bounty(self, bounty_id: str) -> None:
        """Expire a bounty on-chain (background task, best-effort)."""
        client = AITBCHTTPClient(timeout=10.0)
        try:
            client.post(
                f"{self.rpc_url}/bounty/{bounty_id}/expire",
                json={"bounty_id": bounty_id},
                headers={"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""},
            )
            logger.info("Bounty expired on-chain for %s", bounty_id)
        except NetworkError as e:
            logger.error("Failed to expire bounty %s on-chain: %s", bounty_id, e)


def validate_address(address: str) -> bool:
    """Validate that address is safe to use in URL construction"""
    if not address:
        return False
    # Check for path traversal or URL manipulation
    if any(char in address for char in ["/", "\\", "..", "\n", "\r", "\t"]):
        return False
    # Check for URL-like patterns
    if address.startswith(("http://", "https://", "ftp://")):
        return False
    # Validate against address pattern
    return bool(ADDRESS_PATTERN.match(address))


async def mint_tokens(address: str, amount: Decimal) -> dict[str, Any]:
    """Mint tokens to an address"""

    client = AITBCHTTPClient(timeout=10.0)
    try:
        response = client.post(
            f"{BLOCKCHAIN_RPC}/admin/mintFaucet",
            json={"address": address, "amount": str(amount)},
            headers={"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""},
        )
        return response
    except NetworkError as e:
        raise Exception(f"Failed to mint tokens: {e}") from e


def get_balance(address: str) -> Decimal | None:
    """Get token balance for an address"""

    if not validate_address(address):
        logger.error("Invalid address format")
        return None

    try:
        client = AITBCHTTPClient(timeout=10.0)
        try:
            response = client.get(
                f"{BLOCKCHAIN_RPC}/getBalance/{address}",
                headers={"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""},
            )
            return Decimal(str(response.get("balance", 0)))
        except NetworkError as e:
            logger.error("Error getting balance: %s", e)
            return None
    except Exception as e:
        logger.error("Error getting balance: %s", e)
        return None
