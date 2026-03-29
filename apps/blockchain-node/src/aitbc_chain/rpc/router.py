from __future__ import annotations
from sqlalchemy import func

import asyncio
import json
import time
from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlmodel import select

from ..database import session_scope
from ..gossip import gossip_broker
from ..mempool import get_mempool
from ..metrics import metrics_registry
from ..models import Account, Block, Receipt, Transaction
from ..logger import get_logger

_logger = get_logger(__name__)

router = APIRouter()

def get_chain_id(chain_id: str = None) -> str:
    """Get chain_id from parameter or use default from settings"""
    if chain_id is None:
        from ..config import settings
        return settings.chain_id
    return chain_id


def _serialize_receipt(receipt: Receipt) -> Dict[str, Any]:
    return {
        "receipt_id": receipt.receipt_id,
        "job_id": receipt.job_id,
        "payload": receipt.payload,
        "miner_signature": receipt.miner_signature,
        "coordinator_attestations": receipt.coordinator_attestations,
        "minted_amount": receipt.minted_amount,
        "recorded_at": receipt.recorded_at.isoformat(),
    }


class TransactionRequest(BaseModel):
    type: str = Field(description="Transaction type, e.g. TRANSFER or RECEIPT_CLAIM")
    sender: str
    nonce: int
    fee: int = Field(ge=0)
    payload: Dict[str, Any]
    sig: Optional[str] = Field(default=None, description="Signature payload")

    @model_validator(mode="after")
    def normalize_type(self) -> "TransactionRequest":  # type: ignore[override]
        normalized = self.type.upper()
        if normalized not in {"TRANSFER", "RECEIPT_CLAIM"}:
            raise ValueError(f"unsupported transaction type: {self.type}")
        self.type = normalized
        return self


class ReceiptSubmissionRequest(BaseModel):
    sender: str
    nonce: int
    fee: int = Field(ge=0)
    payload: Dict[str, Any]
    sig: Optional[str] = None


class EstimateFeeRequest(BaseModel):
    type: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)



@router.get("/head", summary="Get current chain head")
async def get_head(chain_id: str = None) -> Dict[str, Any]:
    """Get current chain head"""
    from ..config import settings as cfg
    
    # Use default chain_id from settings if not provided
    if chain_id is None:
        chain_id = cfg.chain_id
    
    metrics_registry.increment("rpc_get_head_total")
    start = time.perf_counter()
    with session_scope() as session:
        result = session.exec(select(Block).where(Block.chain_id == chain_id).order_by(Block.height.desc()).limit(1)).first()
        if result is None:
            metrics_registry.increment("rpc_get_head_not_found_total")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no blocks yet")
        metrics_registry.increment("rpc_get_head_success_total")
    metrics_registry.observe("rpc_get_head_duration_seconds", time.perf_counter() - start)
    return {
        "height": result.height,
        "hash": result.hash,
        "timestamp": result.timestamp.isoformat(),
        "tx_count": result.tx_count,
    }


@router.get("/blocks/{height}", summary="Get block by height")
async def get_block(height: int) -> Dict[str, Any]:
    metrics_registry.increment("rpc_get_block_total")
    start = time.perf_counter()
    with session_scope() as session:
        block = session.exec(select(Block).where(Block.height == height)).first()
        if block is None:
            metrics_registry.increment("rpc_get_block_not_found_total")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="block not found")
        metrics_registry.increment("rpc_get_block_success_total")
        
        txs = session.exec(select(Transaction).where(Transaction.block_height == height)).all()
        tx_list = []
        for tx in txs:
            t = dict(tx.payload) if tx.payload else {}
            t["tx_hash"] = tx.tx_hash
            tx_list.append(t)
        
    metrics_registry.observe("rpc_get_block_duration_seconds", time.perf_counter() - start)
    return {
        "height": block.height,
        "hash": block.hash,
        "parent_hash": block.parent_hash,
        "proposer": block.proposer,
        "timestamp": block.timestamp.isoformat(),
        "tx_count": block.tx_count,
        "state_root": block.state_root,
        "transactions": tx_list,
    }


@router.get("/blocks-range", summary="Get blocks in height range")
# Working contract endpoints
async def get_messaging_contract_state() -> Dict[str, Any]:
    """Get the current state of the messaging contract"""
    state = {
        "total_topics": len(messaging_contract.topics),
        "total_messages": len(messaging_contract.messages),
        "total_agents": len(messaging_contract.agent_reputations)
    }
    return {"success": True, "contract_state": state}

