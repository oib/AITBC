from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlmodel import select, delete

from ..database import session_scope
from ..gossip import gossip_broker
from ..mempool import get_mempool
from ..metrics import metrics_registry
from ..models import Account, Block, Receipt, Transaction
from ..logger import get_logger
from ..sync import ChainSync
from ..contracts.agent_messaging_contract import messaging_contract

_logger = get_logger(__name__)

router = APIRouter()

# Global rate limiter for importBlock
_last_import_time = 0
_import_lock = asyncio.Lock()

# Global variable to store the PoA proposer
_poa_proposers: Dict[str, Any] = {}

def set_poa_proposer(proposer, chain_id: str = None):
    """Set the global PoA proposer instance"""
    if chain_id is None:
        chain_id = getattr(getattr(proposer, "_config", None), "chain_id", None) or get_chain_id(None)
    _poa_proposers[chain_id] = proposer

def get_poa_proposer(chain_id: str = None):
    """Get the global PoA proposer instance"""
    chain_id = get_chain_id(chain_id)
    return _poa_proposers.get(chain_id)

def get_chain_id(chain_id: str = None) -> str:
    """Get chain_id from parameter or use default from settings"""
    if chain_id is None:
        from ..config import settings
        return settings.chain_id
    return chain_id

def get_supported_chains() -> List[str]:
    from ..config import settings
    chains = [chain.strip() for chain in settings.supported_chains.split(",") if chain.strip()]
    if not chains and settings.chain_id:
        return [settings.chain_id]
    return chains

