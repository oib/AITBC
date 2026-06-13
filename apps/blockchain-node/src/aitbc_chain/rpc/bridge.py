"""
Bridge-related RPC endpoints.
"""
from typing import Any, cast
from fastapi import HTTPException, Request
from aitbc.rate_limiting import rate_limit
from ..logger import get_logger
from .utils import get_chain_id
_logger = get_logger(__name__)

@rate_limit(rate=20, per=60)  # type: ignore[untyped-decorator]
async def bridge_lock(request: Request, lock_data: dict) -> dict[str, Any]:
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
            raise HTTPException(status_code=503, detail='Cross-chain bridge not initialized')
        source_chain = lock_data.get('source_chain', get_chain_id(None))
        target_chain = lock_data.get('target_chain')
        sender = lock_data.get('sender')
        recipient = lock_data.get('recipient')
        amount = lock_data.get('amount', 0)
        asset = lock_data.get('asset', 'native')
        if not all([target_chain, sender, recipient]):
            raise HTTPException(status_code=400, detail='Missing required fields: target_chain, sender, recipient')
        if amount <= 0:
            raise HTTPException(status_code=400, detail='Amount must be positive')
        transfer = bridge.initiate_transfer(source_chain=source_chain, target_chain=target_chain, sender=cast(str, sender).lower(), recipient=cast(str, recipient).lower(), amount=amount, asset=asset)
        return {'success': True, 'transfer_id': transfer.transfer_id, 'status': transfer.status.value, 'source_chain': source_chain, 'target_chain': target_chain, 'sender': sender, 'recipient': recipient, 'amount': amount, 'fee': amount * 10 // 10000, 'lock_time': transfer.lock_time.isoformat() if transfer.lock_time else None, 'message': 'Funds locked successfully. Use /bridge/confirm to complete.'}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        _logger.error('Bridge lock failed: %s', e)
        raise HTTPException(status_code=500, detail=f'Bridge lock failed: {str(e)}')

@rate_limit(rate=20, per=60)  # type: ignore[untyped-decorator]
async def bridge_confirm(request: Request, confirm_data: dict) -> dict[str, Any]:
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
            raise HTTPException(status_code=503, detail='Cross-chain bridge not initialized')
        transfer_id = confirm_data.get('transfer_id')
        proof = confirm_data.get('proof')
        if not transfer_id or not proof:
            raise HTTPException(status_code=400, detail='Missing required fields: transfer_id, proof')
        transfer = bridge.confirm_transfer(transfer_id, proof)
        return {'success': True, 'transfer_id': transfer.transfer_id, 'status': transfer.status.value, 'source_chain': transfer.source_chain, 'target_chain': transfer.target_chain, 'sender': transfer.sender, 'recipient': transfer.recipient, 'amount': transfer.amount, 'target_tx_hash': transfer.target_tx_hash, 'confirm_time': transfer.confirm_time.isoformat() if transfer.confirm_time else None, 'message': 'Cross-chain transfer completed successfully'}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        _logger.error('Bridge confirm failed: %s', e)
        raise HTTPException(status_code=500, detail=f'Bridge confirm failed: {str(e)}')

@rate_limit(rate=100, per=60)  # type: ignore[untyped-decorator]
async def get_bridge_transfer(request: Request, transfer_id: str) -> dict[str, Any]:
    """Get the status of a cross-chain transfer"""
    try:
        from ..cross_chain.bridge import get_cross_chain_bridge
        bridge = get_cross_chain_bridge()
        if not bridge:
            raise HTTPException(status_code=503, detail='Cross-chain bridge not initialized')
        transfer = bridge.get_transfer(transfer_id)
        if not transfer:
            raise HTTPException(status_code=404, detail=f'Transfer {transfer_id} not found')
        return {'success': True, 'transfer_id': transfer.transfer_id, 'status': transfer.status.value, 'source_chain': transfer.source_chain, 'target_chain': transfer.target_chain, 'sender': transfer.sender, 'recipient': transfer.recipient, 'amount': transfer.amount, 'asset': transfer.asset, 'source_tx_hash': transfer.source_tx_hash, 'target_tx_hash': transfer.target_tx_hash, 'lock_time': transfer.lock_time.isoformat() if transfer.lock_time else None, 'confirm_time': transfer.confirm_time.isoformat() if transfer.confirm_time else None}
    except HTTPException:
        raise
    except Exception as e:
        _logger.error('Get bridge transfer failed: %s', e)
        raise HTTPException(status_code=500, detail=f'Failed to get transfer: {str(e)}')

@rate_limit(rate=50, per=60)  # type: ignore[untyped-decorator]
async def list_pending_transfers(request: Request, chain_id: str | None = None) -> list[dict[str, Any]]:
    """List all pending cross-chain transfers"""
    try:
        from ..cross_chain.bridge import get_cross_chain_bridge
        bridge = get_cross_chain_bridge()
        if not bridge:
            raise HTTPException(status_code=503, detail='Cross-chain bridge not initialized')
        chain_id = get_chain_id(chain_id)
        transfers = bridge.list_pending_transfers(chain_id)
        return [{'transfer_id': t.transfer_id, 'source_chain': t.source_chain, 'target_chain': t.target_chain, 'sender': t.sender, 'recipient': t.recipient, 'amount': t.amount, 'status': t.status.value, 'lock_time': t.lock_time.isoformat() if t.lock_time else None} for t in transfers]
    except Exception as e:
        _logger.error('List pending transfers failed: %s', e)
        raise HTTPException(status_code=500, detail=f'Failed to list transfers: {str(e)}')