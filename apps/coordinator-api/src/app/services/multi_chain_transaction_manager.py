"""
Multi-Chain Transaction Manager
Advanced transaction management system for cross-chain operations with routing, monitoring, and optimization
"""

import asyncio
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from aitbc import get_logger

logger = get_logger(__name__)
from sqlalchemy import desc
from sqlmodel import Session, select

from ..agent_identity.wallet_adapter_enhanced import EnhancedWalletAdapter, SecurityLevel, WalletAdapterFactory
from ..contexts.cross_chain.services.cross_chain.bridge_enhanced import CrossChainBridgeService
from ..domain.multi_chain_transaction import MultiChainTransaction, RoutingStrategy, TransactionPriority, TransactionStatus
from ..domain.multi_chain_transaction import TransactionType as MultiChainTransactionType
from ..reputation.engine import CrossChainReputationEngine


class MultiChainTransactionManager:
    """Advanced multi-chain transaction management system"""

    def __init__(self, session: Session):
        self.session = session
        self.wallet_adapters: dict[int, EnhancedWalletAdapter] = {}
        self.bridge_service: CrossChainBridgeService | None = None
        self.reputation_engine: CrossChainReputationEngine = CrossChainReputationEngine(session)
        self.routing_config: dict[str, Any] = {
            "default_strategy": RoutingStrategy.BALANCED,
            "max_retries": 3,
            "retry_delay": 5,
            "confirmation_threshold": 6,
            "gas_price_multiplier": 1.1,
            "max_pending_per_chain": 100,
        }
        self.metrics: dict[str, Any] = {
            "total_transactions": 0,
            "successful_transactions": 0,
            "failed_transactions": 0,
            "average_processing_time": 0.0,
            "chain_performance": defaultdict(dict),
        }
        self._processing_tasks: list[asyncio.Task] = []
        self._monitoring_task: asyncio.Task | None = None

    async def initialize(self, chain_configs: dict[int, dict[str, Any]]) -> None:
        """Initialize transaction manager with chain configurations"""
        try:
            for chain_id, config in chain_configs.items():
                adapter = WalletAdapterFactory.create_adapter(
                    chain_id=chain_id,
                    rpc_url=config["rpc_url"],
                    security_level=SecurityLevel(config.get("security_level", "medium")),
                )
                self.wallet_adapters[chain_id] = adapter
                self.metrics["chain_performance"][chain_id] = {
                    "total_transactions": 0,
                    "success_rate": 0.0,
                    "average_gas_price": 0.0,
                    "average_confirmation_time": 0.0,
                    "last_updated": datetime.now(UTC),
                }
            self.bridge_service = CrossChainBridgeService(self.session)
            await self.bridge_service.initialize_bridge(chain_configs)
            logger.info("Initialized transaction manager for %s chains", len(chain_configs))
        except Exception as e:
            logger.error("Error initializing transaction manager: %s", e)
            raise

    async def submit_transaction(
        self,
        user_id: str,
        chain_id: int,
        transaction_type: MultiChainTransactionType,
        from_address: str,
        to_address: str,
        amount: Decimal | float | str,
        token_address: str | None = None,
        data: dict[str, Any] | None = None,
        priority: TransactionPriority = TransactionPriority.MEDIUM,
        routing_strategy: RoutingStrategy | None = None,
        gas_limit: int | None = None,
        gas_price: int | None = None,
        max_fee_per_gas: int | None = None,
        deadline_minutes: int = 30,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Submit a multi-chain transaction"""
        try:
            if chain_id not in self.wallet_adapters:
                raise ValueError(f"Unsupported chain ID: {chain_id}")
            adapter = self.wallet_adapters[chain_id]
            if not await adapter.validate_address(from_address) or not await adapter.validate_address(to_address):
                raise ValueError("Invalid addresses provided")
            reputation_summary = await self.reputation_engine.get_agent_reputation_summary(user_id)
            min_reputation = self._get_min_reputation_for_transaction(transaction_type, priority)
            if reputation_summary.get("trust_score", 0) < min_reputation:
                raise ValueError(f"Insufficient reputation for transaction type {transaction_type}")
            transaction_id = f"tx_{uuid4().hex[:8]}"
            transaction = MultiChainTransaction(
                id=transaction_id,
                user_id=user_id,
                chain_id=chain_id,
                transaction_type=transaction_type,
                from_address=from_address,
                to_address=to_address,
                amount=float(amount),
                token_address=token_address,
                data=data or {},
                priority=priority,
                routing_strategy=routing_strategy or self.routing_config["default_strategy"],
                gas_limit=gas_limit,
                gas_price=gas_price,
                max_fee_per_gas=max_fee_per_gas,
                status=TransactionStatus.QUEUED,
                deadline=datetime.now(UTC) + timedelta(minutes=deadline_minutes),
                meta_data=metadata or {},
                retry_count=0,
                submit_attempts=0,
            )
            self.session.add(transaction)
            self.session.commit()
            self.session.refresh(transaction)
            logger.info("Submitted transaction %s for user %s", transaction_id, user_id)
            return {
                "transaction_id": transaction_id,
                "status": TransactionStatus.QUEUED.value,
                "priority": priority.value,
                "estimated_processing_time": await self._estimate_processing_time(transaction),
                "deadline": transaction.deadline.isoformat(),
                "submitted_at": transaction.created_at.isoformat(),
            }
        except Exception as e:
            logger.error("Error submitting transaction: %s", e)
            raise

    async def get_transaction_status(self, transaction_id: str) -> dict[str, Any]:
        """Get detailed transaction status"""
        try:
            transaction = (
                self.session.execute(select(MultiChainTransaction).where(MultiChainTransaction.id == transaction_id))
                .scalars()
                .first()
            )
            if not transaction:
                raise ValueError(f"Transaction {transaction_id} not found")
            if transaction.transaction_hash and transaction.status in [
                TransactionStatus.SUBMITTED,
                TransactionStatus.CONFIRMED,
            ]:
                await self._update_transaction_status(transaction_id)
            progress = await self._calculate_transaction_progress(transaction)
            return {
                "transaction_id": transaction_id,
                "user_id": transaction.user_id,
                "chain_id": transaction.chain_id,
                "transaction_type": transaction.transaction_type,
                "from_address": transaction.from_address,
                "to_address": transaction.to_address,
                "amount": transaction.amount,
                "token_address": transaction.token_address,
                "priority": transaction.priority,
                "status": transaction.status,
                "progress": progress,
                "transaction_hash": transaction.transaction_hash,
                "block_number": transaction.block_number,
                "confirmations": transaction.confirmations,
                "gas_used": transaction.gas_used,
                "gas_price_paid": transaction.gas_price_paid,
                "retry_count": transaction.retry_count,
                "submit_attempts": transaction.submit_attempts,
                "error_message": transaction.error_message,
                "processing_time": transaction.processing_time,
                "created_at": transaction.created_at.isoformat(),
                "updated_at": transaction.updated_at.isoformat(),
                "deadline": transaction.deadline.isoformat(),
            }
        except Exception as e:
            logger.error("Error getting transaction status: %s", e)
            raise

    async def cancel_transaction(self, transaction_id: str, reason: str) -> dict[str, Any]:
        """Cancel a transaction"""
        try:
            transaction = (
                self.session.execute(select(MultiChainTransaction).where(MultiChainTransaction.id == transaction_id))
                .scalars()
                .first()
            )
            if not transaction:
                raise ValueError(f"Transaction {transaction_id} not found")
            if transaction.status not in [TransactionStatus.QUEUED, TransactionStatus.PENDING]:
                raise ValueError(f"Cannot cancel transaction in status: {transaction.status}")
            transaction.status = TransactionStatus.CANCELLED
            transaction.error_message = reason
            transaction.cancelled_at = datetime.now(UTC)
            transaction.cancellation_reason = reason
            transaction.updated_at = datetime.now(UTC)
            self.session.commit()
            self.session.refresh(transaction)
            logger.info("Cancelled transaction %s: %s", transaction_id, reason)
            return {
                "transaction_id": transaction_id,
                "status": TransactionStatus.CANCELLED.value,
                "reason": reason,
                "cancelled_at": transaction.cancelled_at.isoformat(),
            }
        except Exception as e:
            logger.error("Error cancelling transaction: %s", e)
            self.session.rollback()
            raise

    async def get_transaction_history(
        self,
        user_id: str | None = None,
        chain_id: int | None = None,
        transaction_type: MultiChainTransactionType | None = None,
        status: TransactionStatus | None = None,
        priority: TransactionPriority | None = None,
        limit: int = 100,
        offset: int = 0,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Get transaction history with filtering"""
        try:
            stmt = select(MultiChainTransaction)
            if user_id:
                stmt = stmt.where(MultiChainTransaction.user_id == user_id)
            if chain_id:
                stmt = stmt.where(MultiChainTransaction.chain_id == chain_id)
            if transaction_type:
                stmt = stmt.where(MultiChainTransaction.transaction_type == transaction_type)
            if status:
                stmt = stmt.where(MultiChainTransaction.status == status)
            if priority:
                stmt = stmt.where(MultiChainTransaction.priority == priority)
            if from_date:
                stmt = stmt.where(MultiChainTransaction.created_at >= from_date)
            if to_date:
                stmt = stmt.where(MultiChainTransaction.created_at <= to_date)
            stmt = stmt.order_by(desc(MultiChainTransaction.created_at))  # type: ignore[arg-type]
            stmt = stmt.offset(offset).limit(limit)
            transactions = self.session.execute(stmt).scalars().all()
            response_transactions = []
            for tx in transactions:
                response_transactions.append(
                    {
                        "transaction_id": tx.id,
                        "user_id": tx.user_id,
                        "chain_id": tx.chain_id,
                        "transaction_type": tx.transaction_type,
                        "from_address": tx.from_address,
                        "to_address": tx.to_address,
                        "amount": tx.amount,
                        "token_address": tx.token_address,
                        "priority": tx.priority,
                        "status": tx.status,
                        "transaction_hash": tx.transaction_hash,
                        "gas_used": tx.gas_used,
                        "gas_price_paid": tx.gas_price_paid,
                        "retry_count": tx.retry_count,
                        "error_message": tx.error_message,
                        "processing_time": tx.processing_time,
                        "created_at": tx.created_at.isoformat(),
                        "updated_at": tx.updated_at.isoformat(),
                    }
                )
            return response_transactions
        except Exception as e:
            logger.error("Error getting transaction history: %s", e)
            raise

    async def get_transaction_statistics(self, time_period_hours: int = 24, chain_id: int | None = None) -> dict[str, Any]:
        """Get transaction statistics"""
        try:
            cutoff_time = datetime.now(UTC) - timedelta(hours=time_period_hours)
            stmt = select(MultiChainTransaction).where(MultiChainTransaction.created_at >= cutoff_time)
            if chain_id:
                stmt = stmt.where(MultiChainTransaction.chain_id == chain_id)
            transactions = self.session.execute(stmt).scalars().all()
            total_transactions = len(transactions)
            successful_transactions = len([tx for tx in transactions if tx.status == TransactionStatus.COMPLETED])
            failed_transactions = len([tx for tx in transactions if tx.status == TransactionStatus.FAILED])
            success_rate = successful_transactions / max(total_transactions, 1)
            completed_transactions = [
                tx for tx in transactions if tx.status == TransactionStatus.COMPLETED and tx.processing_time
            ]
            avg_processing_time = 0.0
            if completed_transactions:
                avg_processing_time = sum(tx.processing_time for tx in completed_transactions) / len(completed_transactions)
            gas_stats = {}
            for tx in transactions:
                if tx.gas_used and tx.gas_price_paid:
                    tx_chain_id = tx.chain_id
                    if tx_chain_id not in gas_stats:
                        gas_stats[tx_chain_id] = {"total_gas_used": 0, "total_gas_cost": 0.0, "transaction_count": 0}
                    gas_stats[tx_chain_id]["total_gas_used"] += tx.gas_used
                    gas_stats[tx_chain_id]["total_gas_cost"] += tx.gas_used * tx.gas_price_paid / 10**18
                    gas_stats[tx_chain_id]["transaction_count"] += 1
            priority_distribution: dict[str, int] = defaultdict(int)
            for tx in transactions:
                priority_distribution[tx.priority] += 1
            return {
                "time_period_hours": time_period_hours,
                "chain_id": chain_id,
                "total_transactions": total_transactions,
                "successful_transactions": successful_transactions,
                "failed_transactions": failed_transactions,
                "success_rate": success_rate,
                "average_processing_time_seconds": avg_processing_time,
                "gas_statistics": gas_stats,
                "priority_distribution": dict(priority_distribution),
                "generated_at": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error("Error getting transaction statistics: %s", e)
            raise

    async def optimize_transaction_routing(
        self,
        transaction_type: MultiChainTransactionType,
        amount: float,
        from_chain: int,
        to_chain: int | None = None,
        urgency: TransactionPriority = TransactionPriority.MEDIUM,
    ) -> dict[str, Any]:
        """Optimize transaction routing for best performance"""
        try:
            routing_options = []
            for chain_id in self.wallet_adapters.keys():
                if to_chain and chain_id != to_chain:
                    continue
                chain_metrics = self.metrics["chain_performance"][chain_id]
                score = await self._calculate_routing_score(chain_id, transaction_type, amount, urgency, chain_metrics)
                routing_options.append(
                    {
                        "chain_id": chain_id,
                        "score": score,
                        "estimated_gas_price": chain_metrics.get("average_gas_price", 0),
                        "estimated_confirmation_time": chain_metrics.get("average_confirmation_time", 0),
                        "success_rate": chain_metrics.get("success_rate", 0),
                        "queue_length": 0,
                    }
                )
            routing_options.sort(key=lambda x: x["score"], reverse=True)
            best_option = routing_options[0] if routing_options else None
            return {
                "recommended_chain": best_option["chain_id"] if best_option else None,
                "routing_options": routing_options,
                "optimization_factors": {
                    "gas_price_weight": 0.3,
                    "confirmation_time_weight": 0.3,
                    "success_rate_weight": 0.2,
                    "queue_length_weight": 0.2,
                },
                "generated_at": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error("Error optimizing transaction routing: %s", e)
            raise

    async def _calculate_transaction_progress(self, transaction: MultiChainTransaction) -> float:
        """Calculate transaction progress percentage"""
        status_progress = {
            TransactionStatus.QUEUED: 0.0,
            TransactionStatus.PENDING: 10.0,
            TransactionStatus.PROCESSING: 30.0,
            TransactionStatus.SUBMITTED: 50.0,
            TransactionStatus.CONFIRMED: 80.0,
            TransactionStatus.COMPLETED: 100.0,
            TransactionStatus.FAILED: 100.0,
            TransactionStatus.CANCELLED: 100.0,
            TransactionStatus.EXPIRED: 100.0,
        }
        return status_progress.get(transaction.status, 0.0)

    async def _update_transaction_status(self, transaction_id: str) -> None:
        """Update transaction status from blockchain"""
        pass

    async def _estimate_processing_time(self, transaction: MultiChainTransaction) -> float:
        """Estimate transaction processing time in seconds"""
        priority_time = {
            TransactionPriority.CRITICAL: 30.0,
            TransactionPriority.URGENT: 60.0,
            TransactionPriority.HIGH: 120.0,
            TransactionPriority.MEDIUM: 300.0,
            TransactionPriority.LOW: 600.0,
        }
        return priority_time.get(transaction.priority, 300.0)

    def _get_min_reputation_for_transaction(
        self, transaction_type: MultiChainTransactionType, priority: TransactionPriority
    ) -> float:
        """Get minimum reputation score for transaction type and priority"""
        base_reputation = 50.0
        priority_multiplier = {
            TransactionPriority.CRITICAL: 1.5,
            TransactionPriority.URGENT: 1.3,
            TransactionPriority.HIGH: 1.1,
            TransactionPriority.MEDIUM: 1.0,
            TransactionPriority.LOW: 0.8,
        }
        return base_reputation * priority_multiplier.get(priority, 1.0)

    async def _calculate_routing_score(
        self,
        chain_id: int,
        transaction_type: MultiChainTransactionType,
        amount: float,
        urgency: TransactionPriority,
        chain_metrics: dict[str, Any],
    ) -> float:
        """Calculate routing score for a chain"""
        base_score = chain_metrics.get("success_rate", 0.5) * 100
        return base_score  # type: ignore[no-any-return]

    async def _check_stuck_transactions(self) -> None:
        """Check for stuck transactions"""
        try:
            current_time = datetime.now(UTC)
            stuck_threshold = timedelta(minutes=30)
            stmt = select(MultiChainTransaction).where(
                MultiChainTransaction.status.in_([TransactionStatus.PROCESSING, TransactionStatus.SUBMITTED])
            )  # type: ignore[attr-defined]
            transactions = self.session.execute(stmt).scalars().all()
            for tx in transactions:
                if current_time - tx.updated_at > stuck_threshold:
                    logger.warning("Stuck transaction detected: %s", tx.id)
        except Exception as e:
            logger.error("Error checking stuck transactions: %s", e)

    async def _update_transaction_status_v2(self, transaction_id: str) -> None:
        """Update transaction status from blockchain"""
        try:
            transaction = await self._find_transaction(transaction_id)  # type: ignore[attr-defined]
            if not transaction or not transaction["transaction_hash"]:
                return
            adapter = self.wallet_adapters[transaction["chain_id"]]
            tx_status = await adapter.get_transaction_status(transaction["transaction_hash"])
            if tx_status.get("status") == TransactionStatus.COMPLETED.value:
                transaction["status"] = TransactionStatus.COMPLETED.value
                transaction["confirmations"] = await self._get_transaction_confirmations_v2(transaction)
                transaction["updated_at"] = datetime.now(UTC)
        except Exception as e:
            logger.error("Error updating transaction status: %s", e)

    async def _get_transaction_confirmations_v2(self, transaction: dict[str, Any]) -> int:
        """Get transaction confirmations"""
        try:
            self.wallet_adapters[transaction["chain_id"]]
            return await self._get_transaction_confirmations(transaction["chain_id"], transaction["transaction_hash"])  # type: ignore[no-any-return, attr-defined]
        except Exception:
            return transaction.get("confirmations", 0)  # type: ignore[no-any-return]

    async def _estimate_processing_time_v2(self, transaction: dict[str, Any]) -> float:
        """Estimate transaction processing time"""
        try:
            chain_metrics = self.metrics["chain_performance"][transaction["chain_id"]]
            base_time = chain_metrics.get("average_confirmation_time", 120)
            priority_multiplier = {
                TransactionPriority.CRITICAL.value: 0.5,
                TransactionPriority.URGENT.value: 0.7,
                TransactionPriority.HIGH.value: 0.8,
                TransactionPriority.MEDIUM.value: 1.0,
                TransactionPriority.LOW.value: 1.5,
            }
            multiplier = priority_multiplier.get(transaction["priority"], 1.0)
            return base_time * multiplier  # type: ignore[no-any-return]
        except Exception:
            return 120.0

    async def _calculate_transaction_progress_v2(self, transaction: dict[str, Any]) -> float:
        """Calculate transaction progress percentage"""
        try:
            status = transaction["status"]
            if status == TransactionStatus.COMPLETED.value:
                return 100.0
            elif status in [
                TransactionStatus.FAILED.value,
                TransactionStatus.CANCELLED.value,
                TransactionStatus.EXPIRED.value,
            ]:
                return 0.0
            elif status == TransactionStatus.QUEUED.value:
                return 10.0
            elif status == TransactionStatus.PENDING.value:
                return 20.0
            elif status == TransactionStatus.PROCESSING.value:
                return 50.0
            elif status == TransactionStatus.SUBMITTED.value:
                progress = 60.0
                if transaction["confirmations"] > 0:
                    confirmation_progress = min(
                        transaction["confirmations"] / self.routing_config["confirmation_threshold"] * 30, 30.0
                    )
                    progress += confirmation_progress
                return progress
            elif status == TransactionStatus.CONFIRMED.value:
                return 90.0
            elif status == TransactionStatus.RETRYING.value:
                return 40.0
            return 0.0
        except Exception:
            return 0.0

    def _get_min_reputation_for_transaction_v2(
        self, transaction_type: MultiChainTransactionType, priority: TransactionPriority
    ) -> float:
        """Get minimum reputation required for transaction"""
        base_requirements = {
            MultiChainTransactionType.TRANSFER: 100,
            MultiChainTransactionType.SWAP: 200,
            MultiChainTransactionType.BRIDGE: 300,
            MultiChainTransactionType.DEPOSIT: 100,
            MultiChainTransactionType.WITHDRAWAL: 150,
            MultiChainTransactionType.CONTRACT_CALL: 250,
            MultiChainTransactionType.APPROVAL: 100,
        }
        priority_multipliers = {
            TransactionPriority.LOW: 1.0,
            TransactionPriority.MEDIUM: 1.0,
            TransactionPriority.HIGH: 1.2,
            TransactionPriority.URGENT: 1.5,
            TransactionPriority.CRITICAL: 2.0,
        }
        base_req = base_requirements.get(transaction_type, 100)
        multiplier = priority_multipliers.get(priority, 1.0)
        return int(base_req * multiplier)

    async def _calculate_routing_score_v2(
        self,
        chain_id: int,
        transaction_type: MultiChainTransactionType,
        amount: float,
        urgency: TransactionPriority,
        chain_metrics: dict[str, Any],
    ) -> float:
        """Calculate routing score for chain"""
        try:
            gas_price_factor = 1.0 / max(chain_metrics.get("average_gas_price", 1), 1)
            confirmation_time_factor = 1.0 / max(chain_metrics.get("average_confirmation_time", 1), 1)
            success_rate_factor = chain_metrics.get("success_rate", 0.5)
            queue_factor = 1.0
            urgency_multiplier = {
                TransactionPriority.LOW: 0.8,
                TransactionPriority.MEDIUM: 1.0,
                TransactionPriority.HIGH: 1.2,
                TransactionPriority.URGENT: 1.5,
                TransactionPriority.CRITICAL: 2.0,
            }
            urgency_factor = urgency_multiplier.get(urgency, 1.0)
            score = (
                gas_price_factor * 0.25
                + confirmation_time_factor * 0.25
                + success_rate_factor * 0.3
                + queue_factor * 0.1
                + urgency_factor * 0.1
            )
            return score  # type: ignore[no-any-return]
        except Exception as e:
            logger.error("Error calculating routing score: %s", e)
            return 0.5
