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
from ..contracts.agent_messaging_contract import messaging_contract

_logger = get_logger(__name__)

router = APIRouter()

# Global rate limiter for importBlock
_last_import_time = 0
_import_lock = asyncio.Lock()

# Global variable to store the PoA proposer
_poa_proposer = None

def set_poa_proposer(proposer):
    """Set the global PoA proposer instance"""
    global _poa_proposer
    _poa_proposer = proposer

def get_poa_proposer():
    """Get the global PoA proposer instance"""
    return _poa_proposer

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


@router.post("/transaction", summary="Submit transaction")
async def submit_transaction(tx_data: dict) -> Dict[str, Any]:
    """Submit a new transaction to the mempool"""
    from ..mempool import get_mempool
    from ..models import Transaction
    
    try:
        mempool = get_mempool()
        
        # Create transaction data as dictionary
        tx_data_dict = {
            "chain_id": tx_data.get("chain_id", "ait-mainnet"),
            "from": tx_data["from"],
            "to": tx_data["to"],
            "amount": tx_data["amount"],
            "fee": tx_data.get("fee", 10),
            "nonce": tx_data.get("nonce", 0),
            "payload": tx_data.get("payload", "0x"),
            "signature": tx_data.get("signature")
        }
        
        # Add to mempool
        tx_hash = mempool.add(tx_data_dict)
        
        return {
            "success": True,
            "transaction_hash": tx_hash,
            "message": "Transaction submitted to mempool"
        }
    except Exception as e:
        _logger.error("Failed to submit transaction", extra={"error": str(e)})
        raise HTTPException(status_code=400, detail=f"Failed to submit transaction: {str(e)}")


