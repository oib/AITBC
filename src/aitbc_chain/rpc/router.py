from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import datetime
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlmodel import select

from ..config import settings
from ..database import session_scope
from ..gossip import gossip_broker
from ..mempool import get_mempool
from ..metrics import metrics_registry
from ..models import Account, Block, Receipt, Transaction

router = APIRouter()


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


class MintFaucetRequest(BaseModel):
    address: str
    amount: int = Field(gt=0)


@router.get("/head", summary="Get current chain head")
async def get_head() -> Dict[str, Any]:
    metrics_registry.increment("rpc_get_head_total")
    start = time.perf_counter()
    with session_scope() as session:
        result = session.exec(select(Block).order_by(Block.height.desc()).limit(1)).first()
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
    metrics_registry.observe("rpc_get_block_duration_seconds", time.perf_counter() - start)
    return {
            "proposer": block.proposer,
            "proposer": block.proposer,
        "height": block.height,
        "hash": block.hash,
        "parent_hash": block.parent_hash,
        "timestamp": block.timestamp.isoformat(),
        "tx_count": block.tx_count,
        "state_root": block.state_root,
    }


@router.get("/blocks-range", summary="Get blocks in range")
async def get_blocks_range(start_height: int = 0, end_height: int = 100, limit: int = 1000) -> List[Dict[str, Any]]:
    metrics_registry.increment("rpc_get_blocks_range_total")
    start = time.perf_counter()
    
    # Validate parameters
    if limit > 10000:
        limit = 10000
    if end_height - start_height > limit:
        end_height = start_height + limit
    
    with session_scope() as session:
        stmt = (
            select(Block)
            .where(Block.height >= start_height)
            .where(Block.height <= end_height)
            .order_by(Block.height)
        )
        blocks = session.exec(stmt).all()
        
    metrics_registry.observe("rpc_get_blocks_range_duration_seconds", time.perf_counter() - start)
    return [
        {
            "proposer": block.proposer,
            "proposer": block.proposer,
            "height": block.height,
            "hash": block.hash,
            "parent_hash": block.parent_hash,
            "timestamp": block.timestamp.isoformat(),
            "tx_count": block.tx_count,
            "state_root": block.state_root,
        }
        for block in blocks
    ]

@router.get("/tx/{tx_hash}", summary="Get transaction by hash")
async def get_transaction(tx_hash: str) -> Dict[str, Any]:
    metrics_registry.increment("rpc_get_transaction_total")
    start = time.perf_counter()
    with session_scope() as session:
        tx = session.exec(select(Transaction).where(Transaction.tx_hash == tx_hash)).first()
        if tx is None:
            metrics_registry.increment("rpc_get_transaction_not_found_total")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="transaction not found")
        metrics_registry.increment("rpc_get_transaction_success_total")
    metrics_registry.observe("rpc_get_transaction_duration_seconds", time.perf_counter() - start)
    return {
        "tx_hash": tx.tx_hash,
        "block_height": tx.block_height,
        "sender": tx.sender,
        "recipient": tx.recipient,
        "payload": tx.payload,
        "created_at": tx.created_at.isoformat(),
    }


@router.get("/receipts/{receipt_id}", summary="Get receipt by ID")
async def get_receipt(receipt_id: str) -> Dict[str, Any]:
    metrics_registry.increment("rpc_get_receipt_total")
    start = time.perf_counter()
    with session_scope() as session:
        receipt = session.exec(select(Receipt).where(Receipt.receipt_id == receipt_id)).first()
        if receipt is None:
            metrics_registry.increment("rpc_get_receipt_not_found_total")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="receipt not found")
        metrics_registry.increment("rpc_get_receipt_success_total")
    metrics_registry.observe("rpc_get_receipt_duration_seconds", time.perf_counter() - start)
    return _serialize_receipt(receipt)


@router.get("/getBalance/{address}", summary="Get account balance")
async def get_balance(address: str) -> Dict[str, Any]:
    metrics_registry.increment("rpc_get_balance_total")
    start = time.perf_counter()
    with session_scope() as session:
        account = session.get(Account, address)
        if account is None:
            metrics_registry.increment("rpc_get_balance_empty_total")
            metrics_registry.observe("rpc_get_balance_duration_seconds", time.perf_counter() - start)
            return {"address": address, "balance": 0, "nonce": 0}
        metrics_registry.increment("rpc_get_balance_success_total")
    metrics_registry.observe("rpc_get_balance_duration_seconds", time.perf_counter() - start)
    return {
        "address": account.address,
        "balance": account.balance,
        "nonce": account.nonce,
        "updated_at": account.updated_at.isoformat(),
    }


