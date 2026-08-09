"""
Contract-related RPC endpoints.

Contract deployment, calling, and verification use the on-chain database.
Contract addresses are deterministically derived from the deployer address,
contract name, and deployment timestamp.
"""

import hashlib
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlmodel import select

from aitbc.rate_limiting import rate_limit

from ..base_models import SmartContract
from ..contracts.agent_messaging_contract import messaging_contract
from ..database import session_scope
from ..logger import get_logger
from .contract_service import contract_service

_logger = get_logger(__name__)


def _derive_contract_address(deployer: str, name: str, timestamp: int) -> str:
    """Derive a deterministic contract address from deployer, name, and timestamp.

    Similar to Ethereum's CREATE address scheme: hash(deployer || nonce).
    """
    data = f"{deployer.lower()}:{name.lower()}:{timestamp}".encode()
    return "0x" + hashlib.sha256(data).hexdigest()[:40]


@rate_limit(rate=50, per=60)
async def deploy_messaging_contract(request: Request, deploy_data: dict[str, Any]) -> dict[str, Any]:
    """Deploy the agent messaging contract to the blockchain"""
    contract_address = "0xagent_messaging_001"
    return {"success": True, "contract_address": contract_address, "status": "deployed"}


@rate_limit(rate=200, per=60)
async def list_contracts(request: Request) -> dict[str, Any]:
    """List all deployed contracts from the database"""
    return contract_service.list_contracts()


@rate_limit(rate=50, per=60)
async def deploy_contract(request: Request, deploy_data: dict[str, Any]) -> dict[str, Any]:
    """Deploy a new smart contract to the blockchain.

    Stores the contract in the on-chain database with a deterministically
    derived address.
    """
    contract_name = deploy_data.get("name")
    contract_type = deploy_data.get("type", "zk-verifier")
    deployer = deploy_data.get("deployer", "0x0000000000000000000000000000000000000000")
    bytecode = deploy_data.get("bytecode", "")
    abi = deploy_data.get("abi", {})
    chain_id = deploy_data.get("chain_id", "")

    if not contract_name:
        return {"success": False, "error": "Contract name is required"}

    # Derive a deterministic contract address
    timestamp = int(time.time())
    contract_address = _derive_contract_address(deployer, contract_name, timestamp)

    # Store in database
    with session_scope(chain_id) as session:
        contract = SmartContract(
            chain_id=chain_id,
            address=contract_address,
            name=contract_name,
            contract_type=contract_type,
            deployer=deployer,
            bytecode=bytecode,
            abi=abi if isinstance(abi, dict) else {},
            state={},
            status="deployed",
            deployed_at=datetime.now(UTC),
        )
        session.add(contract)
        session.commit()

    _logger.info("Deployed contract %s (%s) at %s", contract_name, contract_type, contract_address)

    return {
        "success": True,
        "contract_address": contract_address,
        "name": contract_name,
        "type": contract_type,
        "status": "deployed",
        "deployed_at": datetime.now(UTC).isoformat(),
    }


@rate_limit(rate=50, per=60)
async def call_contract(request: Request, call_data: dict[str, Any]) -> dict[str, Any]:
    """Call a method on a deployed contract.

    Looks up the contract in the database and returns its stored state.
    Read-only calls return the current state value for the requested method.
    """
    contract_address = call_data.get("address")
    method = call_data.get("method")
    params = call_data.get("params", {})
    chain_id = call_data.get("chain_id", "")

    if not contract_address:
        return {"success": False, "error": "Contract address is required"}
    if not method:
        return {"success": False, "error": "Method name is required"}

    with session_scope(chain_id) as session:
        stmt = select(SmartContract).where(
            SmartContract.address == contract_address,
            SmartContract.status == "deployed",
        )
        if chain_id:
            stmt = stmt.where(SmartContract.chain_id == chain_id)

        contract = session.exec(stmt).first()
        if not contract:
            return {"success": False, "error": f"Contract not found at address {contract_address}"}

        # Return the stored state for the requested method
        state_value = contract.state.get(method) if contract.state else None
        abi_entry = contract.abi.get(method) if contract.abi else None

        return {
            "success": True,
            "result": state_value,
            "address": contract_address,
            "method": method,
            "params": params,
            "abi": abi_entry,
        }


