"""
Multi-Chain Transaction Manager
Advanced transaction management system for cross-chain operations with routing, monitoring, and optimization
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

from sqlmodel import Session

from ..agent_identity.wallet_adapter_enhanced import (
    EnhancedWalletAdapter,
    SecurityLevel,
    TransactionStatus,
    WalletAdapterFactory,
)
from ..reputation.engine import CrossChainReputationEngine
from ..services.cross_chain_bridge_enhanced import CrossChainBridgeService


class TransactionPriority(StrEnum):
    """Transaction priority levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"
    CRITICAL = "critical"


class TransactionType(StrEnum):
    """Transaction types"""

    TRANSFER = "transfer"
    SWAP = "swap"
    BRIDGE = "bridge"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    CONTRACT_CALL = "contract_call"
    APPROVAL = "approval"


class TransactionStatus(StrEnum):
    """Enhanced transaction status"""

    QUEUED = "queued"
    PENDING = "pending"
    PROCESSING = "processing"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    RETRYING = "retrying"


class RoutingStrategy(StrEnum):
    """Transaction routing strategies"""

    FASTEST = "fastest"
    CHEAPEST = "cheapest"
    BALANCED = "balanced"
    RELIABLE = "reliable"
    PRIORITY = "priority"


class MultiChainTransactionManager:
    """Advanced multi-chain transaction management system"""

    def __init__(self, session: Session):
        self.session = session
        self.wallet_adapters: dict[int, EnhancedWalletAdapter] = {}
        self.bridge_service: CrossChainBridgeService | None = None
        self.reputation_engine: CrossChainReputationEngine = CrossChainReputationEngine(session)

        # Transaction queues
        self.transaction_queues: dict[int, list[dict[str, Any]]] = defaultdict(list)
        self.priority_queues: dict[TransactionPriority, list[dict[str, Any]]] = defaultdict(list)

        # Routing configuration
        self.routing_config: dict[str, Any] = {
            "default_strategy": RoutingStrategy.BALANCED,
            "max_retries": 3,
            "retry_delay": 5,  # seconds
            "confirmation_threshold": 6,
            "gas_price_multiplier": 1.1,
            "max_pending_per_chain": 100,
        }

        # Performance metrics
        self.metrics: dict[str, Any] = {
            "total_transactions": 0,
            "successful_transactions": 0,
            "failed_transactions": 0,
            "average_processing_time": 0.0,
            "chain_performance": defaultdict(dict),
        }

        # Background tasks
        self._processing_tasks: list[asyncio.Task] = []
        self._monitoring_task: asyncio.Task | None = None

    async def initialize(self, chain_configs: dict[int, dict[str, Any]]) -> None:
        """Initialize transaction manager with chain configurations"""

        try:
            # Initialize wallet adapters
            for chain_id, config in chain_configs.items():
                adapter = WalletAdapterFactory.create_adapter(
                    chain_id=chain_id,
                    rpc_url=config["rpc_url"],
                    security_level=SecurityLevel(config.get("security_level", "medium")),
                )
                self.wallet_adapters[chain_id] = adapter

                # Initialize chain metrics
                self.metrics["chain_performance"][chain_id] = {
                    "total_transactions": 0,
                    "success_rate": 0.0,
                    "average_gas_price": 0.0,
                    "average_confirmation_time": 0.0,
                    "last_updated": datetime.utcnow(),
                }

            # Initialize bridge service
            self.bridge_service = CrossChainBridgeService(session)
            await self.bridge_service.initialize_bridge(chain_configs)

            # Start background processing
            await self._start_background_processing()

            logger.info(f"Initialized transaction manager for {len(chain_configs)} chains")

        except Exception as e:
            logger.error(f"Error initializing transaction manager: {e}")
            raise

    async def submit_transaction(
        self,
        user_id: str,
        chain_id: int,
        transaction_type: TransactionType,
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
            # Validate inputs
            if chain_id not in self.wallet_adapters:
                raise ValueError(f"Unsupported chain ID: {chain_id}")

            adapter = self.wallet_adapters[chain_id]
            if not await adapter.validate_address(from_address) or not await adapter.validate_address(to_address):
                raise ValueError("Invalid addresses provided")

            # Check user reputation
            reputation_summary = await self.reputation_engine.get_agent_reputation_summary(user_id)
            min_reputation = self._get_min_reputation_for_transaction(transaction_type, priority)

            if reputation_summary.get("trust_score", 0) < min_reputation:
                raise ValueError(f"Insufficient reputation for transaction type {transaction_type}")

            # Create transaction record
            transaction_id = f"tx_{uuid4().hex[:8]}"

            transaction = {
                "id": transaction_id,
                "user_id": user_id,
                "chain_id": chain_id,
                "transaction_type": transaction_type.value,
                "from_address": from_address,
                "to_address": to_address,
                "amount": float(amount),
                "token_address": token_address,
                "data": data or {},
                "priority": priority.value,
                "routing_strategy": (routing_strategy or self.routing_config["default_strategy"]).value,
                "gas_limit": gas_limit,
                "gas_price": gas_price,
                "max_fee_per_gas": max_fee_per_gas,
                "status": TransactionStatus.QUEUED.value,
                "created_at": datetime.utcnow(),
                "deadline": datetime.utcnow() + timedelta(minutes=deadline_minutes),
                "metadata": metadata or {},
                "retry_count": 0,
                "submit_attempts": 0,
                "gas_used": None,
                "gas_price_paid": None,
                "transaction_hash": None,
                "block_number": None,
                "confirmations": 0,
                "error_message": None,
                "processing_time": None,
            }

            # Add to appropriate queue
            await self._queue_transaction(transaction)

            logger.info(f"Submitted transaction {transaction_id} for user {user_id}")

            return {
                "transaction_id": transaction_id,
                "status": TransactionStatus.QUEUED.value,
                "priority": priority.value,
                "estimated_processing_time": await self._estimate_processing_time(transaction),
                "deadline": transaction["deadline"].isoformat(),
                "submitted_at": transaction["created_at"].isoformat(),
            }

        except Exception as e:
            logger.error(f"Error submitting transaction: {e}")
            raise

    async def get_transaction_status(self, transaction_id: str) -> dict[str, Any]:
        """Get detailed transaction status"""

        try:
            # Find transaction in queues
            transaction = await self._find_transaction(transaction_id)

            if not transaction:
                raise ValueError(f"Transaction {transaction_id} not found")

            # Update status if it's on-chain
            if transaction["transaction_hash"] and transaction["status"] in [
                TransactionStatus.SUBMITTED.value,
                TransactionStatus.CONFIRMED.value,
            ]:
                await self._update_transaction_status(transaction_id)

            # Calculate progress
            progress = await self._calculate_transaction_progress(transaction)

            return {
                "transaction_id": transaction_id,
                "user_id": transaction["user_id"],
                "chain_id": transaction["chain_id"],
                "transaction_type": transaction["transaction_type"],
                "from_address": transaction["from_address"],
                "to_address": transaction["to_address"],
                "amount": transaction["amount"],
                "token_address": transaction["token_address"],
                "priority": transaction["priority"],
                "status": transaction["status"],
                "progress": progress,
                "transaction_hash": transaction["transaction_hash"],
                "block_number": transaction["block_number"],
                "confirmations": transaction["confirmations"],
                "gas_used": transaction["gas_used"],
                "gas_price_paid": transaction["gas_price_paid"],
                "retry_count": transaction["retry_count"],
                "submit_attempts": transaction["submit_attempts"],
                "error_message": transaction["error_message"],
                "processing_time": transaction["processing_time"],
                "created_at": transaction["created_at"].isoformat(),
                "updated_at": transaction.get("updated_at", transaction["created_at"]).isoformat(),
                "deadline": transaction["deadline"].isoformat(),
            }

        except Exception as e:
            logger.error(f"Error getting transaction status: {e}")
            raise

    async def cancel_transaction(self, transaction_id: str, reason: str) -> dict[str, Any]:
        """Cancel a transaction"""

        try:
            transaction = await self._find_transaction(transaction_id)

            if not transaction:
                raise ValueError(f"Transaction {transaction_id} not found")

            if transaction["status"] not in [TransactionStatus.QUEUED.value, TransactionStatus.PENDING.value]:
                raise ValueError(f"Cannot cancel transaction in status: {transaction['status']}")

            # Update transaction status
            transaction["status"] = TransactionStatus.CANCELLED.value
            transaction["error_message"] = reason
            transaction["updated_at"] = datetime.utcnow()

            # Remove from queues
            await self._remove_from_queues(transaction_id)

            logger.info(f"Cancelled transaction {transaction_id}: {reason}")

            return {
                "transaction_id": transaction_id,
                "status": TransactionStatus.CANCELLED.value,
                "reason": reason,
                "cancelled_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error cancelling transaction: {e}")
            raise

    async def get_transaction_history(
        self,
        user_id: str | None = None,
        chain_id: int | None = None,
        transaction_type: TransactionType | None = None,
        status: TransactionStatus | None = None,
        priority: TransactionPriority | None = None,
        limit: int = 100,
        offset: int = 0,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Get transaction history with filtering"""

        try:
            # Get all transactions from queues
            all_transactions = []

            for chain_transactions in self.transaction_queues.values():
                all_transactions.extend(chain_transactions)

            for priority_transactions in self.priority_queues.values():
                all_transactions.extend(priority_transactions)

            # Remove duplicates
            seen_ids = set()
            unique_transactions = []
            for tx in all_transactions:
                if tx["id"] not in seen_ids:
                    seen_ids.add(tx["id"])
                    unique_transactions.append(tx)

            # Apply filters
            filtered_transactions = unique_transactions

            if user_id:
                filtered_transactions = [tx for tx in filtered_transactions if tx["user_id"] == user_id]

            if chain_id:
                filtered_transactions = [tx for tx in filtered_transactions if tx["chain_id"] == chain_id]

            if transaction_type:
                filtered_transactions = [
                    tx for tx in filtered_transactions if tx["transaction_type"] == transaction_type.value
                ]

            if status:
                filtered_transactions = [tx for tx in filtered_transactions if tx["status"] == status.value]

            if priority:
                filtered_transactions = [tx for tx in filtered_transactions if tx["priority"] == priority.value]

            if from_date:
                filtered_transactions = [tx for tx in filtered_transactions if tx["created_at"] >= from_date]

            if to_date:
                filtered_transactions = [tx for tx in filtered_transactions if tx["created_at"] <= to_date]

            # Sort by creation time (descending)
            filtered_transactions.sort(key=lambda x: x["created_at"], reverse=True)

            # Apply pagination
            paginated_transactions = filtered_transactions[offset : offset + limit]

            # Format response
            response_transactions = []
            for tx in paginated_transactions:
                response_transactions.append(
                    {
                        "transaction_id": tx["id"],
                        "user_id": tx["user_id"],
                        "chain_id": tx["chain_id"],
                        "transaction_type": tx["transaction_type"],
                        "from_address": tx["from_address"],
                        "to_address": tx["to_address"],
                        "amount": tx["amount"],
                        "token_address": tx["token_address"],
                        "priority": tx["priority"],
                        "status": tx["status"],
                        "transaction_hash": tx["transaction_hash"],
                        "gas_used": tx["gas_used"],
                        "gas_price_paid": tx["gas_price_paid"],
                        "retry_count": tx["retry_count"],
                        "error_message": tx["error_message"],
                        "processing_time": tx["processing_time"],
                        "created_at": tx["created_at"].isoformat(),
                        "updated_at": tx.get("updated_at", tx["created_at"]).isoformat(),
                    }
                )

            return response_transactions

        except Exception as e:
            logger.error(f"Error getting transaction history: {e}")
            raise

    async def get_transaction_statistics(self, time_period_hours: int = 24, chain_id: int | None = None) -> dict[str, Any]:
        """Get transaction statistics"""

        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=time_period_hours)

            # Get all transactions
            all_transactions = []
            for chain_transactions in self.transaction_queues.values():
                all_transactions.extend(chain_transactions)

            # Filter by time period and chain
            filtered_transactions = [
                tx
                for tx in all_transactions
                if tx["created_at"] >= cutoff_time and (chain_id is None or tx["chain_id"] == chain_id)
            ]

            # Calculate statistics
            total_transactions = len(filtered_transactions)
            successful_transactions = len(
                [tx for tx in filtered_transactions if tx["status"] == TransactionStatus.COMPLETED.value]
            )
            failed_transactions = len([tx for tx in filtered_transactions if tx["status"] == TransactionStatus.FAILED.value])

            success_rate = successful_transactions / max(total_transactions, 1)

            # Calculate average processing time
            completed_transactions = [
                tx
                for tx in filtered_transactions
                if tx["status"] == TransactionStatus.COMPLETED.value and tx["processing_time"]
            ]

            avg_processing_time = 0.0
            if completed_transactions:
                avg_processing_time = sum(tx["processing_time"] for tx in completed_transactions) / len(completed_transactions)

            # Calculate gas statistics
            gas_stats = {}
            for tx in filtered_transactions:
                if tx["gas_used"] and tx["gas_price_paid"]:
                    chain_id = tx["chain_id"]
                    if chain_id not in gas_stats:
                        gas_stats[chain_id] = {"total_gas_used": 0, "total_gas_cost": 0.0, "transaction_count": 0}

                    gas_stats[chain_id]["total_gas_used"] += tx["gas_used"]
                    gas_stats[chain_id]["total_gas_cost"] += (tx["gas_used"] * tx["gas_price_paid"]) / 10**18
                    gas_stats[chain_id]["transaction_count"] += 1

            # Priority distribution
            priority_distribution = defaultdict(int)
            for tx in filtered_transactions:
                priority_distribution[tx["priority"]] += 1

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
                "generated_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error getting transaction statistics: {e}")
            raise

    async def optimize_transaction_routing(
        self,
        transaction_type: TransactionType,
        amount: float,
        from_chain: int,
        to_chain: int | None = None,
        urgency: TransactionPriority = TransactionPriority.MEDIUM,
    ) -> dict[str, Any]:
        """Optimize transaction routing for best performance"""

        try:
            routing_options = []

            # Analyze each chain's performance
            for chain_id in self.wallet_adapters.keys():
                if to_chain and chain_id != to_chain:
                    continue

                chain_metrics = self.metrics["chain_performance"][chain_id]

                # Calculate routing score
                score = await self._calculate_routing_score(chain_id, transaction_type, amount, urgency, chain_metrics)

                routing_options.append(
                    {
                        "chain_id": chain_id,
                        "score": score,
                        "estimated_gas_price": chain_metrics.get("average_gas_price", 0),
                        "estimated_confirmation_time": chain_metrics.get("average_confirmation_time", 0),
                        "success_rate": chain_metrics.get("success_rate", 0),
                        "queue_length": len(self.transaction_queues[chain_id]),
                    }
                )

            # Sort by score (descending)
            routing_options.sort(key=lambda x: x["score"], reverse=True)

            # Get best option
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
                "generated_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error optimizing transaction routing: {e}")
            raise

    # Private methods
    async def _queue_transaction(self, transaction: dict[str, Any]) -> None:
        """Add transaction to appropriate queue"""

        try:
            # Add to chain-specific queue
            self.transaction_queues[transaction["chain_id"]].append(transaction)

            # Add to priority queue
            priority = TransactionPriority(transaction["priority"])
            self.priority_queues[priority].append(transaction)

            # Sort priority queue by priority and creation time
            self.priority_queues[priority].sort(key=lambda x: (x["priority"], x["created_at"]), reverse=True)

            # Update metrics
            self.metrics["total_transactions"] += 1

        except Exception as e:
            logger.error(f"Error queuing transaction: {e}")
            raise

    async def _find_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        """Find transaction in queues"""

        for chain_transactions in self.transaction_queues.values():
            for tx in chain_transactions:
                if tx["id"] == transaction_id:
                    return tx

        for priority_transactions in self.priority_queues.values():
            for tx in priority_transactions:
                if tx["id"] == transaction_id:
                    return tx

        return None

    async def _remove_from_queues(self, transaction_id: str) -> None:
        """Remove transaction from all queues"""

        for chain_id in self.transaction_queues:
            self.transaction_queues[chain_id] = [tx for tx in self.transaction_queues[chain_id] if tx["id"] != transaction_id]

        for priority in self.priority_queues:
            self.priority_queues[priority] = [tx for tx in self.priority_queues[priority] if tx["id"] != transaction_id]

    async def _start_background_processing(self) -> None:
        """Start background processing tasks"""

        try:
            # Start transaction processing task
            for chain_id in self.wallet_adapters.keys():
                task = asyncio.create_task(self._process_chain_transactions(chain_id))
                self._processing_tasks.append(task)

            # Start monitoring task
            self._monitoring_task = asyncio.create_task(self._monitor_transactions())

            logger.info("Started background transaction processing")

        except Exception as e:
            logger.error(f"Error starting background processing: {e}")

    async def _process_chain_transactions(self, chain_id: int) -> None:
        """Process transactions for a specific chain"""

        while True:
            try:
                # Get next transaction from queue
                transaction = await self._get_next_transaction(chain_id)

                if not transaction:
                    await asyncio.sleep(1)  # Wait for new transactions
                    continue

                # Process transaction
                await self._process_single_transaction(transaction)

                # Small delay between transactions
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Error processing transactions for chain {chain_id}: {e}")
                await asyncio.sleep(5)

    async def _get_next_transaction(self, chain_id: int) -> dict[str, Any] | None:
        """Get next transaction to process for chain"""

        try:
            # Check queue length limit
            if len(self.transaction_queues[chain_id]) >= self.routing_config["max_pending_per_chain"]:
                return None

            # Get highest priority transaction
            for priority in [
                TransactionPriority.CRITICAL,
                TransactionPriority.URGENT,
                TransactionPriority.HIGH,
                TransactionPriority.MEDIUM,
                TransactionPriority.LOW,
            ]:
                if priority.value in self.priority_queues:
                    for tx in self.priority_queues[priority.value]:
                        if tx["chain_id"] == chain_id and tx["status"] == TransactionStatus.QUEUED.value:
                            return tx

            return None

        except Exception as e:
            logger.error(f"Error getting next transaction: {e}")
            return None

    async def _process_single_transaction(self, transaction: dict[str, Any]) -> None:
        """Process a single transaction"""

        try:
            start_time = datetime.utcnow()

            # Update status to processing
            transaction["status"] = TransactionStatus.PROCESSING.value
            transaction["updated_at"] = start_time

            # Get wallet adapter
            adapter = self.wallet_adapters[transaction["chain_id"]]

            # Execute transaction
            tx_result = await adapter.execute_transaction(
                from_address=transaction["from_address"],
                to_address=transaction["to_address"],
                amount=transaction["amount"],
                token_address=transaction["token_address"],
                data=transaction["data"],
                gas_limit=transaction["gas_limit"],
                gas_price=transaction["gas_price"],
            )

            # Update transaction with result
            transaction["transaction_hash"] = tx_result["transaction_hash"]
            transaction["status"] = TransactionStatus.SUBMITTED.value
            transaction["submit_attempts"] += 1
            transaction["updated_at"] = datetime.utcnow()

            # Wait for confirmations
            await self._wait_for_confirmations(transaction)

            # Update final status
            transaction["status"] = TransactionStatus.COMPLETED.value
            transaction["processing_time"] = (datetime.utcnow() - start_time).total_seconds()
            transaction["updated_at"] = datetime.utcnow()

            # Update metrics
            self.metrics["successful_transactions"] += 1
            chain_metrics = self.metrics["chain_performance"][transaction["chain_id"]]
            chain_metrics["total_transactions"] += 1
            chain_metrics["success_rate"] = chain_metrics["success_rate"] * 0.9 + 0.1  # Moving average

            logger.info(f"Completed transaction {transaction['id']}")

        except Exception as e:
            logger.error(f"Error processing transaction {transaction['id']}: {e}")

            # Handle failure
            await self._handle_transaction_failure(transaction, str(e))

    async def _wait_for_confirmations(self, transaction: dict[str, Any]) -> None:
        """Wait for transaction confirmations"""

        try:
            adapter = self.wallet_adapters[transaction["chain_id"]]
            required_confirmations = self.routing_config["confirmation_threshold"]

            while transaction["confirmations"] < required_confirmations:
                # Get transaction status
                tx_status = await adapter.get_transaction_status(transaction["transaction_hash"])

                if tx_status.get("block_number"):
                    current_block = 12345  # Mock current block
                    tx_block = int(tx_status["block_number"], 16)
                    transaction["confirmations"] = current_block - tx_block
                    transaction["block_number"] = tx_status["block_number"]

                await asyncio.sleep(10)  # Check every 10 seconds

        except Exception as e:
            logger.error(f"Error waiting for confirmations: {e}")
            raise

    async def _handle_transaction_failure(self, transaction: dict[str, Any], error_message: str) -> None:
        """Handle transaction failure"""

        try:
            transaction["retry_count"] += 1
            transaction["error_message"] = error_message
            transaction["updated_at"] = datetime.utcnow()

            # Check if should retry
            if transaction["retry_count"] < self.routing_config["max_retries"]:
                transaction["status"] = TransactionStatus.RETRYING.value

                # Wait before retry
                await asyncio.sleep(self.routing_config["retry_delay"])

                # Reset status to queued for retry
                transaction["status"] = TransactionStatus.QUEUED.value
            else:
                transaction["status"] = TransactionStatus.FAILED.value
                self.metrics["failed_transactions"] += 1

            # Update chain metrics
            chain_metrics = self.metrics["chain_performance"][transaction["chain_id"]]
            chain_metrics["success_rate"] = chain_metrics["success_rate"] * 0.9  # Moving average

        except Exception as e:
            logger.error(f"Error handling transaction failure: {e}")

    async def _monitor_transactions(self) -> None:
        """Monitor transaction processing and performance"""

        while True:
            try:
                # Clean up old transactions
                await self._cleanup_old_transactions()

                # Update performance metrics
                await self._update_performance_metrics()

                # Check for stuck transactions
                await self._check_stuck_transactions()

                # Sleep before next monitoring cycle
                await asyncio.sleep(60)  # Monitor every minute

            except Exception as e:
                logger.error(f"Error in transaction monitoring: {e}")
                await asyncio.sleep(60)

    async def _cleanup_old_transactions(self) -> None:
        """Clean up old completed/failed transactions"""

        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=24)

            for chain_id in self.transaction_queues:
                original_length = len(self.transaction_queues[chain_id])

                self.transaction_queues[chain_id] = [
                    tx
                    for tx in self.transaction_queues[chain_id]
                    if tx["created_at"] > cutoff_time
                    or tx["status"]
                    in [TransactionStatus.QUEUED.value, TransactionStatus.PENDING.value, TransactionStatus.PROCESSING.value]
                ]

                cleaned_up = original_length - len(self.transaction_queues[chain_id])
                if cleaned_up > 0:
                    logger.info(f"Cleaned up {cleaned_up} old transactions for chain {chain_id}")

        except Exception as e:
            logger.error(f"Error cleaning up old transactions: {e}")

    async def _update_performance_metrics(self) -> None:
        """Update performance metrics"""

        try:
            for chain_id, adapter in self.wallet_adapters.items():
                # Get current gas price
                gas_price = await adapter._get_gas_price()

                # Update chain metrics
                chain_metrics = self.metrics["chain_performance"][chain_id]
                chain_metrics["average_gas_price"] = (
                    chain_metrics["average_gas_price"] * 0.9 + gas_price * 0.1  # Moving average
                )
                chain_metrics["last_updated"] = datetime.utcnow()

        except Exception as e:
            logger.error(f"Error updating performance metrics: {e}")

    async def _check_stuck_transactions(self) -> None:
        """Check for stuck transactions"""

        try:
            current_time = datetime.utcnow()
            stuck_threshold = timedelta(minutes=30)

            for chain_id in self.transaction_queues:
                for tx in self.transaction_queues[chain_id]:
                    if (
                        tx["status"] == TransactionStatus.PROCESSING.value
                        and current_time - tx["updated_at"] > stuck_threshold
                    ):

                        logger.warning(f"Found stuck transaction {tx['id']} on chain {chain_id}")

                        # Mark as failed and retry
                        await self._handle_transaction_failure(tx, "Transaction stuck in processing")

        except Exception as e:
            logger.error(f"Error checking stuck transactions: {e}")

    async def _update_transaction_status(self, transaction_id: str) -> None:
        """Update transaction status from blockchain"""

        try:
            transaction = await self._find_transaction(transaction_id)
            if not transaction or not transaction["transaction_hash"]:
                return

            adapter = self.wallet_adapters[transaction["chain_id"]]
            tx_status = await adapter.get_transaction_status(transaction["transaction_hash"])

            if tx_status.get("status") == TransactionStatus.COMPLETED.value:
                transaction["status"] = TransactionStatus.COMPLETED.value
                transaction["confirmations"] = await self._get_transaction_confirmations(transaction)
                transaction["updated_at"] = datetime.utcnow()

        except Exception as e:
            logger.error(f"Error updating transaction status: {e}")

    async def _get_transaction_confirmations(self, transaction: dict[str, Any]) -> int:
        """Get transaction confirmations"""

        try:
            self.wallet_adapters[transaction["chain_id"]]
            return await self._get_transaction_confirmations(transaction["chain_id"], transaction["transaction_hash"])
        except:
            return transaction.get("confirmations", 0)

    async def _estimate_processing_time(self, transaction: dict[str, Any]) -> float:
        """Estimate transaction processing time"""

        try:
            chain_metrics = self.metrics["chain_performance"][transaction["chain_id"]]

            base_time = chain_metrics.get("average_confirmation_time", 120)  # 2 minutes default

            # Adjust based on priority
            priority_multiplier = {
                TransactionPriority.CRITICAL.value: 0.5,
                TransactionPriority.URGENT.value: 0.7,
                TransactionPriority.HIGH.value: 0.8,
                TransactionPriority.MEDIUM.value: 1.0,
                TransactionPriority.LOW.value: 1.5,
            }

            multiplier = priority_multiplier.get(transaction["priority"], 1.0)

            return base_time * multiplier

        except:
            return 120.0  # 2 minutes default

    async def _calculate_transaction_progress(self, transaction: dict[str, Any]) -> float:
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
                        (transaction["confirmations"] / self.routing_config["confirmation_threshold"]) * 30, 30.0
                    )
                    progress += confirmation_progress

                return progress
            elif status == TransactionStatus.CONFIRMED.value:
                return 90.0
            elif status == TransactionStatus.RETRYING.value:
                return 40.0

            return 0.0

        except:
            return 0.0

    def _get_min_reputation_for_transaction(self, transaction_type: TransactionType, priority: TransactionPriority) -> int:
        """Get minimum reputation required for transaction"""

        base_requirements = {
            TransactionType.TRANSFER: 100,
            TransactionType.SWAP: 200,
            TransactionType.BRIDGE: 300,
            TransactionType.DEPOSIT: 100,
            TransactionType.WITHDRAWAL: 150,
            TransactionType.CONTRACT_CALL: 250,
            TransactionType.APPROVAL: 100,
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

    async def _calculate_routing_score(
        self,
        chain_id: int,
        transaction_type: TransactionType,
        amount: float,
        urgency: TransactionPriority,
        chain_metrics: dict[str, Any],
    ) -> float:
        """Calculate routing score for chain"""

        try:
            # Gas price factor (lower is better)
            gas_price_factor = 1.0 / max(chain_metrics.get("average_gas_price", 1), 1)

            # Confirmation time factor (lower is better)
            confirmation_time_factor = 1.0 / max(chain_metrics.get("average_confirmation_time", 1), 1)

            # Success rate factor (higher is better)
            success_rate_factor = chain_metrics.get("success_rate", 0.5)

            # Queue length factor (lower is better)
            queue_length = len(self.transaction_queues[chain_id])
            queue_factor = 1.0 / max(queue_length, 1)

            # Urgency factor
            urgency_multiplier = {
                TransactionPriority.LOW: 0.8,
                TransactionPriority.MEDIUM: 1.0,
                TransactionPriority.HIGH: 1.2,
                TransactionPriority.URGENT: 1.5,
                TransactionPriority.CRITICAL: 2.0,
            }

            urgency_factor = urgency_multiplier.get(urgency, 1.0)

            # Calculate weighted score
            score = (
                gas_price_factor * 0.25
                + confirmation_time_factor * 0.25
                + success_rate_factor * 0.3
                + queue_factor * 0.1
                + urgency_factor * 0.1
            )

            return score

        except Exception as e:
            logger.error(f"Error calculating routing score: {e}")
            return 0.5
