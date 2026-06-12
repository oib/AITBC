"""
Escrow RPC endpoints for the blockchain node.
Provides create/release/refund/get endpoints backed by EscrowManager and Escrow DB model.
"""
from __future__ import annotations
import hashlib
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
import httpx
from fastapi import APIRouter, HTTPException
from ..contracts.escrow import get_escrow_manager
from ..database import session_scope
from ..logger import get_logger
from ..models import Escrow
_HUB_RPC_URL = os.getenv('HUB_RPC_URL', 'http://localhost:8202')
_CHAIN_ID = os.getenv('CHAIN_ID', os.getenv('SUPPORTED_CHAINS', 'ait-hub.aitbc.bubuit.net'))
_NODE_WALLET = os.getenv('NODE_WALLET_ADDRESS', os.getenv('GENESIS_WALLET_ADDRESS', ''))
_logger = get_logger(__name__)
router = APIRouter(tags=['escrow'])

async def _resolve_chain_account(address: str, client: httpx.AsyncClient) -> str | None:
    """Return address if it exists on-chain, else None."""
    try:
        r = await client.get(f'{_HUB_RPC_URL}/accounts/{address}')
        if r.status_code == 200:
            return address
    except Exception:
        pass
    return None

async def _get_account_nonce(address: str, client: httpx.AsyncClient) -> int:
    """Fetch current nonce for an account from the chain."""
    try:
        r = await client.get(f'{_HUB_RPC_URL}/accounts/{address}')
        if r.status_code == 200:
            return r.json().get('nonce', 0)
    except Exception:
        pass
    return 0

async def _submit_payment_tx(buyer: str, provider: str, amount: Decimal, job_id: str, contract_id: str) -> str | None:
    """Submit an ESCROW_RELEASE transaction to the blockchain so payment is on-chain."""
    amount_milli = int(amount * 1000)
    amount_int = amount_milli if amount_milli > 0 else int(amount)
    if amount_int <= 0:
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            sender = await _resolve_chain_account(buyer, client) or _NODE_WALLET
            recipient = await _resolve_chain_account(provider, client) or _NODE_WALLET
            if not sender or not recipient:
                _logger.warning('ESCROW_RELEASE TX skipped: could not resolve sender/recipient (buyer=%s, provider=%s)', buyer, provider)
                return None
            nonce = await _get_account_nonce(sender, client)
            tx = {'from': sender, 'to': recipient, 'amount': amount_int, 'fee': max(1, amount_int // 100), 'nonce': nonce, 'type': 'ESCROW_RELEASE', 'chain_id': _CHAIN_ID, 'payload': {'action': 'escrow_release', 'job_id': job_id, 'contract_id': contract_id, 'buyer_escrow_addr': buyer, 'provider_escrow_addr': provider, 'released_at': datetime.now(UTC).isoformat()}}
            tx_hash = '0x' + hashlib.sha256(f'{sender}{recipient}{amount_int}{nonce}{job_id}'.encode()).hexdigest()
            tx['hash'] = tx_hash
            resp = await client.post(f'{_HUB_RPC_URL}/transactions/marketplace', json=tx)
            if resp.status_code in (200, 201):
                _logger.info('ESCROW_RELEASE TX submitted: hash=%s amount=%s from=%s to=%s', tx_hash, amount_int, sender, recipient)
                return tx_hash
            else:
                _logger.warning('ESCROW_RELEASE TX failed %s: %s', resp.status_code, resp.text[:200])
    except Exception as e:
        _logger.warning('ESCROW_RELEASE TX submission failed (non-fatal): %s', e)
    return None

@router.post('/escrow/create', summary='Create escrow for a job')
async def create_escrow(body: dict[str, Any]) -> dict[str, Any]:
    """Create a new escrow contract locking buyer funds until job completion."""
    job_id = body.get('job_id')
    buyer = body.get('buyer')
    provider = body.get('provider')
    amount = body.get('amount')
    if not all([job_id, buyer, provider, amount is not None]):
        raise HTTPException(status_code=400, detail='job_id, buyer, provider, and amount are required')
    mgr = get_escrow_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail='EscrowManager not initialised')
    try:
        amount_dec = Decimal(str(amount))
    except Exception:
        raise HTTPException(status_code=400, detail=f'Invalid amount: {amount}')
    success, message, contract_id = await mgr.create_contract(job_id=job_id, client_address=buyer, agent_address=provider, amount=amount_dec)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    try:
        with session_scope() as session:
            escrow_record = Escrow(job_id=job_id, buyer=buyer, provider=provider, amount=int(amount_dec))
            session.add(escrow_record)
            session.commit()
    except Exception as e:
        _logger.warning('Failed to persist escrow to DB (in-memory only): %s', e)
    _logger.info('Escrow created: contract_id=%s job_id=%s amount=%s', contract_id, job_id, amount)
    return {'success': True, 'contract_id': contract_id, 'job_id': job_id, 'buyer': buyer, 'provider': provider, 'amount': str(amount_dec), 'message': message}

@router.post('/escrow/{job_id}/release', summary='Release escrow to provider')
async def release_escrow(job_id: str, request: dict[str, Any]) -> dict[str, Any]:
    """Release locked funds to the provider after job completion.
    Accepts optional job_tx_hash as proof of work reference."""
    mgr = get_escrow_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail='EscrowManager not initialised')
    job_tx_hash = request.get('job_tx_hash')
    contract_id = _find_contract_id(mgr, job_id)
    if contract_id is None:
        raise HTTPException(status_code=404, detail=f'No escrow contract found for job_id={job_id}')
    contract = mgr.escrow_contracts.get(contract_id)
    if contract:
        for ms in contract.milestones:
            ms['completed'] = True
            ms['verified'] = True
        from ..contracts.escrow import EscrowState
        contract.state = EscrowState.JOB_COMPLETED
    ok, message = await mgr.release_full_payment(contract_id)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    released_amount = contract.released_amount if contract else Decimal(0)
    released_at = datetime.now(UTC)
    try:
        with session_scope() as session:
            record = session.get(Escrow, job_id)
            if record:
                record.released_at = released_at
                if job_tx_hash:
                    record.job_tx_hash = job_tx_hash
                session.commit()
    except Exception as e:
        _logger.warning('Failed to update released_at/job_tx_hash in DB: %s', e)
    buyer_addr = contract.client_address if contract else ''
    provider_addr = contract.agent_address if contract else ''
    tx_hash = await _submit_payment_tx(buyer_addr, provider_addr, released_amount, job_id, contract_id)
    _logger.info('Escrow released: contract_id=%s job_id=%s tx=%s', contract_id, job_id, tx_hash)
    return {'success': True, 'contract_id': contract_id, 'job_id': job_id, 'message': message, 'released_amount': str(released_amount), 'tx_hash': tx_hash, 'released_at': released_at.isoformat()}

