"""
Sync-related RPC endpoints.
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from sqlalchemy import asc, text
from sqlmodel import Session, delete, select

from aitbc.rate_limiting import rate_limit

from ..config import settings
from ..database import session_scope
from ..logger import get_logger
from ..models import Account, Block, Transaction
from .utils import get_chain_id

_logger = get_logger(__name__)
_last_import_time = 0
_import_lock = asyncio.Lock()


def _serialize_optional_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if hasattr(value, "isoformat"):
        return cast(str, value.isoformat())
    return str(value)


def _parse_datetime_value(value: Any, field_name: str) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid {field_name}: {value}") from exc
    raise HTTPException(status_code=400, detail=f"Invalid {field_name} type: {type(value).__name__}") from None


def _select_export_blocks(session: Session, chain_id: str) -> list[Block]:
    blocks_result = session.execute(
        select(Block).where(Block.chain_id == chain_id).order_by(asc(text("height")), text("id DESC"))
    )
    blocks: list[Block] = []
    seen_heights = set()
    duplicate_count = 0
    for block in blocks_result.scalars().all():
        if block.height in seen_heights:
            duplicate_count += 1
            continue
        seen_heights.add(block.height)
        blocks.append(block)
    if duplicate_count:
        _logger.warning("Filtered %s duplicate exported blocks for chain %s", duplicate_count, chain_id)
    return blocks


def _dedupe_import_blocks(blocks: list[dict[str, Any]], chain_id: str) -> list[dict[str, Any]]:
    latest_by_height: dict[int, dict[str, Any]] = {}
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
                status_code=400, detail=f"Mismatched block chain_id '{block_chain_id}' for import chain '{chain_id}'"
            )
        normalized_block = dict(block_data)
        normalized_block["height"] = height
        normalized_block["chain_id"] = chain_id
        if height in latest_by_height:
            duplicate_count += 1
        latest_by_height[height] = normalized_block
    if duplicate_count:
        _logger.warning("Filtered %s duplicate imported blocks for chain %s", duplicate_count, chain_id)
    return [latest_by_height[height] for height in sorted(latest_by_height)]


@rate_limit(rate=200, per=60)
async def export_chain(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Export full chain state as JSON for manual synchronization"""
    chain_id = get_chain_id(chain_id)
    try:
        with session_scope() as session:
            blocks = _select_export_blocks(session, chain_id)
            accounts_result = session.execute(select(Account).where(Account.chain_id == chain_id).order_by(Account.address))
            accounts = list(accounts_result.scalars().all())
            txs_result = session.execute(
                select(Transaction)
                .where(Transaction.chain_id == chain_id)
                .order_by(asc(text("block_height")), asc(text("id")))
            )
            transactions = list(txs_result.scalars().all())
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
                    {"chain_id": a.chain_id, "address": a.address, "balance": a.balance, "nonce": a.nonce} for a in accounts
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
                ],
            }
            return {"success": True, "export_data": export_data, "export_size_bytes": len(json.dumps(export_data))}
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error exporting chain: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to export chain: {str(e)}") from e