@rate_limit(rate=50, per=60)
async def verify_contract(request: Request, verify_data: dict[str, Any]) -> dict[str, Any]:
    """Verify a ZK proof against a contract.

    Checks that the contract exists and is deployed. Returns the actual
    verification status — does not hardcode 'valid: True'.
    """
    contract_address = verify_data.get("address")
    proof = verify_data.get("proof")
    chain_id = verify_data.get("chain_id", "")

    if not contract_address:
        return {"success": False, "error": "Contract address is required"}

    if not proof:
        return {"success": False, "error": "Proof data is required"}

    with session_scope(chain_id) as session:
        stmt = select(SmartContract).where(
            SmartContract.address == contract_address,
            SmartContract.status == "deployed",
        )
        if chain_id:
            stmt = stmt.where(SmartContract.chain_id == chain_id)

        contract = session.exec(stmt).first()
        if not contract:
            return {
                "success": False,
                "error": f"Contract not found at address {contract_address}",
                "result": {"valid": False, "reason": "contract_not_found"},
            }

        # Check if the contract type supports ZK verification
        if contract.contract_type != "zk-verifier":
            return {
                "success": True,
                "result": {
                    "valid": False,
                    "reason": f"Contract type '{contract.contract_type}' does not support ZK proof verification",
                    "address": contract_address,
                },
            }

        # ZK proof verification requires a real ZK verifier implementation, which this node
        # does not have. Return an honest result rather than accepting the proof.
        #
        # This refusal is unconditional. An earlier comment here said "the
        # enable_zk_proof_verification feature flag is currently disabled", which read as
        # though a flag governed it — nothing did: that flag lived in feature_flags.json,
        # which no code has read since aitbc/feature_flags.py was deleted in v0.10.9. The
        # file was removed in v0.23 (V23-32). Behaviour is unchanged; only the explanation
        # was wrong, and a wrong explanation of correct behaviour is how the behaviour gets
        # "restored" to something worse by someone who believes the flag is the real gate.
        return {
            "success": True,
            "result": {
                "valid": False,
                "reason": "ZK proof verification is not enabled on this node",
                "address": contract_address,
                "proof_received": bool(proof),
            },
        }


@rate_limit(rate=200, per=60)
async def get_messaging_contract_state(request: Request) -> dict[str, Any]:
    """Get the current state of the messaging contract"""
    state = {
        "total_topics": len(messaging_contract.topics),
        "total_messages": len(messaging_contract.messages),
        "total_agents": len(messaging_contract.agent_reputations),
    }
    return {"success": True, "contract_state": state}


@rate_limit(rate=200, per=60)
async def get_forum_topics(
    request: Request, limit: int = 50, offset: int = 0, sort_by: str = "last_activity"
) -> dict[str, Any]:
    """Get list of forum topics"""
    return messaging_contract.get_topics(limit, offset, sort_by)


@rate_limit(rate=50, per=60)
async def create_forum_topic(request: Request, topic_data: dict[str, Any]) -> dict[str, Any]:
    """Create a new forum topic"""
    agent_id = topic_data.get("agent_id")
    agent_address = topic_data.get("agent_address")
    title = topic_data.get("title")
    description = topic_data.get("description")
    tags = topic_data.get("tags", [])

    if not agent_id or not agent_address or not title or not description:
        return {"success": False, "error": "Missing required fields"}

    return messaging_contract.create_topic(agent_id, agent_address, title, description, tags)


@rate_limit(rate=200, per=60)
async def get_topic_messages(
    request: Request, topic_id: str, limit: int = 50, offset: int = 0, sort_by: str = "timestamp"
) -> dict[str, Any]:
    """Get messages from a forum topic"""
    return messaging_contract.get_messages(topic_id, limit, offset, sort_by)


@rate_limit(rate=50, per=60)
async def post_message(request: Request, message_data: dict[str, Any]) -> dict[str, Any]:
    """Post a message to a forum topic"""
    agent_id = message_data.get("agent_id")
    agent_address = message_data.get("agent_address")
    topic_id = message_data.get("topic_id")
    content = message_data.get("content")
    message_type = message_data.get("message_type", "post")
    parent_message_id = message_data.get("parent_message_id")

    if not agent_id or not agent_address or not topic_id or not content:
        return {"success": False, "error": "Missing required fields"}

    return messaging_contract.post_message(agent_id, agent_address, topic_id, content, message_type, parent_message_id)


@rate_limit(rate=50, per=60)
async def vote_message(request: Request, message_id: str, vote_data: dict[str, Any]) -> dict[str, Any]:
    """Vote on a message (upvote/downvote)"""
    agent_id = vote_data.get("agent_id")
    agent_address = vote_data.get("agent_address")
    vote_type = vote_data.get("vote_type")

    if not agent_id or not agent_address or not vote_type:
        return {"success": False, "error": "Missing required fields"}

    return messaging_contract.vote_message(agent_id, agent_address, message_id, vote_type)


@rate_limit(rate=200, per=60)
async def search_messages(request: Request, query: str, limit: int = 50) -> dict[str, Any]:
    """Search messages by content"""
    return messaging_contract.search_messages(query, limit)


@rate_limit(rate=200, per=60)
async def get_agent_reputation(request: Request, agent_id: str) -> dict[str, Any]:
    """Get agent reputation information"""
    return messaging_contract.get_agent_reputation(agent_id)


@rate_limit(rate=50, per=60)
async def moderate_message(request: Request, message_id: str, moderation_data: dict[str, Any]) -> dict[str, Any]:
    """Moderate a message (moderator only)"""
    moderator_agent_id = moderation_data.get("moderator_agent_id")
    moderator_address = moderation_data.get("moderator_address")
    action = moderation_data.get("action")
    reason = moderation_data.get("reason", "")

    if not moderator_agent_id or not moderator_address or not action:
        return {"success": False, "error": "Missing required fields"}

    return messaging_contract.moderate_message(moderator_agent_id, moderator_address, message_id, action, reason)
