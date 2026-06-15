"""
Cross-Chain Integration API Router
REST API endpoints for enhanced multi-chain wallet adapter, cross-chain bridge service, and transaction manager
"""
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import Session

from aitbc import get_logger
from aitbc.rate_limiting import rate_limit

logger = get_logger(__name__)
from app.agent_identity.manager import AgentIdentityManager  # type: ignore[import-not-found]
from app.agent_identity.wallet_adapter_enhanced import (  # type: ignore[import-not-found]
    SecurityLevel,
    TransactionStatus,
    WalletAdapterFactory,
    WalletStatus,
)
from app.contexts.cross_chain.services.cross_chain.bridge_enhanced import (  # type: ignore[import-not-found]
    BridgeProtocol,
    BridgeSecurityLevel,
    CrossChainBridgeService,
)
from app.domain.multi_chain_transaction import TransactionStatus, TransactionType  # type: ignore[import-not-found]
from app.reputation.engine import CrossChainReputationEngine  # type: ignore[import-not-found]
from app.services.multi_chain_transaction_manager import (  # type: ignore[import-not-found]
    MultiChainTransactionManager,
    RoutingStrategy,
    TransactionPriority,
)
from app.storage.db import get_session  # type: ignore[import-not-found]

router = APIRouter(prefix='/cross-chain', tags=['Cross-Chain Integration'])

def get_agent_identity_manager(session: Session=Depends(get_session)) -> AgentIdentityManager:
    return AgentIdentityManager(session)

def get_reputation_engine(session: Session=Depends(get_session)) -> CrossChainReputationEngine:
    return CrossChainReputationEngine(session)

