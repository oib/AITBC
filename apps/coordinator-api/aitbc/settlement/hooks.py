"""
Settlement hooks for coordinator API integration
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import asyncio
import logging

from .manager import BridgeManager
from .bridges.base import (
    SettlementMessage,
    SettlementResult,
    BridgeStatus
)
from ..models.job import Job
from ..models.receipt import Receipt

logger = logging.getLogger(__name__)


class SettlementHook:
    """Settlement hook for coordinator to handle cross-chain settlements"""
    
    def __init__(self, bridge_manager: BridgeManager):
        self.bridge_manager = bridge_manager
        self._enabled = True
    
    async def on_job_completed(self, job: Job) -> None:
        """Called when a job completes successfully"""
        if not self._enabled:
            return
        
        try:
            # Check if cross-chain settlement is required
            if await self._requires_cross_chain_settlement(job):
                await self._initiate_settlement(job)
        except Exception as e:
            logger.error(f"Failed to handle job completion for {job.id}: {e}")
            # Don't fail the job, just log the error
            await self._handle_settlement_error(job, e)
    
    async def on_job_failed(self, job: Job, error: Exception) -> None:
        """Called when a job fails"""
        # For failed jobs, we might want to refund any cross-chain payments
        if job.cross_chain_payment_id:
            try:
                await self._refund_cross_chain_payment(job)
            except Exception as e:
                logger.error(f"Failed to refund cross-chain payment for {job.id}: {e}")
    
    async def initiate_manual_settlement(
        self,
        job_id: str,
        target_chain_id: int,
        bridge_name: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None
    ) -> SettlementResult:
        """Manually initiate cross-chain settlement for a job"""
        # Get job
        job = await Job.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        if not job.completed:
            raise ValueError(f"Job {job_id} is not completed")
        
        # Override target chain if specified
        if target_chain_id:
            job.target_chain = target_chain_id
        
        # Create settlement message
        message = await self._create_settlement_message(job, options)
        
        # Send settlement
        result = await self.bridge_manager.settle_cross_chain(
            message,
            bridge_name=bridge_name
        )
        
        # Update job with settlement info
        job.cross_chain_settlement_id = result.message_id
        job.cross_chain_bridge = bridge_name or self.bridge_manager.default_adapter
        await job.save()
        
        return result
    
    async def get_settlement_status(self, settlement_id: str) -> SettlementResult:
        """Get status of a cross-chain settlement"""
        return await self.bridge_manager.get_settlement_status(settlement_id)
    
    async def estimate_settlement_cost(
        self,
        job_id: str,
        target_chain_id: int,
        bridge_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Estimate cost for cross-chain settlement"""
        # Get job
        job = await Job.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        # Create mock settlement message for estimation
        message = SettlementMessage(
            source_chain_id=await self._get_current_chain_id(),
            target_chain_id=target_chain_id,
            job_id=job.id,
            receipt_hash=job.receipt.hash if job.receipt else "",
            proof_data=job.receipt.proof if job.receipt else {},
            payment_amount=job.payment_amount or 0,
            payment_token=job.payment_token or "AITBC",
            nonce=await self._generate_nonce(),
            signature=""  # Not needed for estimation
        )
        
        return await self.bridge_manager.estimate_settlement_cost(
            message,
            bridge_name=bridge_name
        )
    
    async def list_supported_bridges(self) -> Dict[str, Any]:
        """List all supported bridges and their capabilities"""
        return self.bridge_manager.get_bridge_info()
    
    async def list_supported_chains(self) -> Dict[str, List[int]]:
        """List all supported chains by bridge"""
        return self.bridge_manager.get_supported_chains()
    
    async def enable(self) -> None:
        """Enable settlement hooks"""
        self._enabled = True
        logger.info("Settlement hooks enabled")
    
    async def disable(self) -> None:
        """Disable settlement hooks"""
        self._enabled = False
        logger.info("Settlement hooks disabled")
    
    async def _requires_cross_chain_settlement(self, job: Job) -> bool:
        """Check if job requires cross-chain settlement"""
        # Check if job has target chain different from current
        if job.target_chain and job.target_chain != await self._get_current_chain_id():
            return True
        
        # Check if job explicitly requests cross-chain settlement
        if job.requires_cross_chain_settlement:
            return True
        
        # Check if payment is on different chain
        if job.payment_chain and job.payment_chain != await self._get_current_chain_id():
            return True
        
        return False
    
    async def _initiate_settlement(self, job: Job) -> None:
        """Initiate cross-chain settlement for a job"""
        try:
            # Create settlement message
            message = await self._create_settlement_message(job)
            
            # Get optimal bridge if not specified
            bridge_name = job.preferred_bridge or await self.bridge_manager.get_optimal_bridge(
                message,
                priority=job.settlement_priority or 'cost'
            )
            
            # Send settlement
            result = await self.bridge_manager.settle_cross_chain(
                message,
                bridge_name=bridge_name
            )
            
            # Update job with settlement info
            job.cross_chain_settlement_id = result.message_id
            job.cross_chain_bridge = bridge_name
            job.cross_chain_settlement_status = result.status.value
            await job.save()
            
            logger.info(f"Initiated cross-chain settlement for job {job.id}: {result.message_id}")
            
        except Exception as e:
            logger.error(f"Failed to initiate settlement for job {job.id}: {e}")
            await self._handle_settlement_error(job, e)
    
    async def _create_settlement_message(self, job: Job, options: Optional[Dict[str, Any]] = None) -> SettlementMessage:
        """Create settlement message from job"""
        # Get current chain ID
        source_chain_id = await self._get_current_chain_id()
        
        # Get receipt data
        receipt_hash = ""
        proof_data = {}
        zk_proof = None
        
        if job.receipt:
            receipt_hash = job.receipt.hash
            proof_data = job.receipt.proof or {}
            
            # Check if ZK proof is included in receipt
            if options and options.get("use_zk_proof"):
                zk_proof = job.receipt.payload.get("zk_proof")
                if not zk_proof:
                    logger.warning(f"ZK proof requested but not found in receipt for job {job.id}")
        
        # Sign the settlement message
        signature = await self._sign_settlement_message(job)
        
        return SettlementMessage(
            source_chain_id=source_chain_id,
            target_chain_id=job.target_chain or source_chain_id,
            job_id=job.id,
            receipt_hash=receipt_hash,
            proof_data=proof_data,
            zk_proof=zk_proof,
            payment_amount=job.payment_amount or 0,
            payment_token=job.payment_token or "AITBC",
            nonce=await self._generate_nonce(),
            signature=signature,
            gas_limit=job.settlement_gas_limit,
            privacy_level=options.get("privacy_level") if options else None
        )
    
    async def _get_current_chain_id(self) -> int:
        """Get the current blockchain chain ID"""
        # This would get the chain ID from the blockchain node
        # For now, return a placeholder
        return 1  # Ethereum mainnet
    
    async def _generate_nonce(self) -> int:
        """Generate a unique nonce for settlement"""
        # This would generate a unique nonce
        # For now, use timestamp
        return int(datetime.utcnow().timestamp())
    
    async def _sign_settlement_message(self, job: Job) -> str:
        """Sign the settlement message"""
        # This would sign the message with the appropriate key
        # For now, return a placeholder
        return "0x..." * 20
    
    async def _handle_settlement_error(self, job: Job, error: Exception) -> None:
        """Handle settlement errors"""
        # Update job with error info
        job.cross_chain_settlement_error = str(error)
        job.cross_chain_settlement_status = BridgeStatus.FAILED.value
        await job.save()
        
        # Notify monitoring system
        await self._notify_settlement_failure(job, error)
    
    async def _refund_cross_chain_payment(self, job: Job) -> None:
        """Refund a cross-chain payment if possible"""
        if not job.cross_chain_payment_id:
            return
        
        try:
            result = await self.bridge_manager.refund_failed_settlement(
                job.cross_chain_payment_id
            )
            
            # Update job with refund info
            job.cross_chain_refund_id = result.message_id
            job.cross_chain_refund_status = result.status.value
            await job.save()
            
        except Exception as e:
            logger.error(f"Failed to refund cross-chain payment for {job.id}: {e}")
    
    async def _notify_settlement_failure(self, job: Job, error: Exception) -> None:
        """Notify monitoring system of settlement failure"""
        # This would send alerts to the monitoring system
        logger.error(f"Settlement failure for job {job.id}: {error}")


