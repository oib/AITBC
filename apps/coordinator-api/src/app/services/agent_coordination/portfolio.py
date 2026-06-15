"""
Agent Portfolio Manager Service

Advanced portfolio management for autonomous AI agents in the AITBC ecosystem.
Provides portfolio creation, rebalancing, risk assessment, and trading strategy execution.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlmodel import Session

from ...blockchain.contract_interactions import ContractInteractionService  # type: ignore[import-not-found]
from ...domain.agent_portfolio import (
    AgentPortfolio,
    PortfolioAsset,
    PortfolioStrategy,
    PortfolioTrade,
    RiskMetrics,
    TradeStatus,
)
from ...marketdata.price_service import PriceService  # type: ignore[import-not-found]
from ...ml.strategy_optimizer import StrategyOptimizer  # type: ignore[import-not-found]
from ...risk.risk_calculator import RiskCalculator  # type: ignore[import-not-found]
from ...schemas.portfolio import (  # type: ignore[import-not-found]
    PortfolioCreate,
    PortfolioResponse,
    RebalanceRequest,
    RebalanceResponse,
    RiskAssessmentResponse,
    StrategyCreate,
    StrategyResponse,
    TradeRequest,
    TradeResponse,
)

logger = logging.getLogger(__name__)


class AgentPortfolioManager:
    """Advanced portfolio management for autonomous agents"""

    def __init__(
        self,
        session: Session,
        contract_service: ContractInteractionService,
        price_service: PriceService,
        risk_calculator: RiskCalculator,
        strategy_optimizer: StrategyOptimizer,
    ) -> None:
        self.session = session
        self.contract_service = contract_service
        self.price_service = price_service
        self.risk_calculator = risk_calculator
        self.strategy_optimizer = strategy_optimizer

    async def create_portfolio(self, portfolio_data: PortfolioCreate, agent_address: str) -> PortfolioResponse:
        """Create a new portfolio for an autonomous agent"""
        try:
            if not self._is_valid_address(agent_address):
                raise HTTPException(status_code=400, detail="Invalid agent address")
            existing_portfolio = self.session.execute(
                select(AgentPortfolio).where(AgentPortfolio.agent_address == agent_address)
            ).first()  # type: ignore[arg-type]
            if existing_portfolio:
                raise HTTPException(status_code=400, detail="Portfolio already exists for this agent")
            strategy = self.session.get(PortfolioStrategy, portfolio_data.strategy_id)
            if not strategy or not strategy.is_active:
                raise HTTPException(status_code=404, detail="Strategy not found")
            portfolio = AgentPortfolio(
                agent_address=agent_address,
                strategy_id=portfolio_data.strategy_id,
                initial_capital=portfolio_data.initial_capital,
                risk_tolerance=portfolio_data.risk_tolerance,
                is_active=True,
                created_at=datetime.now(UTC),
                last_rebalance=datetime.now(UTC),
            )
            self.session.add(portfolio)
            self.session.commit()
            self.session.refresh(portfolio)
            await self._initialize_portfolio_assets(portfolio, strategy)
            contract_portfolio_id = await self._deploy_contract_portfolio(portfolio, agent_address, strategy)
            portfolio.contract_portfolio_id = contract_portfolio_id
            self.session.commit()
            logger.info("Created portfolio %s for agent %s", portfolio.id, agent_address)
            return PortfolioResponse.from_orm(portfolio)
        except Exception as e:
            logger.error("Error creating portfolio: %s", str(e))
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    async def execute_trade(self, trade_request: TradeRequest, agent_address: str) -> TradeResponse:
        """Execute a trade within the agent's portfolio"""
        try:
            portfolio = self._get_agent_portfolio(agent_address)
            validation_result = await self._validate_trade_request(portfolio, trade_request)
            if not validation_result.is_valid:
                raise HTTPException(status_code=400, detail=validation_result.error_message)
            sell_price = await self.price_service.get_price(trade_request.sell_token)
            buy_price = await self.price_service.get_price(trade_request.buy_token)
            expected_buy_amount = self._calculate_buy_amount(trade_request.sell_amount, sell_price, buy_price)
            if expected_buy_amount < trade_request.min_buy_amount:
                raise HTTPException(status_code=400, detail="Insufficient buy amount (slippage protection)")
            trade_result = await self.contract_service.execute_portfolio_trade(
                portfolio.contract_portfolio_id,
                trade_request.sell_token,
                trade_request.buy_token,
                trade_request.sell_amount,
                trade_request.min_buy_amount,
            )
            trade = PortfolioTrade(
                portfolio_id=portfolio.id,
                sell_token=trade_request.sell_token,
                buy_token=trade_request.buy_token,
                sell_amount=trade_request.sell_amount,
                buy_amount=trade_result.buy_amount,
                price=trade_result.price,
                status=TradeStatus.EXECUTED,
                transaction_hash=trade_result.transaction_hash,
                executed_at=datetime.now(UTC),
            )
            self.session.add(trade)
            await self._update_portfolio_assets(portfolio, trade)
            await self._update_portfolio_metrics(portfolio)
            self.session.commit()
            self.session.refresh(trade)
            logger.info("Executed trade %s for portfolio %s", trade.id, portfolio.id)
            return TradeResponse.from_orm(trade)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error executing trade: %s", str(e))
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    async def execute_rebalancing(self, rebalance_request: RebalanceRequest, agent_address: str) -> RebalanceResponse:
        """Automated portfolio rebalancing based on market conditions"""
        try:
            portfolio = self._get_agent_portfolio(agent_address)
            if not await self._needs_rebalancing(portfolio):
                return RebalanceResponse(success=False, message="Rebalancing not needed at this time")
            market_conditions = await self.price_service.get_market_conditions()
            optimal_allocations = await self.strategy_optimizer.calculate_optimal_allocations(portfolio, market_conditions)
            rebalance_trades = await self._generate_rebalance_trades(portfolio, optimal_allocations)
            if not rebalance_trades:
                return RebalanceResponse(success=False, message="No rebalancing trades required")
            executed_trades = []
            for trade in rebalance_trades:
                try:
                    trade_response = await self.execute_trade(trade, agent_address)
                    executed_trades.append(trade_response)
                except Exception as e:
                    logger.warning("Failed to execute rebalancing trade: %s", str(e))
                    continue
            portfolio.last_rebalance = datetime.now(UTC)
            self.session.commit()
            logger.info("Rebalanced portfolio %s with %s trades", portfolio.id, len(executed_trades))
            return RebalanceResponse(
                success=True, message=f"Rebalanced with {len(executed_trades)} trades", trades_executed=len(executed_trades)
            )
        except Exception as e:
            logger.error("Error executing rebalancing: %s", str(e))
            raise HTTPException(status_code=500, detail=str(e))

    async def risk_assessment(self, agent_address: str) -> RiskAssessmentResponse:
        """Real-time risk assessment and position sizing"""
        try:
            portfolio = self._get_agent_portfolio(agent_address)
            portfolio_value = await self._calculate_portfolio_value(portfolio)
            risk_metrics = await self.risk_calculator.calculate_portfolio_risk(portfolio, portfolio_value)
            existing_metrics = self.session.execute(
                select(RiskMetrics).where(RiskMetrics.portfolio_id == portfolio.id)
            ).first()  # type: ignore[arg-type]
            if existing_metrics:
                existing_metrics.volatility = risk_metrics.volatility
                existing_metrics.max_drawdown = risk_metrics.max_drawdown
                existing_metrics.sharpe_ratio = risk_metrics.sharpe_ratio
                existing_metrics.var_95 = risk_metrics.var_95
                existing_metrics.risk_level = risk_metrics.risk_level
                existing_metrics.updated_at = datetime.now(UTC)
            else:
                risk_metrics.portfolio_id = portfolio.id
                risk_metrics.updated_at = datetime.now(UTC)
                self.session.add(risk_metrics)
            portfolio.risk_score = risk_metrics.overall_risk_score
            self.session.commit()
            logger.info("Risk assessment completed for portfolio %s", portfolio.id)
            return RiskAssessmentResponse.from_orm(risk_metrics)
        except Exception as e:
            logger.error("Error in risk assessment: %s", str(e))
            raise HTTPException(status_code=500, detail=str(e))

    async def get_portfolio_performance(self, agent_address: str, period: str = "30d") -> dict:
        """Get portfolio performance metrics"""
        try:
            portfolio = self._get_agent_portfolio(agent_address)
            performance_data = await self._calculate_performance_metrics(portfolio, period)
            return performance_data
        except Exception as e:
            logger.error("Error getting portfolio performance: %s", str(e))
            raise HTTPException(status_code=500, detail=str(e))

    async def create_portfolio_strategy(self, strategy_data: StrategyCreate) -> StrategyResponse:
        """Create a new portfolio strategy"""
        try:
            total_allocation = sum(strategy_data.target_allocations.values())
            if abs(total_allocation - 100.0) > 0.01:
                raise HTTPException(status_code=400, detail="Target allocations must sum to 100%")
            strategy = PortfolioStrategy(
                name=strategy_data.name,
                strategy_type=strategy_data.strategy_type,
                target_allocations=strategy_data.target_allocations,
                max_drawdown=strategy_data.max_drawdown,
                rebalance_frequency=strategy_data.rebalance_frequency,
                is_active=True,
                created_at=datetime.now(UTC),
            )
            self.session.add(strategy)
            self.session.commit()
            self.session.refresh(strategy)
            logger.info("Created strategy %s: %s", strategy.id, strategy.name)
            return StrategyResponse.from_orm(strategy)
        except Exception as e:
            logger.error("Error creating strategy: %s", str(e))
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    def _get_agent_portfolio(self, agent_address: str) -> AgentPortfolio:
        """Get portfolio for agent address"""
        portfolio = self.session.execute(select(AgentPortfolio).where(AgentPortfolio.agent_address == agent_address)).first()  # type: ignore[arg-type]
        if not portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        return portfolio  # type: ignore[return-value]

    def _is_valid_address(self, address: str) -> bool:
        """Validate Ethereum address"""
        return address.startswith("0x") and len(address) == 42 and all(c in "0123456789abcdefABCDEF" for c in address[2:])

    async def _initialize_portfolio_assets(self, portfolio: AgentPortfolio, strategy: PortfolioStrategy) -> None:
        """Initialize portfolio assets based on strategy allocations"""
        for token_symbol, allocation in strategy.target_allocations.items():
            if allocation > 0:
                asset = PortfolioAsset(
                    portfolio_id=portfolio.id,
                    token_symbol=token_symbol,
                    target_allocation=allocation,
                    current_allocation=0.0,
                    balance=0,
                    created_at=datetime.now(UTC),
                )
                self.session.add(asset)

    async def _deploy_contract_portfolio(
        self, portfolio: AgentPortfolio, agent_address: str, strategy: PortfolioStrategy
    ) -> str:
        """Deploy smart contract portfolio"""
        try:
            contract_allocations = {token: int(allocation * 100) for token, allocation in strategy.target_allocations.items()}
            portfolio_id = await self.contract_service.create_portfolio(
                agent_address, strategy.strategy_type.value, contract_allocations
            )
            return str(portfolio_id)
        except Exception as e:
            logger.error("Error deploying contract portfolio: %s", str(e))
            raise

    async def _validate_trade_request(self, portfolio: AgentPortfolio, trade_request: TradeRequest) -> ValidationResult:
        """Validate trade request"""
        sell_asset = self.session.execute(
            select(PortfolioAsset).where(
                PortfolioAsset.portfolio_id == portfolio.id, PortfolioAsset.token_symbol == trade_request.sell_token
            )
        ).first()  # type: ignore[arg-type]
        if not sell_asset:
            return ValidationResult(is_valid=False, error_message="Sell token not found in portfolio")
        if sell_asset.balance < trade_request.sell_amount:
            return ValidationResult(is_valid=False, error_message="Insufficient balance")
        current_risk = await self.risk_calculator.calculate_trade_risk(portfolio, trade_request)
        if current_risk > portfolio.risk_tolerance:
            return ValidationResult(is_valid=False, error_message="Trade exceeds risk tolerance")
        return ValidationResult(is_valid=True)

    def _calculate_buy_amount(self, sell_amount: float, sell_price: float, buy_price: float) -> float:
        """Calculate expected buy amount"""
        sell_value = sell_amount * sell_price
        return sell_value / buy_price

    async def _update_portfolio_assets(self, portfolio: AgentPortfolio, trade: PortfolioTrade) -> None:
        """Update portfolio assets after trade"""
        sell_asset = self.session.execute(
            select(PortfolioAsset).where(
                PortfolioAsset.portfolio_id == portfolio.id, PortfolioAsset.token_symbol == trade.sell_token
            )
        ).first()  # type: ignore[arg-type]
        if sell_asset:
            sell_asset.balance -= trade.sell_amount
            sell_asset.updated_at = datetime.now(UTC)
        buy_asset = self.session.execute(
            select(PortfolioAsset).where(
                PortfolioAsset.portfolio_id == portfolio.id, PortfolioAsset.token_symbol == trade.buy_token
            )
        ).first()  # type: ignore[arg-type]
        if buy_asset:
            buy_asset.balance += trade.buy_amount
            buy_asset.updated_at = datetime.now(UTC)
        else:
            new_asset = PortfolioAsset(
                portfolio_id=portfolio.id,
                token_symbol=trade.buy_token,
                target_allocation=0.0,
                current_allocation=0.0,
                balance=trade.buy_amount,
                created_at=datetime.now(UTC),
            )
            self.session.add(new_asset)

    async def _update_portfolio_metrics(self, portfolio: AgentPortfolio) -> None:
        """Update portfolio value and allocations"""
        portfolio_value = await self._calculate_portfolio_value(portfolio)
        assets = self.session.execute(select(PortfolioAsset).where(PortfolioAsset.portfolio_id == portfolio.id)).all()  # type: ignore[arg-type]
        for asset in assets:
            if asset.balance > 0:
                price = await self.price_service.get_price(asset.token_symbol)
                asset_value = asset.balance * price
                asset.current_allocation = asset_value / portfolio_value * 100
                asset.updated_at = datetime.now(UTC)
        portfolio.total_value = portfolio_value
        portfolio.updated_at = datetime.now(UTC)

    async def _calculate_portfolio_value(self, portfolio: AgentPortfolio) -> float:
        """Calculate total portfolio value"""
        assets = self.session.execute(select(PortfolioAsset).where(PortfolioAsset.portfolio_id == portfolio.id)).all()  # type: ignore[arg-type]
        total_value = 0.0
        for asset in assets:
            if asset.balance > 0:
                price = await self.price_service.get_price(asset.token_symbol)
                total_value += asset.balance * price
        return total_value

    async def _needs_rebalancing(self, portfolio: AgentPortfolio) -> bool:
        """Check if portfolio needs rebalancing"""
        strategy = self.session.get(PortfolioStrategy, portfolio.strategy_id)
        if not strategy:
            return False
        time_since_rebalance = datetime.now(UTC) - portfolio.last_rebalance
        if time_since_rebalance > timedelta(seconds=strategy.rebalance_frequency):
            return True
        assets = self.session.execute(select(PortfolioAsset).where(PortfolioAsset.portfolio_id == portfolio.id)).all()  # type: ignore[arg-type]
        for asset in assets:
            if asset.balance > 0:
                deviation = abs(asset.current_allocation - asset.target_allocation)
                if deviation > 5.0:
                    return True
        return False

    async def _generate_rebalance_trades(
        self, portfolio: AgentPortfolio, optimal_allocations: dict[str, float]
    ) -> list[TradeRequest]:
        """Generate rebalancing trades"""
        trades = []
        assets = self.session.execute(select(PortfolioAsset).where(PortfolioAsset.portfolio_id == portfolio.id)).all()  # type: ignore[arg-type]
        for asset in assets:
            target_allocation = optimal_allocations.get(asset.token_symbol, 0.0)
            current_allocation = asset.current_allocation
            if abs(current_allocation - target_allocation) > 1.0:
                if current_allocation > target_allocation:
                    excess_percentage = current_allocation - target_allocation
                    sell_amount = asset.balance * excess_percentage / 100
                    for other_asset in assets:
                        other_target = optimal_allocations.get(other_asset.token_symbol, 0.0)
                        other_current = other_asset.current_allocation
                        if other_current < other_target:
                            trade = TradeRequest(
                                sell_token=asset.token_symbol,
                                buy_token=other_asset.token_symbol,
                                sell_amount=sell_amount,
                                min_buy_amount=0,
                            )
                            trades.append(trade)
                            break
        return trades

    async def _calculate_performance_metrics(self, portfolio: AgentPortfolio, period: str) -> dict:
        """Calculate portfolio performance metrics"""
        trades = self.session.execute(
            select(PortfolioTrade)
            .where(PortfolioTrade.portfolio_id == portfolio.id)
            .order_by(PortfolioTrade.executed_at.desc())
        ).all()  # type: ignore[arg-type, union-attr]
        current_value = await self._calculate_portfolio_value(portfolio)
        initial_value = portfolio.initial_capital
        total_return = (current_value - initial_value) / initial_value * 100
        return {
            "total_return": total_return,
            "current_value": current_value,
            "initial_value": initial_value,
            "total_trades": len(trades),
            "last_updated": datetime.now(UTC).isoformat(),
        }


class ValidationResult:
    """Validation result for trade requests"""

    def __init__(self, is_valid: bool, error_message: str = "") -> None:
        self.is_valid = is_valid
        self.error_message = error_message