@router.post('/escrow/{job_id}/refund', summary='Refund escrow to buyer')
async def refund_escrow(job_id: str, body: dict[str, Any] | None=None) -> dict[str, Any]:
    """Refund locked funds back to the buyer."""
    mgr = get_escrow_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail='EscrowManager not initialised')
    contract_id = _find_contract_id(mgr, job_id)
    if contract_id is None:
        raise HTTPException(status_code=404, detail=f'No escrow contract found for job_id={job_id}')
    reason = (body or {}).get('reason', 'buyer_requested')
    success, message = await mgr.refund_contract(contract_id, reason)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    _logger.info('Escrow refunded: contract_id=%s job_id=%s', contract_id, job_id)
    return {'success': True, 'contract_id': contract_id, 'job_id': job_id, 'message': message}

@router.get('/escrow/{job_id}', summary='Get escrow state')
async def get_escrow(job_id: str) -> dict[str, Any]:
    """Get current escrow state for a job."""
    mgr = get_escrow_manager()
    db_record: Escrow | None = None
    try:
        with session_scope() as session:
            db_record = session.get(Escrow, job_id)
    except Exception as e:
        _logger.warning('Failed to query Escrow DB: %s', e)
    if mgr is not None:
        contract_id = _find_contract_id(mgr, job_id)
        if contract_id:
            contract = mgr.escrow_contracts.get(contract_id)
            if contract:
                return {'job_id': job_id, 'contract_id': contract_id, 'state': contract.state.value, 'buyer': contract.client_address, 'provider': contract.agent_address, 'amount': str(contract.amount), 'released_amount': str(contract.released_amount), 'refunded_amount': str(contract.refunded_amount), 'created_at': db_record.created_at.isoformat() if db_record else None, 'released_at': db_record.released_at.isoformat() if db_record and db_record.released_at else None}
    if db_record:
        return {'job_id': job_id, 'contract_id': None, 'state': 'released' if db_record.released_at else 'funded', 'buyer': db_record.buyer, 'provider': db_record.provider, 'amount': str(db_record.amount), 'released_amount': str(db_record.amount) if db_record.released_at else '0', 'refunded_amount': '0', 'created_at': db_record.created_at.isoformat(), 'released_at': db_record.released_at.isoformat() if db_record.released_at else None}
    raise HTTPException(status_code=404, detail=f'No escrow found for job_id={job_id}')

def _find_contract_id(mgr: Any, job_id: str) -> str | None:
    """Find contract_id by job_id in EscrowManager."""
    for cid, contract in mgr.escrow_contracts.items():
        if contract.job_id == job_id:
            return cid
    return None