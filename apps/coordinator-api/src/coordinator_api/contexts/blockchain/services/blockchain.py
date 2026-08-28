"""Blockchain service for agent-economy operations.

V23-42: the old module sent paths that the node did not serve. The new surface is
``/rpc/agent-staking/*`` and ``/rpc/bounty/*`` and requires a hub operator key.
Every public method now awaits the chain call, raises on failure, and returns the
chain response so routers can decide whether to persist state.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError
from aitbc.network import AITBCHTTPClient
from aitbc.utils.units import ait_to_units

from ....config import settings

logger = get_logger(__name__)

BLOCKCHAIN_RPC = settings.blockchain_rpc_url
RPC = f"{BLOCKCHAIN_RPC}/rpc"

ADDRESS_PATTERN = re.compile(r"^[a-zA-Z0-9]{20,50}$")


def _canonical_sign_payload(payload: dict[str, Any]) -> bytes:
    """Canonical JSON that the node's ``verify_request_signature`` expects."""
    clean = {k: v for k, v in payload.items() if k != "signature"}
    return json.dumps(clean, sort_keys=True, separators=(",", ":")).encode()


def _sign_payload(payload: dict[str, Any]) -> str:
    """Sign with the configured agent-economics operator key."""
    if not settings.agent_economics_operator_key:
        raise RuntimeError("AGENT_ECONOMICS_OPERATOR_KEY is not configured")
    from eth_keys import keys
    from eth_utils import keccak

    message = _canonical_sign_payload(payload)
    pk_hex = settings.agent_economics_operator_key.removeprefix("0x")
    pk = keys.PrivateKey(bytes.fromhex(pk_hex))
    msg_hash = keccak(message)
    return pk.sign_msg_hash(msg_hash).to_hex()