@router.get("/mempool", summary="Get pending transactions")
async def get_mempool(chain_id: str = None, limit: int = 100) -> Dict[str, Any]:
    """Get pending transactions from mempool"""
    from ..mempool import get_mempool
    
    try:
        mempool = get_mempool()
        pending_txs = mempool.get_pending_transactions(chain_id=chain_id, limit=limit)
        
        return {
            "success": True,
            "transactions": pending_txs,
            "count": len(pending_txs)
        }
    except Exception as e:
        _logger.error(f"Failed to get mempool", extra={"error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get mempool: {str(e)}")


@router.get("/accounts/{address}", summary="Get account information")
async def get_account(address: str) -> Dict[str, Any]:
    """Get account information including balance"""
    from ..models import Account
    
    try:
        with session_scope() as session:
            account = session.exec(select(Account).where(Account.address == address)).first()
            
            if account is None:
                return {
                    "address": address,
                    "balance": 0,
                    "nonce": 0,
                    "exists": False
                }
            
            return {
                "address": account.address,
                "balance": account.balance,
                "nonce": account.nonce,
                "exists": True
            }
    except Exception as e:
        _logger.error("Failed to get account", extra={"error": str(e), "address": address})
        raise HTTPException(status_code=500, detail=f"Failed to get account: {str(e)}")


@router.get("/blocks-range", summary="Get blocks in height range")
async def get_blocks_range(start: int = 0, end: int = 10, include_tx: bool = True) -> Dict[str, Any]:
    """Get blocks in a height range
    
    Args:
        start: Starting block height (inclusive)
        end: Ending block height (inclusive)
        include_tx: Whether to include transaction data (default: True)
    """
    with session_scope() as session:
        from ..config import settings as cfg
        from ..models import Transaction
        
        blocks = session.exec(
            select(Block).where(
                Block.chain_id == cfg.chain_id,
                Block.height >= start,
                Block.height <= end,
            ).order_by(Block.height.asc())
        ).all()
        
        result_blocks = []
        for b in blocks:
            block_data = {
                "height": b.height,
                "hash": b.hash,
                "parent_hash": b.parent_hash,
                "proposer": b.proposer,
                "timestamp": b.timestamp.isoformat(),
                "tx_count": b.tx_count,
                "state_root": b.state_root,
            }

            if include_tx:
                # Fetch transactions for this block
                txs = session.exec(
                    select(Transaction).where(Transaction.block_height == b.height)
                ).all()
                block_data["transactions"] = [tx.model_dump() for tx in txs]
            
            result_blocks.append(block_data)
        
        return {
            "success": True,
            "blocks": result_blocks,
            "count": len(blocks),
        }

@router.post("/contracts/deploy/messaging", summary="Deploy messaging contract")
async def deploy_messaging_contract(deploy_data: dict) -> Dict[str, Any]:
    """Deploy the agent messaging contract to the blockchain"""
    contract_address = "0xagent_messaging_001"
    return {"success": True, "contract_address": contract_address, "status": "deployed"}

@router.get("/contracts/messaging/state", summary="Get messaging contract state")
async def get_messaging_contract_state() -> Dict[str, Any]:
    """Get the current state of the messaging contract"""
    state = {
        "total_topics": len(messaging_contract.topics),
        "total_messages": len(messaging_contract.messages),
        "total_agents": len(messaging_contract.agent_reputations)
    }
    return {"success": True, "contract_state": state}

@router.get("/messaging/topics", summary="Get forum topics")
async def get_forum_topics(limit: int = 50, offset: int = 0, sort_by: str = "last_activity") -> Dict[str, Any]:
    """Get list of forum topics"""
    return messaging_contract.get_topics(limit, offset, sort_by)

@router.post("/messaging/topics/create", summary="Create forum topic")
async def create_forum_topic(topic_data: dict) -> Dict[str, Any]:
    """Create a new forum topic"""
    return messaging_contract.create_topic(
        topic_data.get("agent_id"),
        topic_data.get("agent_address"),
        topic_data.get("title"),
        topic_data.get("description"),
        topic_data.get("tags", [])
    )

@router.get("/messaging/topics/{topic_id}/messages", summary="Get topic messages")
async def get_topic_messages(topic_id: str, limit: int = 50, offset: int = 0, sort_by: str = "timestamp") -> Dict[str, Any]:
    """Get messages from a forum topic"""
    return messaging_contract.get_messages(topic_id, limit, offset, sort_by)

@router.post("/messaging/messages/post", summary="Post message")
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

@router.post("/messaging/messages/{message_id}/vote", summary="Vote on message")
async def vote_message(message_id: str, vote_data: dict) -> Dict[str, Any]:
    """Vote on a message (upvote/downvote)"""
    return messaging_contract.vote_message(
        vote_data.get("agent_id"),
        vote_data.get("agent_address"),
        message_id,
        vote_data.get("vote_type")
    )

@router.get("/messaging/messages/search", summary="Search messages")
async def search_messages(query: str, limit: int = 50) -> Dict[str, Any]:
    """Search messages by content"""
    return messaging_contract.search_messages(query, limit)

@router.get("/messaging/agents/{agent_id}/reputation", summary="Get agent reputation")
async def get_agent_reputation(agent_id: str) -> Dict[str, Any]:
    """Get agent reputation information"""
    return messaging_contract.get_agent_reputation(agent_id)

@router.post("/messaging/messages/{message_id}/moderate", summary="Moderate message")
async def moderate_message(message_id: str, moderation_data: dict) -> Dict[str, Any]:
    """Moderate a message (moderator only)"""
    return messaging_contract.moderate_message(
        moderation_data.get("moderator_agent_id"),
        moderation_data.get("moderator_address"),
        message_id,
        moderation_data.get("action"),
        moderation_data.get("reason", "")
    )

@router.post("/importBlock", summary="Import a block")
async def import_block(block_data: dict) -> Dict[str, Any]:
    """Import a block into the blockchain"""
    global _last_import_time
    
    async with _import_lock:
        try:
            # Rate limiting: max 1 import per second
            current_time = time.time()
            time_since_last = current_time - _last_import_time
            if False:  # time_since_last < 1.0:  # 1 second minimum between imports
                await asyncio.sleep(1.0 - time_since_last)
            
            _last_import_time = time.time()
            
            with session_scope() as session:
                # Convert timestamp string to datetime if needed
                timestamp = block_data.get("timestamp")
                if isinstance(timestamp, str):
                    try:
                        timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    except ValueError:
                        # Fallback to current time if parsing fails
                        timestamp = datetime.utcnow()
                elif timestamp is None:
                    timestamp = datetime.utcnow()
                
                # Extract height from either 'number' or 'height' field
                height = block_data.get("number") or block_data.get("height")
                if height is None:
                    raise ValueError("Block height is required")
                
                # Check if block already exists to prevent duplicates
                existing = session.execute(
                    select(Block).where(Block.height == int(height))
                ).scalar_one_or_none()
                if existing:
                    return {
                        "success": True,
                        "block_number": existing.height,
                        "block_hash": existing.hash,
                        "message": "Block already exists"
                    }
                
                # Create block from data
                block = Block(
                    chain_id=block_data.get("chainId", "ait-mainnet"),
                    height=int(height),
                    hash=block_data.get("hash"),
                    parent_hash=block_data.get("parentHash", ""),
                    proposer=block_data.get("miner", ""),
                    timestamp=timestamp,
                    tx_count=len(block_data.get("transactions", [])),
                    state_root=block_data.get("stateRoot"),
                    block_metadata=json.dumps(block_data)
                )
                
                session.add(block)
                session.commit()
                
                _logger.info(f"Successfully imported block {block.height}")
                metrics_registry.increment("blocks_imported_total")
                
                return {
                    "success": True,
                    "block_number": block.height,
                    "block_hash": block.hash
                }
                
        except Exception as e:
            _logger.error(f"Failed to import block: {e}")
            metrics_registry.increment("block_import_errors_total")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to import block: {str(e)}"
            )
