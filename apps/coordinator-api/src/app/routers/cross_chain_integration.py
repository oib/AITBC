"""
Cross-Chain Integration API Router
REST API endpoints for enhanced multi-chain wallet adapter, cross-chain bridge service, and transaction manager
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlmodel import Session, select, func, Field

from ..storage.db import get_session
from ..agent_identity.wallet_adapter_enhanced import (
    EnhancedWalletAdapter, WalletAdapterFactory, SecurityLevel,
    WalletStatus, TransactionStatus
)
from ..services.cross_chain_bridge_enhanced import (
    CrossChainBridgeService, BridgeProtocol, BridgeSecurityLevel,
    BridgeRequestStatus
)
from ..services.multi_chain_transaction_manager import (
    MultiChainTransactionManager, TransactionPriority, TransactionType,
    RoutingStrategy
)
from ..agent_identity.manager import AgentIdentityManager
from ..reputation.engine import CrossChainReputationEngine

router = APIRouter(
    prefix="/cross-chain",
    tags=["Cross-Chain Integration"]
)

# Dependency injection
def get_agent_identity_manager(session: Session = Depends(get_session)) -> AgentIdentityManager:
    return AgentIdentityManager(session)

def get_reputation_engine(session: Session = Depends(get_session)) -> CrossChainReputationEngine:
    return CrossChainReputationEngine(session)


# Enhanced Wallet Adapter Endpoints
@router.post("/wallets/create", response_model=Dict[str, Any])
async def create_enhanced_wallet(
    owner_address: str,
    chain_id: int,
    security_config: Dict[str, Any],
    security_level: SecurityLevel = SecurityLevel.MEDIUM,
    session: Session = Depends(get_session),
    identity_manager: AgentIdentityManager = Depends(get_agent_identity_manager)
) -> Dict[str, Any]:
    """Create an enhanced multi-chain wallet"""
    
    try:
        # Validate owner identity
        identity = await identity_manager.get_identity_by_address(owner_address)
        if not identity:
            raise HTTPException(status_code=404, detail="Identity not found for address")
        
        # Create wallet adapter
        adapter = WalletAdapterFactory.create_adapter(chain_id, "mock_rpc_url", security_level)
        
        # Create wallet
        wallet_data = await adapter.create_wallet(owner_address, security_config)
        
        # Store wallet in database (mock implementation)
        wallet_id = f"wallet_{uuid4().hex[:8]}"
        
        return {
            "wallet_id": wallet_id,
            "address": wallet_data["address"],
            "chain_id": chain_id,
            "chain_type": wallet_data["chain_type"],
            "owner_address": owner_address,
            "security_level": security_level.value,
            "status": WalletStatus.ACTIVE.value,
            "created_at": wallet_data["created_at"],
            "security_config": wallet_data["security_config"]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating wallet: {str(e)}")


@router.get("/wallets/{wallet_address}/balance", response_model=Dict[str, Any])
async def get_wallet_balance(
    wallet_address: str,
    chain_id: int,
    token_address: Optional[str] = Query(None),
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Get wallet balance with multi-token support"""
    
    try:
        # Create wallet adapter
        adapter = WalletAdapterFactory.create_adapter(chain_id, "mock_rpc_url")
        
        # Validate address
        if not await adapter.validate_address(wallet_address):
            raise HTTPException(status_code=400, detail="Invalid wallet address")
        
        # Get balance
        balance_data = await adapter.get_balance(wallet_address, token_address)
        
        return balance_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting balance: {str(e)}")