@router.post("/sendTx", summary="Submit a new transaction")
async def send_transaction(request: TransactionRequest) -> Dict[str, Any]:
    metrics_registry.increment("rpc_send_tx_total")
    start = time.perf_counter()
    mempool = get_mempool()
    tx_dict = request.model_dump()
    tx_hash = mempool.add(tx_dict)
    try:
        asyncio.create_task(
            gossip_broker.publish(
                "transactions",
                {
                    "tx_hash": tx_hash,
                    "sender": request.sender,
                    "payload": request.payload,
                    "nonce": request.nonce,
                    "fee": request.fee,
                    "type": request.type,
                },
            )
        )
        metrics_registry.increment("rpc_send_tx_success_total")
        return {"tx_hash": tx_hash}
    except Exception:
        metrics_registry.increment("rpc_send_tx_failed_total")
        raise
    finally:
        metrics_registry.observe("rpc_send_tx_duration_seconds", time.perf_counter() - start)


@router.post("/submitReceipt", summary="Submit receipt claim transaction")
async def submit_receipt(request: ReceiptSubmissionRequest) -> Dict[str, Any]:
    metrics_registry.increment("rpc_submit_receipt_total")
    start = time.perf_counter()
    tx_payload = {
        "type": "RECEIPT_CLAIM",
        "sender": request.sender,
        "nonce": request.nonce,
        "fee": request.fee,
        "payload": request.payload,
        "sig": request.sig,
    }
    tx_request = TransactionRequest.model_validate(tx_payload)
    try:
        response = await send_transaction(tx_request)
        metrics_registry.increment("rpc_submit_receipt_success_total")
        return response
    except HTTPException:
        metrics_registry.increment("rpc_submit_receipt_failed_total")
        raise
    except Exception:
        metrics_registry.increment("rpc_submit_receipt_failed_total")
        raise
    finally:
        metrics_registry.observe("rpc_submit_receipt_duration_seconds", time.perf_counter() - start)


@router.post("/estimateFee", summary="Estimate transaction fee")
async def estimate_fee(request: EstimateFeeRequest) -> Dict[str, Any]:
    metrics_registry.increment("rpc_estimate_fee_total")
    start = time.perf_counter()
    base_fee = 10
    per_byte = 1
    payload_bytes = len(json.dumps(request.payload, sort_keys=True, separators=(",", ":")).encode())
    estimated_fee = base_fee + per_byte * payload_bytes
    tx_type = (request.type or "TRANSFER").upper()
    metrics_registry.increment("rpc_estimate_fee_success_total")
    metrics_registry.observe("rpc_estimate_fee_duration_seconds", time.perf_counter() - start)
    return {
        "type": tx_type,
        "base_fee": base_fee,
        "payload_bytes": payload_bytes,
        "estimated_fee": estimated_fee,
    }


@router.post("/admin/mintFaucet", summary="Mint devnet funds to an address")
async def mint_faucet(request: MintFaucetRequest) -> Dict[str, Any]:
    metrics_registry.increment("rpc_mint_faucet_total")
    start = time.perf_counter()
    with session_scope() as session:
        account = session.get(Account, request.address)
        if account is None:
            account = Account(address=request.address, balance=request.amount)
            session.add(account)
        else:
            account.balance += request.amount
        session.commit()
        updated_balance = account.balance
    metrics_registry.increment("rpc_mint_faucet_success_total")
    metrics_registry.observe("rpc_mint_faucet_duration_seconds", time.perf_counter() - start)
    return {"address": request.address, "balance": updated_balance}


class TransactionData(BaseModel):
    tx_hash: str
    sender: str
    recipient: str
    payload: Dict[str, Any] = Field(default_factory=dict)

class ReceiptData(BaseModel):
    receipt_id: str
    job_id: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    miner_signature: Optional[str] = None
    coordinator_attestations: List[str] = Field(default_factory=list)
    minted_amount: int = 0
    recorded_at: str

class BlockImportRequest(BaseModel):
    height: int = Field(gt=0)
    hash: str
    parent_hash: str
    proposer: str
    timestamp: str
    tx_count: int = Field(ge=0)
    state_root: Optional[str] = None
    transactions: List[TransactionData] = Field(default_factory=list)
    receipts: List[ReceiptData] = Field(default_factory=list)


