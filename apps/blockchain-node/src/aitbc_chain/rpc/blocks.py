"""
Block-related RPC endpoints.
"""
import asyncio
import json
import re
import time
from datetime import UTC, datetime
from typing import Any, cast
from fastapi import HTTPException, Request, status
from sqlmodel import delete, select
from aitbc.rate_limiting import rate_limit
from ..database import session_scope
from ..logger import get_logger
from ..metrics import metrics_registry
from ..models import Block, Transaction
from .utils import get_chain_id
_logger = get_logger(__name__)
_last_import_time = 0.0
_import_lock = asyncio.Lock()

@rate_limit(rate=200, per=60)
async def get_genesis_allocations(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Get genesis allocations from genesis block metadata for RPC bootstrap"""
    chain_id = get_chain_id(chain_id)
    with session_scope(chain_id) as session:
        genesis = session.exec(select(Block).where(Block.chain_id == chain_id).where(Block.height == 0)).first()
        if not genesis:
            raise HTTPException(status_code=404, detail=f'Genesis block not found for chain {chain_id}')
        if not genesis.block_metadata:
            raise HTTPException(status_code=404, detail=f'Genesis block metadata not found for chain {chain_id}')
        try:
            metadata = json.loads(genesis.block_metadata)
            allocations = metadata.get('allocations', [])
            return {'chain_id': chain_id, 'allocations': allocations, 'genesis_hash': genesis.hash, 'genesis_height': genesis.height, 'genesis_state_root': genesis.state_root}
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f'Failed to parse genesis block metadata: {e}')

@rate_limit(rate=200, per=60)
async def get_head(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Get current chain head"""
    chain_id = get_chain_id(chain_id)
    metrics_registry.increment('rpc_get_head_total')
    start = time.perf_counter()
    with session_scope(chain_id) as session:
        result = session.exec(select(Block).where(Block.chain_id == chain_id).order_by(Block.height.desc()).limit(1)).first()  # type: ignore[attr-defined]
        if result is None:
            metrics_registry.increment('rpc_get_head_not_found_total')
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no blocks yet')
        metrics_registry.increment('rpc_get_head_success_total')
    metrics_registry.observe('rpc_get_head_duration_seconds', time.perf_counter() - start)
    return {'height': result.height, 'hash': result.hash, 'timestamp': result.timestamp.isoformat(), 'tx_count': result.tx_count}

@rate_limit(rate=200, per=60)
async def get_block(request: Request, height: int, chain_id: str | None = None) -> dict[str, Any]:
    """Get block by height"""
    chain_id = get_chain_id(chain_id)
    metrics_registry.increment('rpc_get_block_total')
    start = time.perf_counter()
    with session_scope(chain_id) as session:
        block = session.exec(select(Block).where(Block.chain_id == chain_id).where(Block.height == height)).first()
        if block is None:
            metrics_registry.increment('rpc_get_block_not_found_total')
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='block not found')
        metrics_registry.increment('rpc_get_block_success_total')
        txs = session.exec(select(Transaction).where(Transaction.chain_id == chain_id).where(Transaction.block_height == height)).all()
        tx_list = []
        for tx in txs:
            t = dict(tx.payload) if tx.payload else {}
            t['tx_hash'] = tx.tx_hash
            tx_list.append(t)
    metrics_registry.observe('rpc_get_block_duration_seconds', time.perf_counter() - start)
    return {'chain_id': block.chain_id, 'height': block.height, 'hash': block.hash, 'parent_hash': block.parent_hash, 'proposer': block.proposer, 'timestamp': block.timestamp.isoformat(), 'tx_count': block.tx_count, 'state_root': block.state_root, 'transactions': tx_list}

@rate_limit(rate=200, per=60)
async def get_blocks_range(request: Request, start: int = 0, end: int = 10, include_tx: bool = True, chain_id: str | None = None) -> dict[str, Any]:
    """Get blocks in a height range
    
    Args:
        start: Starting block height (inclusive)
        end: Ending block height (inclusive)
        include_tx: Whether to include transaction data (default: True)
    """
    with session_scope() as session:
        chain_id = get_chain_id(chain_id)
        blocks = session.exec(select(Block).where(Block.chain_id == chain_id, Block.height >= start, Block.height <= end).order_by(Block.height.asc())).all()  # type: ignore[attr-defined]
        result_blocks = []
        for b in blocks:
            block_data = {'height': b.height, 'hash': b.hash, 'parent_hash': b.parent_hash, 'proposer': b.proposer, 'timestamp': b.timestamp.isoformat(), 'tx_count': b.tx_count, 'state_root': b.state_root}
            if include_tx:
                txs = session.exec(select(Transaction).where(Transaction.chain_id == chain_id).where(Transaction.block_height == b.height)).all()
                block_data['transactions'] = [tx.model_dump() for tx in txs]
            result_blocks.append(block_data)
        return {'success': True, 'blocks': result_blocks, 'count': len(blocks)}

@rate_limit(rate=50, per=60)
async def import_block(request: Request, block_data: dict) -> dict[str, Any]:
    """Import a block into the blockchain"""
    global _last_import_time
    async with _import_lock:
        try:
            current_time = time.time()
            time_since_last = current_time - _last_import_time
            if time_since_last < 1.0:
                await asyncio.sleep(1.0 - time_since_last)
            _last_import_time = time.time()
            chain_id = block_data.get('chain_id') or block_data.get('chainId') or get_chain_id(None)
            block_hash = block_data['hash']
            if not isinstance(block_hash, str) or not re.fullmatch('0x[0-9a-fA-F]{64}', block_hash):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid block hash format')
            try:
                block_height = int(block_data['height'])
            except (KeyError, TypeError, ValueError) as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid block height') from exc
            timestamp = block_data.get('timestamp')
            if isinstance(timestamp, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                except ValueError:
                    timestamp = datetime.now(UTC)
            elif timestamp is None:
                timestamp = datetime.now(UTC)
            with session_scope(chain_id) as session:
                existing_height_block = session.exec(select(Block).where(Block.chain_id == chain_id).where(Block.height == block_height)).first()
                if existing_height_block is not None:
                    if existing_height_block.hash == block_hash:
                        return {'success': True, 'block_height': existing_height_block.height, 'block_hash': existing_height_block.hash, 'chain_id': chain_id}
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f'Block height {block_height} already exists with different hash')
                parent_hash = block_data['parent_hash']
                if block_height > 1:
                    parent_block = session.exec(select(Block).where(Block.hash == parent_hash)).first()
                    if parent_block is None:
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Parent block not found')
                existing_block = session.execute(select(Block).where(Block.hash == block_hash)).first()
                if existing_block:
                    _logger.warning('Deleting existing block with conflicting hash %s from chain %s', block_hash, existing_block[0].chain_id)
                    session.execute(delete(Block).where(Block.hash == block_hash))  # type: ignore[arg-type]
                    session.commit()
                block = Block(chain_id=chain_id, height=block_height, hash=block_hash, parent_hash=block_data['parent_hash'], proposer=block_data['proposer'], timestamp=timestamp, state_root=block_data.get('state_root'), tx_count=block_data.get('tx_count', 0))
                session.add(block)
                session.commit()
                return {'success': True, 'block_height': block.height, 'block_hash': block.hash, 'chain_id': chain_id}
        except HTTPException:
            raise
        except Exception as e:
            _logger.error('Error importing block: %s', e)
            raise HTTPException(status_code=500, detail=f'Failed to import block: {str(e)}')