class BlockchainService:
    """Agent-economics chain client."""

    def __init__(self) -> None:
        pass

    def _client(self) -> AITBCHTTPClient:
        return AITBCHTTPClient(timeout=10.0)

    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""}

    def _signed(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload["signature"] = _sign_payload(payload)
        return payload

    async def create_stake_contract(
        self,
        stake_id: str,
        staker_address: str,
        agent_wallet: str,
        amount: Decimal,
        lock_period: int,
    ) -> dict[str, Any]:
        """Lock an agent stake on-chain."""
        payload = self._signed(
            {
                "stake_id": stake_id,
                "user_address": staker_address,
                "agent_wallet": agent_wallet,
                "amount": ait_to_units(amount),
                "lock_period": lock_period,
            }
        )
        return self._client().post(f"{RPC}/agent-staking/stake", json=payload, headers=self._headers())

    async def add_to_stake(self, stake_id: str, staker_address: str, additional_amount: Decimal) -> dict[str, Any]:
        payload = self._signed(
            {
                "stake_id": stake_id,
                "user_address": staker_address,
                "additional_amount": ait_to_units(additional_amount),
            }
        )
        return self._client().post(f"{RPC}/agent-staking/stake/{stake_id}/add", json=payload, headers=self._headers())

    async def unbond_stake(self, stake_id: str, staker_address: str) -> dict[str, Any]:
        payload = self._signed({"stake_id": stake_id, "user_address": staker_address})
        return self._client().post(f"{RPC}/agent-staking/stake/{stake_id}/unbond", json=payload, headers=self._headers())

    async def complete_unbonding(self, stake_id: str, staker_address: str) -> dict[str, Any]:
        payload = self._signed({"stake_id": stake_id, "user_address": staker_address})
        return self._client().post(f"{RPC}/agent-staking/stake/{stake_id}/complete", json=payload, headers=self._headers())

    async def update_agent_performance(self, agent_wallet: str, accuracy: Decimal, successful: bool) -> dict[str, Any]:
        payload = self._signed({"agent_wallet": agent_wallet, "accuracy": str(accuracy), "successful": successful})
        return self._client().post(f"{RPC}/agent-staking/performance", json=payload, headers=self._headers())

    async def distribute_earnings(self, agent_wallet: str, total_earnings: Decimal) -> dict[str, Any]:
        payload = self._signed({"agent_wallet": agent_wallet, "total_earnings": str(total_earnings)})
        return self._client().post(
            f"{RPC}/agent-staking/agents/{agent_wallet}/distribute", json=payload, headers=self._headers()
        )

    async def claim_rewards(self, stake_ids: list[str]) -> dict[str, Any]:
        payload = self._signed({"stake_ids": stake_ids})
        return self._client().post(f"{RPC}/agent-staking/claim-rewards", json=payload, headers=self._headers())

    async def deploy_bounty_contract(self, bounty_id: str, creator_address: str, reward_amount: Decimal) -> dict[str, Any]:
        payload = self._signed(
            {
                "bounty_id": bounty_id,
                "user_address": creator_address,
                "reward_amount": ait_to_units(reward_amount),
            }
        )
        return self._client().post(f"{RPC}/bounty/deploy", json=payload, headers=self._headers())

    async def submit_bounty_solution(
        self,
        bounty_id: str,
        submission_id: str,
        submitter_address: str,
        zk_proof: dict[str, Any] | None,
        performance_hash: str,
        accuracy: float,
        response_time: int | None,
    ) -> dict[str, Any]:
        payload = self._signed(
            {
                "submission_id": submission_id,
                "user_address": submitter_address,
                "zk_proof": zk_proof,
                "performance_hash": performance_hash,
                "accuracy": accuracy,
                "response_time": response_time,
            }
        )
        return self._client().post(f"{RPC}/bounty/{bounty_id}/submit", json=payload, headers=self._headers())

    async def verify_submission(
        self, bounty_id: str, submission_id: str, verified: bool, winner_address: str
    ) -> dict[str, Any]:
        payload = self._signed(
            {
                "submission_id": submission_id,
                "verified": verified,
                "user_address": winner_address,
            }
        )
        return self._client().post(f"{RPC}/bounty/{bounty_id}/verify", json=payload, headers=self._headers())

    async def dispute_submission(
        self, bounty_id: str, submission_id: str, disputer_address: str, dispute_reason: str
    ) -> dict[str, Any]:
        payload = self._signed(
            {
                "submission_id": submission_id,
                "user_address": disputer_address,
                "dispute_reason": dispute_reason,
            }
        )
        return self._client().post(f"{RPC}/bounty/{bounty_id}/dispute", json=payload, headers=self._headers())

    async def expire_bounty(self, bounty_id: str, creator_address: str) -> dict[str, Any]:
        payload = self._signed({"bounty_id": bounty_id, "user_address": creator_address})
        return self._client().post(f"{RPC}/bounty/{bounty_id}/expire", json=payload, headers=self._headers())


def validate_address(address: str) -> bool:
    if not address:
        return False
    if any(char in address for char in ["/", "\\", "..", "\n", "\r", "\t"]):
        return False
    if address.startswith(("http://", "https://", "ftp://")):
        return False
    return bool(ADDRESS_PATTERN.match(address))


async def mint_tokens(address: str, amount: Decimal) -> dict[str, Any]:
    """Not implemented. See V23-42.

    The old implementation POSTed ``/admin/mintFaucet``, which does not exist on the node.
    Developer platform routes now return 501 for this path.
    """
    raise NotImplementedError(
        "No mint endpoint exists on the blockchain node. Reward payout needs a real on-chain "
        "distribution path with verification, not the devnet faucet — see V23-42."
    )


def get_balance(address: str) -> Decimal | None:
    from aitbc.utils.units import units_to_ait

    if not validate_address(address):
        logger.error("Invalid address format")
        return None
    try:
        client = AITBCHTTPClient(timeout=10.0)
        response = client.get(
            f"{RPC}/balance/{address}",
            headers={"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""},
        )
        return units_to_ait(response.get("available_balance", 0))
    except NetworkError as e:
        logger.error("Error getting balance: %s", e)
        return None
    except Exception as e:
        logger.error("Error getting balance: %s", e)
        return None
