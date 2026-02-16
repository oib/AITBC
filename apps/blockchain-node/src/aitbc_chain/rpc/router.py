from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlmodel import select

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
        "height": block.height,
        "hash": block.hash,
        "parent_hash": block.parent_hash,
        "timestamp": block.timestamp.isoformat(),
        "tx_count": block.tx_count,
        "state_root": block.state_root,
    }


@router.get("/blocks-range", summary="Get blocks in height range")
async def get_blocks_range(start: int, end: int) -> Dict[str, Any]:
    metrics_registry.increment("rpc_get_blocks_range_total")
    start_time = time.perf_counter()
    
    # Validate parameters
    if start < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="start must be non-negative")
    if end < start:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end must be greater than or equal to start")
    if end - start > 1000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="range cannot exceed 1000 blocks")
    
    with session_scope() as session:
        # Get blocks in the specified height range (ascending order by height)
        blocks = session.exec(
            select(Block)
            .where(Block.height >= start)
            .where(Block.height <= end)
            .order_by(Block.height.asc())
        ).all()
        
        if not blocks:
            metrics_registry.increment("rpc_get_blocks_range_empty_total")
            return {
                "blocks": [],
                "start": start,
                "end": end,
                "count": 0,
            }
        
        # Serialize blocks
        block_list = []
        for block in blocks:
            block_list.append({
                "height": block.height,
                "hash": block.hash,
                "parent_hash": block.parent_hash,
                "timestamp": block.timestamp.isoformat(),
                "tx_count": block.tx_count,
                "state_root": block.state_root,
            })
        
        metrics_registry.increment("rpc_get_blocks_range_success_total")
    metrics_registry.observe("rpc_get_blocks_range_duration_seconds", time.perf_counter() - start_time)
    
    return {
        "blocks": block_list,
        "start": start,
        "end": end,
        "count": len(block_list),
    }


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


