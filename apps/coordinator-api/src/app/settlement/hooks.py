"""
Settlement hooks for coordinator API integration
"""

import asyncio
import os
from datetime import UTC, datetime
from typing import Any

from aitbc import get_logger

from ..domain.job import Job
from .bridges.base import BridgeStatus, SettlementMessage, SettlementResult
from .manager import BridgeManager

logger = get_logger(__name__)


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
            if await self._requires_cross_chain_settlement(job):
                await self._initiate_settlement(job)
        except Exception as e:
            logger.error("Failed to handle job completion for %s: %s", job.id, e)
            await self._handle_settlement_error(job, e)

    async def on_job_failed(self, job: Job, error: Exception) -> None:
        """Called when a job fails"""
        if job.cross_chain_payment_id:  # type: ignore[attr-defined]
            try:
                await self._refund_cross_chain_payment(job)
            except Exception as e:
                logger.error("Failed to refund cross-chain payment for %s: %s", job.id, e)

    async def initiate_manual_settlement(
        self, job_id: str, target_chain_id: int, bridge_name: str | None = None, options: dict[str, Any] | None = None
    ) -> SettlementResult:
        """Manually initiate cross-chain settlement for a job"""
        job = await Job.get(job_id)  # type: ignore[attr-defined]
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if not job.completed:
            raise ValueError(f"Job {job_id} is not completed")
        if target_chain_id:
            job.target_chain = target_chain_id
        message = await self._create_settlement_message(job, options)
        result = await self.bridge_manager.settle_cross_chain(message, bridge_name=bridge_name)
        job.cross_chain_settlement_id = result.message_id
        job.cross_chain_bridge = bridge_name or self.bridge_manager.default_adapter
        await job.save()
        return result

    async def get_settlement_status(self, settlement_id: str) -> SettlementResult:
        """Get status of a cross-chain settlement"""
        return await self.bridge_manager.get_settlement_status(settlement_id)

    async def estimate_settlement_cost(
        self, job_id: str, target_chain_id: int, bridge_name: str | None = None
    ) -> dict[str, Any]:
        """Estimate cost for cross-chain settlement"""
        job = await Job.get(job_id)  # type: ignore[attr-defined]
        if not job:
            raise ValueError(f"Job {job_id} not found")
        message = SettlementMessage(
            source_chain_id=await self._get_current_chain_id(),
            target_chain_id=target_chain_id,
            job_id=job.id,
            receipt_hash=job.receipt.hash if job.receipt else "",
            proof_data=job.receipt.proof if job.receipt else {},
            payment_amount=job.payment_amount or 0,
            payment_token=job.payment_token or "AITBC",
            nonce=await self._generate_nonce(),
            signature="",
        )
        return await self.bridge_manager.estimate_settlement_cost(message, bridge_name=bridge_name)

    async def list_supported_bridges(self) -> dict[str, Any]:
        """List all supported bridges and their capabilities"""
        return self.bridge_manager.get_bridge_info()

    async def list_supported_chains(self) -> dict[str, list[int]]:
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
        if job.target_chain and job.target_chain != await self._get_current_chain_id():  # type: ignore[attr-defined]
            return True
        if job.requires_cross_chain_settlement:  # type: ignore[attr-defined]
            return True
        if job.payment_chain and job.payment_chain != await self._get_current_chain_id():  # type: ignore[attr-defined]
            return True
        return False

    async def _initiate_settlement(self, job: Job) -> None:
        """Initiate cross-chain settlement for a job"""
        try:
            message = await self._create_settlement_message(job)
            bridge_name = job.preferred_bridge or await self.bridge_manager.get_optimal_bridge(
                message, priority=job.settlement_priority or "cost"
            )  # type: ignore[attr-defined]
            result = await self.bridge_manager.settle_cross_chain(message, bridge_name=bridge_name)
            job.cross_chain_settlement_id = result.message_id
            job.cross_chain_bridge = bridge_name
            job.cross_chain_settlement_status = result.status.value
            await job.save()  # type: ignore[attr-defined]
            logger.info("Initiated cross-chain settlement for job %s: %s", job.id, result.message_id)
        except Exception as e:
            logger.error("Failed to initiate settlement for job %s: %s", job.id, e)
            await self._handle_settlement_error(job, e)

    async def _create_settlement_message(self, job: Job, options: dict[str, Any] | None = None) -> SettlementMessage:
        """Create settlement message from job"""
        source_chain_id = await self._get_current_chain_id()
        receipt_hash = ""
        proof_data: dict[str, Any] = {}
        zk_proof = None
        if job.receipt:
            receipt_hash = job.receipt.hash  # type: ignore[attr-defined]
            proof_data = job.receipt.proof or {}  # type: ignore[attr-defined]
            if options and options.get("use_zk_proof"):
                zk_proof = job.receipt.payload.get("zk_proof")  # type: ignore[attr-defined]
                if not zk_proof:
                    logger.warning("ZK proof requested but not found in receipt for job %s", job.id)
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
            privacy_level=options.get("privacy_level") if options else None,
        )  # type: ignore[attr-defined, call-arg]

    async def _get_current_chain_id(self) -> int:
        """Get the current blockchain chain ID"""
        try:
            import httpx

            response = httpx.get("http://localhost:8202/rpc/chain")
            if response.status_code == 200:
                chain_data = response.json()
                return chain_data.get("chain_id", 1)  # type: ignore[no-any-return]
        except Exception as e:
            logger.warning("Failed to get chain ID: %s", e)
        return 1

    async def _generate_nonce(self) -> int:
        """Generate a unique nonce for settlement"""
        import random

        return int(datetime.now(UTC).timestamp() * 1000) + random.randint(0, 9999)

    async def _sign_settlement_message(self, job: Job) -> str:
        """Sign the settlement message"""
        try:
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives import hashes

            private_key_hex = os.environ.get("SETTLEMENT_PRIVATE_KEY")
            if not private_key_hex:
                logger.warning("SETTLEMENT_PRIVATE_KEY not set, using placeholder signature")
                return "0x" + "0" * 40
            message = f"{job.job_id}:{job.cross_chain_amount}:{job.cross_chain_target_address}"  # type: ignore[attr-defined]
            message_hash = hashes.Hash(hashes.SHA256(), default_backend())
            message_hash.update(message.encode())
            digest = message_hash.finalize()
            signature = "0x" + digest.hex()[:40]
            return signature
        except Exception as e:
            logger.warning("Failed to sign settlement message: %s", e)
            return "0x" + "0" * 40

    async def _handle_settlement_error(self, job: Job, error: Exception) -> None:
        """Handle settlement errors"""
        job.cross_chain_settlement_error = str(error)
        job.cross_chain_settlement_status = BridgeStatus.FAILED.value
        await job.save()  # type: ignore[attr-defined]
        await self._notify_settlement_failure(job, error)

    async def _refund_cross_chain_payment(self, job: Job) -> None:
        """Refund a cross-chain payment if possible"""
        if not job.cross_chain_payment_id:  # type: ignore[attr-defined]
            return
        try:
            result = await self.bridge_manager.refund_failed_settlement(job.cross_chain_payment_id)  # type: ignore[attr-defined]
            job.cross_chain_refund_id = result.message_id
            job.cross_chain_refund_status = result.status.value
            await job.save()  # type: ignore[attr-defined]
        except Exception as e:
            logger.error("Failed to refund cross-chain payment for %s: %s", job.id, e)

    async def _notify_settlement_failure(self, job: Job, error: Exception) -> None:
        """Notify monitoring system of settlement failure"""
        logger.error("Settlement failure for job %s: %s", job.id, error)


class BatchSettlementHook:
    """Hook for handling batch settlements"""

    def __init__(self, bridge_manager: BridgeManager):
        self.bridge_manager = bridge_manager
        self.batch_size = 10
        self.batch_timeout = 300

    async def add_to_batch(self, job: Job) -> None:
        """Add job to batch settlement queue"""
        pass

    async def process_batch(self) -> list[SettlementResult]:
        """Process a batch of settlements"""
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
                pending = await self.bridge_manager.storage.get_pending_settlements()
                for settlement in pending:
                    await self.bridge_manager.get_settlement_status(settlement["message_id"])
                await asyncio.sleep(30)
            except Exception as e:
                logger.error("Error in settlement monitoring: %s", e)
                await asyncio.sleep(60)

    async def stop_monitoring(self) -> None:
        """Stop monitoring settlements"""
        self._monitoring = False
