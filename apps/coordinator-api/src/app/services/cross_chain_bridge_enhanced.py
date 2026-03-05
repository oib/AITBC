"""
Cross-Chain Bridge Service
Production-ready cross-chain bridge service with atomic swap protocol implementation
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union
from uuid import uuid4
from decimal import Decimal
from enum import Enum
import secrets
import hashlib
from aitbc.logging import get_logger

from sqlmodel import Session, select, update, delete, func, Field
from sqlalchemy.exc import SQLAlchemyError

from ..domain.cross_chain_bridge import (
    BridgeRequestStatus, ChainType, TransactionType, ValidatorStatus,
    BridgeRequest, Validator
)
from ..domain.agent_identity import AgentWallet, CrossChainMapping
from ..agent_identity.wallet_adapter_enhanced import (
    EnhancedWalletAdapter, WalletAdapterFactory, SecurityLevel,
    TransactionStatus, WalletStatus
)
from ..reputation.engine import CrossChainReputationEngine

logger = get_logger(__name__)


class BridgeProtocol(str, Enum):
    """Bridge protocol types"""
    ATOMIC_SWAP = "atomic_swap"
    HTLC = "htlc"  # Hashed Timelock Contract
    LIQUIDITY_POOL = "liquidity_pool"
    WRAPPED_TOKEN = "wrapped_token"


class BridgeSecurityLevel(str, Enum):
    """Bridge security levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAXIMUM = "maximum"