@rate_limit(rate=50, per=60)
async def import_chain(request: Request, import_data: dict[str, Any]) -> dict[str, Any]:
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
                existing_blocks = session.execute(select(Block).where(Block.chain_id == chain_id).order_by(Block.height))  # type: ignore[arg-type]
                existing_count = len(list(existing_blocks.scalars().all()))
                if existing_count > 0:
                    _logger.info("Backing up existing chain with %s blocks", existing_count)
                _logger.info("Clearing existing transactions for chain %s", chain_id)
                session.execute(delete(Transaction).where(Transaction.chain_id == chain_id))  # type: ignore[arg-type]
                if accounts:
                    _logger.info("Clearing existing accounts for chain %s", chain_id)
                    session.execute(delete(Account).where(Account.chain_id == chain_id))  # type: ignore[arg-type]
                _logger.info("Clearing existing blocks for chain %s", chain_id)
                session.execute(delete(Block).where(Block.chain_id == chain_id))  # type: ignore[arg-type]
                import_hashes = {block_data["hash"] for block_data in unique_blocks}
                if import_hashes:
                    from sqlalchemy import Column, String

                    hash_conflict_result = session.execute(
                        select(Block.hash, Block.chain_id).where(Column("hash", String).in_(import_hashes))
                    )
                    hash_conflicts = hash_conflict_result.all()
                    if hash_conflicts:
                        conflict_chains = {chain_id for _, chain_id in hash_conflicts}
                        _logger.warning(
                            "Clearing %s blocks with conflicting hashes across chains: %s",
                            len(hash_conflicts),
                            conflict_chains,
                        )
                        session.execute(delete(Block).where(Block.hash.in_(import_hashes)))  # type: ignore[attr-defined]
                session.commit()
                session.expire_all()
                _logger.info("Importing %s unique blocks (filtered from %s total)", len(unique_blocks), len(blocks))
                for block_data in unique_blocks:
                    block_timestamp = _parse_datetime_value(block_data.get("timestamp"), "block timestamp") or datetime.now(
                        UTC
                    )
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
            _logger.error("Error importing chain: %s", e)
            raise HTTPException(status_code=500, detail=f"Failed to import chain: {str(e)}") from e


@rate_limit(rate=50, per=60)
async def force_sync(request: Request, peer_data: dict[str, Any]) -> dict[str, Any]:
    """Force blockchain reorganization to sync with specified peer"""
    try:
        peer_url = peer_data.get("peer_url")
        target_height = peer_data.get("target_height")
        if not peer_url:
            raise HTTPException(status_code=400, detail="peer_url is required")
        parsed = urlparse(peer_url)
        if not parsed.scheme or parsed.scheme not in ["http", "https"]:
            raise HTTPException(status_code=400, detail="Invalid URL scheme")
        hostname = parsed.hostname
        if hostname:
            if (
                hostname in ["localhost", "127.0.0.1", "::1"]
                or hostname.startswith("192.168.")
                or hostname.startswith("10.")
                or hostname.startswith("172.16.")
            ):
                raise HTTPException(status_code=400, detail="Invalid peer URL")
        import requests

        response = requests.get(f"{peer_url}/rpc/export-chain", timeout=30)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Failed to fetch peer chain: {response.status_code}")
        peer_chain_data = response.json()
        peer_blocks = peer_chain_data["export_data"]["blocks"]
        if target_height and len(peer_blocks) < target_height:
            raise HTTPException(
                status_code=400, detail=f"Peer only has {len(peer_blocks)} blocks, cannot sync to height {target_height}"
            )
        import_result = await import_chain(request, peer_chain_data["export_data"])
        return {
            "success": True,
            "synced_from": peer_url,
            "synced_blocks": import_result["imported_blocks"],
            "target_height": target_height or import_result["imported_blocks"],
            "message": f"Successfully synced with peer {peer_url}",
        }
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Error forcing sync: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to force sync: {str(e)}") from e


@rate_limit(rate=200, per=60)
async def get_sync_config(request: Request) -> dict[str, Any]:
    """Get sync optimization configuration (v0.6.2)"""
    return {
        "sync_parallel_enabled": settings.sync_parallel_enabled,
        "sync_parallel_max_peers": settings.sync_parallel_max_peers,
        "sync_parallel_timeout": settings.sync_parallel_timeout,
        "sync_delta_enabled": settings.sync_delta_enabled,
        "sync_delta_threshold": settings.sync_delta_threshold,
        "sync_delta_max_blocks": settings.sync_delta_max_blocks,
        "gossip_priority_enabled": settings.gossip_priority_enabled,
        "gossip_protocol_version": settings.gossip_protocol_version,
        "gossip_backward_compat": settings.gossip_backward_compat,
        "gossip_message_batch_size": settings.gossip_message_batch_size,
    }