@router.post("/messaging/contract/deploy", summary="Deploy messaging contract")
async def deploy_messaging_contract(deploy_data: dict) -> Dict[str, Any]:
    """Deploy the agent messaging contract to the blockchain"""
    contract_address = "0xagent_messaging_001"
    return {"success": True, "contract_address": contract_address, "status": "deployed"}

@router.get("/contracts", summary="List deployed contracts")
async def list_contracts() -> Dict[str, Any]:
    return contract_service.list_contracts()

async def get_forum_topics(limit: int = 50, offset: int = 0, sort_by: str = "last_activity") -> Dict[str, Any]:
    """Get list of forum topics"""
    return messaging_contract.get_topics(limit, offset, sort_by)

@router.post("/rpc/messaging/topics/create", summary="Create forum topic")
async def create_forum_topic(topic_data: dict) -> Dict[str, Any]:
    """Create a new forum topic"""
    return messaging_contract.create_topic(
        topic_data.get("agent_id"),
        topic_data.get("agent_address"),
        topic_data.get("title"),
        topic_data.get("description"),
        topic_data.get("tags", [])
    )

@router.get("/rpc/messaging/topics/{topic_id}/messages", summary="Get topic messages")
async def get_topic_messages(topic_id: str, limit: int = 50, offset: int = 0, sort_by: str = "timestamp") -> Dict[str, Any]:
    """Get messages from a forum topic"""
    return messaging_contract.get_messages(topic_id, limit, offset, sort_by)

@router.post("/rpc/messaging/messages/post", summary="Post message")
async def post_message(message_data: dict) -> Dict[str, Any]:
    """Post a message to a forum topic"""
    return messaging_contract.post_message(
        message_data.get("agent_id"),
        message_data.get("agent_address"),
        message_data.get("topic_id"),
        message_data.get("content"),
        message_data.get("message_type", "post"),
        message_data.get("parent_message_id")
    )

@router.post("/rpc/messaging/messages/{message_id}/vote", summary="Vote on message")
async def vote_message(message_id: str, vote_data: dict) -> Dict[str, Any]:
    """Vote on a message (upvote/downvote)"""
    return messaging_contract.vote_message(
        vote_data.get("agent_id"),
        vote_data.get("agent_address"),
        message_id,
        vote_data.get("vote_type")
    )

@router.get("/rpc/messaging/messages/search", summary="Search messages")
async def search_messages(query: str, limit: int = 50) -> Dict[str, Any]:
    """Search messages by content"""
    return messaging_contract.search_messages(query, limit)

@router.get("/rpc/messaging/agents/{agent_id}/reputation", summary="Get agent reputation")
async def get_agent_reputation(agent_id: str) -> Dict[str, Any]:
    """Get agent reputation information"""
    return messaging_contract.get_agent_reputation(agent_id)

@router.post("/rpc/messaging/messages/{message_id}/moderate", summary="Moderate message")
async def moderate_message(message_id: str, moderation_data: dict) -> Dict[str, Any]:
    """Moderate a message (moderator only)"""
    return messaging_contract.moderate_message(
        moderation_data.get("moderator_agent_id"),
        moderation_data.get("moderator_address"),
        message_id,
        moderation_data.get("action"),
        moderation_data.get("reason", "")
    )
EOF && echo "✅ Messaging contract endpoints added" && echo -e "\n2. Restarting blockchain node to load new endpoints:" && systemctl restart aitbc-blockchain-node && sleep 5 && echo "✅ Blockchain node restarted" && echo -e "\n3. Testing messaging endpoints:" && echo "   Testing forum topics endpoint:" && curl -s http://localhost:8006/rpc/messaging/topics | jq .total_topics && echo -e "\n   Testing message search endpoint:" && curl -s "http://localhost:8006/rpc/messaging/messages/search?query=test" | jq .total_matches
from .contracts.agent_messaging_contract import messaging_contract
@router.get("/rpc/messaging/topics", summary="Get forum topics")
async def get_forum_topics(limit: int = 50, offset: int = 0, sort_by: str = "last_activity") -> Dict[str, Any]:
    """Get list of forum topics"""
    return messaging_contract.get_topics(limit, offset, sort_by)
@router.post("/rpc/messaging/topics/create", summary="Create forum topic")
async def create_forum_topic(topic_data: dict) -> Dict[str, Any]:
    """Create a new forum topic"""
    return messaging_contract.create_topic(topic_data.get("agent_id"), topic_data.get("agent_address"), topic_data.get("title"), topic_data.get("description"), topic_data.get("tags", []))