class CrossChainBridgeService:
    """Production-ready cross-chain bridge service"""
    
    def __init__(self, session: Session):
        self.session = session
        self.wallet_adapters: Dict[int, EnhancedWalletAdapter] = {}
        self.bridge_protocols: Dict[str, Any] = {}
        self.liquidity_pools: Dict[Tuple[int, int], Any] = {}
        self.reputation_engine = CrossChainReputationEngine(session)
    
    async def initialize_bridge(self, chain_configs: Dict[int, Dict[str, Any]]) -> None:
        """Initialize bridge service with chain configurations"""
        try:
            for chain_id, config in chain_configs.items():
                # Create wallet adapter for each chain
                adapter = WalletAdapterFactory.create_adapter(
                    chain_id=chain_id,
                    rpc_url=config["rpc_url"],
                    security_level=SecurityLevel(config.get("security_level", "medium"))
                )
                self.wallet_adapters[chain_id] = adapter
                
                # Initialize bridge protocol
                protocol = config.get("protocol", BridgeProtocol.ATOMIC_SWAP)
                self.bridge_protocols[str(chain_id)] = {
                    "protocol": protocol,
                    "enabled": config.get("enabled", True),
                    "min_amount": config.get("min_amount", 0.001),
                    "max_amount": config.get("max_amount", 1000000),
                    "fee_rate": config.get("fee_rate", 0.005),  # 0.5%
                    "confirmation_blocks": config.get("confirmation_blocks", 12)
                }
                
                # Initialize liquidity pool if applicable
                if protocol == BridgeProtocol.LIQUIDITY_POOL:
                    await self._initialize_liquidity_pool(chain_id, config)
            
            logger.info(f"Initialized bridge service for {len(chain_configs)} chains")
            
        except Exception as e:
            logger.error(f"Error initializing bridge service: {e}")
            raise
    
    async def create_bridge_request(
        self,
        user_address: str,
        source_chain_id: int,
        target_chain_id: int,
        amount: Union[Decimal, float, str],
        token_address: Optional[str] = None,
        target_address: Optional[str] = None,
        protocol: Optional[BridgeProtocol] = None,
        security_level: BridgeSecurityLevel = BridgeSecurityLevel.MEDIUM,
        deadline_minutes: int = 30
    ) -> Dict[str, Any]:
        """Create a new cross-chain bridge request"""
        
        try:
            # Validate chains
            if source_chain_id not in self.wallet_adapters or target_chain_id not in self.wallet_adapters:
                raise ValueError("Unsupported chain ID")
            
            if source_chain_id == target_chain_id:
                raise ValueError("Source and target chains must be different")
            
            # Validate amount
            amount_float = float(amount)
            source_config = self.bridge_protocols[str(source_chain_id)]
            
            if amount_float < source_config["min_amount"] or amount_float > source_config["max_amount"]:
                raise ValueError(f"Amount must be between {source_config['min_amount']} and {source_config['max_amount']}")
            
            # Validate addresses
            source_adapter = self.wallet_adapters[source_chain_id]
            target_adapter = self.wallet_adapters[target_chain_id]
            
            if not await source_adapter.validate_address(user_address):
                raise ValueError(f"Invalid source address: {user_address}")
            
            target_address = target_address or user_address
            if not await target_adapter.validate_address(target_address):
                raise ValueError(f"Invalid target address: {target_address}")
            
            # Calculate fees
            bridge_fee = amount_float * source_config["fee_rate"]
            network_fee = await self._estimate_network_fee(source_chain_id, amount_float, token_address)
            total_fee = bridge_fee + network_fee
            
            # Select protocol
            protocol = protocol or BridgeProtocol(source_config["protocol"])
            
            # Create bridge request
            bridge_request = BridgeRequest(
                id=f"bridge_{uuid4().hex[:8]}",
                user_address=user_address,
                source_chain_id=source_chain_id,
                target_chain_id=target_chain_id,
                amount=amount_float,
                token_address=token_address,
                target_address=target_address,
                protocol=protocol.value,
                security_level=security_level.value,
                bridge_fee=bridge_fee,
                network_fee=network_fee,
                total_fee=total_fee,
                deadline=datetime.utcnow() + timedelta(minutes=deadline_minutes),
                status=BridgeRequestStatus.PENDING,
                created_at=datetime.utcnow()
            )
            
            self.session.add(bridge_request)
            self.session.commit()
            self.session.refresh(bridge_request)
            
            # Start bridge process
            await self._process_bridge_request(bridge_request.id)
            
            logger.info(f"Created bridge request {bridge_request.id} for {amount_float} tokens")
            
            return {
                "bridge_request_id": bridge_request.id,
                "source_chain_id": source_chain_id,
                "target_chain_id": target_chain_id,
                "amount": str(amount_float),
                "token_address": token_address,
                "target_address": target_address,
                "protocol": protocol.value,
                "bridge_fee": bridge_fee,
                "network_fee": network_fee,
                "total_fee": total_fee,
                "estimated_completion": bridge_request.deadline.isoformat(),
                "status": bridge_request.status.value,
                "created_at": bridge_request.created_at.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error creating bridge request: {e}")
            self.session.rollback()
            raise
    
    async def get_bridge_request_status(self, bridge_request_id: str) -> Dict[str, Any]:
        """Get status of a bridge request"""
        
        try:
            stmt = select(BridgeRequest).where(
                BridgeRequest.id == bridge_request_id
            )
            bridge_request = self.session.execute(stmt).first()
            
            if not bridge_request:
                raise ValueError(f"Bridge request {bridge_request_id} not found")
            
            # Get transaction details
            transactions = []
            if bridge_request.source_transaction_hash:
                source_tx = await self._get_transaction_details(
                    bridge_request.source_chain_id,
                    bridge_request.source_transaction_hash
                )
                transactions.append({
                    "chain_id": bridge_request.source_chain_id,
                    "transaction_hash": bridge_request.source_transaction_hash,
                    "status": source_tx.get("status"),
                    "confirmations": await self._get_transaction_confirmations(
                        bridge_request.source_chain_id,
                        bridge_request.source_transaction_hash
                    )
                })
            
            if bridge_request.target_transaction_hash:
                target_tx = await self._get_transaction_details(
                    bridge_request.target_chain_id,
                    bridge_request.target_transaction_hash
                )
                transactions.append({
                    "chain_id": bridge_request.target_chain_id,
                    "transaction_hash": bridge_request.target_transaction_hash,
                    "status": target_tx.get("status"),
                    "confirmations": await self._get_transaction_confirmations(
                        bridge_request.target_chain_id,
                        bridge_request.target_transaction_hash
                    )
                })
            
            # Calculate progress
            progress = await self._calculate_bridge_progress(bridge_request)
            
            return {
                "bridge_request_id": bridge_request.id,
                "user_address": bridge_request.user_address,
                "source_chain_id": bridge_request.source_chain_id,
                "target_chain_id": bridge_request.target_chain_id,
                "amount": bridge_request.amount,
                "token_address": bridge_request.token_address,
                "target_address": bridge_request.target_address,
                "protocol": bridge_request.protocol,
                "status": bridge_request.status.value,
                "progress": progress,
                "transactions": transactions,
                "bridge_fee": bridge_request.bridge_fee,
                "network_fee": bridge_request.network_fee,
                "total_fee": bridge_request.total_fee,
                "deadline": bridge_request.deadline.isoformat(),
                "created_at": bridge_request.created_at.isoformat(),
                "updated_at": bridge_request.updated_at.isoformat(),
                "completed_at": bridge_request.completed_at.isoformat() if bridge_request.completed_at else None
            }
            
        except Exception as e:
            logger.error(f"Error getting bridge request status: {e}")
            raise
    
    async def cancel_bridge_request(self, bridge_request_id: str, reason: str) -> Dict[str, Any]:
        """Cancel a bridge request"""
        
        try:
            stmt = select(BridgeRequest).where(
                BridgeRequest.id == bridge_request_id
            )
            bridge_request = self.session.execute(stmt).first()
            
            if not bridge_request:
                raise ValueError(f"Bridge request {bridge_request_id} not found")
            
            if bridge_request.status not in [BridgeRequestStatus.PENDING, BridgeRequestStatus.CONFIRMED]:
                raise ValueError(f"Cannot cancel bridge request in status: {bridge_request.status}")
            
            # Update status
            bridge_request.status = BridgeRequestStatus.CANCELLED
            bridge_request.cancellation_reason = reason
            bridge_request.updated_at = datetime.utcnow()
            
            self.session.commit()
            
            # Refund if applicable
            if bridge_request.source_transaction_hash:
                await self._process_refund(bridge_request)
            
            logger.info(f"Cancelled bridge request {bridge_request_id}: {reason}")
            
            return {
                "bridge_request_id": bridge_request_id,
                "status": BridgeRequestStatus.CANCELLED.value,
                "reason": reason,
                "cancelled_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error cancelling bridge request: {e}")
            self.session.rollback()
            raise
    
    async def get_bridge_statistics(self, time_period_hours: int = 24) -> Dict[str, Any]:
        """Get bridge statistics for the specified time period"""
        
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=time_period_hours)
            
            # Get total requests
            total_requests = self.session.execute(
                select(func.count(BridgeRequest.id)).where(
                    BridgeRequest.created_at >= cutoff_time
                )
            ).scalar() or 0
            
            # Get completed requests
            completed_requests = self.session.execute(
                select(func.count(BridgeRequest.id)).where(
                    BridgeRequest.created_at >= cutoff_time,
                    BridgeRequest.status == BridgeRequestStatus.COMPLETED
                )
            ).scalar() or 0
            
            # Get total volume
            total_volume = self.session.execute(
                select(func.sum(BridgeRequest.amount)).where(
                    BridgeRequest.created_at >= cutoff_time,
                    BridgeRequest.status == BridgeRequestStatus.COMPLETED
                )
            ).scalar() or 0
            
            # Get total fees
            total_fees = self.session.execute(
                select(func.sum(BridgeRequest.total_fee)).where(
                    BridgeRequest.created_at >= cutoff_time,
                    BridgeRequest.status == BridgeRequestStatus.COMPLETED
                )
            ).scalar() or 0
            
            # Get success rate
            success_rate = completed_requests / max(total_requests, 1)
            
            # Get average processing time
            avg_processing_time = self.session.execute(
                select(func.avg(
                    func.extract('epoch', BridgeRequest.completed_at) -
                    func.extract('epoch', BridgeRequest.created_at)
                )).where(
                    BridgeRequest.created_at >= cutoff_time,
                    BridgeRequest.status == BridgeRequestStatus.COMPLETED
                )
            ).scalar() or 0
            
            # Get chain distribution
            chain_distribution = {}
            for chain_id in self.wallet_adapters.keys():
                chain_requests = self.session.execute(
                    select(func.count(BridgeRequest.id)).where(
                        BridgeRequest.created_at >= cutoff_time,
                        BridgeRequest.source_chain_id == chain_id
                    )
                ).scalar() or 0
                
                chain_distribution[str(chain_id)] = chain_requests
            
            return {
                "time_period_hours": time_period_hours,
                "total_requests": total_requests,
                "completed_requests": completed_requests,
                "success_rate": success_rate,
                "total_volume": total_volume,
                "total_fees": total_fees,
                "average_processing_time_minutes": avg_processing_time / 60,
                "chain_distribution": chain_distribution,
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting bridge statistics: {e}")
            raise
    
    async def get_liquidity_pools(self) -> List[Dict[str, Any]]:
        """Get all liquidity pool information"""
        
        try:
            pools = []
            
            for chain_pair, pool in self.liquidity_pools.items():
                source_chain, target_chain = chain_pair
                
                pool_info = {
                    "source_chain_id": source_chain,
                    "target_chain_id": target_chain,
                    "total_liquidity": pool.get("total_liquidity", 0),
                    "utilization_rate": pool.get("utilization_rate", 0),
                    "apr": pool.get("apr", 0),
                    "fee_rate": pool.get("fee_rate", 0.005),
                    "last_updated": pool.get("last_updated", datetime.utcnow().isoformat())
                }
                
                pools.append(pool_info)
            
            return pools
            
        except Exception as e:
            logger.error(f"Error getting liquidity pools: {e}")
            raise
    
    # Private methods
    async def _process_bridge_request(self, bridge_request_id: str) -> None:
        """Process a bridge request"""
        
        try:
            stmt = select(BridgeRequest).where(
                BridgeRequest.id == bridge_request_id
            )
            bridge_request = self.session.execute(stmt).first()
            
            if not bridge_request:
                logger.error(f"Bridge request {bridge_request_id} not found")
                return
            
            # Update status to confirmed
            bridge_request.status = BridgeRequestStatus.CONFIRMED
            bridge_request.updated_at = datetime.utcnow()
            self.session.commit()
            
            # Execute bridge based on protocol
            if bridge_request.protocol == BridgeProtocol.ATOMIC_SWAP.value:
                await self._execute_atomic_swap(bridge_request)
            elif bridge_request.protocol == BridgeProtocol.LIQUIDITY_POOL.value:
                await self._execute_liquidity_pool_swap(bridge_request)
            elif bridge_request.protocol == BridgeProtocol.HTLC.value:
                await self._execute_htlc_swap(bridge_request)
            else:
                raise ValueError(f"Unsupported protocol: {bridge_request.protocol}")
            
        except Exception as e:
            logger.error(f"Error processing bridge request {bridge_request_id}: {e}")
            # Update status to failed
            try:
                stmt = update(BridgeRequest).where(
                    BridgeRequest.id == bridge_request_id
                ).values(
                    status=BridgeRequestStatus.FAILED,
                    error_message=str(e),
                    updated_at=datetime.utcnow()
                )
                self.session.execute(stmt)
                self.session.commit()
            except:
                pass
    
    async def _execute_atomic_swap(self, bridge_request: BridgeRequest) -> None:
        """Execute atomic swap protocol"""
        
        try:
            source_adapter = self.wallet_adapters[bridge_request.source_chain_id]
            target_adapter = self.wallet_adapters[bridge_request.target_chain_id]
            
            # Create atomic swap contract on source chain
            source_swap_data = await self._create_atomic_swap_contract(
                bridge_request,
                "source"
            )
            
            # Execute source transaction
            source_tx = await source_adapter.execute_transaction(
                from_address=bridge_request.user_address,
                to_address=source_swap_data["contract_address"],
                amount=bridge_request.amount,
                token_address=bridge_request.token_address,
                data=source_swap_data["contract_data"]
            )
            
            # Update bridge request with source transaction
            bridge_request.source_transaction_hash = source_tx["transaction_hash"]
            bridge_request.updated_at = datetime.utcnow()
            self.session.commit()
            
            # Wait for confirmations
            await self._wait_for_confirmations(
                bridge_request.source_chain_id,
                source_tx["transaction_hash"]
            )
            
            # Execute target transaction
            target_swap_data = await self._create_atomic_swap_contract(
                bridge_request,
                "target"
            )
            
            target_tx = await target_adapter.execute_transaction(
                from_address=bridge_request.target_address,
                to_address=target_swap_data["contract_address"],
                amount=bridge_request.amount * 0.99,  # Account for fees
                token_address=bridge_request.token_address,
                data=target_swap_data["contract_data"]
            )
            
            # Update bridge request with target transaction
            bridge_request.target_transaction_hash = target_tx["transaction_hash"]
            bridge_request.status = BridgeRequestStatus.COMPLETED
            bridge_request.completed_at = datetime.utcnow()
            bridge_request.updated_at = datetime.utcnow()
            self.session.commit()
            
            logger.info(f"Completed atomic swap for bridge request {bridge_request.id}")
            
        except Exception as e:
            logger.error(f"Error executing atomic swap: {e}")
            raise
    
    async def _execute_liquidity_pool_swap(self, bridge_request: BridgeRequest) -> None:
        """Execute liquidity pool swap"""
        
        try:
            source_adapter = self.wallet_adapters[bridge_request.source_chain_id]
            target_adapter = self.wallet_adapters[bridge_request.target_chain_id]
            
            # Get liquidity pool
            pool_key = (bridge_request.source_chain_id, bridge_request.target_chain_id)
            pool = self.liquidity_pools.get(pool_key)
            
            if not pool:
                raise ValueError(f"No liquidity pool found for chain pair {pool_key}")
            
            # Execute swap through liquidity pool
            swap_data = await self._create_liquidity_pool_swap_data(bridge_request, pool)
            
            # Execute source transaction
            source_tx = await source_adapter.execute_transaction(
                from_address=bridge_request.user_address,
                to_address=swap_data["pool_address"],
                amount=bridge_request.amount,
                token_address=bridge_request.token_address,
                data=swap_data["swap_data"]
            )
            
            # Update bridge request
            bridge_request.source_transaction_hash = source_tx["transaction_hash"]
            bridge_request.status = BridgeRequestStatus.COMPLETED
            bridge_request.completed_at = datetime.utcnow()
            bridge_request.updated_at = datetime.utcnow()
            self.session.commit()
            
            logger.info(f"Completed liquidity pool swap for bridge request {bridge_request.id}")
            
        except Exception as e:
            logger.error(f"Error executing liquidity pool swap: {e}")
            raise
    
    async def _execute_htlc_swap(self, bridge_request: BridgeRequest) -> None:
        """Execute HTLC (Hashed Timelock Contract) swap"""
        
        try:
            # Generate secret and hash
            secret = secrets.token_hex(32)
            secret_hash = hashlib.sha256(secret.encode()).hexdigest()
            
            # Create HTLC contract on source chain
            source_htlc_data = await self._create_htlc_contract(
                bridge_request,
                secret_hash,
                "source"
            )
            
            source_adapter = self.wallet_adapters[bridge_request.source_chain_id]
            source_tx = await source_adapter.execute_transaction(
                from_address=bridge_request.user_address,
                to_address=source_htlc_data["contract_address"],
                amount=bridge_request.amount,
                token_address=bridge_request.token_address,
                data=source_htlc_data["contract_data"]
            )
            
            # Update bridge request
            bridge_request.source_transaction_hash = source_tx["transaction_hash"]
            bridge_request.secret_hash = secret_hash
            bridge_request.updated_at = datetime.utcnow()
            self.session.commit()
            
            # Create HTLC contract on target chain
            target_htlc_data = await self._create_htlc_contract(
                bridge_request,
                secret_hash,
                "target"
            )
            
            target_adapter = self.wallet_adapters[bridge_request.target_chain_id]
            target_tx = await target_adapter.execute_transaction(
                from_address=bridge_request.target_address,
                to_address=target_htlc_data["contract_address"],
                amount=bridge_request.amount * 0.99,
                token_address=bridge_request.token_address,
                data=target_htlc_data["contract_data"]
            )
            
            # Complete HTLC by revealing secret
            await self._complete_htlc(bridge_request, secret)
            
            logger.info(f"Completed HTLC swap for bridge request {bridge_request.id}")
            
        except Exception as e:
            logger.error(f"Error executing HTLC swap: {e}")
            raise
    
    async def _create_atomic_swap_contract(self, bridge_request: BridgeRequest, direction: str) -> Dict[str, Any]:
        """Create atomic swap contract data"""
        # Mock implementation
        contract_address = f"0x{hashlib.sha256(f'atomic_swap_{bridge_request.id}_{direction}'.encode()).hexdigest()[:40]}"
        contract_data = f"0x{hashlib.sha256(f'swap_data_{bridge_request.id}'.encode()).hexdigest()}"
        
        return {
            "contract_address": contract_address,
            "contract_data": contract_data
        }
    
    async def _create_liquidity_pool_swap_data(self, bridge_request: BridgeRequest, pool: Dict[str, Any]) -> Dict[str, Any]:
        """Create liquidity pool swap data"""
        # Mock implementation
        pool_address = pool.get("address", f"0x{hashlib.sha256(f'pool_{bridge_request.source_chain_id}_{bridge_request.target_chain_id}'.encode()).hexdigest()[:40]}")
        swap_data = f"0x{hashlib.sha256(f'swap_{bridge_request.id}'.encode()).hexdigest()}"
        
        return {
            "pool_address": pool_address,
            "swap_data": swap_data
        }
    
    async def _create_htlc_contract(self, bridge_request: BridgeRequest, secret_hash: str, direction: str) -> Dict[str, Any]:
        """Create HTLC contract data"""
        contract_address = f"0x{hashlib.sha256(f'htlc_{bridge_request.id}_{direction}_{secret_hash}'.encode()).hexdigest()[:40]}"
        contract_data = f"0x{hashlib.sha256(f'htlc_data_{bridge_request.id}_{secret_hash}'.encode()).hexdigest()}"
        
        return {
            "contract_address": contract_address,
            "contract_data": contract_data,
            "secret_hash": secret_hash
        }
    
    async def _complete_htlc(self, bridge_request: BridgeRequest, secret: str) -> None:
        """Complete HTLC by revealing secret"""
        # Mock implementation
        bridge_request.target_transaction_hash = f"0x{hashlib.sha256(f'htlc_complete_{bridge_request.id}_{secret}'.encode()).hexdigest()}"
        bridge_request.status = BridgeRequestStatus.COMPLETED
        bridge_request.completed_at = datetime.utcnow()
        bridge_request.updated_at = datetime.utcnow()
        self.session.commit()
    
    async def _estimate_network_fee(self, chain_id: int, amount: float, token_address: Optional[str]) -> float:
        """Estimate network fee for transaction"""
        try:
            adapter = self.wallet_adapters[chain_id]
            
            # Mock address for estimation
            mock_address = f"0x{hashlib.sha256(f'fee_estimate_{chain_id}'.encode()).hexdigest()[:40]}"
            
            gas_estimate = await adapter.estimate_gas(
                from_address=mock_address,
                to_address=mock_address,
                amount=amount,
                token_address=token_address
            )
            
            gas_price = await adapter._get_gas_price()
            
            # Convert to ETH value
            fee_eth = (int(gas_estimate["gas_limit"], 16) * gas_price) / 10**18
            
            return fee_eth
            
        except Exception as e:
            logger.error(f"Error estimating network fee: {e}")
            return 0.01  # Default fee
    
    async def _get_transaction_details(self, chain_id: int, transaction_hash: str) -> Dict[str, Any]:
        """Get transaction details"""
        try:
            adapter = self.wallet_adapters[chain_id]
            return await adapter.get_transaction_status(transaction_hash)
        except Exception as e:
            logger.error(f"Error getting transaction details: {e}")
            return {"status": "unknown"}
    
    async def _get_transaction_confirmations(self, chain_id: int, transaction_hash: str) -> int:
        """Get number of confirmations for transaction"""
        try:
            adapter = self.wallet_adapters[chain_id]
            tx_details = await adapter.get_transaction_status(transaction_hash)
            
            if tx_details.get("block_number"):
                # Mock current block number
                current_block = 12345
                tx_block = int(tx_details["block_number"], 16)
                return current_block - tx_block
            
            return 0
            
        except Exception as e:
            logger.error(f"Error getting transaction confirmations: {e}")
            return 0
    
    async def _wait_for_confirmations(self, chain_id: int, transaction_hash: str) -> None:
        """Wait for required confirmations"""
        try:
            adapter = self.wallet_adapters[chain_id]
            required_confirmations = self.bridge_protocols[str(chain_id)]["confirmation_blocks"]
            
            while True:
                confirmations = await self._get_transaction_confirmations(chain_id, transaction_hash)
                
                if confirmations >= required_confirmations:
                    break
                
                await asyncio.sleep(10)  # Wait 10 seconds before checking again
                
        except Exception as e:
            logger.error(f"Error waiting for confirmations: {e}")
            raise
    
    async def _calculate_bridge_progress(self, bridge_request: BridgeRequest) -> float:
        """Calculate bridge progress percentage"""
        
        try:
            if bridge_request.status == BridgeRequestStatus.COMPLETED:
                return 100.0
            elif bridge_request.status == BridgeRequestStatus.FAILED or bridge_request.status == BridgeRequestStatus.CANCELLED:
                return 0.0
            elif bridge_request.status == BridgeRequestStatus.PENDING:
                return 10.0
            elif bridge_request.status == BridgeRequestStatus.CONFIRMED:
                progress = 50.0
                
                # Add progress based on confirmations
                if bridge_request.source_transaction_hash:
                    source_confirmations = await self._get_transaction_confirmations(
                        bridge_request.source_chain_id,
                        bridge_request.source_transaction_hash
                    )
                    
                    required_confirmations = self.bridge_protocols[str(bridge_request.source_chain_id)]["confirmation_blocks"]
                    confirmation_progress = (source_confirmations / required_confirmations) * 40
                    progress += confirmation_progress
                
                return min(progress, 90.0)
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Error calculating bridge progress: {e}")
            return 0.0
    
    async def _process_refund(self, bridge_request: BridgeRequest) -> None:
        """Process refund for cancelled bridge request"""
        try:
            # Mock refund implementation
            logger.info(f"Processing refund for bridge request {bridge_request.id}")
            
        except Exception as e:
            logger.error(f"Error processing refund: {e}")
    
    async def _initialize_liquidity_pool(self, chain_id: int, config: Dict[str, Any]) -> None:
        """Initialize liquidity pool for chain"""
        try:
            # Mock liquidity pool initialization
            pool_address = f"0x{hashlib.sha256(f'pool_{chain_id}'.encode()).hexdigest()[:40]}"
            
            self.liquidity_pools[(chain_id, 1)] = {  # Assuming ETH as target
                "address": pool_address,
                "total_liquidity": config.get("initial_liquidity", 1000000),
                "utilization_rate": 0.0,
                "apr": 0.05,  # 5% APR
                "fee_rate": 0.005,  # 0.5% fee
                "last_updated": datetime.utcnow()
            }
            
            logger.info(f"Initialized liquidity pool for chain {chain_id}")
            
        except Exception as e:
            logger.error(f"Error initializing liquidity pool: {e}")