@router.get("/transactions", summary="Get latest transactions")
async def get_transactions(limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    metrics_registry.increment("rpc_get_transactions_total")
    start = time.perf_counter()
    
    # Validate parameters
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="limit must be between 1 and 100")
    if offset < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="offset must be non-negative")
    
    with session_scope() as session:
        # Get transactions in descending order (newest first)
        transactions = session.exec(
            select(Transaction)
            .order_by(Transaction.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        
        # Get total count for pagination info
        total_count = len(session.exec(select(Transaction)).all())
        
        if not transactions:
            metrics_registry.increment("rpc_get_transactions_empty_total")
            return {
                "transactions": [],
                "total": total_count,
                "limit": limit,
                "offset": offset,
            }
        
        # Serialize transactions
        tx_list = []
        for tx in transactions:
            tx_list.append({
                "tx_hash": tx.tx_hash,
                "block_height": tx.block_height,
                "sender": tx.sender,
                "recipient": tx.recipient,
                "payload": tx.payload,
                "created_at": tx.created_at.isoformat(),
            })
        
        metrics_registry.increment("rpc_get_transactions_success_total")
    metrics_registry.observe("rpc_get_transactions_duration_seconds", time.perf_counter() - start)
    
    return {
        "transactions": tx_list,
        "total": total_count,
        "limit": limit,
        "offset": offset,
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


@router.get("/receipts", summary="Get latest receipts")
async def get_receipts(limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    metrics_registry.increment("rpc_get_receipts_total")
    start = time.perf_counter()
    
    # Validate parameters
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="limit must be between 1 and 100")
    if offset < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="offset must be non-negative")
    
    with session_scope() as session:
        # Get receipts in descending order (newest first)
        receipts = session.exec(
            select(Receipt)
            .order_by(Receipt.recorded_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        
        # Get total count for pagination info
        total_count = len(session.exec(select(Receipt)).all())
        
        if not receipts:
            metrics_registry.increment("rpc_get_receipts_empty_total")
            return {
                "receipts": [],
                "total": total_count,
                "limit": limit,
                "offset": offset,
            }
        
        # Serialize receipts
        receipt_list = []
        for receipt in receipts:
            receipt_list.append(_serialize_receipt(receipt))
        
        metrics_registry.increment("rpc_get_receipts_success_total")
    metrics_registry.observe("rpc_get_receipts_duration_seconds", time.perf_counter() - start)
    
    return {
        "receipts": receipt_list,
        "total": total_count,
        "limit": limit,
        "offset": offset,
    }


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


@router.get("/address/{address}", summary="Get address details including transactions")
async def get_address_details(address: str, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    metrics_registry.increment("rpc_get_address_total")
    start = time.perf_counter()
    
    # Validate parameters
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="limit must be between 1 and 100")
    if offset < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="offset must be non-negative")
    
    with session_scope() as session:
        # Get account info
        account = session.get(Account, address)
        
        # Get transactions where this address is sender or recipient
        sent_txs = session.exec(
            select(Transaction)
            .where(Transaction.sender == address)
            .order_by(Transaction.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        
        received_txs = session.exec(
            select(Transaction)
            .where(Transaction.recipient == address)
            .order_by(Transaction.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        
        # Get total counts
        total_sent = len(session.exec(select(Transaction).where(Transaction.sender == address)).all())
        total_received = len(session.exec(select(Transaction).where(Transaction.recipient == address)).all())
        
        # Serialize transactions
        serialize_tx = lambda tx: {
            "tx_hash": tx.tx_hash,
            "block_height": tx.block_height,
            "direction": "sent" if tx.sender == address else "received",
            "counterparty": tx.recipient if tx.sender == address else tx.sender,
            "payload": tx.payload,
            "created_at": tx.created_at.isoformat(),
        }
        
        response = {
            "address": address,
            "balance": account.balance if account else 0,
            "nonce": account.nonce if account else 0,
            "total_transactions_sent": total_sent,
            "total_transactions_received": total_received,
            "latest_sent": [serialize_tx(tx) for tx in sent_txs],
            "latest_received": [serialize_tx(tx) for tx in received_txs],
        }
        
        if account:
            response["updated_at"] = account.updated_at.isoformat()
        
        metrics_registry.increment("rpc_get_address_success_total")
    metrics_registry.observe("rpc_get_address_duration_seconds", time.perf_counter() - start)
    
    return response


@router.get("/addresses", summary="Get list of active addresses")
async def get_addresses(limit: int = 20, offset: int = 0, min_balance: int = 0) -> Dict[str, Any]:
    metrics_registry.increment("rpc_get_addresses_total")
    start = time.perf_counter()
    
    # Validate parameters
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="limit must be between 1 and 100")
    if offset < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="offset must be non-negative")
    
    with session_scope() as session:
        # Get addresses with balance >= min_balance
        addresses = session.exec(
            select(Account)
            .where(Account.balance >= min_balance)
            .order_by(Account.balance.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        
        # Get total count
        total_count = len(session.exec(select(Account).where(Account.balance >= min_balance)).all())
        
        if not addresses:
            metrics_registry.increment("rpc_get_addresses_empty_total")
            return {
                "addresses": [],
                "total": total_count,
                "limit": limit,
                "offset": offset,
            }
        
        # Serialize addresses
        address_list = []
        for addr in addresses:
            # Get transaction counts
            sent_count = len(session.exec(select(Transaction).where(Transaction.sender == addr.address)).all())
            received_count = len(session.exec(select(Transaction).where(Transaction.recipient == addr.address)).all())
            
            address_list.append({
                "address": addr.address,
                "balance": addr.balance,
                "nonce": addr.nonce,
                "total_transactions_sent": sent_count,
                "total_transactions_received": received_count,
                "updated_at": addr.updated_at.isoformat(),
            })
        
        metrics_registry.increment("rpc_get_addresses_success_total")
    metrics_registry.observe("rpc_get_addresses_duration_seconds", time.perf_counter() - start)
    
    return {
        "addresses": address_list,
        "total": total_count,
        "limit": limit,
        "offset": offset,
    }


@router.post("/sendTx", summary="Submit a new transaction")
async def send_transaction(request: TransactionRequest) -> Dict[str, Any]:
    metrics_registry.increment("rpc_send_tx_total")
    start = time.perf_counter()
    mempool = get_mempool()
    tx_dict = request.model_dump()
    try:
        tx_hash = mempool.add(tx_dict)
    except ValueError as e:
        metrics_registry.increment("rpc_send_tx_rejected_total")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        metrics_registry.increment("rpc_send_tx_failed_total")
        raise HTTPException(status_code=503, detail=f"Mempool unavailable: {e}")
    recipient = request.payload.get("recipient", "")
    try:
        asyncio.create_task(
            gossip_broker.publish(
                "transactions",
                {
                    "tx_hash": tx_hash,
                    "sender": request.sender,
                    "recipient": recipient,
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


class ImportBlockRequest(BaseModel):
    height: int
    hash: str
    parent_hash: str
    proposer: str
    timestamp: str
    tx_count: int = 0
    state_root: Optional[str] = None
    transactions: Optional[list] = None


@router.post("/importBlock", summary="Import a block from a remote peer")
async def import_block(request: ImportBlockRequest) -> Dict[str, Any]:
    from ..sync import ChainSync, ProposerSignatureValidator
    from ..config import settings as cfg

    metrics_registry.increment("rpc_import_block_total")
    start = time.perf_counter()

    trusted = [p.strip() for p in cfg.trusted_proposers.split(",") if p.strip()]
    validator = ProposerSignatureValidator(trusted_proposers=trusted if trusted else None)
    sync = ChainSync(
        session_factory=session_scope,
        chain_id=cfg.chain_id,
        max_reorg_depth=cfg.max_reorg_depth,
        validator=validator,
        validate_signatures=cfg.sync_validate_signatures,
    )

    block_data = request.model_dump(exclude={"transactions"})
    result = sync.import_block(block_data, request.transactions)

    duration = time.perf_counter() - start
    metrics_registry.observe("rpc_import_block_duration_seconds", duration)

    if result.accepted:
        metrics_registry.increment("rpc_import_block_accepted_total")
    else:
        metrics_registry.increment("rpc_import_block_rejected_total")

    return {
        "accepted": result.accepted,
        "height": result.height,
        "hash": result.block_hash,
        "reason": result.reason,
        "reorged": result.reorged,
        "reorg_depth": result.reorg_depth,
    }


@router.get("/syncStatus", summary="Get chain sync status")
async def sync_status() -> Dict[str, Any]:
    from ..sync import ChainSync
    from ..config import settings as cfg

    metrics_registry.increment("rpc_sync_status_total")
    sync = ChainSync(session_factory=session_scope, chain_id=cfg.chain_id)
    return sync.get_sync_status()
