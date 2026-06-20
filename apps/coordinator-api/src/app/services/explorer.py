from __future__ import annotations

import sqlite3
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError
from aitbc.network import AITBCHTTPClient

from ..config import settings
from ..domain import Job, JobReceipt
from ..schemas import (
    AddressListResponse,
    AddressSummary,
    BlockListResponse,
    BlockSummary,
    JobState,
    ReceiptListResponse,
    ReceiptSummary,
    TransactionListResponse,
    TransactionSummary,
)

logger = get_logger(__name__)
_STATUS_LABELS = {
    JobState.queued: "Queued",
    JobState.running: "Running",
    JobState.completed: "Succeeded",
    JobState.failed: "Failed",
    JobState.canceled: "Canceled",
    JobState.expired: "Expired",
}
_DEFAULT_HEIGHT_BASE = 100000


class ExplorerService:
    """Derives explorer-friendly summaries from coordinator data."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_blocks(self, *, limit: int = 20, offset: int = 0) -> BlockListResponse:
        rpc_base = settings.blockchain_rpc_url.rstrip("/")
        try:
            client = AITBCHTTPClient(timeout=10.0)
            try:
                head = client.get(f"{rpc_base}/rpc/head")
                height = head.get("height", 0)
                start = max(0, height - offset - limit + 1)
                end = height - offset
                if start > end:
                    return BlockListResponse(items=[], next_offset=None)
                rpc_data = client.get(f"{rpc_base}/rpc/blocks-range", params={"start": start, "end": end})
                raw_blocks = rpc_data.get("blocks", [])
                raw_blocks = list(reversed(raw_blocks))
                items: list[BlockSummary] = []
                for block in raw_blocks:
                    ts = block.get("timestamp")
                    if isinstance(ts, str):
                        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    items.append(
                        BlockSummary(
                            height=block["height"],
                            hash=block["hash"],
                            timestamp=ts,
                            txCount=block.get("tx_count", 0),
                            proposer=block.get("proposer", "—"),
                        )
                    )
                next_offset = offset + len(items) if len(items) == limit else None
                return BlockListResponse(items=items, next_offset=next_offset)
            except NetworkError:
                return BlockListResponse(items=[], next_offset=None)
        except Exception as e:
            logger.warning("Failed to fetch blocks from RPC: %s, falling back to fake data", e)
            statement = select(Job).order_by(Job.requested_at.desc())  # type: ignore[attr-defined]
            jobs = self.session.execute(statement.offset(offset).limit(limit)).all()
            for index, job in enumerate(jobs):
                height = _DEFAULT_HEIGHT_BASE + offset + index
                proposer = job.assigned_miner_id or "unassigned"
                items.append(
                    BlockSummary(height=height, hash=job.id, timestamp=job.requested_at, txCount=1, proposer=proposer)
                )
            next_offset = offset + len(items) if len(items) == limit else None
            return BlockListResponse(items=items, next_offset=next_offset)

    def list_transactions(self, *, limit: int = 50, offset: int = 0) -> TransactionListResponse:
        statement = select(Job).order_by(Job.requested_at.desc()).offset(offset).limit(limit)  # type: ignore[attr-defined]
        jobs = self.session.execute(statement).all()
        items: list[TransactionSummary] = []
        for index, job in enumerate(jobs):
            height = _DEFAULT_HEIGHT_BASE + offset + index
            state_val = job.state.value if hasattr(job.state, "value") else job.state
            status_label = _STATUS_LABELS.get(job.state) or state_val.title()
            value_str = "0"
            if job.receipt and isinstance(job.receipt, dict):
                price = job.receipt.get("price")
                if price is not None:
                    value_str = f"{price}"
            if value_str == "0":
                value = job.payload.get("value") if isinstance(job.payload, dict) else None
                if value is not None:
                    if isinstance(value, int | float):
                        value_str = f"{value}"
                    else:
                        value_str = str(value)
            items.append(
                TransactionSummary(
                    hash=job.id,
                    block=height,
                    from_address=job.client_id,
                    to_address=job.assigned_miner_id,
                    value=value_str,
                    status=status_label,
                )
            )
        next_offset: int | None = offset + len(items) if len(items) == limit else None
        return TransactionListResponse(items=items, next_offset=next_offset)

    def list_addresses(self, *, limit: int = 50, offset: int = 0) -> AddressListResponse:
        statement = select(Job).order_by(Job.requested_at.desc())  # type: ignore[attr-defined]
        jobs = self.session.execute(statement.offset(offset).limit(limit)).all()
        address_map: dict[str, dict[str, object]] = defaultdict(
            lambda: {
                "address": "",
                "balance": 0.0,
                "tx_count": 0,
                "last_active": datetime.min,
                "recent_transactions": deque(maxlen=5),
                "earned": 0.0,
                "spent": 0.0,
            }
        )

        def _ensure_dt(val: object) -> datetime:
            if isinstance(val, datetime):
                return val.replace(tzinfo=None)
            if isinstance(val, str):
                try:
                    dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                    return dt.replace(tzinfo=None)
                except ValueError:
                    return datetime.min
            return datetime.min

        def touch(address: str | None, tx_id: str, when: object, earned: float = 0.0, spent: float = 0.0) -> None:
            if not address:
                return
            entry = address_map[address]
            entry["address"] = address
            entry["tx_count"] = int(entry["tx_count"]) + 1  # type: ignore[call-overload]
            when_dt = _ensure_dt(when)
            if when_dt > _ensure_dt(entry["last_active"]):
                entry["last_active"] = when_dt
            entry["earned"] = float(entry["earned"]) + earned  # type: ignore[arg-type]
            entry["spent"] = float(entry["spent"]) + spent  # type: ignore[arg-type]
            entry["balance"] = float(entry["earned"]) - float(entry["spent"])  # type: ignore[arg-type]
            recent: deque[str] = entry["recent_transactions"]  # type: ignore[assignment]
            recent.appendleft(tx_id)

        for job in jobs:
            price = 0.0
            if job.receipt and isinstance(job.receipt, dict):
                receipt_price = job.receipt.get("price")
                if receipt_price is not None:
                    try:
                        price = float(receipt_price)
                    except (TypeError, ValueError):
                        pass
            touch(job.assigned_miner_id, job.id, job.requested_at, earned=price)
            touch(job.client_id, job.id, job.requested_at, spent=price)
        sorted_addresses = sorted(address_map.values(), key=lambda entry: entry["last_active"], reverse=True)  # type: ignore[arg-type, return-value]
        sliced = sorted_addresses[offset : offset + limit]
        items = [
            AddressSummary(
                address=entry["address"],
                balance=f"{float(entry['balance']):.6f}",
                txCount=int(entry["tx_count"]),
                lastActive=entry["last_active"],
                recentTransactions=list(entry["recent_transactions"]),
            )
            for entry in sliced
        ]  # type: ignore[call-overload, arg-type]
        next_offset: int | None = offset + len(sliced) if len(sliced) == limit else None
        return AddressListResponse(items=items, next_offset=next_offset)

    def list_receipts(self, *, job_id: str | None = None, limit: int = 50, offset: int = 0) -> ReceiptListResponse:
        statement = select(JobReceipt).order_by(JobReceipt.created_at.desc())  # type: ignore[attr-defined]
        if job_id:
            statement = statement.where(JobReceipt.job_id == job_id)
        rows = self.session.execute(statement.offset(offset).limit(limit)).all()
        items: list[ReceiptSummary] = []
        for row in rows:
            payload = row.payload or {}
            miner = payload.get("provider") or payload.get("miner") or payload.get("miner_id") or "unknown"
            coordinator = payload.get("client") or payload.get("coordinator") or payload.get("coordinator_id") or "unknown"
            status = payload.get("status") or payload.get("state") or "Unknown"
            job_id_from_payload = payload.get("job_id") or row.job_id
            items.append(
                ReceiptSummary(
                    receiptId=row.receipt_id,
                    miner=miner,
                    coordinator=coordinator,
                    issuedAt=row.created_at,
                    status=status,
                    payload=payload,
                    jobId=job_id_from_payload,
                )
            )
        resolved_job_id = job_id or "all"
        return ReceiptListResponse(jobId=resolved_job_id, items=items)

    def get_transaction(self, tx_hash: str) -> dict:
        """Get transaction details by hash from blockchain RPC"""
        rpc_base = settings.blockchain_rpc_url.rstrip("/")
        try:
            client = AITBCHTTPClient(timeout=10.0)
            try:
                tx_data = client.get(f"{rpc_base}/rpc/tx/{tx_hash}")
                return {
                    "hash": tx_data.get("tx_hash", tx_hash),
                    "from": tx_data.get("sender", "unknown"),
                    "to": tx_data.get("recipient", "unknown"),
                    "amount": tx_data.get("payload", {}).get("value", "0"),
                    "fee": "0",
                    "timestamp": tx_data.get("created_at"),
                    "block": tx_data.get("block_height", "pending"),
                    "status": "confirmed",
                    "raw": tx_data,
                }
            except NetworkError as e:
                if "404" in str(e) or "not found" in str(e).lower():
                    return {"error": "Transaction not found", "hash": tx_hash}
                return {"error": f"Failed to fetch transaction: {str(e)}", "hash": tx_hash}
        except Exception as e:
            logger.warning("Failed to fetch transaction from RPC", tx_hash=tx_hash, error=str(e))  # type: ignore[call-arg]
            return {"error": f"Failed to fetch transaction: {str(e)}", "hash": tx_hash}

    def get_block_by_hash(self, block_hash: str) -> dict:
        """Get block details by hash from blockchain database"""
        try:
            # Try blockchain database first
            chain_db_path = Path("/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db")
            if not chain_db_path.exists():
                chain_db_path = Path("/var/lib/aitbc/data/chain.db")
            
            if chain_db_path.exists():
                conn = sqlite3.connect(str(chain_db_path))
                cursor = conn.cursor()
                
                # Search for block by hash (with or without 0x prefix)
                clean_hash = block_hash.lower().replace("0x", "")
                cursor.execute("""
                    SELECT height, hash, proposer, timestamp, tx_count, state_root
                    FROM block 
                    WHERE lower(replace(hash, '0x', '')) = ?
                """, (clean_hash,))
                
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    height, hash, proposer, timestamp, tx_count, state_root = result
                    return {
                        "height": height,
                        "hash": hash,
                        "proposer": proposer,
                        "timestamp": timestamp,
                        "txCount": tx_count,
                        "stateRoot": state_root,
                    }
            
            return {"error": "Block not found", "hash": block_hash}
        except Exception as e:
            logger.warning("Failed to fetch block by hash from database", block_hash=block_hash, error=str(e))  # type: ignore[call-arg]
            return {"error": f"Failed to fetch block: {str(e)}", "hash": block_hash}

    def get_transaction_by_hash(self, tx_hash: str) -> dict:
        """Get transaction details by hash from blockchain database"""
        try:
            # Try blockchain database first
            chain_db_path = Path("/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db")
            if not chain_db_path.exists():
                chain_db_path = Path("/var/lib/aitbc/data/chain.db")
            
            if chain_db_path.exists():
                conn = sqlite3.connect(str(chain_db_path))
                cursor = conn.cursor()
                
                # Search for transaction by hash (with or without 0x prefix)
                clean_hash = tx_hash.lower().replace("0x", "")
                cursor.execute("""
                    SELECT tx_hash, sender, recipient, payload, block_height, created_at, type, status
                    FROM "transaction" 
                    WHERE lower(replace(tx_hash, '0x', '')) = ?
                """, (clean_hash,))
                
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    tx_hash, sender, recipient, payload, block_height, created_at, tx_type, status = result
                    return {
                        "tx_hash": tx_hash,
                        "sender": sender,
                        "recipient": recipient,
                        "payload": payload,
                        "block_height": block_height,
                        "created_at": created_at,
                        "type": tx_type,
                        "status": status,
                    }
            
            return {"error": "Transaction not found", "tx_hash": tx_hash}
        except Exception as e:
            logger.warning("Failed to fetch transaction by hash from database", tx_hash=tx_hash, error=str(e))  # type: ignore[call-arg]
            return {"error": f"Failed to fetch transaction: {str(e)}", "tx_hash": tx_hash}
