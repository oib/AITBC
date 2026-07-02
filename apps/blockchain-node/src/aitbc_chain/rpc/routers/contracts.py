"""
Contracts router.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from aitbc.rate_limiting import rate_limit

from ...logger import get_logger

_logger = get_logger(__name__)

router = APIRouter(prefix="/contracts", tags=["contracts"])

# Optional imports - will be None if module not available
call_contract = None
create_forum_topic = None
deploy_contract = None
deploy_messaging_contract = None
get_agent_reputation = None
get_forum_topics = None
get_messaging_contract_state = None
get_topic_messages = None
list_contracts = None
moderate_message = None
post_message = None
search_messages = None
verify_contract = None
vote_message = None

try:
    from ..contracts import (
        call_contract,
        create_forum_topic,
        deploy_contract,
        deploy_messaging_contract,
        get_agent_reputation,
        get_forum_topics,
        get_messaging_contract_state,
        get_topic_messages,
        list_contracts,
        moderate_message,
        post_message,
        search_messages,
        verify_contract,
        vote_message,
    )
except ImportError as e:
    _logger.error("Contracts module not available: %s — affected endpoints will return 503", e)


@router.post("/deploy/messaging", summary="Deploy messaging contract")
@rate_limit(rate=50, per=60)
async def deploy_messaging_contract_route(request: Request, deploy_data: dict) -> dict[str, Any]:
    """Deploy the agent messaging contract to the blockchain"""
    if deploy_messaging_contract is None:
        raise HTTPException(status_code=503, detail="Contracts module not available")
    return await deploy_messaging_contract(request, deploy_data)


@router.get("", summary="List deployed contracts")
@rate_limit(rate=200, per=60)
async def list_contracts_route(request: Request) -> dict[str, Any]:
    """List all deployed contracts"""
    if list_contracts is None:
        raise HTTPException(status_code=503, detail="Contracts module not available")
    return await list_contracts(request)


@router.post("/deploy", summary="Deploy a smart contract")
@rate_limit(rate=50, per=60)
async def deploy_contract_route(request: Request, deploy_data: dict) -> dict[str, Any]:
    """Deploy a new smart contract to the blockchain"""
    if deploy_contract is None:
        raise HTTPException(status_code=503, detail="Contracts module not available")
    return await deploy_contract(request, deploy_data)


@router.post("/call", summary="Call a contract method")
@rate_limit(rate=50, per=60)
async def call_contract_route(request: Request, call_data: dict) -> dict[str, Any]:
    """Call a method on a deployed contract"""
    if call_contract is None:
        raise HTTPException(status_code=503, detail="Contracts module not available")
    return await call_contract(request, call_data)


@router.post("/verify", summary="Verify a ZK proof")
@rate_limit(rate=50, per=60)
async def verify_contract_route(request: Request, verify_data: dict) -> dict[str, Any]:
    """Verify a ZK proof against a contract"""
    if verify_contract is None:
        raise HTTPException(status_code=503, detail="Contracts module not available")
    return await verify_contract(request, verify_data)


@router.get("/messaging/state", summary="Get messaging contract state")
@rate_limit(rate=200, per=60)
async def get_messaging_contract_state_route(request: Request) -> dict[str, Any]:
    """Get the current state of the messaging contract"""
    if get_messaging_contract_state is None:
        raise HTTPException(status_code=503, detail="Contracts module not available")
    return await get_messaging_contract_state(request)


# Messaging/forum endpoints (grouped under /messaging for better organization)
@router.get("/messaging/topics", summary="Get forum topics")
@rate_limit(rate=200, per=60)
async def get_forum_topics_route(
    request: Request, limit: int = 50, offset: int = 0, sort_by: str = "last_activity"
) -> dict[str, Any]:
    """Get list of forum topics"""
    if get_forum_topics is None:
        raise HTTPException(status_code=503, detail="Contracts module not available")
    return await get_forum_topics(request, limit, offset, sort_by)


@router.post("/messaging/topics/create", summary="Create forum topic")
@rate_limit(rate=50, per=60)
async def create_forum_topic_route(request: Request, topic_data: dict) -> dict[str, Any]:
    """Create a new forum topic"""
    if create_forum_topic is None:
        raise HTTPException(status_code=503, detail="Contracts module not available")
    return await create_forum_topic(request, topic_data)


@router.get("/messaging/topics/{topic_id}/messages", summary="Get topic messages")
@rate_limit(rate=200, per=60)
async def get_topic_messages_route(
    request: Request, topic_id: str, limit: int = 50, offset: int = 0, sort_by: str = "timestamp"
) -> dict[str, Any]:
    """Get messages from a forum topic"""
    if get_topic_messages is None:
        raise HTTPException(status_code=503, detail="Contracts module not available")
    return await get_topic_messages(request, topic_id, limit, offset, sort_by)


@router.post("/messaging/messages/post", summary="Post message")
@rate_limit(rate=50, per=60)
async def post_message_route(request: Request, message_data: dict) -> dict[str, Any]:
    """Post a message to a forum topic"""
    if post_message is None:
        raise HTTPException(status_code=503, detail="Contracts module not available")
    return await post_message(request, message_data)


@router.post("/messaging/messages/{message_id}/vote", summary="Vote on message")
@rate_limit(rate=50, per=60)
async def vote_message_route(request: Request, message_id: str, vote_data: dict) -> dict[str, Any]:
    """Vote on a message (upvote/downvote)"""
    if vote_message is None:
        raise HTTPException(status_code=503, detail="Contracts module not available")
    return await vote_message(request, message_id, vote_data)


@router.get("/messaging/messages/search", summary="Search messages")
@rate_limit(rate=200, per=60)
async def search_messages_route(request: Request, query: str, limit: int = 50) -> dict[str, Any]:
    """Search messages by content"""
    if search_messages is None:
        raise HTTPException(status_code=503, detail="Contracts module not available")
    return await search_messages(request, query, limit)


@router.get("/messaging/agents/{agent_id}/reputation", summary="Get agent reputation")
@rate_limit(rate=200, per=60)
async def get_agent_reputation_route(request: Request, agent_id: str) -> dict[str, Any]:
    """Get agent reputation information"""
    if get_agent_reputation is None:
        raise HTTPException(status_code=503, detail="Contracts module not available")
    return await get_agent_reputation(request, agent_id)


@router.post("/messaging/messages/{message_id}/moderate", summary="Moderate message")
@rate_limit(rate=50, per=60)
async def moderate_message_route(request: Request, message_id: str, moderation_data: dict) -> dict[str, Any]:
    """Moderate a message (moderator only)"""
    if moderate_message is None:
        raise HTTPException(status_code=503, detail="Contracts module not available")
    return await moderate_message(request, message_id, moderation_data)