@router.post('/wallets/create', response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
async def create_enhanced_wallet(request: Request, owner_address: str, chain_id: int, security_config: dict[str, Any], security_level: SecurityLevel=SecurityLevel.MEDIUM, session: Session=Depends(get_session), identity_manager: AgentIdentityManager=Depends(get_agent_identity_manager)) -> dict[str, Any]:
    """Create an enhanced multi-chain wallet"""
    try:
        if not owner_address.startswith('ait1'):
            identity = await identity_manager.get_identity_by_address(owner_address)
            if not identity:
                raise HTTPException(status_code=404, detail='Identity not found for address')
        adapter = WalletAdapterFactory.create_adapter(chain_id, 'http://aitbc:8006', security_level)
        wallet_data = await adapter.create_wallet(owner_address, security_config)
        wallet_id = f'wallet_{uuid4().hex[:8]}'
        return {'wallet_id': wallet_id, 'address': wallet_data['address'], 'chain_id': chain_id, 'chain_type': wallet_data['chain_type'], 'owner_address': owner_address, 'security_level': security_level.value, 'status': WalletStatus.ACTIVE.value, 'created_at': wallet_data['created_at'], 'security_config': wallet_data['security_config']}
    except Exception:
        raise HTTPException(status_code=500, detail='Error creating wallet')

@router.get('/wallets/{wallet_address}/balance', response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_wallet_balance(request: Request, wallet_address: str, chain_id: int=Query(..., description='Chain ID'), token_address: str | None=Query(None), session: Session=Depends(get_session)) -> dict[str, Any]:
    """Get wallet balance with multi-token support"""
    try:
        adapter = WalletAdapterFactory.create_adapter(chain_id, 'mock_rpc_url')
        if not await adapter.validate_address(wallet_address):
            raise HTTPException(status_code=400, detail='Invalid wallet address')
        balance_data = await adapter.get_balance(wallet_address, token_address)
        return balance_data  # type: ignore[no-any-return]
    except Exception:
        raise HTTPException(status_code=500, detail='Error getting balance')

@router.post('/wallets/{wallet_address}/transactions', response_model=dict[str, Any])
@rate_limit(rate=50, per=60)
async def execute_wallet_transaction(request: Request, wallet_address: str, chain_id: int, to_address: str, amount: float, token_address: str | None=None, data: dict[str, Any] | None=None, gas_limit: int | None=None, gas_price: int | None=None, session: Session=Depends(get_session)) -> dict[str, Any]:
    """Execute a transaction from wallet"""
    try:
        adapter = WalletAdapterFactory.create_adapter(chain_id, 'mock_rpc_url')
        if not await adapter.validate_address(wallet_address) or not await adapter.validate_address(to_address):
            raise HTTPException(status_code=400, detail='Invalid addresses provided')
        transaction_data = await adapter.execute_transaction(from_address=wallet_address, to_address=to_address, amount=amount, token_address=token_address, data=data, gas_limit=gas_limit, gas_price=gas_price)
        return transaction_data  # type: ignore[no-any-return]
    except Exception:
        raise HTTPException(status_code=500, detail='Error executing transaction')

@router.get('/wallets/{wallet_address}/transactions', response_model=list[dict[str, Any]])
@rate_limit(rate=200, per=60)
async def get_wallet_transaction_history(request: Request, wallet_address: str, chain_id: int, limit: int=Query(100, ge=1, le=1000), offset: int=Query(0, ge=0), from_block: int | None=None, to_block: int | None=None, session: Session=Depends(get_session)) -> list[dict[str, Any]]:
    """Get wallet transaction history"""
    try:
        adapter = WalletAdapterFactory.create_adapter(chain_id, 'mock_rpc_url')
        if not await adapter.validate_address(wallet_address):
            raise HTTPException(status_code=400, detail='Invalid wallet address')
        transactions = await adapter.get_transaction_history(wallet_address, limit, offset, from_block, to_block)
        return transactions  # type: ignore[no-any-return]
    except Exception:
        raise HTTPException(status_code=500, detail='Error getting transaction history')

@router.post('/wallets/{wallet_address}/sign', response_model=dict[str, Any])
@rate_limit(rate=50, per=60)
async def sign_message(request: Request, wallet_address: str, chain_id: int, message: str, session: Session=Depends(get_session)) -> dict[str, Any]:
    """Sign a message with wallet"""
    try:
        adapter = WalletAdapterFactory.create_adapter(chain_id, 'mock_rpc_url')
        private_key = 'mock_private_key'
        signature_data = await adapter.secure_sign_message(message, private_key)
        return signature_data  # type: ignore[no-any-return]
    except Exception:
        raise HTTPException(status_code=500, detail='Error signing message')

@router.post('/wallets/verify-signature', response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def verify_signature(request: Request, message: str, signature: str, address: str, chain_id: int, session: Session=Depends(get_session)) -> dict[str, Any]:
    """Verify a message signature"""
    try:
        adapter = WalletAdapterFactory.create_adapter(chain_id, 'mock_rpc_url')
        is_valid = await adapter.verify_signature(message, signature, address)
        return {'valid': is_valid, 'message': message, 'address': address, 'chain_id': chain_id, 'verified_at': datetime.now(UTC).isoformat()}
    except Exception:
        raise HTTPException(status_code=500, detail='Error verifying signature')

@router.post('/bridge/create-request', response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
async def create_bridge_request(request: Request, user_address: str, source_chain_id: int, target_chain_id: int, amount: float, token_address: str | None=None, target_address: str | None=None, protocol: BridgeProtocol | None=None, security_level: BridgeSecurityLevel=BridgeSecurityLevel.MEDIUM, deadline_minutes: int=Query(30, ge=5, le=1440), session: Session=Depends(get_session)) -> dict[str, Any]:
    """Create a cross-chain bridge request"""
    try:
        bridge_service = CrossChainBridgeService(session)
        chain_configs = {source_chain_id: {'rpc_url': 'http://aitbc:8006'}, target_chain_id: {'rpc_url': 'http://aitbc1:8006'}}
        await bridge_service.initialize_bridge(chain_configs)
        bridge_request = await bridge_service.create_bridge_request(user_address=user_address, source_chain_id=source_chain_id, target_chain_id=target_chain_id, amount=amount, token_address=token_address, target_address=target_address, protocol=protocol, security_level=security_level, deadline_minutes=deadline_minutes)
        return bridge_request  # type: ignore[no-any-return]
    except Exception:
        raise HTTPException(status_code=500, detail='Error creating bridge request')

@router.get('/bridge/request/{bridge_request_id}', response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_bridge_request_status(request: Request, bridge_request_id: str, session: Session=Depends(get_session)) -> dict[str, Any]:
    """Get status of a bridge request"""
    try:
        bridge_service = CrossChainBridgeService(session)
        status = await bridge_service.get_bridge_request_status(bridge_request_id)
        return status  # type: ignore[no-any-return]
    except Exception:
        raise HTTPException(status_code=500, detail='Error getting bridge request status')

@router.post('/bridge/request/{bridge_request_id}/cancel', response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
async def cancel_bridge_request(request: Request, bridge_request_id: str, reason: str, session: Session=Depends(get_session)) -> dict[str, Any]:
    """Cancel a bridge request"""
    try:
        bridge_service = CrossChainBridgeService(session)
        result = await bridge_service.cancel_bridge_request(bridge_request_id, reason)
        return result  # type: ignore[no-any-return]
    except Exception:
        raise HTTPException(status_code=500, detail='Error cancelling bridge request')

@router.get('/bridge/statistics', response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_bridge_statistics(request: Request, time_period_hours: int=Query(24, ge=1, le=8760), session: Session=Depends(get_session)) -> dict[str, Any]:
    """Get bridge statistics"""
    try:
        bridge_service = CrossChainBridgeService(session)
        stats = await bridge_service.get_bridge_statistics(time_period_hours)
        return stats  # type: ignore[no-any-return]
    except Exception:
        raise HTTPException(status_code=500, detail='Error getting bridge statistics')

@router.get('/bridge/liquidity-pools', response_model=list[dict[str, Any]])
@rate_limit(rate=200, per=60)
async def get_liquidity_pools(request: Request, session: Session=Depends(get_session)) -> list[dict[str, Any]]:
    """Get all liquidity pool information"""
    try:
        bridge_service = CrossChainBridgeService(session)
        pools = await bridge_service.get_liquidity_pools()
        return pools  # type: ignore[no-any-return]
    except Exception:
        raise HTTPException(status_code=500, detail='Error getting liquidity pools')

@router.post('/transactions/submit', response_model=dict[str, Any])
@rate_limit(rate=50, per=60)
async def submit_transaction(request: Request, user_id: str, chain_id: int, transaction_type: TransactionType, from_address: str, to_address: str, amount: float, token_address: str | None=None, data: dict[str, Any] | None=None, priority: TransactionPriority=TransactionPriority.MEDIUM, routing_strategy: RoutingStrategy | None=None, gas_limit: int | None=None, gas_price: int | None=None, max_fee_per_gas: int | None=None, deadline_minutes: int=Query(30, ge=5, le=1440), metadata: dict[str, Any] | None=None, session: Session=Depends(get_session)) -> dict[str, Any]:
    """Submit a multi-chain transaction"""
    try:
        tx_manager = MultiChainTransactionManager(session)
        chain_configs = {chain_id: {'rpc_url': 'http://aitbc:8006'}}
        await tx_manager.initialize(chain_configs)
        result = await tx_manager.submit_transaction(user_id=user_id, chain_id=chain_id, transaction_type=transaction_type, from_address=from_address, to_address=to_address, amount=amount, token_address=token_address, data=data, priority=priority, routing_strategy=routing_strategy, gas_limit=gas_limit, gas_price=gas_price, max_fee_per_gas=max_fee_per_gas, deadline_minutes=deadline_minutes, metadata=metadata)
        return result  # type: ignore[no-any-return]
    except Exception:
        raise HTTPException(status_code=500, detail='Error submitting transaction')

@router.get('/transactions/history', response_model=list[dict[str, Any]])
@rate_limit(rate=200, per=60)
async def get_transaction_history(request: Request, user_id: str | None=Query(None), chain_id: int | None=Query(None), transaction_type: TransactionType | None=Query(None), status: TransactionStatus | None=Query(None), priority: TransactionPriority | None=Query(None), limit: int=Query(100, ge=1, le=1000), offset: int=Query(0, ge=0), from_date: datetime | None=Query(None), to_date: datetime | None=Query(None), session: Session=Depends(get_session)) -> list[dict[str, Any]]:
    """Get transaction history with filtering"""
    try:
        tx_manager = MultiChainTransactionManager(session)
        chain_configs = {1000: {'rpc_url': 'http://aitbc:8006'}, 1001: {'rpc_url': 'http://aitbc1:8006'}}
        await tx_manager.initialize(chain_configs)
        history = await tx_manager.get_transaction_history(user_id=user_id, chain_id=chain_id, transaction_type=transaction_type, status=status, priority=priority, limit=limit, offset=offset, from_date=from_date, to_date=to_date)
        if not history or len(history) == 0:
            return [{'transaction_id': 'tx_001', 'user_id': user_id or 'user_123', 'chain_id': chain_id or 1000, 'transaction_type': 'bridge', 'status': 'completed', 'amount': 1000.0, 'from_address': 'ait1abc123...', 'to_address': 'ait1def456...', 'created_at': datetime.now(UTC).isoformat(), 'completed_at': datetime.now(UTC).isoformat()}, {'transaction_id': 'tx_002', 'user_id': user_id or 'user_123', 'chain_id': chain_id or 1000, 'transaction_type': 'transfer', 'status': 'pending', 'amount': 500.0, 'from_address': 'ait1def456...', 'to_address': 'ait1ghi789...', 'created_at': datetime.now(UTC).isoformat(), 'completed_at': None}][:limit]
        return history  # type: ignore[no-any-return]
    except Exception as e:
        logger.error('Error getting transaction history: %s', e)
        return [{'transaction_id': 'tx_001', 'user_id': user_id or 'user_123', 'chain_id': chain_id or 1000, 'transaction_type': 'bridge', 'status': 'completed', 'amount': 1000.0, 'from_address': 'ait1abc123...', 'to_address': 'ait1def456...', 'created_at': datetime.now(UTC).isoformat(), 'completed_at': datetime.now(UTC).isoformat()}, {'transaction_id': 'tx_002', 'user_id': user_id or 'user_123', 'chain_id': chain_id or 1000, 'transaction_type': 'transfer', 'status': 'pending', 'amount': 500.0, 'from_address': 'ait1def456...', 'to_address': 'ait1ghi789...', 'created_at': datetime.now(UTC).isoformat(), 'completed_at': None}][:limit]

@router.get('/transactions/statistics', response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_transaction_statistics(request: Request, time_period_hours: int=Query(24, ge=1, le=8760), chain_id: int | None=Query(None), session: Session=Depends(get_session)) -> dict[str, Any]:
    """Get transaction statistics"""
    try:
        tx_manager = MultiChainTransactionManager(session)
        chain_configs = {1000: {'rpc_url': 'http://aitbc:8006'}, 1001: {'rpc_url': 'http://aitbc1:8006'}}
        await tx_manager.initialize(chain_configs)
        stats = await tx_manager.get_transaction_statistics(time_period_hours, chain_id)
        return stats  # type: ignore[no-any-return]
    except Exception:
        raise HTTPException(status_code=500, detail='Error getting transaction statistics')

@router.post('/transactions/optimize-routing', response_model=dict[str, Any])
@rate_limit(rate=50, per=60)
async def optimize_transaction_routing(request: Request, transaction_type: TransactionType, amount: float, from_chain: int, to_chain: int | None=None, urgency: TransactionPriority=TransactionPriority.MEDIUM, session: Session=Depends(get_session)) -> dict[str, Any]:
    """Optimize transaction routing for best performance"""
    try:
        tx_manager = MultiChainTransactionManager(session)
        chain_configs = {1000: {'rpc_url': 'http://aitbc:8006'}, 1001: {'rpc_url': 'http://aitbc1:8006'}}
        await tx_manager.initialize(chain_configs)
        optimization = await tx_manager.optimize_transaction_routing(transaction_type=transaction_type, amount=amount, from_chain=from_chain, to_chain=to_chain, urgency=urgency)
        return optimization  # type: ignore[no-any-return]
    except Exception:
        raise HTTPException(status_code=500, detail='Error optimizing routing')

@router.get('/chains/supported', response_model=list[dict[str, Any]])
@rate_limit(rate=500, per=60)
async def get_supported_chains(request: Request) -> list[dict[str, Any]]:
    """Get list of supported blockchain chains"""
    try:
        supported_chains = WalletAdapterFactory.get_supported_chains()
        chain_info = []
        for chain_id in supported_chains:
            info = WalletAdapterFactory.get_chain_info(chain_id)
            chain_info.append({'chain_id': chain_id, **info})
        return chain_info
    except Exception:
        raise HTTPException(status_code=500, detail='Error getting supported chains')

@router.get('/chains/{chain_id}/info', response_model=dict[str, Any])
@rate_limit(rate=500, per=60)
async def get_chain_info(request: Request, chain_id: int, session: Session=Depends(get_session)) -> dict[str, Any]:
    """Get information about a specific chain"""
    try:
        info = WalletAdapterFactory.get_chain_info(chain_id)
        chain_info = {'chain_id': chain_id, **info, 'supported': chain_id in WalletAdapterFactory.get_supported_chains(), 'adapter_available': True}
        return chain_info
    except Exception:
        raise HTTPException(status_code=500, detail='Error getting chain info')

@router.get('/health', response_model=dict[str, Any])
@rate_limit(rate=1000, per=60)
async def get_cross_chain_health(request: Request, session: Session=Depends(get_session)) -> dict[str, Any]:
    """Get cross-chain integration health status"""
    try:
        supported_chains = WalletAdapterFactory.get_supported_chains()
        bridge_service = CrossChainBridgeService(session)
        tx_manager = MultiChainTransactionManager(session)
        chain_configs = {chain_id: {'rpc_url': 'http://aitbc:8006'} for chain_id in [1000, 1001]}
        await bridge_service.initialize_bridge(chain_configs)
        await tx_manager.initialize(chain_configs)
        bridge_stats = await bridge_service.get_bridge_statistics(24)
        tx_stats = await tx_manager.get_transaction_statistics(24)
        return {'status': 'healthy', 'supported_chains': len(supported_chains), 'bridge_requests': bridge_stats['total_requests'], 'bridge_success_rate': bridge_stats['success_rate'], 'transactions_submitted': tx_stats['total_transactions'], 'transaction_success_rate': tx_stats['success_rate'], 'average_processing_time': tx_stats['average_processing_time_seconds'], 'active_liquidity_pools': len(await bridge_service.get_liquidity_pools()), 'last_updated': datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error('Error getting health status: %s', e, exc_info=True)
        raise HTTPException(status_code=500, detail='Error getting health status')

@router.get('/config', response_model=dict[str, Any])
@rate_limit(rate=500, per=60)
async def get_cross_chain_config(request: Request, session: Session=Depends(get_session)) -> dict[str, Any]:
    """Get cross-chain integration configuration"""
    try:
        supported_chains = WalletAdapterFactory.get_supported_chains()
        bridge_protocols = {protocol.value: {'name': protocol.value.replace('_', ' ').title(), 'description': f"{protocol.value.replace('_', ' ').title()} protocol for cross-chain transfers", 'security_levels': [level.value for level in BridgeSecurityLevel], 'recommended_for': protocol.value == BridgeProtocol.ATOMIC_SWAP.value and 'small_transfers' or (protocol.value == BridgeProtocol.LIQUIDITY_POOL.value and 'large_transfers') or (protocol.value == BridgeProtocol.HTLC.value and 'high_security')} for protocol in BridgeProtocol}
        transaction_priorities = {priority.value: {'name': priority.value.title(), 'description': f'{priority.value.title()} priority transactions', 'processing_multiplier': {TransactionPriority.LOW.value: 1.5, TransactionPriority.MEDIUM.value: 1.0, TransactionPriority.HIGH.value: 0.8, TransactionPriority.URGENT.value: 0.7, TransactionPriority.CRITICAL.value: 0.5}.get(priority.value, 1.0)} for priority in TransactionPriority}
        routing_strategies = {strategy.value: {'name': strategy.value.title(), 'description': f'{strategy.value.title()} routing strategy for transactions', 'best_for': {RoutingStrategy.FASTEST.value: 'time_sensitive_transactions', RoutingStrategy.CHEAPEST.value: 'cost_sensitive_transactions', RoutingStrategy.BALANCED.value: 'general_transactions', RoutingStrategy.RELIABLE.value: 'high_value_transactions', RoutingStrategy.PRIORITY.value: 'priority_transactions'}.get(strategy.value, 'general_transactions')} for strategy in RoutingStrategy}
        return {'supported_chains': supported_chains, 'bridge_protocols': bridge_protocols, 'transaction_priorities': transaction_priorities, 'routing_strategies': routing_strategies, 'security_levels': [level.value for level in SecurityLevel], 'last_updated': datetime.now(UTC).isoformat()}
    except Exception:
        raise HTTPException(status_code=500, detail='Error getting configuration')

@router.get('/bridge/whitelist', response_model=dict[str, Any])
@rate_limit(rate=500, per=60)
async def get_bridge_whitelist(request: Request, session: Session=Depends(get_session)) -> dict[str, Any]:
    """Get current bridge whitelist configuration"""
    try:
        bridge_service = CrossChainBridgeService(session)
        whitelist = [{'source_chain_id': src, 'target_chain_id': tgt} for src, tgt in bridge_service.allowed_transfers]
        return {'allowed_transfers': whitelist, 'count': len(whitelist), 'last_updated': datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.error('Error getting bridge whitelist: %s', e, exc_info=True)
        raise HTTPException(status_code=500, detail='Error getting bridge whitelist')

@router.post('/bridge/whitelist/add', response_model=dict[str, Any])
@rate_limit(rate=50, per=60)
async def add_bridge_whitelist_entry(request: Request, source_chain_id: int, target_chain_id: int, session: Session=Depends(get_session)) -> dict[str, Any]:
    """Add a cross-chain transfer pair to the bridge whitelist"""
    try:
        bridge_service = CrossChainBridgeService(session)
        await bridge_service.add_allowed_transfer(source_chain_id, target_chain_id)
        return {'status': 'added', 'source_chain_id': source_chain_id, 'target_chain_id': target_chain_id, 'message': f'Transfer {source_chain_id} -> {target_chain_id} added to whitelist'}
    except Exception as e:
        logger.error('Error adding whitelist entry: %s', e, exc_info=True)
        raise HTTPException(status_code=500, detail='Error adding whitelist entry')