@router.post("/wallets/{wallet_address}/transactions", response_model=Dict[str, Any])
async def execute_wallet_transaction(
    wallet_address: str,
    chain_id: int,
    to_address: str,
    amount: float,
    token_address: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    gas_limit: Optional[int] = None,
    gas_price: Optional[int] = None,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Execute a transaction from wallet"""
    
    try:
        # Create wallet adapter
        adapter = WalletAdapterFactory.create_adapter(chain_id, "mock_rpc_url")
        
        # Validate addresses
        if not await adapter.validate_address(wallet_address) or not await adapter.validate_address(to_address):
            raise HTTPException(status_code=400, detail="Invalid addresses provided")
        
        # Execute transaction
        transaction_data = await adapter.execute_transaction(
            from_address=wallet_address,
            to_address=to_address,
            amount=amount,
            token_address=token_address,
            data=data,
            gas_limit=gas_limit,
            gas_price=gas_price
        )
        
        return transaction_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing transaction: {str(e)}")


@router.get("/wallets/{wallet_address}/transactions", response_model=List[Dict[str, Any]])
async def get_wallet_transaction_history(
    wallet_address: str,
    chain_id: int,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    from_block: Optional[int] = None,
    to_block: Optional[int] = None,
    session: Session = Depends(get_session)
) -> List[Dict[str, Any]]:
    """Get wallet transaction history"""
    
    try:
        # Create wallet adapter
        adapter = WalletAdapterFactory.create_adapter(chain_id, "mock_rpc_url")
        
        # Validate address
        if not await adapter.validate_address(wallet_address):
            raise HTTPException(status_code=400, detail="Invalid wallet address")
        
        # Get transaction history
        transactions = await adapter.get_transaction_history(
            wallet_address, limit, offset, from_block, to_block
        )
        
        return transactions
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting transaction history: {str(e)}")


@router.post("/wallets/{wallet_address}/sign", response_model=Dict[str, Any])
async def sign_message(
    wallet_address: str,
    chain_id: int,
    message: str,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Sign a message with wallet"""
    
    try:
        # Create wallet adapter
        adapter = WalletAdapterFactory.create_adapter(chain_id, "mock_rpc_url")
        
        # Get private key (in production, this would be securely retrieved)
        private_key = "mock_private_key"  # Mock implementation
        
        # Sign message
        signature_data = await adapter.secure_sign_message(message, private_key)
        
        return signature_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error signing message: {str(e)}")


@router.post("/wallets/verify-signature", response_model=Dict[str, Any])
async def verify_signature(
    message: str,
    signature: str,
    address: str,
    chain_id: int,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Verify a message signature"""
    
    try:
        # Create wallet adapter
        adapter = WalletAdapterFactory.create_adapter(chain_id, "mock_rpc_url")
        
        # Verify signature
        is_valid = await adapter.verify_signature(message, signature, address)
        
        return {
            "valid": is_valid,
            "message": message,
            "address": address,
            "chain_id": chain_id,
            "verified_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error verifying signature: {str(e)}")


# Cross-Chain Bridge Endpoints
@router.post("/bridge/create-request", response_model=Dict[str, Any])
async def create_bridge_request(
    user_address: str,
    source_chain_id: int,
    target_chain_id: int,
    amount: float,
    token_address: Optional[str] = None,
    target_address: Optional[str] = None,
    protocol: Optional[BridgeProtocol] = None,
    security_level: BridgeSecurityLevel = BridgeSecurityLevel.MEDIUM,
    deadline_minutes: int = Query(30, ge=5, le=1440),
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Create a cross-chain bridge request"""
    
    try:
        # Create bridge service
        bridge_service = CrossChainBridgeService(session)
        
        # Initialize bridge if not already done
        chain_configs = {
            source_chain_id: {"rpc_url": "mock_rpc_url"},
            target_chain_id: {"rpc_url": "mock_rpc_url"}
        }
        await bridge_service.initialize_bridge(chain_configs)
        
        # Create bridge request
        bridge_request = await bridge_service.create_bridge_request(
            user_address=user_address,
            source_chain_id=source_chain_id,
            target_chain_id=target_chain_id,
            amount=amount,
            token_address=token_address,
            target_address=target_address,
            protocol=protocol,
            security_level=security_level,
            deadline_minutes=deadline_minutes
        )
        
        return bridge_request
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating bridge request: {str(e)}")


@router.get("/bridge/request/{bridge_request_id}", response_model=Dict[str, Any])
async def get_bridge_request_status(
    bridge_request_id: str,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Get status of a bridge request"""
    
    try:
        # Create bridge service
        bridge_service = CrossChainBridgeService(session)
        
        # Get bridge request status
        status = await bridge_service.get_bridge_request_status(bridge_request_id)
        
        return status
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting bridge request status: {str(e)}")


@router.post("/bridge/request/{bridge_request_id}/cancel", response_model=Dict[str, Any])
async def cancel_bridge_request(
    bridge_request_id: str,
    reason: str,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Cancel a bridge request"""
    
    try:
        # Create bridge service
        bridge_service = CrossChainBridgeService(session)
        
        # Cancel bridge request
        result = await bridge_service.cancel_bridge_request(bridge_request_id, reason)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cancelling bridge request: {str(e)}")


@router.get("/bridge/statistics", response_model=Dict[str, Any])
async def get_bridge_statistics(
    time_period_hours: int = Query(24, ge=1, le=8760),
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Get bridge statistics"""
    
    try:
        # Create bridge service
        bridge_service = CrossChainBridgeService(session)
        
        # Get statistics
        stats = await bridge_service.get_bridge_statistics(time_period_hours)
        
        return stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting bridge statistics: {str(e)}")


@router.get("/bridge/liquidity-pools", response_model=List[Dict[str, Any]])
async def get_liquidity_pools(
    session: Session = Depends(get_session)
) -> List[Dict[str, Any]]:
    """Get all liquidity pool information"""
    
    try:
        # Create bridge service
        bridge_service = CrossChainBridgeService(session)
        
        # Get liquidity pools
        pools = await bridge_service.get_liquidity_pools()
        
        return pools
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting liquidity pools: {str(e)}")


# Multi-Chain Transaction Manager Endpoints
@router.post("/transactions/submit", response_model=Dict[str, Any])
async def submit_transaction(
    user_id: str,
    chain_id: int,
    transaction_type: TransactionType,
    from_address: str,
    to_address: str,
    amount: float,
    token_address: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    priority: TransactionPriority = TransactionPriority.MEDIUM,
    routing_strategy: Optional[RoutingStrategy] = None,
    gas_limit: Optional[int] = None,
    gas_price: Optional[int] = None,
    max_fee_per_gas: Optional[int] = None,
    deadline_minutes: int = Query(30, ge=5, le=1440),
    metadata: Optional[Dict[str, Any]] = None,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Submit a multi-chain transaction"""
    
    try:
        # Create transaction manager
        tx_manager = MultiChainTransactionManager(session)
        
        # Initialize with mock configs
        chain_configs = {
            chain_id: {"rpc_url": "mock_rpc_url"}
        }
        await tx_manager.initialize(chain_configs)
        
        # Submit transaction
        result = await tx_manager.submit_transaction(
            user_id=user_id,
            chain_id=chain_id,
            transaction_type=transaction_type,
            from_address=from_address,
            to_address=to_address,
            amount=amount,
            token_address=token_address,
            data=data,
            priority=priority,
            routing_strategy=routing_strategy,
            gas_limit=gas_limit,
            gas_price=gas_price,
            max_fee_per_gas=max_fee_per_gas,
            deadline_minutes=deadline_minutes,
            metadata=metadata
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error submitting transaction: {str(e)}")


@router.get("/transactions/{transaction_id}", response_model=Dict[str, Any])
async def get_transaction_status(
    transaction_id: str,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Get detailed transaction status"""
    
    try:
        # Create transaction manager
        tx_manager = MultiChainTransactionManager(session)
        
        # Initialize with mock configs
        chain_configs = {
            1: {"rpc_url": "mock_rpc_url"},
            137: {"rpc_url": "mock_rpc_url"}
        }
        await tx_manager.initialize(chain_configs)
        
        # Get transaction status
        status = await tx_manager.get_transaction_status(transaction_id)
        
        return status
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting transaction status: {str(e)}")


@router.post("/transactions/{transaction_id}/cancel", response_model=Dict[str, Any])
async def cancel_transaction(
    transaction_id: str,
    reason: str,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Cancel a transaction"""
    
    try:
        # Create transaction manager
        tx_manager = MultiChainTransactionManager(session)
        
        # Initialize with mock configs
        chain_configs = {
            1: {"rpc_url": "mock_rpc_url"},
            137: {"rpc_url": "mock_rpc_url"}
        }
        await tx_manager.initialize(chain_configs)
        
        # Cancel transaction
        result = await tx_manager.cancel_transaction(transaction_id, reason)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cancelling transaction: {str(e)}")


@router.get("/transactions/history", response_model=List[Dict[str, Any]])
async def get_transaction_history(
    user_id: Optional[str] = Query(None),
    chain_id: Optional[int] = Query(None),
    transaction_type: Optional[TransactionType] = Query(None),
    status: Optional[TransactionStatus] = Query(None),
    priority: Optional[TransactionPriority] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    session: Session = Depends(get_session)
) -> List[Dict[str, Any]]:
    """Get transaction history with filtering"""
    
    try:
        # Create transaction manager
        tx_manager = MultiChainTransactionManager(session)
        
        # Initialize with mock configs
        chain_configs = {
            1: {"rpc_url": "mock_rpc_url"},
            137: {"rpc_url": "mock_rpc_url"}
        }
        await tx_manager.initialize(chain_configs)
        
        # Get transaction history
        history = await tx_manager.get_transaction_history(
            user_id=user_id,
            chain_id=chain_id,
            transaction_type=transaction_type,
            status=status,
            priority=priority,
            limit=limit,
            offset=offset,
            from_date=from_date,
            to_date=to_date
        )
        
        return history
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting transaction history: {str(e)}")


@router.get("/transactions/statistics", response_model=Dict[str, Any])
async def get_transaction_statistics(
    time_period_hours: int = Query(24, ge=1, le=8760),
    chain_id: Optional[int] = Query(None),
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Get transaction statistics"""
    
    try:
        # Create transaction manager
        tx_manager = MultiChainTransactionManager(session)
        
        # Initialize with mock configs
        chain_configs = {
            1: {"rpc_url": "mock_rpc_url"},
            137: {"rpc_url": "mock_rpc_url"}
        }
        await tx_manager.initialize(chain_configs)
        
        # Get statistics
        stats = await tx_manager.get_transaction_statistics(time_period_hours, chain_id)
        
        return stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting transaction statistics: {str(e)}")


@router.post("/transactions/optimize-routing", response_model=Dict[str, Any])
async def optimize_transaction_routing(
    transaction_type: TransactionType,
    amount: float,
    from_chain: int,
    to_chain: Optional[int] = None,
    urgency: TransactionPriority = TransactionPriority.MEDIUM,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Optimize transaction routing for best performance"""
    
    try:
        # Create transaction manager
        tx_manager = MultiChainTransactionManager(session)
        
        # Initialize with mock configs
        chain_configs = {
            1: {"rpc_url": "mock_rpc_url"},
            137: {"rpc_url": "mock_rpc_url"}
        }
        await tx_manager.initialize(chain_configs)
        
        # Optimize routing
        optimization = await tx_manager.optimize_transaction_routing(
            transaction_type=transaction_type,
            amount=amount,
            from_chain=from_chain,
            to_chain=to_chain,
            urgency=urgency
        )
        
        return optimization
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error optimizing routing: {str(e)}")


# Configuration and Status Endpoints
@router.get("/chains/supported", response_model=List[Dict[str, Any]])
async def get_supported_chains() -> List[Dict[str, Any]]:
    """Get list of supported blockchain chains"""
    
    try:
        # Get supported chains from wallet adapter factory
        supported_chains = WalletAdapterFactory.get_supported_chains()
        
        chain_info = []
        for chain_id in supported_chains:
            info = WalletAdapterFactory.get_chain_info(chain_id)
            chain_info.append({
                "chain_id": chain_id,
                **info
            })
        
        return chain_info
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting supported chains: {str(e)}")


@router.get("/chains/{chain_id}/info", response_model=Dict[str, Any])
async def get_chain_info(
    chain_id: int,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Get information about a specific chain"""
    
    try:
        # Get chain info from wallet adapter factory
        info = WalletAdapterFactory.get_chain_info(chain_id)
        
        # Add additional information
        chain_info = {
            "chain_id": chain_id,
            **info,
            "supported": chain_id in WalletAdapterFactory.get_supported_chains(),
            "adapter_available": True
        }
        
        return chain_info
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting chain info: {str(e)}")


@router.get("/health", response_model=Dict[str, Any])
async def get_cross_chain_health(
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Get cross-chain integration health status"""
    
    try:
        # Get supported chains
        supported_chains = WalletAdapterFactory.get_supported_chains()
        
        # Create mock services for health check
        bridge_service = CrossChainBridgeService(session)
        tx_manager = MultiChainTransactionManager(session)
        
        # Initialize with mock configs
        chain_configs = {
            chain_id: {"rpc_url": "mock_rpc_url"}
            for chain_id in supported_chains
        }
        
        await bridge_service.initialize_bridge(chain_configs)
        await tx_manager.initialize(chain_configs)
        
        # Get statistics
        bridge_stats = await bridge_service.get_bridge_statistics(1)
        tx_stats = await tx_manager.get_transaction_statistics(1)
        
        return {
            "status": "healthy",
            "supported_chains": len(supported_chains),
            "bridge_requests": bridge_stats["total_requests"],
            "bridge_success_rate": bridge_stats["success_rate"],
            "transactions_submitted": tx_stats["total_transactions"],
            "transaction_success_rate": tx_stats["success_rate"],
            "average_processing_time": tx_stats["average_processing_time_minutes"],
            "active_liquidity_pools": len(await bridge_service.get_liquidity_pools()),
            "last_updated": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting health status: {str(e)}")


@router.get("/config", response_model=Dict[str, Any])
async def get_cross_chain_config(
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """Get cross-chain integration configuration"""
    
    try:
        # Get supported chains
        supported_chains = WalletAdapterFactory.get_supported_chains()
        
        # Get bridge protocols
        bridge_protocols = {
            protocol.value: {
                "name": protocol.value.replace("_", " ").title(),
                "description": f"{protocol.value.replace('_', ' ').title()} protocol for cross-chain transfers",
                "security_levels": [level.value for level in BridgeSecurityLevel],
                "recommended_for": protocol.value == BridgeProtocol.ATOMIC_SWAP.value and "small_transfers" or
                                protocol.value == BridgeProtocol.LIQUIDITY_POOL.value and "large_transfers" or
                                protocol.value == BridgeProtocol.HTLC.value and "high_security"
            }
            for protocol in BridgeProtocol
        }
        
        # Get transaction priorities
        transaction_priorities = {
            priority.value: {
                "name": priority.value.title(),
                "description": f"{priority.value.title()} priority transactions",
                "processing_multiplier": {
                    TransactionPriority.LOW.value: 1.5,
                    TransactionPriority.MEDIUM.value: 1.0,
                    TransactionPriority.HIGH.value: 0.8,
                    TransactionPriority.URGENT.value: 0.7,
                    TransactionPriority.CRITICAL.value: 0.5
                }.get(priority.value, 1.0)
            }
            for priority in TransactionPriority
        }
        
        # Get routing strategies
        routing_strategies = {
            strategy.value: {
                "name": strategy.value.title(),
                "description": f"{strategy.value.title()} routing strategy for transactions",
                "best_for": {
                    RoutingStrategy.FASTEST.value: "time_sensitive_transactions",
                    RoutingStrategy.CHEAPEST.value: "cost_sensitive_transactions",
                    RoutingStrategy.BALANCED.value: "general_transactions",
                    RoutingStrategy.RELIABLE.value: "high_value_transactions",
                    RoutingStrategy.PRIORITY.value: "priority_transactions"
                }.get(strategy.value, "general_transactions")
            }
            for strategy in RoutingStrategy
        }
        
        return {
            "supported_chains": supported_chains,
            "bridge_protocols": bridge_protocols,
            "transaction_priorities": transaction_priorities,
            "routing_strategies": routing_strategies,
            "security_levels": [level.value for level in SecurityLevel],
            "last_updated": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting configuration: {str(e)}")
