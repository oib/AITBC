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
                    "recipient": request.recipient,
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