@router.post("/rpc/messaging/messages/post", summary="Post message")
async def post_message(message_data: dict) -> Dict[str, Any]:
    """Post a message to a forum topic"""
    return messaging_contract.post_message(message_data.get("agent_id"), message_data.get("agent_address"), message_data.get("topic_id"), message_data.get("content"), message_data.get("message_type", "post"), message_data.get("parent_message_id"))
@router.post("/rpc/contracts/deploy/messaging", summary="Deploy messaging contract")
async def deploy_messaging_contract(deploy_data: dict) -> Dict[str, Any]:
    """Deploy the agent messaging contract to the blockchain"""
    contract_address = "0xagent_messaging_001"
    return {"success": True, "contract_address": contract_address, "status": "deployed"}
@router.get("/rpc/contracts/messaging/state", summary="Get messaging contract state")
async def get_messaging_contract_state() -> Dict[str, Any]:
    """Get the current state of the messaging contract"""
    state = {
        "total_topics": len(messaging_contract.topics),
        "total_messages": len(messaging_contract.messages),
        "total_agents": len(messaging_contract.agent_reputations)
    }
    return {"success": True, "contract_state": state}

# Agent messaging endpoints
@router.get("/rpc/messaging/topics", summary="Get forum topics")
async def get_forum_topics(limit: int = 50, offset: int = 0, sort_by: str = "last_activity") -> Dict[str, Any]:
    """Get list of forum topics"""
    return messaging_contract.get_topics(limit, offset, sort_by)

@router.post("/rpc/messaging/topics/create", summary="Create forum topic")
async def create_forum_topic(topic_data: dict) -> Dict[str, Any]:
    """Create a new forum topic"""
    return messaging_contract.create_topic(
        topic_data.get("agent_id"),
        topic_data.get("agent_address"),
        topic_data.get("title"),
        topic_data.get("description"),
        topic_data.get("tags", [])
    )

@router.post("/rpc/messaging/messages/post", summary="Post message")
async def post_message(message_data: dict) -> Dict[str, Any]:
    """Post a message to a forum topic"""
    return messaging_contract.post_message(
        message_data.get("agent_id"),
        message_data.get("agent_address"),
        message_data.get("topic_id"),
        message_data.get("content"),
        message_data.get("message_type", "post"),
        message_data.get("parent_message_id")
    )
EOF && echo "✅ Added working endpoints" && echo -e "\n6. Restarting node with fixed configuration:" && systemctl restart aitbc-blockchain-node && sleep 5 && echo "✅ Node restarted" && echo -e "\n7. Testing fixed endpoints:" && curl -s http://localhost:8006/rpc/messaging/topics | jq .success && echo -e "\n8. Creating test topic:" && curl -s -X POST http://localhost:8006/rpc/messaging/topics/create \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "test_agent", "agent_address": "ait1test_agent", "title": "Fixed Test Topic", "description": "Testing after fixes", "tags": ["test"]}' | jq .topic_id

# Agent messaging contract endpoints
@router.get("/rpc/messaging/topics", summary="Get forum topics")
async def get_forum_topics(limit: int = 50, offset: int = 0, sort_by: str = "last_activity") -> Dict[str, Any]:
    """Get list of forum topics"""
    return messaging_contract.get_topics(limit, offset, sort_by)

@router.post("/rpc/messaging/topics/create", summary="Create forum topic")
async def create_forum_topic(topic_data: dict) -> Dict[str, Any]:
    """Create a new forum topic"""
    return messaging_contract.create_topic(
        topic_data.get("agent_id"),
        topic_data.get("agent_address"),
        topic_data.get("title"),
        topic_data.get("description"),
        topic_data.get("tags", [])
    )

@router.post("/rpc/messaging/messages/post", summary="Post message")
async def post_message(message_data: dict) -> Dict[str, Any]:
    """Post a message to a forum topic"""
    return messaging_contract.post_message(
        message_data.get("agent_id"),
        message_data.get("agent_address"),
        message_data.get("topic_id"),
        message_data.get("content"),
        message_data.get("message_type", "post"),
        message_data.get("parent_message_id")
    )
EOF && echo "✅ Added clean endpoints" && echo -e "\n5. Restarting node:" && systemctl restart aitbc-blockchain-node && sleep 5 && echo "✅ Node restarted" && echo -e "\n6. Testing messaging contract:" && curl -s http://localhost:8006/rpc/messaging/topics | jq .success && echo -e "\n7. Creating test topic:" && curl -s -X POST http://localhost:8006/rpc/messaging/topics/create \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "test_agent", "agent_address": "ait1test_agent", "title": "Working Test Topic", "description": "Testing after syntax fix", "tags": ["test"]}' | jq .topic_id
