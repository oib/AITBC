"""
AMM Service

Automated market making for AI service tokens in the AITBC ecosystem.
Provides liquidity pool management, token swapping, and dynamic fee adjustment.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlmodel import Session

from ..blockchain.contract_interactions import ContractInteractionService  # type: ignore[import-not-found]
from ..domain.amm import (  # type: ignore[import-not-found]
    FeeStructure,
    IncentiveProgram,
    LiquidityPool,
    LiquidityPosition,
    PoolMetrics,
    SwapTransaction,
)
from ..marketdata.price_service import PriceService  # type: ignore[import-not-found]
from ..risk.volatility_calculator import VolatilityCalculator  # type: ignore[import-not-found]
from ..schemas.amm import (  # type: ignore[import-not-found]
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
        self.default_fee_percentage = 0.3
        self.min_liquidity_threshold = 1000
        self.max_slippage_percentage = 5.0
        self.incentive_duration_days = 30

    async def create_service_pool(self, pool_data: PoolCreate, creator_address: str) -> PoolResponse:
        """Create liquidity pool for AI service trading"""
        try:
            validation_result = await self._validate_pool_creation(pool_data, creator_address)
            if not validation_result.is_valid:
                raise HTTPException(status_code=400, detail=validation_result.error_message)
            existing_pool = await self._get_existing_pool(pool_data.token_a, pool_data.token_b)
            if existing_pool:
                raise HTTPException(status_code=400, detail="Pool already exists for this token pair")
            contract_pool_id = await self.contract_service.create_amm_pool(
                pool_data.token_a, pool_data.token_b, int(pool_data.fee_percentage * 100)
            )
            pool = LiquidityPool(
                contract_pool_id=str(contract_pool_id),
                token_a=pool_data.token_a,
                token_b=pool_data.token_b,
                fee_percentage=pool_data.fee_percentage,
                total_liquidity=0.0,
                reserve_a=0.0,
                reserve_b=0.0,
                is_active=True,
                created_at=datetime.now(UTC),
                created_by=creator_address,
            )
            self.session.add(pool)
            self.session.commit()
            self.session.refresh(pool)
            await self._initialize_pool_metrics(pool)
            logger.info("Created AMM pool %s for %s/%s", pool.id, pool_data.token_a, pool_data.token_b)
            return PoolResponse.from_orm(pool)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error creating service pool: %s", str(e))
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e)) from e

    async def add_liquidity(self, liquidity_request: LiquidityAddRequest, provider_address: str) -> LiquidityAddResponse:
        """Add liquidity to a pool"""
        try:
            pool = await self._get_pool_by_id(liquidity_request.pool_id)
            validation_result = await self._validate_liquidity_addition(pool, liquidity_request, provider_address)
            if not validation_result.is_valid:
                raise HTTPException(status_code=400, detail=validation_result.error_message)
            optimal_amount_b = await self._calculate_optimal_amount_b(pool, liquidity_request.amount_a)
            if liquidity_request.amount_b < optimal_amount_b:
                raise HTTPException(
                    status_code=400, detail=f"Insufficient token B amount. Minimum required: {optimal_amount_b}"
                )
            liquidity_result = await self.contract_service.add_liquidity(
                pool.contract_pool_id,
                liquidity_request.amount_a,
                liquidity_request.amount_b,
                liquidity_request.min_amount_a,
                liquidity_request.min_amount_b,
            )
            pool.reserve_a += liquidity_request.amount_a
            pool.reserve_b += liquidity_request.amount_b
            pool.total_liquidity += liquidity_result.liquidity_received
            pool.updated_at = datetime.now(UTC)
            position = self.session.execute(
                select(LiquidityPosition).where(
                    LiquidityPosition.pool_id == pool.id, LiquidityPosition.provider_address == provider_address
                )
            ).first()
            if position:
                position.liquidity_amount += liquidity_result.liquidity_received
                position.shares_owned = position.liquidity_amount / pool.total_liquidity * 100
                position.last_deposit = datetime.now(UTC)
            else:
                position = LiquidityPosition(
                    pool_id=pool.id,
                    provider_address=provider_address,
                    liquidity_amount=liquidity_result.liquidity_received,
                    shares_owned=liquidity_result.liquidity_received / pool.total_liquidity * 100,
                    last_deposit=datetime.now(UTC),
                    created_at=datetime.now(UTC),
                )
                self.session.add(position)
            self.session.commit()
            self.session.refresh(position)
            await self._update_pool_metrics(pool)
            logger.info("Added liquidity to pool %s by %s", pool.id, provider_address)
            return LiquidityAddResponse.from_orm(position)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error adding liquidity: %s", str(e))
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e)) from e

    async def remove_liquidity(
        self, liquidity_request: LiquidityRemoveRequest, provider_address: str
    ) -> LiquidityRemoveResponse:
        """Remove liquidity from a pool"""
        try:
            pool = await self._get_pool_by_id(liquidity_request.pool_id)
            position = self.session.execute(
                select(LiquidityPosition).where(
                    LiquidityPosition.pool_id == pool.id, LiquidityPosition.provider_address == provider_address
                )
            ).first()
            if not position:
                raise HTTPException(status_code=404, detail="Liquidity position not found")
            if position.liquidity_amount < liquidity_request.liquidity_amount:
                raise HTTPException(status_code=400, detail="Insufficient liquidity amount")
            removal_result = await self.contract_service.remove_liquidity(
                pool.contract_pool_id,
                liquidity_request.liquidity_amount,
                liquidity_request.min_amount_a,
                liquidity_request.min_amount_b,
            )
            pool.reserve_a -= removal_result.amount_a
            pool.reserve_b -= removal_result.amount_b
            pool.total_liquidity -= liquidity_request.liquidity_amount
            pool.updated_at = datetime.now(UTC)
            position.liquidity_amount -= liquidity_request.liquidity_amount
            position.shares_owned = position.liquidity_amount / pool.total_liquidity * 100 if pool.total_liquidity > 0 else 0
            position.last_withdrawal = datetime.now(UTC)
            if position.liquidity_amount == 0:
                self.session.delete(position)
            self.session.commit()
            await self._update_pool_metrics(pool)
            logger.info("Removed liquidity from pool %s by %s", pool.id, provider_address)
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
            logger.error("Error removing liquidity: %s", str(e))
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e)) from e

    async def execute_swap(self, swap_request: SwapRequest, user_address: str) -> SwapResponse:
        """Execute token swap"""
        try:
            pool = await self._get_pool_by_id(swap_request.pool_id)
            validation_result = await self._validate_swap_request(pool, swap_request, user_address)
            if not validation_result.is_valid:
                raise HTTPException(status_code=400, detail=validation_result.error_message)
            expected_output = await self._calculate_swap_output(pool, swap_request.amount_in, swap_request.token_in)
            slippage_percentage = (expected_output - swap_request.min_amount_out) / expected_output * 100
            if slippage_percentage > self.max_slippage_percentage:
                raise HTTPException(status_code=400, detail=f"Slippage too high: {slippage_percentage:.2f}%")
            swap_result = await self.contract_service.execute_swap(
                pool.contract_pool_id,
                swap_request.token_in,
                swap_request.token_out,
                swap_request.amount_in,
                swap_request.min_amount_out,
                user_address,
                swap_request.deadline,
            )
            if swap_request.token_in == pool.token_a:
                pool.reserve_a += swap_request.amount_in
                pool.reserve_b -= swap_result.amount_out
            else:
                pool.reserve_b += swap_request.amount_in
                pool.reserve_a -= swap_result.amount_out
            pool.updated_at = datetime.now(UTC)
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
                executed_at=datetime.now(UTC),
            )
            self.session.add(swap_transaction)
            self.session.commit()
            self.session.refresh(swap_transaction)
            await self._update_pool_metrics(pool)
            logger.info("Executed swap %s in pool %s", swap_transaction.id, pool.id)
            return SwapResponse.from_orm(swap_transaction)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error executing swap: %s", str(e))
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e)) from e

    async def dynamic_fee_adjustment(self, pool_id: int, volatility: float) -> FeeStructure:
        """Adjust trading fees based on market volatility"""
        try:
            pool = await self._get_pool_by_id(pool_id)
            base_fee = self.default_fee_percentage
            volatility_multiplier = 1.0 + volatility / 100.0
            new_fee = min(base_fee * volatility_multiplier, 1.0)
            new_fee = max(new_fee, 0.05)
            await self.contract_service.update_pool_fee(pool.contract_pool_id, int(new_fee * 100))
            pool.fee_percentage = new_fee
            pool.updated_at = datetime.now(UTC)
            self.session.commit()
            fee_structure = FeeStructure(
                pool_id=pool_id,
                base_fee_percentage=base_fee,
                current_fee_percentage=new_fee,
                volatility_adjustment=volatility_multiplier - 1.0,
                adjusted_at=datetime.now(UTC),
            )
            logger.info("Adjusted fee for pool %s to %s%", pool_id, new_fee)
            return fee_structure
        except Exception as e:
            logger.error("Error adjusting fees: %s", str(e))
            raise HTTPException(status_code=500, detail=str(e)) from e

    async def liquidity_incentives(self, pool_id: int) -> IncentiveProgram:
        """Implement liquidity provider rewards"""
        try:
            pool = await self._get_pool_by_id(pool_id)
            pool_metrics = await self._get_pool_metrics(pool)
            liquidity_ratio = pool_metrics.total_value_locked / 1000000
            incentive_multiplier = max(1.0, 2.0 - liquidity_ratio)
            daily_reward = 100 * incentive_multiplier
            existing_program = self.session.execute(
                select(IncentiveProgram).where(IncentiveProgram.pool_id == pool_id)
            ).first()
            if existing_program:
                existing_program.daily_reward_amount = daily_reward
                existing_program.incentive_multiplier = incentive_multiplier
                existing_program.updated_at = datetime.now(UTC)
                program = existing_program
            else:
                program = IncentiveProgram(
                    pool_id=pool_id,
                    daily_reward_amount=daily_reward,
                    incentive_multiplier=incentive_multiplier,
                    duration_days=self.incentive_duration_days,
                    is_active=True,
                    created_at=datetime.now(UTC),
                )
                self.session.add(program)
            self.session.commit()
            self.session.refresh(program)
            logger.info("Created incentive program for pool %s with daily reward $%s", pool_id, daily_reward)
            return program
        except Exception as e:
            logger.error("Error creating incentive program: %s", str(e))
            raise HTTPException(status_code=500, detail=str(e)) from e

    async def get_pool_metrics(self, pool_id: int) -> PoolMetricsResponse:
        """Get comprehensive pool metrics"""
        try:
            pool = await self._get_pool_by_id(pool_id)
            metrics = await self._get_pool_metrics(pool)
            return PoolMetricsResponse.from_orm(metrics)
        except Exception as e:
            logger.error("Error getting pool metrics: %s", str(e))
            raise HTTPException(status_code=500, detail=str(e)) from e

    async def get_user_positions(self, user_address: str) -> list[LiquidityPosition]:
        """Get all liquidity positions for a user"""
        try:
            positions = self.session.execute(
                select(LiquidityPosition).where(LiquidityPosition.provider_address == user_address)
            ).all()
            return positions  # type: ignore[return-value]
        except Exception as e:
            logger.error("Error getting user positions: %s", str(e))
            raise HTTPException(status_code=500, detail=str(e)) from e

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
                (LiquidityPool.token_a == token_a) & (LiquidityPool.token_b == token_b)
                | (LiquidityPool.token_a == token_b) & (LiquidityPool.token_b == token_a)
            )
        ).first()
        return pool

    async def _validate_pool_creation(self, pool_data: PoolCreate, creator_address: str) -> ValidationResult:
        """Validate pool creation request"""
        if pool_data.token_a == pool_data.token_b:
            return ValidationResult(is_valid=False, error_message="Token addresses must be different")
        if not 0.05 <= pool_data.fee_percentage <= 1.0:
            return ValidationResult(is_valid=False, error_message="Fee percentage must be between 0.05% and 1.0%")
        return ValidationResult(is_valid=True)

    async def _validate_liquidity_addition(
        self, pool: LiquidityPool, liquidity_request: LiquidityAddRequest, provider_address: str
    ) -> ValidationResult:
        """Validate liquidity addition request"""
        if liquidity_request.amount_a <= 0 or liquidity_request.amount_b <= 0:
            return ValidationResult(is_valid=False, error_message="Amounts must be greater than 0")
        if pool.total_liquidity == 0:
            return ValidationResult(is_valid=True)
        optimal_amount_b = await self._calculate_optimal_amount_b(pool, liquidity_request.amount_a)
        min_required = optimal_amount_b * 0.99
        if liquidity_request.amount_b < min_required:
            return ValidationResult(is_valid=False, error_message=f"Insufficient token B amount. Minimum: {min_required}")
        return ValidationResult(is_valid=True)

    async def _validate_swap_request(
        self, pool: LiquidityPool, swap_request: SwapRequest, user_address: str
    ) -> ValidationResult:
        """Validate swap request"""
        if swap_request.token_in == pool.token_a:
            if pool.reserve_b < swap_request.min_amount_out:
                return ValidationResult(is_valid=False, error_message="Insufficient liquidity in pool")
        elif pool.reserve_a < swap_request.min_amount_out:
            return ValidationResult(is_valid=False, error_message="Insufficient liquidity in pool")
        if datetime.now(UTC) > swap_request.deadline:
            return ValidationResult(is_valid=False, error_message="Transaction deadline expired")
        if swap_request.amount_in <= 0:
            return ValidationResult(is_valid=False, error_message="Amount must be greater than 0")
        return ValidationResult(is_valid=True)

    async def _calculate_optimal_amount_b(self, pool: LiquidityPool, amount_a: float) -> float:
        """Calculate optimal amount of token B for adding liquidity"""
        if pool.reserve_a == 0:
            return 0.0
        return amount_a * pool.reserve_b / pool.reserve_a  # type: ignore[no-any-return]

    async def _calculate_swap_output(self, pool: LiquidityPool, amount_in: float, token_in: str) -> float:
        """Calculate output amount for swap using constant product formula"""
        if token_in == pool.token_a:
            reserve_in = pool.reserve_a
            reserve_out = pool.reserve_b
        else:
            reserve_in = pool.reserve_b
            reserve_out = pool.reserve_a
        fee_amount = amount_in * pool.fee_percentage / 100
        amount_in_after_fee = amount_in - fee_amount
        amount_out = amount_in_after_fee * reserve_out / (reserve_in + amount_in_after_fee)
        return amount_out  # type: ignore[no-any-return]

    async def _initialize_pool_metrics(self, pool: LiquidityPool) -> None:
        """Initialize pool metrics"""
        metrics = PoolMetrics(
            pool_id=pool.id,
            total_volume_24h=0.0,
            total_fees_24h=0.0,
            total_value_locked=0.0,
            apr=0.0,
            utilization_rate=0.0,
            updated_at=datetime.now(UTC),
        )
        self.session.add(metrics)
        self.session.commit()

    async def _update_pool_metrics(self, pool: LiquidityPool) -> None:
        """Update pool metrics"""
        metrics = self.session.execute(select(PoolMetrics).where(PoolMetrics.pool_id == pool.id)).first()
        if not metrics:
            await self._initialize_pool_metrics(pool)
            metrics = self.session.execute(select(PoolMetrics).where(PoolMetrics.pool_id == pool.id)).first()
        token_a_price = await self.price_service.get_price(pool.token_a)
        token_b_price = await self.price_service.get_price(pool.token_b)
        tvl = pool.reserve_a * token_a_price + pool.reserve_b * token_b_price
        apr = 0.0
        if tvl > 0 and pool.total_liquidity > 0:
            daily_fees = metrics.total_fees_24h  # type: ignore[union-attr]
            annual_fees = daily_fees * 365
            apr = annual_fees / tvl * 100
        utilization_rate = 0.0
        if pool.total_liquidity > 0:
            utilization_rate = tvl / pool.total_liquidity * 100
        metrics.total_value_locked = tvl  # type: ignore[union-attr]
        metrics.apr = apr  # type: ignore[union-attr]
        metrics.utilization_rate = utilization_rate  # type: ignore[union-attr]
        metrics.updated_at = datetime.now(UTC)  # type: ignore[union-attr]
        self.session.commit()

    async def _get_pool_metrics(self, pool: LiquidityPool) -> PoolMetrics:
        """Get comprehensive pool metrics"""
        metrics = self.session.execute(select(PoolMetrics).where(PoolMetrics.pool_id == pool.id)).first()
        if not metrics:
            await self._initialize_pool_metrics(pool)
            metrics = self.session.execute(select(PoolMetrics).where(PoolMetrics.pool_id == pool.id)).first()
        twenty_four_hours_ago = datetime.now(UTC) - timedelta(hours=24)
        recent_swaps = self.session.execute(
            select(SwapTransaction).where(
                SwapTransaction.pool_id == pool.id, SwapTransaction.executed_at >= twenty_four_hours_ago
            )
        ).all()
        total_volume = sum(swap.amount_in for swap in recent_swaps)
        total_fees = sum(swap.fee_amount for swap in recent_swaps)
        metrics.total_volume_24h = total_volume  # type: ignore[union-attr]
        metrics.total_fees_24h = total_fees  # type: ignore[union-attr]
        return metrics


class ValidationResult:
    """Validation result for requests"""

    def __init__(self, is_valid: bool, error_message: str = ""):
        self.is_valid = is_valid
        self.error_message = error_message
