"""Blockchain service for token operations.

V23-42: this module's URLs were never checked against the node that serves them. The node
mounts its whole RPC surface under ``/rpc`` (``app.py``), and none of the paths below carried
that prefix, so every call here returned 404. Twelve of the fourteen have no counterpart on
the node under any prefix — the staking and bounty paths are near-copies of *this app's own*
route table pointed at the chain node's base URL.

The failures were invisible because the ``BlockchainService`` methods are fired from FastAPI
background tasks and catch ``NetworkError`` to a log line, so the caller had already received
its 200. ``tests/test_blockchain_client_paths.py`` now compares these URLs against the node's
real route table, so the gap cannot widen in silence.
"""

import re
from decimal import Decimal
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError
from aitbc.network import AITBCHTTPClient
from aitbc.utils import seconds_to_ait

from ....config import settings

logger = get_logger(__name__)

# Blockchain node RPC — default to the canonical port 8202 (see apps/blockchain-node/src/aitbc_chain/main.py).
# Overridable via settings.blockchain_rpc_url. The node mounts every RPC route under /rpc, so
# callers must include that prefix; settings.blockchain_rpc_url is the bare origin.
BLOCKCHAIN_RPC = settings.blockchain_rpc_url
RPC = f"{BLOCKCHAIN_RPC}/rpc"

# Basic validation for blockchain addresses (alphanumeric, common prefixes)
ADDRESS_PATTERN = re.compile(r"^[a-zA-Z0-9]{20,50}$")


class BlockchainService:
    """Blockchain service for staking/bounty routers — fires background RPC calls to the node.

    **None of the twelve endpoints below exists on the blockchain node.** They are not merely
    missing the ``/rpc`` prefix: ``/staking/stake`` is the only one with any counterpart at
    all (``POST /rpc/staking/stake``), and that one wants ``{address, amount, lock_days,
    signature}`` and rejects unsigned requests with 403 — this app has no access to an agent's
    staking key, so it cannot produce that signature. The rest, including every ``/bounty/*``
    path, have no counterpart under any prefix. They are near-copies of *this app's own*
    staking routes (``contexts/staking/routers/staking.py``) addressed to the node's host.

    The URLs are left as they are rather than given a ``/rpc`` prefix, because a prefix would
    imply they resolve. What is needed is either the endpoints on the node or the removal of
    these calls — a design decision, recorded as V23-42, not a rename.

    Every method here is a background task that catches ``NetworkError`` into a log line, so
    the router has already returned 200/201 by the time the call fails. A client that stakes
    or deploys a bounty is told it succeeded and nothing reaches the chain.
    """

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
    """Not implemented. There is no mint endpoint on the node, and the faucet is not one.

    This used to POST ``/admin/mintFaucet``, which has never existed on any node in this
    repository — only ``tests/fixtures/mock_blockchain_node.py`` served it, which is why the
    integration suite stayed green. The nearest real endpoint is ``POST /rpc/faucet``, a
    devnet faucet that mints from nothing, rate-limited to 10/hour and capped at 10M AIT.

    It is deliberately *not* wired up here. The only caller is
    ``DeveloperPlatformService.claim_rewards``, which pays out a hardcoded 45.75 and returns
    ``"0xmock_claim_tx_hash"``; pointing that at a working faucet would turn a broken fake
    into a functioning one that credits real chain balance to anyone who asks. The HTTP layer
    already refuses for exactly this reason — every route in
    ``developer_platform/routers/staking.py`` returns 501, noting "The current implementation
    mints tokens without verification". This raises so the service layer says the same thing.
    """
    raise NotImplementedError(
        "No mint endpoint exists on the blockchain node. Reward payout needs a real on-chain "
        "distribution path with verification, not the devnet faucet — see V23-42."
    )


def get_balance(address: str) -> Decimal | None:
    """Get an address's available balance, in AIT.

    Three separate mismatches, all in one call: the path lacked the node's ``/rpc`` prefix,
    the node calls the route ``balance`` rather than ``getBalance``, and its response has no
    ``balance`` key at all — it returns ``available_balance``/``staked``/``bridge_locked``/
    ``total_balance``, so ``response.get("balance", 0)`` would have reported every account as
    empty even from the right URL. The figures are compute-seconds, hence the conversion.
    """
    if not validate_address(address):
        logger.error("Invalid address format")
        return None

    try:
        client = AITBCHTTPClient(timeout=10.0)
        try:
            response = client.get(
                f"{RPC}/balance/{address}",
                headers={"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""},
            )
            return seconds_to_ait(response.get("available_balance", 0))
        except NetworkError as e:
            logger.error("Error getting balance: %s", e)
            return None
    except Exception as e:
        logger.error("Error getting balance: %s", e)
        return None