def _normalize_transaction_data(tx_data: Dict[str, Any], chain_id: str) -> Dict[str, Any]:
    sender = tx_data.get("from")
    recipient = tx_data.get("to")
    if not isinstance(sender, str) or not sender.strip():
        raise ValueError("transaction.from is required")
    if not isinstance(recipient, str) or not recipient.strip():
        raise ValueError("transaction.to is required")

    try:
        amount = int(tx_data["amount"])
    except KeyError as exc:
        raise ValueError("transaction.amount is required") from exc
    except (TypeError, ValueError) as exc:
        raise ValueError("transaction.amount must be an integer") from exc

    try:
        fee = int(tx_data.get("fee", 10))
    except (TypeError, ValueError) as exc:
        raise ValueError("transaction.fee must be an integer") from exc

    try:
        nonce = int(tx_data.get("nonce", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("transaction.nonce must be an integer") from exc

    if amount < 0:
        raise ValueError("transaction.amount must be non-negative")
    if fee < 0:
        raise ValueError("transaction.fee must be non-negative")
    if nonce < 0:
        raise ValueError("transaction.nonce must be non-negative")

    payload = tx_data.get("payload", {})
    if payload is None:
        payload = {}

    tx_type = tx_data.get("type", "TRANSFER")
    if tx_type:
        tx_type = tx_type.upper()

    # Ensure payload is a dict
    if isinstance(payload, str):
        try:
            import json
            payload = json.loads(payload)
        except:
            payload = {}
    
    if not isinstance(payload, dict):
        payload = {}

    return {
        "chain_id": chain_id,
        "type": tx_type,
        "from": sender.strip(),
        "to": recipient.strip(),
        "amount": amount,
        "fee": fee,
        "nonce": nonce,
        "payload": payload,
        "signature": tx_data.get("signature") or tx_data.get("sig"),
    }

def _validate_transaction_admission(tx_data: Dict[str, Any], mempool: Any) -> None:
    from ..mempool import compute_tx_hash

    chain_id = tx_data["chain_id"]
    supported_chains = get_supported_chains()
    if not chain_id:
        raise ValueError("transaction.chain_id is required")
    if supported_chains and chain_id not in supported_chains:
        raise ValueError(f"unsupported chain_id '{chain_id}'. Supported chains: {supported_chains}")

    tx_hash = compute_tx_hash(tx_data)

    with session_scope() as session:
        sender_account = session.get(Account, (chain_id, tx_data["from"]))
        if sender_account is None:
            raise ValueError(f"sender account not found on chain '{chain_id}'")

        total_cost = tx_data["amount"] + tx_data["fee"]
        if sender_account.balance < total_cost:
            raise ValueError(
                f"insufficient balance for sender '{tx_data['from']}' on chain '{chain_id}': has {sender_account.balance}, needs {total_cost}"
            )

        if tx_data["nonce"] != sender_account.nonce:
            raise ValueError(
                f"invalid nonce for sender '{tx_data['from']}' on chain '{chain_id}': expected {sender_account.nonce}, got {tx_data['nonce']}"
            )

        existing_tx = session.exec(
            select(Transaction)
            .where(Transaction.chain_id == chain_id)
            .where(Transaction.tx_hash == tx_hash)
        ).first()
        if existing_tx is not None:
            raise ValueError(f"transaction '{tx_hash}' is already confirmed on chain '{chain_id}'")

        existing_nonce = session.exec(
            select(Transaction)
            .where(Transaction.chain_id == chain_id)
            .where(Transaction.sender == tx_data["from"])
            .where(Transaction.nonce == tx_data["nonce"])
        ).first()
        if existing_nonce is not None:
            raise ValueError(
                f"sender '{tx_data['from']}' already used nonce {tx_data['nonce']} on chain '{chain_id}'"
            )

    pending_txs = mempool.list_transactions(chain_id=chain_id)
    if any(pending_tx.tx_hash == tx_hash for pending_tx in pending_txs):
        raise ValueError(f"transaction '{tx_hash}' is already pending on chain '{chain_id}'")
    if any(
        pending_tx.content.get("from") == tx_data["from"] and pending_tx.content.get("nonce") == tx_data["nonce"]
        for pending_tx in pending_txs
    ):
        raise ValueError(
            f"sender '{tx_data['from']}' already has pending nonce {tx_data['nonce']} on chain '{chain_id}'"
        )

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
    type: str = Field(description="Transaction type, e.g. TRANSFER, RECEIPT_CLAIM, GPU_MARKETPLACE, EXCHANGE, MESSAGE")
    sender: str = Field(alias="from")  # Accept both "sender" and "from"
    nonce: int
    fee: int = Field(ge=0)
    payload: Dict[str, Any]
    sig: Optional[str] = Field(default=None, description="Signature payload")

    @model_validator(mode="after")
    def normalize_type(self) -> "TransactionRequest":  # type: ignore[override]
        normalized = self.type.upper()
        valid_types = {"TRANSFER", "RECEIPT_CLAIM", "GPU_MARKETPLACE", "EXCHANGE", "MESSAGE"}
        if normalized not in valid_types:
            raise ValueError(f"unsupported transaction type: {normalized}. Valid types: {valid_types}")
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
async def get_block(height: int, chain_id: str = None) -> Dict[str, Any]:
    """Get block by height"""
    chain_id = get_chain_id(chain_id)
    metrics_registry.increment("rpc_get_block_total")
    start = time.perf_counter()
    with session_scope() as session:
        block = session.exec(
            select(Block).where(Block.chain_id == chain_id).where(Block.height == height)
        ).first()
        if block is None:
            metrics_registry.increment("rpc_get_block_not_found_total")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="block not found")
        metrics_registry.increment("rpc_get_block_success_total")
        
        txs = session.exec(
            select(Transaction)
            .where(Transaction.chain_id == chain_id)
            .where(Transaction.block_height == height)
        ).all()
        tx_list = []
        for tx in txs:
            t = dict(tx.payload) if tx.payload else {}
            t["tx_hash"] = tx.tx_hash
            tx_list.append(t)
        
    metrics_registry.observe("rpc_get_block_duration_seconds", time.perf_counter() - start)
    return {
        "chain_id": block.chain_id,
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
async def submit_transaction(tx_data: TransactionRequest) -> Dict[str, Any]:
    """Submit a new transaction to the mempool"""
    from ..mempool import get_mempool
     
    try:
        mempool = get_mempool()
        chain_id = get_chain_id(None)

        # Convert TransactionRequest to dict for normalization
        # _normalize_transaction_data expects "from", not "sender"
        tx_data_dict = {
            "from": tx_data.sender,
            "to": tx_data.payload.get("to"),  # Get to from payload (required field)
            "amount": tx_data.payload.get("amount", 0),  # Get amount from payload
            "fee": tx_data.fee,
            "nonce": tx_data.nonce,
            "payload": tx_data.payload,
            "type": tx_data.type,
            "signature": tx_data.sig
        }
        
        tx_data_dict = _normalize_transaction_data(tx_data_dict, chain_id)
        _validate_transaction_admission(tx_data_dict, mempool)

        tx_hash = mempool.add(tx_data_dict, chain_id=chain_id)
         
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


@router.get("/account/{address}", summary="Get account information")
async def get_account(address: str, chain_id: str = None) -> Dict[str, Any]:
    """Get account information"""
    chain_id = get_chain_id(chain_id)
    
    with session_scope() as session:
        account = session.exec(select(Account).where(Account.address == address).where(Account.chain_id == chain_id)).first()
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        
        return {
            "address": account.address,
            "balance": account.balance,
            "nonce": account.nonce,
            "chain_id": account.chain_id
        }


@router.get("/accounts/{address}", summary="Get account information (alias)")
async def get_account_alias(address: str, chain_id: str = None) -> Dict[str, Any]:
    """Get account information (alias endpoint)"""
    return await get_account(address, chain_id)


@router.post("/transactions/marketplace", summary="Submit marketplace transaction")
async def submit_marketplace_transaction(tx_data: Dict[str, Any]) -> Dict[str, Any]:
    """Submit a marketplace purchase transaction to the blockchain"""
    from ..config import settings as cfg
    chain_id = get_chain_id(tx_data.get("chain_id"))
    
    metrics_registry.increment("rpc_marketplace_transaction_total")
    start = time.perf_counter()
    
    try:
        with session_scope() as session:
            # Validate sender account
            sender_addr = tx_data.get("from")
            sender_account = session.get(Account, (chain_id, sender_addr))
            if not sender_account:
                raise ValueError(f"Sender account not found: {sender_addr}")
            
            # Validate balance
            amount = tx_data.get("value", 0)
            fee = tx_data.get("fee", 0)
            total_cost = amount + fee
            
            if sender_account.balance < total_cost:
                raise ValueError(f"Insufficient balance: {sender_account.balance} < {total_cost}")
            
            # Validate nonce
            tx_nonce = tx_data.get("nonce", 0)
            if tx_nonce != sender_account.nonce:
                raise ValueError(f"Invalid nonce: expected {sender_account.nonce}, got {tx_nonce}")
            
            # Get or create recipient account
            recipient_addr = tx_data.get("to")
            recipient_account = session.get(Account, (chain_id, recipient_addr))
            if not recipient_account:
                recipient_account = Account(
                    chain_id=chain_id,
                    address=recipient_addr,
                    balance=0,
                    nonce=0
                )
                session.add(recipient_account)
            
            # Create transaction record
            tx_hash = compute_tx_hash(tx_data)
            transaction = Transaction(
                chain_id=chain_id,
                tx_hash=tx_hash,
                sender=sender_addr,
                recipient=recipient_addr,
                payload=tx_data.get("payload", {}),
                created_at=datetime.utcnow(),
                nonce=tx_nonce,
                value=amount,
                fee=fee,
                status="pending",
                timestamp=datetime.utcnow().isoformat()
            )
            session.add(transaction)
            
            # Update account balances (pending state)
            sender_account.balance -= total_cost
            sender_account.nonce += 1
            recipient_account.balance += amount
            
            metrics_registry.increment("rpc_marketplace_transaction_success")
            duration = time.perf_counter() - start
            metrics_registry.observe("rpc_marketplace_transaction_duration_seconds", duration)
            
            _logger.info(f"Marketplace transaction submitted: {tx_hash[:16]}... from {sender_addr[:16]}... to {recipient_addr[:16]}... amount={amount}")
            
            return {
                "success": True,
                "tx_hash": tx_hash,
                "status": "pending",
                "chain_id": chain_id,
                "amount": amount,
                "fee": fee,
                "from": sender_addr,
                "to": recipient_addr
            }
            
    except ValueError as e:
        metrics_registry.increment("rpc_marketplace_transaction_validation_errors_total")
        _logger.error(f"Marketplace transaction validation failed: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        metrics_registry.increment("rpc_marketplace_transaction_errors_total")
        _logger.error(f"Failed to submit marketplace transaction", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Failed to submit marketplace transaction: {str(e)}")


@router.get("/transactions", summary="Query transactions")
async def query_transactions(
    transaction_type: Optional[str] = None,
    island_id: Optional[str] = None,
    pair: Optional[str] = None,
    status: Optional[str] = None,
    order_id: Optional[str] = None,
    limit: Optional[int] = 100,
    chain_id: str = None
) -> List[Dict[str, Any]]:
    """Query transactions with optional filters"""
    chain_id = get_chain_id(chain_id)
    
    with session_scope() as session:
        query = select(Transaction).where(Transaction.chain_id == chain_id)
        
        # Apply filters based on payload fields
        transactions = session.exec(query).all()
        
        results = []
        for tx in transactions:
            # Filter by transaction type in payload
            if transaction_type and tx.payload.get('type') != transaction_type:
                continue
            
            # Filter by island_id in payload
            if island_id and tx.payload.get('island_id') != island_id:
                continue
            
            # Filter by pair in payload
            if pair and tx.payload.get('pair') != pair:
                continue
            
            # Filter by status in payload
            if status and tx.payload.get('status') != status:
                continue
            
            # Filter by order_id in payload
            if order_id and tx.payload.get('order_id') != order_id and tx.payload.get('offer_id') != order_id and tx.payload.get('bid_id') != order_id:
                continue
            
            results.append({
                "transaction_id": tx.id,
                "tx_hash": tx.tx_hash,
                "sender": tx.sender,
                "recipient": tx.recipient,
                "payload": tx.payload,
                "status": tx.status,
                "created_at": tx.created_at.isoformat(),
                "timestamp": tx.timestamp,
                "nonce": tx.nonce,
                "value": tx.value,
                "fee": tx.fee
            })
        
        # Apply limit
        if limit:
            results = results[:limit]
        
        return results


@router.get("/blocks-range", summary="Get blocks in height range")
async def get_blocks_range(start: int = 0, end: int = 10, include_tx: bool = True, chain_id: str = None) -> Dict[str, Any]:
    """Get blocks in a height range
    
    Args:
        start: Starting block height (inclusive)
        end: Ending block height (inclusive)
        include_tx: Whether to include transaction data (default: True)
    """
    with session_scope() as session:
        from ..models import Transaction
        chain_id = get_chain_id(chain_id)
        
        blocks = session.exec(
            select(Block).where(
                Block.chain_id == chain_id,
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
                    select(Transaction)
                    .where(Transaction.chain_id == chain_id)
                    .where(Transaction.block_height == b.height)
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
            if time_since_last < 1.0:
                await asyncio.sleep(1.0 - time_since_last)
            
            _last_import_time = time.time()
            
            chain_id = block_data.get("chain_id") or block_data.get("chainId") or get_chain_id(None)

            timestamp = block_data.get("timestamp")
            if isinstance(timestamp, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                except ValueError:
                    timestamp = datetime.utcnow()
            elif timestamp is None:
                timestamp = datetime.utcnow()

            with session_scope() as session:
                # Check for hash conflicts across chains
                block_hash = block_data["hash"]
                existing_block = session.execute(
                    select(Block).where(Block.hash == block_hash)
                ).first()
                
                if existing_block:
                    # Delete existing block with conflicting hash
                    _logger.warning(f"Deleting existing block with conflicting hash {block_hash} from chain {existing_block[0].chain_id}")
                    session.execute(delete(Block).where(Block.hash == block_hash))
                    session.commit()
                
                # Create block
                block = Block(
                    chain_id=chain_id,
                    height=block_data["height"],
                    hash=block_hash,
                    parent_hash=block_data["parent_hash"],
                    proposer=block_data["proposer"],
                    timestamp=timestamp,
                    state_root=block_data.get("state_root"),
                    tx_count=block_data.get("tx_count", 0)
                )
                session.add(block)
                session.commit()

                return {
                    "success": True,
                    "block_height": block.height,
                    "block_hash": block.hash,
                    "chain_id": chain_id
                }
        except Exception as e:
            _logger.error(f"Error importing block: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to import block: {str(e)}")

def _serialize_optional_timestamp(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)

def _parse_datetime_value(value: Any, field_name: str) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid {field_name}: {value}") from exc
    raise HTTPException(status_code=400, detail=f"Invalid {field_name} type: {type(value).__name__}")

def _select_export_blocks(session, chain_id: str) -> List[Block]:
    blocks_result = session.execute(
        select(Block)
        .where(Block.chain_id == chain_id)
        .order_by(Block.height.asc(), Block.id.desc())
    )
    blocks: List[Block] = []
    seen_heights = set()
    duplicate_count = 0
    for block in blocks_result.scalars().all():
        if block.height in seen_heights:
            duplicate_count += 1
            continue
        seen_heights.add(block.height)
        blocks.append(block)
    if duplicate_count:
        _logger.warning(f"Filtered {duplicate_count} duplicate exported blocks for chain {chain_id}")
    return blocks

def _dedupe_import_blocks(blocks: List[Dict[str, Any]], chain_id: str) -> List[Dict[str, Any]]:
    latest_by_height: Dict[int, Dict[str, Any]] = {}
    duplicate_count = 0
    for block_data in blocks:
        if "height" not in block_data:
            raise HTTPException(status_code=400, detail="Block height is required")
        try:
            height = int(block_data["height"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid block height: {block_data.get('height')}") from exc
        block_chain_id = block_data.get("chain_id")
        if block_chain_id and block_chain_id != chain_id:
            raise HTTPException(
                status_code=400,
                detail=f"Mismatched block chain_id '{block_chain_id}' for import chain '{chain_id}'",
            )
        normalized_block = dict(block_data)
        normalized_block["height"] = height
        normalized_block["chain_id"] = chain_id
        if height in latest_by_height:
            duplicate_count += 1
        latest_by_height[height] = normalized_block
    if duplicate_count:
        _logger.warning(f"Filtered {duplicate_count} duplicate imported blocks for chain {chain_id}")
    return [latest_by_height[height] for height in sorted(latest_by_height)]

@router.get("/export-chain", summary="Export full chain state")
async def export_chain(chain_id: str = None) -> Dict[str, Any]:
    """Export full chain state as JSON for manual synchronization"""
    chain_id = get_chain_id(chain_id)
    try:
        # Use session_scope for database operations
        with session_scope() as session:
            blocks = _select_export_blocks(session, chain_id)
            
            accounts_result = session.execute(
                select(Account)
                .where(Account.chain_id == chain_id)
                .order_by(Account.address)
            )
            accounts = list(accounts_result.scalars().all())
            
            txs_result = session.execute(
                select(Transaction)
                .where(Transaction.chain_id == chain_id)
                .order_by(Transaction.block_height, Transaction.id)
            )
            transactions = list(txs_result.scalars().all())
            
            # Build export data
            export_data = {
                "chain_id": chain_id,
                "export_timestamp": datetime.now().isoformat(),
                "block_count": len(blocks),
                "account_count": len(accounts),
                "transaction_count": len(transactions),
                "blocks": [
                    {
                        "chain_id": b.chain_id,
                        "height": b.height,
                        "hash": b.hash,
                        "parent_hash": b.parent_hash,
                        "proposer": b.proposer,
                        "timestamp": b.timestamp.isoformat() if b.timestamp else None,
                        "state_root": b.state_root,
                        "tx_count": b.tx_count,
                        "block_metadata": b.block_metadata,
                    }
                    for b in blocks
                ],
                "accounts": [
                    {
                        "chain_id": a.chain_id,
                        "address": a.address,
                        "balance": a.balance,
                        "nonce": a.nonce
                    }
                    for a in accounts
                ],
                "transactions": [
                    {
                        "id": t.id,
                        "chain_id": t.chain_id,
                        "tx_hash": t.tx_hash,
                        "block_height": t.block_height,
                        "sender": t.sender,
                        "recipient": t.recipient,
                        "payload": t.payload,
                        "value": t.value,
                        "fee": t.fee,
                        "nonce": t.nonce,
                        "timestamp": _serialize_optional_timestamp(t.timestamp),
                        "status": t.status,
                        "created_at": t.created_at.isoformat() if t.created_at else None,
                        "tx_metadata": t.tx_metadata,
                    }
                    for t in transactions
                ]
            }
            
            return {
                "success": True,
                "export_data": export_data,
                "export_size_bytes": len(json.dumps(export_data))
            }
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Error exporting chain: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export chain: {str(e)}")

@router.post("/import-chain", summary="Import chain state")
async def import_chain(import_data: dict) -> Dict[str, Any]:
     """Import chain state from JSON for manual synchronization"""
     async with _import_lock:
         try:
             chain_id = import_data.get("chain_id")
             blocks = import_data.get("blocks", [])
             accounts = import_data.get("accounts", [])
             transactions = import_data.get("transactions", [])

             if not chain_id and blocks:
                 chain_id = blocks[0].get("chain_id")
             chain_id = get_chain_id(chain_id)

             unique_blocks = _dedupe_import_blocks(blocks, chain_id)

             with session_scope() as session:
                 if not unique_blocks:
                     raise HTTPException(status_code=400, detail="No blocks to import")

                 existing_blocks = session.execute(
                     select(Block)
                     .where(Block.chain_id == chain_id)
                     .order_by(Block.height)
                 )
                 existing_count = len(list(existing_blocks.scalars().all()))

                 if existing_count > 0:
                     _logger.info(f"Backing up existing chain with {existing_count} blocks")

                 _logger.info(f"Clearing existing transactions for chain {chain_id}")
                 session.execute(delete(Transaction).where(Transaction.chain_id == chain_id))
                 if accounts:
                     _logger.info(f"Clearing existing accounts for chain {chain_id}")
                     session.execute(delete(Account).where(Account.chain_id == chain_id))
                 _logger.info(f"Clearing existing blocks for chain {chain_id}")
                 session.execute(delete(Block).where(Block.chain_id == chain_id))
                
                 import_hashes = {block_data["hash"] for block_data in unique_blocks}
                 if import_hashes:
                     hash_conflict_result = session.execute(
                         select(Block.hash, Block.chain_id)
                         .where(Block.hash.in_(import_hashes))
                     )
                     hash_conflicts = hash_conflict_result.all()
                     if hash_conflicts:
                         conflict_chains = {chain_id for _, chain_id in hash_conflicts}
                         _logger.warning(f"Clearing {len(hash_conflicts)} blocks with conflicting hashes across chains: {conflict_chains}")
                         session.execute(delete(Block).where(Block.hash.in_(import_hashes)))
                
                 session.commit()
                 session.expire_all()

                 _logger.info(f"Importing {len(unique_blocks)} unique blocks (filtered from {len(blocks)} total)")

                 for block_data in unique_blocks:
                     block_timestamp = _parse_datetime_value(block_data.get("timestamp"), "block timestamp") or datetime.utcnow()
                     block = Block(
                         chain_id=chain_id,
                         height=block_data["height"],
                         hash=block_data["hash"],
                         parent_hash=block_data["parent_hash"],
                         proposer=block_data["proposer"],
                         timestamp=block_timestamp,
                         state_root=block_data.get("state_root"),
                         tx_count=block_data.get("tx_count", 0),
                         block_metadata=block_data.get("block_metadata"),
                     )
                     session.add(block)

                 for account_data in accounts:
                     account_chain_id = account_data.get("chain_id", chain_id)
                     if account_chain_id != chain_id:
                         raise HTTPException(
                             status_code=400,
                             detail=f"Mismatched account chain_id '{account_chain_id}' for import chain '{chain_id}'",
                         )
                     account = Account(
                         chain_id=account_chain_id,
                         address=account_data["address"],
                         balance=account_data["balance"],
                         nonce=account_data["nonce"],
                     )
                     session.add(account)

                 for tx_data in transactions:
                     tx_chain_id = tx_data.get("chain_id", chain_id)
                     if tx_chain_id != chain_id:
                         raise HTTPException(
                             status_code=400,
                             detail=f"Mismatched transaction chain_id '{tx_chain_id}' for import chain '{chain_id}'",
                         )
                     tx = Transaction(
                         id=tx_data.get("id"),
                         chain_id=tx_chain_id,
                         tx_hash=str(tx_data.get("tx_hash") or tx_data.get("id") or ""),
                         block_height=tx_data.get("block_height"),
                         sender=tx_data["sender"],
                         recipient=tx_data["recipient"],
                         payload=tx_data.get("payload", {}),
                         value=tx_data.get("value", 0),
                         fee=tx_data.get("fee", 0),
                         nonce=tx_data.get("nonce", 0),
                         timestamp=_serialize_optional_timestamp(tx_data.get("timestamp")),
                         status=tx_data.get("status", "pending"),
                         tx_metadata=tx_data.get("tx_metadata"),
                     )
                     created_at = _parse_datetime_value(tx_data.get("created_at"), "transaction created_at")
                     if created_at is not None:
                         tx.created_at = created_at
                     session.add(tx)

                 session.commit()

                 return {
                    "success": True,
                    "imported_blocks": len(unique_blocks),
                    "imported_accounts": len(accounts),
                    "imported_transactions": len(transactions),
                    "chain_id": chain_id,
                    "message": f"Successfully imported {len(unique_blocks)} blocks",
                }

         except HTTPException:
             raise
         except Exception as e:
             _logger.error(f"Error importing chain: {e}")
             raise HTTPException(status_code=500, detail=f"Failed to import chain: {str(e)}")

@router.post("/force-sync", summary="Force reorg to specified peer")
async def force_sync(peer_data: dict) -> Dict[str, Any]:
     """Force blockchain reorganization to sync with specified peer"""
     try:
         peer_url = peer_data.get("peer_url")
         target_height = peer_data.get("target_height")

         if not peer_url:
             raise HTTPException(status_code=400, detail="peer_url is required")

         # Validate peer_url to prevent SSRF
         import re
         from urllib.parse import urlparse

         parsed = urlparse(peer_url)
         if not parsed.scheme or parsed.scheme not in ['http', 'https']:
             raise HTTPException(status_code=400, detail="Invalid URL scheme")
         
         # Block private/internal IPs
         hostname = parsed.hostname
         if hostname:
             # Block localhost and private IP ranges
             if hostname in ['localhost', '127.0.0.1', '::1'] or hostname.startswith('192.168.') or hostname.startswith('10.') or hostname.startswith('172.16.'):
                 raise HTTPException(status_code=400, detail="Invalid peer URL")

         import requests

         response = requests.get(f"{peer_url}/rpc/export-chain", timeout=30)

         if response.status_code != 200:
             raise HTTPException(status_code=400, detail=f"Failed to fetch peer chain: {response.status_code}")

         peer_chain_data = response.json()
         peer_blocks = peer_chain_data["export_data"]["blocks"]

         if target_height and len(peer_blocks) < target_height:
             raise HTTPException(status_code=400, detail=f"Peer only has {len(peer_blocks)} blocks, cannot sync to height {target_height}")

         import_result = await import_chain(peer_chain_data["export_data"])

         return {
            "success": True,
            "synced_from": peer_url,
            "synced_blocks": import_result["imported_blocks"],
            "target_height": target_height or import_result["imported_blocks"],
            "message": f"Successfully synced with peer {peer_url}"
        }

     except HTTPException:
         raise
     except Exception as e:
         _logger.error(f"Error forcing sync: {e}")
         raise HTTPException(status_code=500, detail=f"Failed to force sync: {str(e)}")


class GetLogsRequest(BaseModel):
    """Request model for eth_getLogs RPC endpoint."""
    address: Optional[str] = Field(None, description="Contract address to filter logs")
    from_block: Optional[int] = Field(None, description="Starting block height")
    to_block: Optional[int] = Field(None, description="Ending block height")
    topics: Optional[List[str]] = Field(None, description="Event topics to filter")


class LogEntry(BaseModel):
    """Single log entry from smart contract event."""
    address: str
    topics: List[str]
    data: str
    block_number: int
    transaction_hash: str
    log_index: int


class GetLogsResponse(BaseModel):
    """Response model for eth_getLogs RPC endpoint."""
    logs: List[LogEntry]
    count: int


@router.post("/eth_getLogs", summary="Query smart contract event logs")
async def get_logs(
    request: GetLogsRequest,
    chain_id: Optional[str] = None
) -> GetLogsResponse:
    """
    Query smart contract event logs using eth_getLogs-compatible endpoint.
    Filters Receipt model for logs matching contract address and event topics.
    """
    chain_id = get_chain_id(chain_id)

    with session_scope() as session:
        # Build query for receipts
        query = select(Receipt).where(Receipt.chain_id == chain_id)

        # Filter by block range
        if request.from_block is not None:
            query = query.where(Receipt.block_height >= request.from_block)
        if request.to_block is not None:
            query = query.where(Receipt.block_height <= request.to_block)

        # Execute query
        receipts = session.execute(query).scalars().all()

        logs = []
        for receipt in receipts:
            # Extract event logs from receipt payload
            payload = receipt.payload or {}
            events = payload.get("events", [])

            for event in events:
                # Filter by contract address if specified
                if request.address and event.get("address") != request.address:
                    continue

                # Filter by topics if specified
                if request.topics:
                    event_topics = event.get("topics", [])
                    if not any(topic in event_topics for topic in request.topics):
                        continue

                # Create log entry
                log_entry = LogEntry(
                    address=event.get("address", ""),
                    topics=event.get("topics", []),
                    data=str(event.get("data", "")),
                    block_number=receipt.block_height or 0,
                    transaction_hash=receipt.receipt_id,
                    log_index=event.get("logIndex", 0)
                )
                logs.append(log_entry)

        return GetLogsResponse(logs=logs, count=len(logs))