@router.get("/test-endpoint", summary="Test endpoint")
async def test_endpoint() -> Dict[str, str]:
    """Test if new code is deployed"""
    return {"status": "updated_code_running"}

@router.post("/blocks/import", summary="Import block from remote node")
async def import_block(request: BlockImportRequest) -> Dict[str, Any]:
    """Import a block from a remote node after validation."""
    import logging
    logger = logging.getLogger(__name__)
    
    metrics_registry.increment("rpc_import_block_total")
    start = time.perf_counter()
    
    try:
        logger.info(f"Received block import request: height={request.height}, hash={request.hash}")
        logger.info(f"Transactions count: {len(request.transactions)}")
        if request.transactions:
            logger.info(f"First transaction: {request.transactions[0]}")
        
        with session_scope() as session:
            # Check if block already exists
            existing = session.exec(select(Block).where(Block.height == request.height)).first()
            if existing:
                if existing.hash == request.hash:
                    metrics_registry.increment("rpc_import_block_exists_total")
                    return {"status": "exists", "height": request.height, "hash": request.hash}
                else:
                    metrics_registry.increment("rpc_import_block_conflict_total")
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Block at height {request.height} already exists with different hash"
                    )
            
            # Check if parent block exists
            if request.height > 0:
                parent = session.exec(select(Block).where(Block.hash == request.parent_hash)).first()
                if not parent:
                    metrics_registry.increment("rpc_import_block_orphan_total")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Parent block not found"
                    )
            
            # Validate block hash using the same algorithm as PoA proposer
            payload = f"{settings.chain_id}|{request.height}|{request.parent_hash}|{request.timestamp}".encode()
            expected_hash = "0x" + hashlib.sha256(payload).hexdigest()
            
            if request.hash != expected_hash:
                metrics_registry.increment("rpc_import_block_invalid_hash_total")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid block hash. Expected: {expected_hash}, Got: {request.hash}"
                )
            
            # Create and save block
            block_timestamp = datetime.fromisoformat(request.timestamp.replace('Z', '+00:00'))
            
            block = Block(
                height=request.height,
                hash=request.hash,
                parent_hash=request.parent_hash,
                proposer=request.proposer,
                timestamp=block_timestamp,
                tx_count=request.tx_count,
                state_root=request.state_root
            )
            
            session.add(block)
            session.flush()  # Get block ID
            
            # Add transactions if provided
            for tx_data in request.transactions:
                # Create transaction using constructor with all fields
                tx = Transaction(
                    tx_hash=str(tx_data.tx_hash),
                    block_height=block.id,  # Use block.id instead of block.height for foreign key
                    sender=str(tx_data.sender),
                    recipient=str(tx_data.recipient),
                    payload=tx_data.payload if tx_data.payload else {},
                    created_at=datetime.utcnow()
                )
                
                session.add(tx)
            
            # Add receipts if provided
            for receipt_data in request.receipts:
                receipt = Receipt(
                    block_height=block.id,  # Use block.id instead of block.height for foreign key
                    receipt_id=receipt_data.receipt_id,
                    job_id=receipt_data.job_id,
                    payload=receipt_data.payload,
                    miner_signature=receipt_data.miner_signature,
                    coordinator_attestations=receipt_data.coordinator_attestations,
                    minted_amount=receipt_data.minted_amount,
                    recorded_at=datetime.fromisoformat(receipt_data.recorded_at.replace('Z', '+00:00'))
                )
                session.add(receipt)
            
            session.commit()
            
            # Broadcast block via gossip
            try:
                gossip_broker.broadcast("blocks", {
                    "type": "block_imported",
                    "height": block.height,
                    "hash": block.hash,
                    "proposer": block.proposer
                })
            except Exception:
                pass  # Gossip broadcast is optional
            
            metrics_registry.increment("rpc_import_block_success_total")
            metrics_registry.observe("rpc_import_block_duration_seconds", time.perf_counter() - start)
            
            logger.info(f"Successfully imported block {request.height}")
            
            return {
                "status": "imported",
                "height": block.height,
                "hash": block.hash,
                "tx_count": block.tx_count
            }
    
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Failed to import block {request.height}: {str(e)}", exc_info=True)
        metrics_registry.increment("rpc_import_block_failed_total")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )
