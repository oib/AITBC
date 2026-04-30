"""
AMM Service

Automated market making for AI service tokens in the AITBC ecosystem.
Provides liquidity pool management, token swapping, and dynamic fee adjustment.
"""

from __future__ import annotations

from datetime import datetime, UTC, timedelta

from aitbc import get_logger
from fastapi import HTTPException
from sqlalchemy import select
from sqlmodel import Session

from ..blockchain.contract_interactions import ContractInteractionService
from ..domain.amm import FeeStructure, IncentiveProgram, LiquidityPool, LiquidityPosition, PoolMetrics, SwapTransaction
from ..marketdata.price_service import PriceService
from ..risk.volatility_calculator import VolatilityCalculator
from ..schemas.amm import (
    LiquidityAddRequest,
    LiquidityAddResponse,
    LiquidityRemoveRequest,
    LiquidityRemoveResponse,
    PoolCreate,
    PoolMetricsResponse,
    PoolResponse,
    SwapRequest,
    SwapResponse,
)

logger = logging.getLogger(__name__)


class AMMService:
    """Automated market making for AI service tokens"""

    def __init__(
        self,
        session: Session,
        contract_service: ContractInteractionService,
        price_service: PriceService,
        volatility_calculator: VolatilityCalculator,
    ) -> None:
        self.session = session
        self.contract_service = contract_service
        self.price_service = price_service
        self.volatility_calculator = volatility_calculator

        # Default configuration
        self.default_fee_percentage = 0.3  # 0.3% default fee
        self.min_liquidity_threshold = 1000  # Minimum liquidity in USD
        self.max_slippage_percentage = 5.0  # Maximum 5% slippage
        self.incentive_duration_days = 30  # Default incentive duration

    async def create_service_pool(self, pool_data: PoolCreate, creator_address: str) -> PoolResponse:
        """Create liquidity pool for AI service trading"""

        try:
            # Validate pool creation request
            validation_result = await self._validate_pool_creation(pool_data, creator_address)
            if not validation_result.is_valid:
                raise HTTPException(status_code=400, detail=validation_result.error_message)

            # Check if pool already exists for this token pair
            existing_pool = await self._get_existing_pool(pool_data.token_a, pool_data.token_b)
            if existing_pool:
                raise HTTPException(status_code=400, detail="Pool already exists for this token pair")

            # Create pool on blockchain
            contract_pool_id = await self.contract_service.create_amm_pool(
                pool_data.token_a, pool_data.token_b, int(pool_data.fee_percentage * 100)  # Convert to basis points
            )

            # Create pool record in database
            pool = LiquidityPool(
                contract_pool_id=str(contract_pool_id),
                token_a=pool_data.token_a,
                token_b=pool_data.token_b,
                fee_percentage=pool_data.fee_percentage,
                total_liquidity=0.0,
                reserve_a=0.0,
                reserve_b=0.0,
                is_active=True,
                created_at=datetime.now(datetime.UTC),
                created_by=creator_address,
            )

            self.session.add(pool)
            self.session.commit()
            self.session.refresh(pool)

            # Initialize pool metrics
            await self._initialize_pool_metrics(pool)

            logger.info(f"Created AMM pool {pool.id} for {pool_data.token_a}/{pool_data.token_b}")

            return PoolResponse.from_orm(pool)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating service pool: {str(e)}")
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    async def add_liquidity(self, liquidity_request: LiquidityAddRequest, provider_address: str) -> LiquidityAddResponse:
        """Add liquidity to a pool"""

        try:
            # Get pool
            pool = await self._get_pool_by_id(liquidity_request.pool_id)

            # Validate liquidity request
            validation_result = await self._validate_liquidity_addition(pool, liquidity_request, provider_address)
            if not validation_result.is_valid:
                raise HTTPException(status_code=400, detail=validation_result.error_message)

            # Calculate optimal amounts
            optimal_amount_b = await self._calculate_optimal_amount_b(pool, liquidity_request.amount_a)

            if liquidity_request.amount_b < optimal_amount_b:
                raise HTTPException(
                    status_code=400, detail=f"Insufficient token B amount. Minimum required: {optimal_amount_b}"
                )

            # Add liquidity on blockchain
            liquidity_result = await self.contract_service.add_liquidity(
                pool.contract_pool_id,
                liquidity_request.amount_a,
                liquidity_request.amount_b,
                liquidity_request.min_amount_a,
                liquidity_request.min_amount_b,
            )

            # Update pool reserves
            pool.reserve_a += liquidity_request.amount_a
            pool.reserve_b += liquidity_request.amount_b
            pool.total_liquidity += liquidity_result.liquidity_received
            pool.updated_at = datetime.now(datetime.UTC)

            # Update or create liquidity position
            position = self.session.execute(
                select(LiquidityPosition).where(
                    LiquidityPosition.pool_id == pool.id, LiquidityPosition.provider_address == provider_address
                )
            ).first()

            if position:
                position.liquidity_amount += liquidity_result.liquidity_received
                position.shares_owned = (position.liquidity_amount / pool.total_liquidity) * 100
                position.last_deposit = datetime.now(datetime.UTC)
            else:
                position = LiquidityPosition(
                    pool_id=pool.id,
                    provider_address=provider_address,
                    liquidity_amount=liquidity_result.liquidity_received,
                    shares_owned=(liquidity_result.liquidity_received / pool.total_liquidity) * 100,
                    last_deposit=datetime.now(datetime.UTC),
                    created_at=datetime.now(datetime.UTC),
                )
                self.session.add(position)

            self.session.commit()
            self.session.refresh(position)

            # Update pool metrics
            await self._update_pool_metrics(pool)

            logger.info(f"Added liquidity to pool {pool.id} by {provider_address}")

            return LiquidityAddResponse.from_orm(position)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error adding liquidity: {str(e)}")
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    async def remove_liquidity(
        self, liquidity_request: LiquidityRemoveRequest, provider_address: str
    ) -> LiquidityRemoveResponse:
        """Remove liquidity from a pool"""

        try:
            # Get pool
            pool = await self._get_pool_by_id(liquidity_request.pool_id)

            # Get liquidity position
            position = self.session.execute(
                select(LiquidityPosition).where(
                    LiquidityPosition.pool_id == pool.id, LiquidityPosition.provider_address == provider_address
                )
            ).first()

            if not position:
                raise HTTPException(status_code=404, detail="Liquidity position not found")

            if position.liquidity_amount < liquidity_request.liquidity_amount:
                raise HTTPException(status_code=400, detail="Insufficient liquidity amount")

            # Remove liquidity on blockchain
            removal_result = await self.contract_service.remove_liquidity(
                pool.contract_pool_id,
                liquidity_request.liquidity_amount,
                liquidity_request.min_amount_a,
                liquidity_request.min_amount_b,
            )

            # Update pool reserves
            pool.reserve_a -= removal_result.amount_a
            pool.reserve_b -= removal_result.amount_b
            pool.total_liquidity -= liquidity_request.liquidity_amount
            pool.updated_at = datetime.now(datetime.UTC)

            # Update liquidity position
            position.liquidity_amount -= liquidity_request.liquidity_amount
            position.shares_owned = (position.liquidity_amount / pool.total_liquidity) * 100 if pool.total_liquidity > 0 else 0
            position.last_withdrawal = datetime.now(datetime.UTC)

            # Remove position if empty
            if position.liquidity_amount == 0:
                self.session.delete(position)

            self.session.commit()

            # Update pool metrics
            await self._update_pool_metrics(pool)

            logger.info(f"Removed liquidity from pool {pool.id} by {provider_address}")

            return LiquidityRemoveResponse(
                pool_id=pool.id,
                amount_a=removal_result.amount_a,
                amount_b=removal_result.amount_b,
                liquidity_removed=liquidity_request.liquidity_amount,
                remaining_liquidity=position.liquidity_amount if position.liquidity_amount > 0 else 0,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error removing liquidity: {str(e)}")
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    async def execute_swap(self, swap_request: SwapRequest, user_address: str) -> SwapResponse:
        """Execute token swap"""

        try:
            # Get pool
            pool = await self._get_pool_by_id(swap_request.pool_id)

            # Validate swap request
            validation_result = await self._validate_swap_request(pool, swap_request, user_address)
            if not validation_result.is_valid:
                raise HTTPException(status_code=400, detail=validation_result.error_message)

            # Calculate expected output amount
            expected_output = await self._calculate_swap_output(pool, swap_request.amount_in, swap_request.token_in)

            # Check slippage
            slippage_percentage = ((expected_output - swap_request.min_amount_out) / expected_output) * 100
            if slippage_percentage > self.max_slippage_percentage:
                raise HTTPException(status_code=400, detail=f"Slippage too high: {slippage_percentage:.2f}%")

            # Execute swap on blockchain
            swap_result = await self.contract_service.execute_swap(
                pool.contract_pool_id,
                swap_request.token_in,
                swap_request.token_out,
                swap_request.amount_in,
                swap_request.min_amount_out,
                user_address,
                swap_request.deadline,
            )

            # Update pool reserves
            if swap_request.token_in == pool.token_a:
                pool.reserve_a += swap_request.amount_in
                pool.reserve_b -= swap_result.amount_out
            else:
                pool.reserve_b += swap_request.amount_in
                pool.reserve_a -= swap_result.amount_out

            pool.updated_at = datetime.now(datetime.UTC)

            # Record swap transaction
            swap_transaction = SwapTransaction(
                pool_id=pool.id,
                user_address=user_address,
                token_in=swap_request.token_in,
                token_out=swap_request.token_out,
                amount_in=swap_request.amount_in,
                amount_out=swap_result.amount_out,
                price=swap_result.price,
                fee_amount=swap_result.fee_amount,
                transaction_hash=swap_result.transaction_hash,
                executed_at=datetime.now(datetime.UTC),
            )

            self.session.add(swap_transaction)
            self.session.commit()
            self.session.refresh(swap_transaction)

            # Update pool metrics
            await self._update_pool_metrics(pool)

            logger.info(f"Executed swap {swap_transaction.id} in pool {pool.id}")

            return SwapResponse.from_orm(swap_transaction)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error executing swap: {str(e)}")
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    async def dynamic_fee_adjustment(self, pool_id: int, volatility: float) -> FeeStructure:
        """Adjust trading fees based on market volatility"""

        try:
            # Get pool
            pool = await self._get_pool_by_id(pool_id)

            # Calculate optimal fee based on volatility
            base_fee = self.default_fee_percentage
            volatility_multiplier = 1.0 + (volatility / 100.0)  # Increase fee with volatility

            # Apply fee caps
            new_fee = min(base_fee * volatility_multiplier, 1.0)  # Max 1% fee
            new_fee = max(new_fee, 0.05)  # Min 0.05% fee

            # Update pool fee on blockchain
            await self.contract_service.update_pool_fee(pool.contract_pool_id, int(new_fee * 100))  # Convert to basis points

            # Update pool in database
            pool.fee_percentage = new_fee
            pool.updated_at = datetime.now(datetime.UTC)
            self.session.commit()

            # Create fee structure response
            fee_structure = FeeStructure(
                pool_id=pool_id,
                base_fee_percentage=base_fee,
                current_fee_percentage=new_fee,
                volatility_adjustment=volatility_multiplier - 1.0,
                adjusted_at=datetime.now(datetime.UTC),
            )

            logger.info(f"Adjusted fee for pool {pool_id} to {new_fee:.3f}%")

            return fee_structure

        except Exception as e:
            logger.error(f"Error adjusting fees: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def liquidity_incentives(self, pool_id: int) -> IncentiveProgram:
        """Implement liquidity provider rewards"""

        try:
            # Get pool
            pool = await self._get_pool_by_id(pool_id)

            # Calculate incentive parameters based on pool metrics
            pool_metrics = await self._get_pool_metrics(pool)

            # Higher incentives for lower liquidity pools
            liquidity_ratio = pool_metrics.total_value_locked / 1000000  # Normalize to 1M USD
            incentive_multiplier = max(1.0, 2.0 - liquidity_ratio)  # 2x for small pools, 1x for large

            # Calculate daily reward amount
            daily_reward = 100 * incentive_multiplier  # Base $100 per day, adjusted by multiplier

            # Create or update incentive program
            existing_program = self.session.execute(
                select(IncentiveProgram).where(IncentiveProgram.pool_id == pool_id)
            ).first()

            if existing_program:
                existing_program.daily_reward_amount = daily_reward
                existing_program.incentive_multiplier = incentive_multiplier
                existing_program.updated_at = datetime.now(datetime.UTC)
                program = existing_program
            else:
                program = IncentiveProgram(
                    pool_id=pool_id,
                    daily_reward_amount=daily_reward,
                    incentive_multiplier=incentive_multiplier,
                    duration_days=self.incentive_duration_days,
                    is_active=True,
                    created_at=datetime.now(datetime.UTC),
                )
                self.session.add(program)

            self.session.commit()
            self.session.refresh(program)

            logger.info(f"Created incentive program for pool {pool_id} with daily reward ${daily_reward:.2f}")

            return program

        except Exception as e:
            logger.error(f"Error creating incentive program: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_pool_metrics(self, pool_id: int) -> PoolMetricsResponse:
        """Get comprehensive pool metrics"""

        try:
            # Get pool
            pool = await self._get_pool_by_id(pool_id)

            # Get detailed metrics
            metrics = await self._get_pool_metrics(pool)

            return PoolMetricsResponse.from_orm(metrics)

        except Exception as e:
            logger.error(f"Error getting pool metrics: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_user_positions(self, user_address: str) -> list[LiquidityPosition]:
        """Get all liquidity positions for a user"""

        try:
            positions = self.session.execute(
                select(LiquidityPosition).where(LiquidityPosition.provider_address == user_address)
            ).all()

            return positions

        except Exception as e:
            logger.error(f"Error getting user positions: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    # Private helper methods

    async def _get_pool_by_id(self, pool_id: int) -> LiquidityPool:
        """Get pool by ID"""
        pool = self.session.get(LiquidityPool, pool_id)
        if not pool or not pool.is_active:
            raise HTTPException(status_code=404, detail="Pool not found")
        return pool

    async def _get_existing_pool(self, token_a: str, token_b: str) -> LiquidityPool | None:
        """Check if pool exists for token pair"""
        pool = self.session.execute(
            select(LiquidityPool).where(
                ((LiquidityPool.token_a == token_a) & (LiquidityPool.token_b == token_b))
                | ((LiquidityPool.token_a == token_b) & (LiquidityPool.token_b == token_a))
            )
        ).first()
        return pool

    async def _validate_pool_creation(self, pool_data: PoolCreate, creator_address: str) -> ValidationResult:
        """Validate pool creation request"""

        # Check token addresses
        if pool_data.token_a == pool_data.token_b:
            return ValidationResult(is_valid=False, error_message="Token addresses must be different")

        # Validate fee percentage
        if not (0.05 <= pool_data.fee_percentage <= 1.0):
            return ValidationResult(is_valid=False, error_message="Fee percentage must be between 0.05% and 1.0%")

        # Check if tokens are supported
        # This would integrate with a token registry service
        # For now, we'll assume all tokens are supported

        return ValidationResult(is_valid=True)

    async def _validate_liquidity_addition(
        self, pool: LiquidityPool, liquidity_request: LiquidityAddRequest, provider_address: str
    ) -> ValidationResult:
        """Validate liquidity addition request"""

        # Check minimum amounts
        if liquidity_request.amount_a <= 0 or liquidity_request.amount_b <= 0:
            return ValidationResult(is_valid=False, error_message="Amounts must be greater than 0")

        # Check if this is first liquidity (no ratio constraints)
        if pool.total_liquidity == 0:
            return ValidationResult(is_valid=True)

        # Calculate optimal ratio
        optimal_amount_b = await self._calculate_optimal_amount_b(pool, liquidity_request.amount_a)

        # Allow 1% deviation
        min_required = optimal_amount_b * 0.99
        if liquidity_request.amount_b < min_required:
            return ValidationResult(is_valid=False, error_message=f"Insufficient token B amount. Minimum: {min_required}")

        return ValidationResult(is_valid=True)

    async def _validate_swap_request(
        self, pool: LiquidityPool, swap_request: SwapRequest, user_address: str
    ) -> ValidationResult:
        """Validate swap request"""

        # Check if pool has sufficient liquidity
        if swap_request.token_in == pool.token_a:
            if pool.reserve_b < swap_request.min_amount_out:
                return ValidationResult(is_valid=False, error_message="Insufficient liquidity in pool")
        else:
            if pool.reserve_a < swap_request.min_amount_out:
                return ValidationResult(is_valid=False, error_message="Insufficient liquidity in pool")

        # Check deadline
        if datetime.now(datetime.UTC) > swap_request.deadline:
            return ValidationResult(is_valid=False, error_message="Transaction deadline expired")

        # Check minimum amount
        if swap_request.amount_in <= 0:
            return ValidationResult(is_valid=False, error_message="Amount must be greater than 0")

        return ValidationResult(is_valid=True)

    async def _calculate_optimal_amount_b(self, pool: LiquidityPool, amount_a: float) -> float:
        """Calculate optimal amount of token B for adding liquidity"""

        if pool.reserve_a == 0:
            return 0.0

        return (amount_a * pool.reserve_b) / pool.reserve_a

    async def _calculate_swap_output(self, pool: LiquidityPool, amount_in: float, token_in: str) -> float:
        """Calculate output amount for swap using constant product formula"""

        # Determine reserves
        if token_in == pool.token_a:
            reserve_in = pool.reserve_a
            reserve_out = pool.reserve_b
        else:
            reserve_in = pool.reserve_b
            reserve_out = pool.reserve_a

        # Apply fee
        fee_amount = (amount_in * pool.fee_percentage) / 100
        amount_in_after_fee = amount_in - fee_amount

        # Calculate output using constant product formula
        # x * y = k
        # (x + amount_in) * (y - amount_out) = k
        # amount_out = (amount_in_after_fee * y) / (x + amount_in_after_fee)

        amount_out = (amount_in_after_fee * reserve_out) / (reserve_in + amount_in_after_fee)

        return amount_out

    async def _initialize_pool_metrics(self, pool: LiquidityPool) -> None:
        """Initialize pool metrics"""

        metrics = PoolMetrics(
            pool_id=pool.id,
            total_volume_24h=0.0,
            total_fees_24h=0.0,
            total_value_locked=0.0,
            apr=0.0,
            utilization_rate=0.0,
            updated_at=datetime.now(datetime.UTC),
        )

        self.session.add(metrics)
        self.session.commit()

    async def _update_pool_metrics(self, pool: LiquidityPool) -> None:
        """Update pool metrics"""

        # Get existing metrics
        metrics = self.session.execute(select(PoolMetrics).where(PoolMetrics.pool_id == pool.id)).first()

        if not metrics:
            await self._initialize_pool_metrics(pool)
            metrics = self.session.execute(select(PoolMetrics).where(PoolMetrics.pool_id == pool.id)).first()

        # Calculate TVL (simplified - would use actual token prices)
        token_a_price = await self.price_service.get_price(pool.token_a)
        token_b_price = await self.price_service.get_price(pool.token_b)

        tvl = (pool.reserve_a * token_a_price) + (pool.reserve_b * token_b_price)

        # Calculate APR (simplified)
        apr = 0.0
        if tvl > 0 and pool.total_liquidity > 0:
            daily_fees = metrics.total_fees_24h
            annual_fees = daily_fees * 365
            apr = (annual_fees / tvl) * 100

        # Calculate utilization rate
        utilization_rate = 0.0
        if pool.total_liquidity > 0:
            # Simplified utilization calculation
            utilization_rate = (tvl / pool.total_liquidity) * 100

        # Update metrics
        metrics.total_value_locked = tvl
        metrics.apr = apr
        metrics.utilization_rate = utilization_rate
        metrics.updated_at = datetime.now(datetime.UTC)

        self.session.commit()

    async def _get_pool_metrics(self, pool: LiquidityPool) -> PoolMetrics:
        """Get comprehensive pool metrics"""

        metrics = self.session.execute(select(PoolMetrics).where(PoolMetrics.pool_id == pool.id)).first()

        if not metrics:
            await self._initialize_pool_metrics(pool)
            metrics = self.session.execute(select(PoolMetrics).where(PoolMetrics.pool_id == pool.id)).first()

        # Calculate 24h volume and fees
        twenty_four_hours_ago = datetime.now(datetime.UTC) - timedelta(hours=24)

        recent_swaps = self.session.execute(
            select(SwapTransaction).where(
                SwapTransaction.pool_id == pool.id, SwapTransaction.executed_at >= twenty_four_hours_ago
            )
        ).all()

        total_volume = sum(swap.amount_in for swap in recent_swaps)
        total_fees = sum(swap.fee_amount for swap in recent_swaps)

        metrics.total_volume_24h = total_volume
        metrics.total_fees_24h = total_fees

        return metrics


class ValidationResult:
    """Validation result for requests"""

    def __init__(self, is_valid: bool, error_message: str = ""):
        self.is_valid = is_valid
        self.error_message = error_message
