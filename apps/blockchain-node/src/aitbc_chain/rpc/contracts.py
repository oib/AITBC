"""
Contract-related RPC endpoints.
"""

import time
from datetime import UTC, datetime
from typing import Any

from fastapi import Request

from aitbc.rate_limiting import rate_limit

from ..logger import get_logger

_logger = get_logger(__name__)

# Import contract services
from ..contracts.agent_messaging_contract import messaging_contract
from .contract_service import contract_service


@rate_limit(rate=50, per=60)
async def deploy_messaging_contract(request: Request, deploy_data: dict[str, Any]) -> dict[str, Any]:
    """Deploy the agent messaging contract to the blockchain"""
    contract_address = "0xagent_messaging_001"
    return {"success": True, "contract_address": contract_address, "status": "deployed"}


@rate_limit(rate=200, per=60)
async def list_contracts(request: Request) -> dict[str, Any]:
    """List all deployed contracts"""
    return contract_service.list_contracts()


@rate_limit(rate=50, per=60)
async def deploy_contract(request: Request, deploy_data: dict[str, Any]) -> dict[str, Any]:
    """Deploy a new smart contract to the blockchain"""
    contract_name = deploy_data.get("name")
    contract_type = deploy_data.get("type", "zk-verifier")

    if not contract_name:
        return {"success": False, "error": "Contract name is required"}

    # Generate a mock contract address for now
    contract_address = f"0x{contract_name.lower()}_{int(time.time())}"

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
    """Call a method on a deployed contract"""
    contract_address = call_data.get("address")
    method = call_data.get("method")
    call_data.get("params")

    if not contract_address:
        return {"success": False, "error": "Contract address is required"}
    if not method:
        return {"success": False, "error": "Method name is required"}

    # Mock call result for now
    return {"success": True, "result": f"Called {method} on {contract_address}", "address": contract_address, "method": method}


@rate_limit(rate=50, per=60)
async def verify_contract(request: Request, verify_data: dict[str, Any]) -> dict[str, Any]:
    """Verify a ZK proof against a contract"""
    contract_address = verify_data.get("address")
    verify_data.get("proof")

    if not contract_address:
        return {"success": False, "error": "Contract address is required"}

    # Mock verification result for now
    return {"success": True, "result": {"valid": True, "receipt_hash": "0xmock_receipt_hash", "address": contract_address}}


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