class BatchSettlementHook:
    """Hook for handling batch settlements"""
    
    def __init__(self, bridge_manager: BridgeManager):
        self.bridge_manager = bridge_manager
        self.batch_size = 10
        self.batch_timeout = 300  # 5 minutes
    
    async def add_to_batch(self, job: Job) -> None:
        """Add job to batch settlement queue"""
        # This would add the job to a batch queue
        pass
    
    async def process_batch(self) -> List[SettlementResult]:
        """Process a batch of settlements"""
        # This would process queued jobs in batches
        # For now, return empty list
        return []


class SettlementMonitor:
    """Monitor for cross-chain settlements"""
    
    def __init__(self, bridge_manager: BridgeManager):
        self.bridge_manager = bridge_manager
        self._monitoring = False
    
    async def start_monitoring(self) -> None:
        """Start monitoring settlements"""
        self._monitoring = True
        
        while self._monitoring:
            try:
                # Get pending settlements
                pending = await self.bridge_manager.storage.get_pending_settlements()
                
                # Check status of each
                for settlement in pending:
                    await self.bridge_manager.get_settlement_status(
                        settlement['message_id']
                    )
                
                # Wait before next check
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Error in settlement monitoring: {e}")
                await asyncio.sleep(60)
    
    async def stop_monitoring(self) -> None:
        """Stop monitoring settlements"""
        self._monitoring = False
