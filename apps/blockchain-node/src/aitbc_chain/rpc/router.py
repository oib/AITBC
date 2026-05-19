from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from typing import Any, Dict, Optional, List
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel, Field, model_validator
from sqlmodel import select, delete

from ..database import session_scope, get_engine
from ..gossip import gossip_broker
from ..mempool import get_mempool
from ..metrics import metrics_registry
from ..models import Account, Block, Receipt, Transaction
from ..logger import get_logger
from ..sync import ChainSync
from ..contracts.agent_messaging_contract import messaging_contract
from .contract_service import contract_service
from .dispute_resolution_service import dispute_resolution_service
from ..network.island_manager import get_island_manager

from aitbc.rate_limiting import rate_limit

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
        return settings.chain_id or "ait-mainnet"
    return chain_id

def validate_chain_id(chain_id: str) -> bool:
    """Validate that chain_id is in supported_chains list"""
    from ..config import settings
    supported_chains = [c.strip() for c in settings.supported_chains.split(",")]
    return chain_id in supported_chains

def get_supported_chains() -> List[str]:
    from ..config import settings
    chains = [chain.strip() for chain in settings.supported_chains.split(",") if chain.strip()]
    if not chains and settings.chain_id:
        return [settings.chain_id]
    return chains

def get_chain_db(chain_id: str = None):
    """Get chain-specific database engine"""
    resolved_chain_id = get_chain_id(chain_id)
    if not validate_chain_id(resolved_chain_id):
        raise HTTPException(status_code=400, detail=f"Chain {resolved_chain_id} not in supported_chains")
    return get_engine(resolved_chain_id)

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
        except Exception:
            payload = {}
    
    if not isinstance(payload, dict):
        payload = {}

    return {
        "chain_id": chain_id,
        "type": tx_type,
        "from": sender.strip(),
        "to": recipient.strip(),
        "amount": amount,
        "value": amount,  # Add value field for state transition compatibility
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
    model_config = {"populate_by_name": True}
    
    type: str = Field(description="Transaction type, e.g. TRANSFER or RECEIPT_CLAIM")
    sender: str = Field(alias="from")
    nonce: int
    fee: int = Field(ge=0)
    payload: Dict[str, Any]
    sig: Optional[str] = Field(default=None, description="Signature payload")
    chain_id: Optional[str] = None

    @model_validator(mode="after")
    def normalize_type(self) -> "TransactionRequest":  # type: ignore[override]
        normalized = self.type.upper()
        if normalized not in {"TRANSFER", "RECEIPT_CLAIM"}:
            raise ValueError(f"unsupported transaction type: {self.type}")
        self.type = normalized

        # Support both payload shapes during migration:
        # - {"recipient": "...", "amount": ...}
        # - {"to": "...", "value": ...}
        if self.type == "TRANSFER":
            recipient = self.payload.get("recipient") or self.payload.get("to")
            if not recipient:
                raise ValueError("transfer payload requires 'recipient' (or legacy 'to')")
            self.payload["recipient"] = recipient
            self.payload.setdefault("to", recipient)

            if "amount" not in self.payload and "value" in self.payload:
                self.payload["amount"] = self.payload["value"]
            if "value" not in self.payload and "amount" in self.payload:
                self.payload["value"] = self.payload["amount"]

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



@router.get("/genesis_allocations", summary="Get genesis allocations from blockchain")
@rate_limit(rate=200, per=60)
async def get_genesis_allocations(
    request: Request, chain_id: str = None
) -> Dict[str, Any]:
    """Get genesis allocations from genesis block metadata for RPC bootstrap"""
    chain_id = get_chain_id(chain_id)
    
    with session_scope(chain_id) as session:
        # Get genesis block (height 0)
        genesis = session.exec(
            select(Block).where(Block.chain_id == chain_id).where(Block.height == 0)
        ).first()
        
        if not genesis:
            raise HTTPException(status_code=404, detail=f"Genesis block not found for chain {chain_id}")
        
        # Extract allocations from block metadata
        if not genesis.block_metadata:
            raise HTTPException(status_code=404, detail=f"Genesis block metadata not found for chain {chain_id}")
        
        try:
            metadata = json.loads(genesis.block_metadata)
            allocations = metadata.get("allocations", [])
            return {
                "chain_id": chain_id,
                "allocations": allocations,
                "genesis_hash": genesis.hash,
                "genesis_height": genesis.height,
                "genesis_state_root": genesis.state_root,  # Include the actual genesis state_root
            }
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse genesis block metadata: {e}")


@router.get("/head", summary="Get current chain head")
@rate_limit(rate=200, per=60)
async def get_head(
    request: Request, chain_id: str = None
) -> Dict[str, Any]:
    """Get current chain head"""
    chain_id = get_chain_id(chain_id)
    
    metrics_registry.increment("rpc_get_head_total")
    start = time.perf_counter()
    with session_scope(chain_id) as session:
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
@rate_limit(rate=200, per=60)
async def get_block(
    request: Request, height: int, chain_id: str = None
) -> Dict[str, Any]:
    """Get block by height"""
    chain_id = get_chain_id(chain_id)
    
    metrics_registry.increment("rpc_get_block_total")
    start = time.perf_counter()
    with session_scope(chain_id) as session:
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
@rate_limit(rate=50, per=60)
async def submit_transaction(
    request: Request, tx_data: TransactionRequest
) -> Dict[str, Any]:
    """Submit a new transaction to the mempool"""
    from ..mempool import get_mempool

    try:
        mempool = get_mempool()
        chain_id = get_chain_id(None)

        # Convert TransactionRequest to dict for normalization
        # Model validator already normalized payload, so use 'to' directly from payload
        tx_data_dict = {
            "from": tx_data.sender,
            "to": tx_data.payload.get("to"),  # Model validator sets this from recipient/to
            "amount": tx_data.payload.get("amount", tx_data.payload.get("value", 0)),
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
@rate_limit(rate=200, per=60)
async def get_mempool(
    request: Request, chain_id: str = None, limit: int = 100
) -> Dict[str, Any]:
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
@rate_limit(rate=200, per=60)
async def get_account(
    request: Request, address: str, chain_id: str = None
) -> Dict[str, Any]:
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
@rate_limit(rate=200, per=60)
async def get_account_alias(
    request: Request, address: str, chain_id: str = None
) -> Dict[str, Any]:
    """Get account information (alias endpoint)"""
    return await get_account(address, chain_id)


@router.post("/transactions/marketplace", summary="Submit marketplace transaction")
@rate_limit(rate=50, per=60)
async def submit_marketplace_transaction(
    request: Request, tx_data: Dict[str, Any]
) -> Dict[str, Any]:
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
                created_at=datetime.now(timezone.utc),
                nonce=tx_nonce,
                value=amount,
                fee=fee,
                status="pending",
                timestamp=datetime.now(timezone.utc).isoformat()
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
@rate_limit(rate=200, per=60)
async def query_transactions(
    request: Request,
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
@rate_limit(rate=200, per=60)
async def get_blocks_range(
    request: Request, start: int = 0, end: int = 10, include_tx: bool = True, chain_id: str = None
) -> Dict[str, Any]:
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
@rate_limit(rate=50, per=60)
async def deploy_messaging_contract(
    request: Request, deploy_data: dict
) -> Dict[str, Any]:
    """Deploy the agent messaging contract to the blockchain"""
    contract_address = "0xagent_messaging_001"
    return {"success": True, "contract_address": contract_address, "status": "deployed"}

@router.get("/contracts", summary="List deployed contracts")
@rate_limit(rate=200, per=60)
async def list_contracts(
    request: Request
) -> Dict[str, Any]:
    """List all deployed contracts"""
    return contract_service.list_contracts()

@router.post("/contracts/deploy", summary="Deploy a smart contract")
@rate_limit(rate=50, per=60)
async def deploy_contract(
    request: Request, deploy_data: dict
) -> Dict[str, Any]:
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
        "deployed_at": datetime.now(UTC).isoformat()
    }

@router.post("/contracts/call", summary="Call a contract method")
@rate_limit(rate=50, per=60)
async def call_contract(
    request: Request, call_data: dict
) -> Dict[str, Any]:
    """Call a method on a deployed contract"""
    contract_address = call_data.get("address")
    method = call_data.get("method")
    params = call_data.get("params")
    
    if not contract_address:
        return {"success": False, "error": "Contract address is required"}
    if not method:
        return {"success": False, "error": "Method name is required"}
    
    # Mock call result for now
    return {
        "success": True,
        "result": f"Called {method} on {contract_address}",
        "address": contract_address,
        "method": method
    }

@router.post("/contracts/verify", summary="Verify a ZK proof")
@rate_limit(rate=50, per=60)
async def verify_contract(
    request: Request, verify_data: dict
) -> Dict[str, Any]:
    """Verify a ZK proof against a contract"""
    contract_address = verify_data.get("address")
    proof = verify_data.get("proof")
    
    if not contract_address:
        return {"success": False, "error": "Contract address is required"}
    
    # Mock verification result for now
    return {
        "success": True,
        "result": {
            "valid": True,
            "receipt_hash": "0xmock_receipt_hash",
            "address": contract_address
        }
    }

@router.get("/contracts/messaging/state", summary="Get messaging contract state")
@rate_limit(rate=200, per=60)
async def get_messaging_contract_state(
    request: Request
) -> Dict[str, Any]:
    """Get the current state of the messaging contract"""
    state = {
        "total_topics": len(messaging_contract.topics),
        "total_messages": len(messaging_contract.messages),
        "total_agents": len(messaging_contract.agent_reputations)
    }
    return {"success": True, "contract_state": state}

@router.get("/messaging/topics", summary="Get forum topics")
@rate_limit(rate=200, per=60)
async def get_forum_topics(
    request: Request, limit: int = 50, offset: int = 0, sort_by: str = "last_activity"
) -> Dict[str, Any]:
    """Get list of forum topics"""
    return messaging_contract.get_topics(limit, offset, sort_by)

@router.post("/messaging/topics/create", summary="Create forum topic")
@rate_limit(rate=50, per=60)
async def create_forum_topic(
    request: Request, topic_data: dict
) -> Dict[str, Any]:
    """Create a new forum topic"""
    return messaging_contract.create_topic(
        topic_data.get("agent_id"),
        topic_data.get("agent_address"),
        topic_data.get("title"),
        topic_data.get("description"),
        topic_data.get("tags", [])
    )

@router.get("/messaging/topics/{topic_id}/messages", summary="Get topic messages")
@rate_limit(rate=200, per=60)
async def get_topic_messages(
    request: Request, topic_id: str, limit: int = 50, offset: int = 0, sort_by: str = "timestamp"
) -> Dict[str, Any]:
    """Get messages from a forum topic"""
    return messaging_contract.get_messages(topic_id, limit, offset, sort_by)

@router.post("/messaging/messages/post", summary="Post message")
@rate_limit(rate=50, per=60)
async def post_message(
    request: Request, message_data: dict
) -> Dict[str, Any]:
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
@rate_limit(rate=50, per=60)
async def vote_message(
    request: Request, message_id: str, vote_data: dict
) -> Dict[str, Any]:
    """Vote on a message (upvote/downvote)"""
    return messaging_contract.vote_message(
        vote_data.get("agent_id"),
        vote_data.get("agent_address"),
        message_id,
        vote_data.get("vote_type")
    )

@router.get("/messaging/messages/search", summary="Search messages")
@rate_limit(rate=200, per=60)
async def search_messages(
    request: Request, query: str, limit: int = 50
) -> Dict[str, Any]:
    """Search messages by content"""
    return messaging_contract.search_messages(query, limit)

@router.get("/messaging/agents/{agent_id}/reputation", summary="Get agent reputation")
@rate_limit(rate=200, per=60)
async def get_agent_reputation(
    request: Request, agent_id: str
) -> Dict[str, Any]:
    """Get agent reputation information"""
    return messaging_contract.get_agent_reputation(agent_id)

@router.post("/messaging/messages/{message_id}/moderate", summary="Moderate message")
@rate_limit(rate=50, per=60)
async def moderate_message(
    request: Request, message_id: str, moderation_data: dict
) -> Dict[str, Any]:
    """Moderate a message (moderator only)"""
    return messaging_contract.moderate_message(
        moderation_data.get("moderator_agent_id"),
        moderation_data.get("moderator_address"),
        message_id,
        moderation_data.get("action"),
        moderation_data.get("reason", "")
    )

@router.post("/importBlock", summary="Import a block")
@rate_limit(rate=50, per=60)
async def import_block(
    request: Request, block_data: dict
) -> Dict[str, Any]:
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
            block_hash = block_data["hash"]

            try:
                block_height = int(block_data["height"])
            except (KeyError, TypeError, ValueError) as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid block height") from exc

            timestamp = block_data.get("timestamp")
            if isinstance(timestamp, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                except ValueError:
                    timestamp = datetime.now(timezone.utc)
            elif timestamp is None:
                timestamp = datetime.now(timezone.utc)

            with session_scope(chain_id) as session:
                existing_height_block = session.exec(
                    select(Block)
                    .where(Block.chain_id == chain_id)
                    .where(Block.height == block_height)
                ).first()
                if existing_height_block is not None:
                    if existing_height_block.hash == block_hash:
                        return {
                            "success": True,
                            "block_height": existing_height_block.height,
                            "block_hash": existing_height_block.hash,
                            "chain_id": chain_id
                        }
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Block height {block_height} already exists with different hash",
                    )

                # Check for hash conflicts across chains
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
                    height=block_height,
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
        except HTTPException:
            raise
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
@rate_limit(rate=200, per=60)
async def export_chain(
    request: Request, chain_id: str = None
) -> Dict[str, Any]:
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
@rate_limit(rate=50, per=60)
async def import_chain(
    request: Request, import_data: dict
) -> Dict[str, Any]:
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
                     block_timestamp = _parse_datetime_value(block_data.get("timestamp"), "block timestamp") or datetime.now(timezone.utc)
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
@rate_limit(rate=50, per=60)
async def force_sync(
    request: Request, peer_data: dict
) -> Dict[str, Any]:
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
@rate_limit(rate=200, per=60)
async def get_logs(
    request: Request,
    logs_request: GetLogsRequest,
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


# Island Management Endpoints for Edge API
class JoinIslandRequest(BaseModel):
    """Request model for joining an island"""
    island_id: str
    island_name: str
    chain_id: str
    role: str = "compute-provider"
    is_hub: bool = False


class JoinIslandResponse(BaseModel):
    """Response model for joining an island"""
    success: bool
    island_id: str
    status: str
    message: str


class LeaveIslandRequest(BaseModel):
    """Request model for leaving an island"""
    island_id: str


class LeaveIslandResponse(BaseModel):
    """Response model for leaving an island"""
    success: bool
    island_id: str
    status: str
    message: str


class BridgeRequestRequest(BaseModel):
    """Request model for requesting a bridge"""
    target_island_id: str


class BridgeRequestResponse(BaseModel):
    """Response model for bridge request"""
    success: bool
    request_id: str
    target_island_id: str
    status: str
    message: str


# Dispute Resolution Endpoints
class FileDisputeRequest(BaseModel):
    """Request model for filing a dispute"""
    agreement_id: int = Field(description="ID of the agreement being disputed")
    respondent: str = Field(description="Address of the respondent")
    dispute_type: str = Field(description="Type of dispute (Performance, Payment, ServiceQuality, Availability, Other)")
    reason: str = Field(description="Reason for the dispute")
    evidence_hash: str = Field(description="Hash of initial evidence")


class FileDisputeResponse(BaseModel):
    """Response model for filing a dispute"""
    success: bool
    dispute_id: int
    status: str
    message: str


class SubmitEvidenceRequest(BaseModel):
    """Request model for submitting evidence"""
    dispute_id: int = Field(description="ID of the dispute")
    evidence_type: str = Field(description="Type of evidence")
    evidence_data: str = Field(description="Evidence data (IPFS hash, URL, etc.)")


class SubmitEvidenceResponse(BaseModel):
    """Response model for submitting evidence"""
    success: bool
    evidence_id: int
    status: str
    message: str


class VerifyEvidenceRequest(BaseModel):
    """Request model for verifying evidence"""
    dispute_id: int = Field(description="ID of the dispute")
    evidence_id: int = Field(description="ID of the evidence")
    is_valid: bool = Field(description="Whether the evidence is valid")
    verification_score: int = Field(description="Verification score (0-100)")


class VerifyEvidenceResponse(BaseModel):
    """Response model for verifying evidence"""
    success: bool
    status: str
    message: str


class SubmitArbitrationVoteRequest(BaseModel):
    """Request model for submitting arbitration vote"""
    dispute_id: int = Field(description="ID of the dispute")
    vote_in_favor_of_initiator: bool = Field(description="Vote for initiator")
    confidence: int = Field(description="Confidence level (0-100)")
    reasoning: str = Field(description="Reasoning for the vote")


class SubmitArbitrationVoteResponse(BaseModel):
    """Response model for submitting arbitration vote"""
    success: bool
    status: str
    message: str


class AuthorizeArbitratorRequest(BaseModel):
    """Request model for authorizing an arbitrator"""
    arbitrator: str = Field(description="Address of the arbitrator")
    reputation_score: int = Field(description="Initial reputation score")


class AuthorizeArbitratorResponse(BaseModel):
    """Response model for authorizing an arbitrator"""
    success: bool
    status: str
    message: str


class GetDisputeResponse(BaseModel):
    """Response model for getting dispute details"""
    dispute_id: int
    agreement_id: int
    initiator: str
    respondent: str
    status: str
    dispute_type: str
    reason: str
    evidence_hash: str
    filing_time: int
    evidence_deadline: int
    arbitration_deadline: int
    resolution_amount: int
    winner: str
    resolution_reason: str
    arbitrator_count: int
    is_escalated: bool
    escalation_level: int


class GetEvidenceResponse(BaseModel):
    """Response model for getting dispute evidence"""
    evidence_id: int
    dispute_id: int
    submitter: str
    evidence_type: str
    evidence_data: str
    evidence_hash: str
    submission_time: int
    is_valid: bool
    verification_score: int
    verified_by: str


class GetArbitrationVotesResponse(BaseModel):
    """Response model for getting arbitration votes"""
    dispute_id: int
    arbitrator: str
    vote_in_favor_of_initiator: bool
    confidence: int
    reasoning: str
    vote_time: int
    is_valid: bool


@router.post("/disputes/file", summary="File a new dispute")
async def file_dispute(request: FileDisputeRequest) -> FileDisputeResponse:
    """
    File a new dispute for a marketplace transaction.
    This interacts with the DisputeResolution smart contract.
    """
    try:
        # Use dispute resolution service
        result = dispute_resolution_service.file_dispute(
            agreement_id=request.agreement_id,
            respondent=request.respondent,
            dispute_type=request.dispute_type,
            reason=request.reason,
            evidence_hash=request.evidence_hash,
            sender_address="0x0000000000000000000000000000000000000000"  # TODO: Get from auth
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to file dispute"))
        
        return FileDisputeResponse(
            success=True,
            dispute_id=result["dispute_id"],
            status=result["status"],
            message=result["message"]
        )
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Error filing dispute: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to file dispute: {str(e)}")


@router.post("/disputes/evidence", summary="Submit evidence for a dispute")
async def submit_evidence(request: SubmitEvidenceRequest) -> SubmitEvidenceResponse:
    """
    Submit evidence for a dispute.
    This interacts with the DisputeResolution smart contract.
    """
    try:
        result = dispute_resolution_service.submit_evidence(
            dispute_id=request.dispute_id,
            evidence_type=request.evidence_type,
            evidence_data=request.evidence_data,
            submitter_address="0x0000000000000000000000000000000000000000"  # TODO: Get from auth
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to submit evidence"))
        
        return SubmitEvidenceResponse(
            success=True,
            evidence_id=result["evidence_id"],
            status=result["status"],
            message=result["message"]
        )
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Error submitting evidence: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit evidence: {str(e)}")


@router.post("/disputes/verify-evidence", summary="Verify evidence (arbitrator only)")
async def verify_evidence(request: VerifyEvidenceRequest) -> VerifyEvidenceResponse:
    """
    Verify evidence submitted in a dispute.
    This can only be called by authorized arbitrators.
    """
    try:
        result = dispute_resolution_service.verify_evidence(
            dispute_id=request.dispute_id,
            evidence_id=request.evidence_id,
            is_valid=request.is_valid,
            verification_score=request.verification_score,
            arbitrator_address="0x0000000000000000000000000000000000000000"  # TODO: Get from auth
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to verify evidence"))
        
        return VerifyEvidenceResponse(
            success=True,
            status=result["status"],
            message=result["message"]
        )
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Error verifying evidence: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to verify evidence: {str(e)}")


@router.post("/disputes/vote", summary="Submit arbitration vote (arbitrator only)")
async def submit_arbitration_vote(request: SubmitArbitrationVoteRequest) -> SubmitArbitrationVoteResponse:
    """
    Submit an arbitration vote for a dispute.
    This can only be called by authorized arbitrators assigned to the dispute.
    """
    try:
        # TODO: Implement actual smart contract interaction with arbitrator authorization check
        
        return SubmitArbitrationVoteResponse(
            success=True,
            status="Submitted",
            message=f"Vote submitted successfully for dispute {request.dispute_id}"
        )
    except Exception as e:
        _logger.error(f"Error submitting arbitration vote: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit vote: {str(e)}")


@router.post("/disputes/arbitrators/authorize", summary="Authorize an arbitrator (admin only)")
async def authorize_arbitrator(request: AuthorizeArbitratorRequest) -> AuthorizeArbitratorResponse:
    """
    Authorize a new arbitrator.
    This can only be called by the contract owner.
    """
    try:
        result = dispute_resolution_service.authorize_arbitrator(
            arbitrator_address=request.arbitrator,
            reputation_score=request.reputation_score,
            owner_address="0x0000000000000000000000000000000000000000"  # TODO: Get from auth
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to authorize arbitrator"))
        
        return AuthorizeArbitratorResponse(
            success=True,
            status=result["status"],
            message=result["message"]
        )
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Error authorizing arbitrator: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to authorize arbitrator: {str(e)}")


@router.get("/disputes/active", summary="Get all active disputes")
async def get_active_disputes() -> Dict[str, Any]:
    """
    Get all active disputes.
    This retrieves information from the DisputeResolution smart contract.
    """
    try:
        result = dispute_resolution_service.get_active_disputes()
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to get active disputes"))
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Error getting active disputes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get active disputes: {str(e)}")


@router.get("/disputes/arbitrators", summary="Get all authorized arbitrators")
async def get_authorized_arbitrators() -> Dict[str, Any]:
    """
    Get all authorized arbitrators.
    This retrieves information from the DisputeResolution smart contract.
    """
    try:
        result = dispute_resolution_service.get_authorized_arbitrators()
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to get authorized arbitrators"))
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Error getting authorized arbitrators: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get authorized arbitrators: {str(e)}")


@router.get("/disputes/arbitrators/{arbitrator_address}", summary="Get disputes for an arbitrator")
async def get_arbitrator_disputes(arbitrator_address: str) -> Dict[str, Any]:
    """
    Get all disputes assigned to an arbitrator.
    This retrieves information from the DisputeResolution smart contract.
    """
    try:
        result = dispute_resolution_service.get_arbitrator_disputes(arbitrator_address)
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to get arbitrator disputes"))
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Error getting arbitrator disputes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get arbitrator disputes: {str(e)}")


@router.get("/disputes/user/{user_address}", summary="Get disputes for a user")
async def get_user_disputes(user_address: str) -> Dict[str, Any]:
    """
    Get all disputes for a specific user.
    This retrieves information from the DisputeResolution smart contract.
    """
    try:
        result = dispute_resolution_service.get_user_disputes(user_address)
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to get user disputes"))
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Error getting user disputes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get user disputes: {str(e)}")


@router.get("/disputes/{dispute_id}", summary="Get dispute details")
async def get_dispute(dispute_id: int) -> GetDisputeResponse:
    """
    Get details of a specific dispute.
    This retrieves information from the DisputeResolution smart contract.
    """
    try:
        result = dispute_resolution_service.get_dispute(dispute_id)
        
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error", "Dispute not found"))
        
        dispute_data = result["dispute"]
        return GetDisputeResponse(**dispute_data)
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Error getting dispute: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get dispute: {str(e)}")


@router.get("/disputes/{dispute_id}/evidence", summary="Get evidence for a dispute")
async def get_dispute_evidence(dispute_id: int) -> List[GetEvidenceResponse]:
    """
    Get all evidence submitted for a dispute.
    This retrieves information from the DisputeResolution smart contract.
    """
    try:
        result = dispute_resolution_service.get_dispute_evidence(dispute_id)
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to get dispute evidence"))
        
        return [GetEvidenceResponse(**e) for e in result["evidence"]]
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Error getting dispute evidence: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get dispute evidence: {str(e)}")


@router.get("/disputes/{dispute_id}/votes", summary="Get arbitration votes for a dispute")
async def get_arbitration_votes(dispute_id: int) -> List[GetArbitrationVotesResponse]:
    """
    Get all arbitration votes for a dispute.
    This retrieves information from the DisputeResolution smart contract.
    """
    try:
        result = dispute_resolution_service.get_arbitration_votes(dispute_id)
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to get arbitration votes"))
        
        return [GetArbitrationVotesResponse(**v) for v in result["votes"]]
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Error getting arbitration votes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get arbitration votes: {str(e)}")


@router.post("/islands/join", summary="Join an island")
async def join_island(request: JoinIslandRequest) -> JoinIslandResponse:
    """
    Join an island for edge compute operations.
    Calls IslandManager.join_island to register the node as a member of the specified island.
    """
    island_manager = get_island_manager()
    if island_manager is None:
        raise HTTPException(status_code=503, detail="Island manager not available")
    
    success = island_manager.join_island(
        island_id=request.island_id,
        island_name=request.island_name,
        chain_id=request.chain_id,
        is_hub=request.is_hub
    )
    
    if success:
        return JoinIslandResponse(
            success=True,
            island_id=request.island_id,
            status="joined",
            message=f"Successfully joined island {request.island_id}"
        )
    else:
        return JoinIslandResponse(
            success=False,
            island_id=request.island_id,
            status="failed",
            message=f"Failed to join island {request.island_id} (may already be a member)"
        )


@router.post("/islands/leave", summary="Leave an island")
async def leave_island(request: LeaveIslandRequest) -> LeaveIslandResponse:
    """
    Leave an island.
    Calls IslandManager.leave_island to remove the node from the specified island.
    """
    island_manager = get_island_manager()
    if island_manager is None:
        raise HTTPException(status_code=503, detail="Island manager not available")
    
    success = island_manager.leave_island(request.island_id)
    
    if success:
        return LeaveIslandResponse(
            success=True,
            island_id=request.island_id,
            status="left",
            message=f"Successfully left island {request.island_id}"
        )
    else:
        return LeaveIslandResponse(
            success=False,
            island_id=request.island_id,
            status="failed",
            message=f"Failed to leave island {request.island_id} (may not be a member)"
        )


@router.get("/islands", summary="List all islands")
@rate_limit(rate=100, per=60)
async def list_islands() -> Dict[str, Any]:
    """
    List all islands that the node is a member of.
    Calls IslandManager.get_all_islands to retrieve island memberships.
    """
    island_manager = get_island_manager()
    if island_manager is None:
        raise HTTPException(status_code=503, detail="Island manager not available")
    
    islands = island_manager.get_all_islands()
    
    return {
        "islands": [
            {
                "island_id": island.island_id,
                "island_name": island.island_name,
                "chain_id": island.chain_id,
                "status": island.status.value,
                "role": getattr(island, 'role', 'unknown'),
                "peer_count": island.peer_count,
                "is_hub": island.is_hub,
                "joined_at": island.joined_at
            }
            for island in islands
        ],
        "total": len(islands)
    }


@router.get("/islands/{island_id}", summary="Get island details")
@rate_limit(rate=100, per=60)
async def get_island(island_id: str) -> Dict[str, Any]:
    """
    Get details about a specific island.
    Calls IslandManager.get_island_info to retrieve island membership details.
    """
    island_manager = get_island_manager()
    if island_manager is None:
        raise HTTPException(status_code=503, detail="Island manager not available")
    
    island = island_manager.get_island_info(island_id)
    
    if island is None:
        raise HTTPException(status_code=404, detail=f"Island {island_id} not found")
    
    return {
        "island_id": island.island_id,
        "island_name": island.island_name,
        "chain_id": island.chain_id,
        "status": island.status.value,
        "role": getattr(island, 'role', 'unknown'),
        "peer_count": island.peer_count,
        "is_hub": island.is_hub,
        "joined_at": island.joined_at
    }


@router.post("/islands/bridge", summary="Request a bridge to another island")
async def request_bridge(request: BridgeRequestRequest) -> BridgeRequestResponse:
    """
    Request a bridge to another island for cross-island communication.
    Calls IslandManager.request_bridge to initiate a bridge request.
    """
    island_manager = get_island_manager()
    if island_manager is None:
        raise HTTPException(status_code=503, detail="Island manager not available")
    
    request_id = island_manager.request_bridge(request.target_island_id)
    
    if request_id:
        return BridgeRequestResponse(
            success=True,
            request_id=request_id,
            target_island_id=request.target_island_id,
            status="pending",
            message=f"Bridge request {request_id} submitted for {request.target_island_id}"
        )
    else:
        return BridgeRequestResponse(
            success=False,
            request_id="",
            target_island_id=request.target_island_id,
            status="failed",
            message=f"Failed to request bridge to {request.target_island_id} (may already be a member)"
        )


@router.get("/accounts/{address}", summary="Get account details")
@rate_limit(rate=200, per=60)
async def get_account(
    request: Request,
    address: str,
    chain_id: str = None
) -> Dict[str, Any]:
    """
    Get account details including balance and nonce.
    
    Args:
        address: The account address
        chain_id: Optional chain ID (defaults to node's chain)
    
    Returns:
        Account details or 404 if not found
    """
    chain_id = get_chain_id(chain_id)
    address = address.lower().strip()
    
    with session_scope() as session:
        account = session.get(Account, (chain_id, address))
        if not account:
            raise HTTPException(status_code=404, detail=f"Account {address} not found on chain {chain_id}")
        
        return {
            "success": True,
            "address": account.address,
            "chain_id": account.chain_id,
            "balance": account.balance,
            "nonce": account.nonce,
            "updated_at": account.updated_at.isoformat() if account.updated_at else None
        }


@router.post("/register-account", summary="Create/register a new account on the blockchain")
@rate_limit(rate=100, per=60)
async def create_account(
    request: Request,
    account_data: dict
) -> Dict[str, Any]:
    """
    Create or register a new account on the blockchain.
    
    This endpoint allows wallets to register their public keys as accounts
    on the blockchain, enabling them to send and receive transactions.
    
    Args:
        account_data: Dictionary containing:
            - address: The account address/public key (hex string)
            - chain_id: Optional chain ID (defaults to node's chain)
    
    Returns:
        Dictionary with success status and account details
    """
    chain_id = get_chain_id(account_data.get("chain_id"))
    address = account_data.get("address")
    
    if not address:
        raise HTTPException(status_code=400, detail="address is required")
    
    # Normalize address (ensure lowercase hex)
    address = address.lower().strip()
    if not address.startswith("0x"):
        address = "0x" + address
    
    # Validate address format (should be hex)
    if not all(c in "0123456789abcdef" for c in address[2:]):
        raise HTTPException(status_code=400, detail="address must be a valid hex string")
    
    with session_scope() as session:
        # Check if account already exists
        existing_account = session.get(Account, (chain_id, address))
        if existing_account:
            return {
                "success": True,
                "address": address,
                "chain_id": chain_id,
                "balance": existing_account.balance,
                "nonce": existing_account.nonce,
                "created": False,
                "message": "Account already exists"
            }
        
        # Create new account with zero balance
        new_account = Account(
            chain_id=chain_id,
            address=address,
            balance=0,
            nonce=0
        )
        session.add(new_account)
        session.commit()
        
        _logger.info(f"Created new account: address={address}, chain_id={chain_id}")
        
        return {
            "success": True,
            "address": address,
            "chain_id": chain_id,
            "balance": 0,
            "nonce": 0,
            "created": True,
            "message": "Account created successfully"
        }


@router.post("/faucet", summary="Request test tokens from faucet")
@rate_limit(rate=10, per=3600)  # 10 requests per hour per IP
async def faucet_request(
    request: Request,
    faucet_data: dict
) -> Dict[str, Any]:
    """
    Request test tokens from the blockchain faucet.
    
    This endpoint allows newly created wallets to receive initial funds
    for testing and development purposes.
    
    Args:
        faucet_data: Dictionary containing:
            - address: The account address to fund
            - amount: Optional amount to request (default: 1000000)
            - chain_id: Optional chain ID (defaults to node's chain)
    
    Returns:
        Dictionary with success status and transaction details
    """
    chain_id = get_chain_id(faucet_data.get("chain_id"))
    address = faucet_data.get("address")
    amount = faucet_data.get("amount", 1000000)  # Default 1M units
    
    if not address:
        raise HTTPException(status_code=400, detail="address is required")
    
    # Normalize address
    address = address.lower().strip()
    if not address.startswith("0x"):
        address = "0x" + address
    
    # Validate address format
    if not all(c in "0123456789abcdef" for c in address[2:]):
        raise HTTPException(status_code=400, detail="address must be a valid hex string")
    
    # Cap max faucet amount
    if amount > 10000000:  # Max 10M per request
        amount = 10000000
    
    with session_scope() as session:
        # Check if account exists
        account = session.get(Account, (chain_id, address))
        if not account:
            # Auto-create account if it doesn't exist
            account = Account(chain_id=chain_id, address=address, balance=0, nonce=0)
            session.add(account)
            session.flush()
            _logger.info(f"Faucet auto-created account: {address}")
        
        # Generate faucet transaction (special minting transaction)
        timestamp = datetime.now(timezone.utc)
        tx_hash = hashlib.sha256(
            f"faucet:{address}:{amount}:{timestamp.isoformat()}:{uuid.uuid4()}".encode()
        ).hexdigest()
        
        # Apply balance update directly (faucet is special system tx)
        account.balance += amount
        session.add(account)
        
        # Create faucet transaction record
        faucet_tx = Transaction(
            chain_id=chain_id,
            tx_hash=tx_hash,
            sender="faucet",
            recipient=address,
            payload={"type": "FAUCET", "amount": amount, "reason": "test_funding"},
            value=amount,
            fee=0,
            nonce=0,
            timestamp=timestamp,
            block_height=None,  # Not in a block - direct system tx
            status="confirmed",
            type="FAUCET"
        )
        session.add(faucet_tx)
        session.commit()
        
        _logger.info(f"Faucet funded {address} with {amount} units on {chain_id}")
        
        return {
            "success": True,
            "tx_hash": tx_hash,
            "address": address,
            "amount": amount,
            "chain_id": chain_id,
            "new_balance": account.balance,
            "message": f"Successfully funded {address} with {amount} units"
        }


@router.post("/bridge/lock", summary="Lock funds for cross-chain transfer")
@rate_limit(rate=20, per=60)
async def bridge_lock(
    request: Request,
    lock_data: dict
) -> Dict[str, Any]:
    """
    Initiate a cross-chain bridge transfer by locking funds.
    
    This is step 1 of the atomic bridge:
    1. Lock funds on source chain (this endpoint)
    2. Generate proof
    3. Confirm on target chain
    """
    try:
        from ..cross_chain.bridge import get_cross_chain_bridge
        bridge = get_cross_chain_bridge()
        
        if not bridge:
            raise HTTPException(status_code=503, detail="Cross-chain bridge not initialized")
        
        source_chain = lock_data.get("source_chain", get_chain_id(None))
        target_chain = lock_data.get("target_chain")
        sender = lock_data.get("sender")
        recipient = lock_data.get("recipient")
        amount = lock_data.get("amount", 0)
        asset = lock_data.get("asset", "native")
        
        if not all([target_chain, sender, recipient]):
            raise HTTPException(status_code=400, detail="Missing required fields: target_chain, sender, recipient")
        
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")
        
        # Execute lock
        transfer = bridge.initiate_transfer(
            source_chain=source_chain,
            target_chain=target_chain,
            sender=sender.lower(),
            recipient=recipient.lower(),
            amount=amount,
            asset=asset
        )
        
        return {
            "success": True,
            "transfer_id": transfer.transfer_id,
            "status": transfer.status.value,
            "source_chain": source_chain,
            "target_chain": target_chain,
            "sender": sender,
            "recipient": recipient,
            "amount": amount,
            "fee": (amount * 10) // 10000,  # 0.1% fee
            "lock_time": transfer.lock_time.isoformat() if transfer.lock_time else None,
            "message": "Funds locked successfully. Use /bridge/confirm to complete."
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        _logger.error(f"Bridge lock failed: {e}")
        raise HTTPException(status_code=500, detail=f"Bridge lock failed: {str(e)}")


@router.post("/bridge/confirm", summary="Confirm and release cross-chain transfer")
@rate_limit(rate=20, per=60)
async def bridge_confirm(
    request: Request,
    confirm_data: dict
) -> Dict[str, Any]:
    """
    Confirm a cross-chain bridge transfer and release funds.
    
    This is step 2 of the atomic bridge:
    1. Validate proof of lock
    2. Release funds on target chain
    3. Mark transfer as complete
    """
    try:
        from ..cross_chain.bridge import get_cross_chain_bridge
        bridge = get_cross_chain_bridge()
        
        if not bridge:
            raise HTTPException(status_code=503, detail="Cross-chain bridge not initialized")
        
        transfer_id = confirm_data.get("transfer_id")
        proof = confirm_data.get("proof")
        
        if not transfer_id or not proof:
            raise HTTPException(status_code=400, detail="Missing required fields: transfer_id, proof")
        
        # Execute confirmation
        transfer = bridge.confirm_transfer(transfer_id, proof)
        
        return {
            "success": True,
            "transfer_id": transfer.transfer_id,
            "status": transfer.status.value,
            "source_chain": transfer.source_chain,
            "target_chain": transfer.target_chain,
            "sender": transfer.sender,
            "recipient": transfer.recipient,
            "amount": transfer.amount,
            "target_tx_hash": transfer.target_tx_hash,
            "confirm_time": transfer.confirm_time.isoformat() if transfer.confirm_time else None,
            "message": "Cross-chain transfer completed successfully"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        _logger.error(f"Bridge confirm failed: {e}")
        raise HTTPException(status_code=500, detail=f"Bridge confirm failed: {str(e)}")


@router.get("/bridge/transfer/{transfer_id}", summary="Get transfer status")
@rate_limit(rate=100, per=60)
async def get_bridge_transfer(
    request: Request,
    transfer_id: str
) -> Dict[str, Any]:
    """Get the status of a cross-chain transfer"""
    try:
        from ..cross_chain.bridge import get_cross_chain_bridge
        bridge = get_cross_chain_bridge()
        
        if not bridge:
            raise HTTPException(status_code=503, detail="Cross-chain bridge not initialized")
        
        transfer = bridge.get_transfer(transfer_id)
        if not transfer:
            raise HTTPException(status_code=404, detail=f"Transfer {transfer_id} not found")
        
        return {
            "success": True,
            "transfer_id": transfer.transfer_id,
            "status": transfer.status.value,
            "source_chain": transfer.source_chain,
            "target_chain": transfer.target_chain,
            "sender": transfer.sender,
            "recipient": transfer.recipient,
            "amount": transfer.amount,
            "asset": transfer.asset,
            "source_tx_hash": transfer.source_tx_hash,
            "target_tx_hash": transfer.target_tx_hash,
            "lock_time": transfer.lock_time.isoformat() if transfer.lock_time else None,
            "confirm_time": transfer.confirm_time.isoformat() if transfer.confirm_time else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Get bridge transfer failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get transfer: {str(e)}")


@router.get("/bridge/pending", summary="List pending bridge transfers")
@rate_limit(rate=50, per=60)
async def list_pending_transfers(
    request: Request,
    chain_id: str = None
) -> List[Dict[str, Any]]:
    """List all pending cross-chain transfers"""
    try:
        from ..cross_chain.bridge import get_cross_chain_bridge
        bridge = get_cross_chain_bridge()
        
        if not bridge:
            raise HTTPException(status_code=503, detail="Cross-chain bridge not initialized")
        
        chain_id = get_chain_id(chain_id)
        transfers = bridge.list_pending_transfers(chain_id)
        
        return [
            {
                "transfer_id": t.transfer_id,
                "source_chain": t.source_chain,
                "target_chain": t.target_chain,
                "sender": t.sender,
                "recipient": t.recipient,
                "amount": t.amount,
                "status": t.status.value,
                "lock_time": t.lock_time.isoformat() if t.lock_time else None
            }
            for t in transfers
        ]
        
    except Exception as e:
        _logger.error(f"List pending transfers failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list transfers: {str(e)}")


@router.post("/staking/stake", summary="Stake tokens")
@rate_limit(rate=20, per=60)
async def stake_tokens(
    request: Request,
    stake_data: dict
) -> Dict[str, Any]:
    """
    Stake tokens for consensus participation.
    
    Locks tokens for a specified period. Staked tokens earn rewards
    and provide voting power in consensus.
    """
    chain_id = get_chain_id(stake_data.get("chain_id"))
    address = stake_data.get("address")
    amount = stake_data.get("amount", 0)
    lock_days = stake_data.get("lock_days", 30)
    
    if not address:
        raise HTTPException(status_code=400, detail="address is required")
    
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    
    # Normalize address
    address = address.lower().strip()
    if not address.startswith("0x"):
        address = "0x" + address
    
    with session_scope() as session:
        # Get account
        account = session.get(Account, (chain_id, address))
        if not account:
            raise HTTPException(status_code=404, detail=f"Account {address} not found")
        
        if account.balance < amount:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient balance: {account.balance} < {amount}"
            )
        
        # Lock tokens (deduct from balance)
        account.balance -= amount
        session.add(account)
        
        # Calculate lock period
        locked_until = datetime.now(timezone.utc)
        locked_until = locked_until.replace(day=locked_until.day + lock_days)
        
        # Create stake record
        stake = Stake(
            chain_id=chain_id,
            address=address,
            amount=amount,
            locked_until=locked_until,
            status="active"
        )
        session.add(stake)
        session.commit()
        
        _logger.info(f"Tokens staked: {address} staked {amount} on {chain_id}")
        
        return {
            "success": True,
            "stake_id": stake.id,
            "address": address,
            "amount": amount,
            "chain_id": chain_id,
            "locked_until": locked_until.isoformat(),
            "status": "active",
            "remaining_balance": account.balance
        }


@router.post("/staking/unstake", summary="Unstake tokens")
@rate_limit(rate=10, per=60)
async def unstake_tokens(
    request: Request,
    unstake_data: dict
) -> Dict[str, Any]:
    """
    Unstake tokens after lock period expires.
    
    Returns staked tokens to account balance.
    """
    chain_id = get_chain_id(unstake_data.get("chain_id"))
    address = unstake_data.get("address")
    stake_id = unstake_data.get("stake_id")
    
    if not address or not stake_id:
        raise HTTPException(status_code=400, detail="address and stake_id are required")
    
    # Normalize address
    address = address.lower().strip()
    if not address.startswith("0x"):
        address = "0x" + address
    
    with session_scope() as session:
        # Get stake record
        stake = session.get(Stake, stake_id)
        if not stake:
            raise HTTPException(status_code=404, detail=f"Stake {stake_id} not found")
        
        if stake.address != address:
            raise HTTPException(status_code=403, detail="Not authorized to unstake")
        
        if stake.status != "active":
            raise HTTPException(status_code=400, detail=f"Stake is not active: {stake.status}")
        
        # Check if lock period expired
        now = datetime.now(timezone.utc)
        if stake.locked_until and now < stake.locked_until:
            raise HTTPException(
                status_code=400,
                detail=f"Lock period not expired. Locked until: {stake.locked_until.isoformat()}"
            )
        
        # Return tokens to account
        account = session.get(Account, (chain_id, address))
        if not account:
            # Account was deleted, recreate
            account = Account(chain_id=chain_id, address=address, balance=0, nonce=0)
            session.add(account)
        
        account.balance += stake.amount
        session.add(account)
        
        # Update stake status
        stake.status = "withdrawn"
        session.add(stake)
        session.commit()
        
        _logger.info(f"Tokens unstaked: {address} recovered {stake.amount} from stake {stake_id}")
        
        return {
            "success": True,
            "stake_id": stake_id,
            "address": address,
            "amount": stake.amount,
            "chain_id": chain_id,
            "new_balance": account.balance,
            "status": "withdrawn"
        }


@router.get("/staking/{address}", summary="Get staking info")
@rate_limit(rate=100, per=60)
async def get_staking_info(
    request: Request,
    address: str,
    chain_id: str = None
) -> Dict[str, Any]:
    """Get staking information for an address"""
    chain_id = get_chain_id(chain_id)
    address = address.lower().strip()
    
    with session_scope() as session:
        from sqlalchemy import select, func
        
        # Get all stakes for address
        statement = select(Stake).where(
            Stake.chain_id == chain_id,
            Stake.address == address
        )
        stakes = session.exec(statement).all()
        
        total_staked = sum(s.amount for s in stakes if s.status == "active")
        active_stakes = [
            {
                "stake_id": s.id,
                "amount": s.amount,
                "locked_until": s.locked_until.isoformat() if s.locked_until else None,
                "status": s.status,
                "created_at": s.created_at.isoformat() if s.created_at else None
            }
            for s in stakes if s.status == "active"
        ]
        
        return {
            "success": True,
            "address": address,
            "chain_id": chain_id,
            "total_staked": total_staked,
            "active_stake_count": len(active_stakes),
            "active_stakes": active_stakes
        }


@router.get("/balance/{address}", summary="Get detailed balance breakdown")
@rate_limit(rate=100, per=60)
async def get_balance_breakdown(
    request: Request,
    address: str,
    chain_id: str = None
) -> Dict[str, Any]:
    """
    Get detailed balance breakdown including:
    - Available balance
    - Staked amount
    - Bridge-locked amount
    - Total balance
    """
    try:
        from ..services.balance_tracker import get_balance_tracker
        tracker = get_balance_tracker()
        
        if not tracker:
            raise HTTPException(status_code=503, detail="Balance tracker not initialized")
        
        chain_id = get_chain_id(chain_id)
        address = address.lower().strip()
        
        breakdown = tracker.get_balance_breakdown(address, chain_id)
        return breakdown
        
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Failed to get balance breakdown: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get balance: {str(e)}")


@router.get("/balance/{address}/reconcile", summary="Reconcile balance")
@rate_limit(rate=20, per=60)
async def reconcile_balance(
    request: Request,
    address: str,
    chain_id: str = None
) -> Dict[str, Any]:
    """
    Reconcile account balance against all recorded operations.
    
    Verifies that current balance matches expected balance
    based on all transactions, stakes, and bridge operations.
    """
    try:
        from ..services.balance_tracker import get_balance_tracker
        tracker = get_balance_tracker()
        
        if not tracker:
            raise HTTPException(status_code=503, detail="Balance tracker not initialized")
        
        chain_id = get_chain_id(chain_id)
        address = address.lower().strip()
        
        result = tracker.reconcile_balance(address, chain_id)
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Balance reconciliation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Reconciliation failed: {str(e)}")
