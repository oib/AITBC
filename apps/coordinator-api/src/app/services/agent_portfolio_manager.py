"""
Agent Portfolio Manager Service

Advanced portfolio management for autonomous AI agents in the AITBC ecosystem.
Provides portfolio creation, rebalancing, risk assessment, and trading strategy execution.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlmodel import Session

from ..domain.agent_portfolio import (
    AgentPortfolio,
    PortfolioStrategy,
    PortfolioAsset,
    PortfolioTrade,
    RiskMetrics,
    StrategyType,
    TradeStatus,
    RiskLevel
)
from ..schemas.portfolio import (
    PortfolioCreate,
    PortfolioResponse,
    PortfolioUpdate,
    TradeRequest,
    TradeResponse,
    RiskAssessmentResponse,
    RebalanceRequest,
    RebalanceResponse,
    StrategyCreate,
    StrategyResponse
)
from ..blockchain.contract_interactions import ContractInteractionService
from ..marketdata.price_service import PriceService
from ..risk.risk_calculator import RiskCalculator
from ..ml.strategy_optimizer import StrategyOptimizer

logger = logging.getLogger(__name__)


class AgentPortfolioManager:
    """Advanced portfolio management for autonomous agents"""
    
    def __init__(
        self,
        session: Session,
        contract_service: ContractInteractionService,
        price_service: PriceService,
        risk_calculator: RiskCalculator,
        strategy_optimizer: StrategyOptimizer
    ) -> None:
        self.session = session
        self.contract_service = contract_service
        self.price_service = price_service
        self.risk_calculator = risk_calculator
        self.strategy_optimizer = strategy_optimizer
        
    async def create_portfolio(
        self,
        portfolio_data: PortfolioCreate,
        agent_address: str
    ) -> PortfolioResponse:
        """Create a new portfolio for an autonomous agent"""
        
        try:
            # Validate agent address
            if not self._is_valid_address(agent_address):
                raise HTTPException(status_code=400, detail="Invalid agent address")
            
            # Check if portfolio already exists
            existing_portfolio = self.session.execute(
                select(AgentPortfolio).where(
                    AgentPortfolio.agent_address == agent_address
                )
            ).first()
            
            if existing_portfolio:
                raise HTTPException(
                    status_code=400, 
                    detail="Portfolio already exists for this agent"
                )
            
            # Get strategy
            strategy = self.session.get(PortfolioStrategy, portfolio_data.strategy_id)
            if not strategy or not strategy.is_active:
                raise HTTPException(status_code=404, detail="Strategy not found")
            
            # Create portfolio
            portfolio = AgentPortfolio(
                agent_address=agent_address,
                strategy_id=portfolio_data.strategy_id,
                initial_capital=portfolio_data.initial_capital,
                risk_tolerance=portfolio_data.risk_tolerance,
                is_active=True,
                created_at=datetime.utcnow(),
                last_rebalance=datetime.utcnow()
            )
            
            self.session.add(portfolio)
            self.session.commit()
            self.session.refresh(portfolio)
            
            # Initialize portfolio assets based on strategy
            await self._initialize_portfolio_assets(portfolio, strategy)
            
            # Deploy smart contract portfolio
            contract_portfolio_id = await self._deploy_contract_portfolio(
                portfolio, agent_address, strategy
            )
            
            portfolio.contract_portfolio_id = contract_portfolio_id
            self.session.commit()
            
            logger.info(f"Created portfolio {portfolio.id} for agent {agent_address}")
            
            return PortfolioResponse.from_orm(portfolio)
            
        except Exception as e:
            logger.error(f"Error creating portfolio: {str(e)}")
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))
    
    async def execute_trade(
        self,
        trade_request: TradeRequest,
        agent_address: str
    ) -> TradeResponse:
        """Execute a trade within the agent's portfolio"""
        
        try:
            # Get portfolio
            portfolio = self._get_agent_portfolio(agent_address)
            
            # Validate trade request
            validation_result = await self._validate_trade_request(
                portfolio, trade_request
            )
            if not validation_result.is_valid:
                raise HTTPException(
                    status_code=400, 
                    detail=validation_result.error_message
                )
            
            # Get current prices
            sell_price = await self.price_service.get_price(trade_request.sell_token)
            buy_price = await self.price_service.get_price(trade_request.buy_token)
            
            # Calculate expected buy amount
            expected_buy_amount = self._calculate_buy_amount(
                trade_request.sell_amount, sell_price, buy_price
            )
            
            # Check slippage
            if expected_buy_amount < trade_request.min_buy_amount:
                raise HTTPException(
                    status_code=400, 
                    detail="Insufficient buy amount (slippage protection)"
                )
            
            # Execute trade on blockchain
            trade_result = await self.contract_service.execute_portfolio_trade(
                portfolio.contract_portfolio_id,
                trade_request.sell_token,
                trade_request.buy_token,
                trade_request.sell_amount,
                trade_request.min_buy_amount
            )
            
            # Record trade in database
            trade = PortfolioTrade(
                portfolio_id=portfolio.id,
                sell_token=trade_request.sell_token,
                buy_token=trade_request.buy_token,
                sell_amount=trade_request.sell_amount,
                buy_amount=trade_result.buy_amount,
                price=trade_result.price,
                status=TradeStatus.EXECUTED,
                transaction_hash=trade_result.transaction_hash,
                executed_at=datetime.utcnow()
            )
            
            self.session.add(trade)
            
            # Update portfolio assets
            await self._update_portfolio_assets(portfolio, trade)
            
            # Update portfolio value and risk
            await self._update_portfolio_metrics(portfolio)
            
            self.session.commit()
            self.session.refresh(trade)
            
            logger.info(f"Executed trade {trade.id} for portfolio {portfolio.id}")
            
            return TradeResponse.from_orm(trade)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error executing trade: {str(e)}")
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))
    
    async def execute_rebalancing(
        self,
        rebalance_request: RebalanceRequest,
        agent_address: str
    ) -> RebalanceResponse:
        """Automated portfolio rebalancing based on market conditions"""
        
        try:
            # Get portfolio
            portfolio = self._get_agent_portfolio(agent_address)
            
            # Check if rebalancing is needed
            if not await self._needs_rebalancing(portfolio):
                return RebalanceResponse(
                    success=False,
                    message="Rebalancing not needed at this time"
                )
            
            # Get current market conditions
            market_conditions = await self.price_service.get_market_conditions()
            
            # Calculate optimal allocations
            optimal_allocations = await self.strategy_optimizer.calculate_optimal_allocations(
                portfolio, market_conditions
            )
            
            # Generate rebalancing trades
            rebalance_trades = await self._generate_rebalance_trades(
                portfolio, optimal_allocations
            )
            
            if not rebalance_trades:
                return RebalanceResponse(
                    success=False,
                    message="No rebalancing trades required"
                )
            
            # Execute rebalancing trades
            executed_trades = []
            for trade in rebalance_trades:
                try:
                    trade_response = await self.execute_trade(trade, agent_address)
                    executed_trades.append(trade_response)
                except Exception as e:
                    logger.warning(f"Failed to execute rebalancing trade: {str(e)}")
                    continue
            
            # Update portfolio rebalance timestamp
            portfolio.last_rebalance = datetime.utcnow()
            self.session.commit()
            
            logger.info(f"Rebalanced portfolio {portfolio.id} with {len(executed_trades)} trades")
            
            return RebalanceResponse(
                success=True,
                message=f"Rebalanced with {len(executed_trades)} trades",
                trades_executed=len(executed_trades)
            )
            
        except Exception as e:
            logger.error(f"Error executing rebalancing: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def risk_assessment(self, agent_address: str) -> RiskAssessmentResponse:
        """Real-time risk assessment and position sizing"""
        
        try:
            # Get portfolio
            portfolio = self._get_agent_portfolio(agent_address)
            
            # Get current portfolio value
            portfolio_value = await self._calculate_portfolio_value(portfolio)
            
            # Calculate risk metrics
            risk_metrics = await self.risk_calculator.calculate_portfolio_risk(
                portfolio, portfolio_value
            )
            
            # Update risk metrics in database
            existing_metrics = self.session.execute(
                select(RiskMetrics).where(RiskMetrics.portfolio_id == portfolio.id)
            ).first()
            
            if existing_metrics:
                existing_metrics.volatility = risk_metrics.volatility
                existing_metrics.max_drawdown = risk_metrics.max_drawdown
                existing_metrics.sharpe_ratio = risk_metrics.sharpe_ratio
                existing_metrics.var_95 = risk_metrics.var_95
                existing_metrics.risk_level = risk_metrics.risk_level
                existing_metrics.updated_at = datetime.utcnow()
            else:
                risk_metrics.portfolio_id = portfolio.id
                risk_metrics.updated_at = datetime.utcnow()
                self.session.add(risk_metrics)
            
            # Update portfolio risk score
            portfolio.risk_score = risk_metrics.overall_risk_score
            self.session.commit()
            
            logger.info(f"Risk assessment completed for portfolio {portfolio.id}")
            
            return RiskAssessmentResponse.from_orm(risk_metrics)
            
        except Exception as e:
            logger.error(f"Error in risk assessment: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def get_portfolio_performance(
        self,
        agent_address: str,
        period: str = "30d"
    ) -> Dict:
        """Get portfolio performance metrics"""
        
        try:
            # Get portfolio
            portfolio = self._get_agent_portfolio(agent_address)
            
            # Calculate performance metrics
            performance_data = await self._calculate_performance_metrics(
                portfolio, period
            )
            
            return performance_data
            
        except Exception as e:
            logger.error(f"Error getting portfolio performance: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def create_portfolio_strategy(
        self,
        strategy_data: StrategyCreate
    ) -> StrategyResponse:
        """Create a new portfolio strategy"""
        
        try:
            # Validate strategy allocations
            total_allocation = sum(strategy_data.target_allocations.values())
            if abs(total_allocation - 100.0) > 0.01:  # Allow small rounding errors
                raise HTTPException(
                    status_code=400,
                    detail="Target allocations must sum to 100%"
                )
            
            # Create strategy
            strategy = PortfolioStrategy(
                name=strategy_data.name,
                strategy_type=strategy_data.strategy_type,
                target_allocations=strategy_data.target_allocations,
                max_drawdown=strategy_data.max_drawdown,
                rebalance_frequency=strategy_data.rebalance_frequency,
                is_active=True,
                created_at=datetime.utcnow()
            )
            
            self.session.add(strategy)
            self.session.commit()
            self.session.refresh(strategy)
            
            logger.info(f"Created strategy {strategy.id}: {strategy.name}")
            
            return StrategyResponse.from_orm(strategy)
            
        except Exception as e:
            logger.error(f"Error creating strategy: {str(e)}")
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))
    
    # Private helper methods
    
    def _get_agent_portfolio(self, agent_address: str) -> AgentPortfolio:
        """Get portfolio for agent address"""
        portfolio = self.session.execute(
            select(AgentPortfolio).where(
                AgentPortfolio.agent_address == agent_address
            )
        ).first()
        
        if not portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        
        return portfolio
    
    def _is_valid_address(self, address: str) -> bool:
        """Validate Ethereum address"""
        return (
            address.startswith("0x") and 
            len(address) == 42 and 
            all(c in "0123456789abcdefABCDEF" for c in address[2:])
        )
    
    async def _initialize_portfolio_assets(
        self,
        portfolio: AgentPortfolio,
        strategy: PortfolioStrategy
    ) -> None:
        """Initialize portfolio assets based on strategy allocations"""
        
        for token_symbol, allocation in strategy.target_allocations.items():
            if allocation > 0:
                asset = PortfolioAsset(
                    portfolio_id=portfolio.id,
                    token_symbol=token_symbol,
                    target_allocation=allocation,
                    current_allocation=0.0,
                    balance=0,
                    created_at=datetime.utcnow()
                )
                self.session.add(asset)
    
    async def _deploy_contract_portfolio(
        self,
        portfolio: AgentPortfolio,
        agent_address: str,
        strategy: PortfolioStrategy
    ) -> str:
        """Deploy smart contract portfolio"""
        
        try:
            # Convert strategy allocations to contract format
            contract_allocations = {
                token: int(allocation * 100)  # Convert to basis points
                for token, allocation in strategy.target_allocations.items()
            }
            
            # Create portfolio on blockchain
            portfolio_id = await self.contract_service.create_portfolio(
                agent_address,
                strategy.strategy_type.value,
                contract_allocations
            )
            
            return str(portfolio_id)
            
        except Exception as e:
            logger.error(f"Error deploying contract portfolio: {str(e)}")
            raise
    
    async def _validate_trade_request(
        self,
        portfolio: AgentPortfolio,
        trade_request: TradeRequest
    ) -> ValidationResult:
        """Validate trade request"""
        
        # Check if sell token exists in portfolio
        sell_asset = self.session.execute(
            select(PortfolioAsset).where(
                PortfolioAsset.portfolio_id == portfolio.id,
                PortfolioAsset.token_symbol == trade_request.sell_token
            )
        ).first()
        
        if not sell_asset:
            return ValidationResult(
                is_valid=False,
                error_message="Sell token not found in portfolio"
            )
        
        # Check sufficient balance
        if sell_asset.balance < trade_request.sell_amount:
            return ValidationResult(
                is_valid=False,
                error_message="Insufficient balance"
            )
        
        # Check risk limits
        current_risk = await self.risk_calculator.calculate_trade_risk(
            portfolio, trade_request
        )
        
        if current_risk > portfolio.risk_tolerance:
            return ValidationResult(
                is_valid=False,
                error_message="Trade exceeds risk tolerance"
            )
        
        return ValidationResult(is_valid=True)
    
    def _calculate_buy_amount(
        self,
        sell_amount: float,
        sell_price: float,
        buy_price: float
    ) -> float:
        """Calculate expected buy amount"""
        sell_value = sell_amount * sell_price
        return sell_value / buy_price
    
    async def _update_portfolio_assets(
        self,
        portfolio: AgentPortfolio,
        trade: PortfolioTrade
    ) -> None:
        """Update portfolio assets after trade"""
        
        # Update sell asset
        sell_asset = self.session.execute(
            select(PortfolioAsset).where(
                PortfolioAsset.portfolio_id == portfolio.id,
                PortfolioAsset.token_symbol == trade.sell_token
            )
        ).first()
        
        if sell_asset:
            sell_asset.balance -= trade.sell_amount
            sell_asset.updated_at = datetime.utcnow()
        
        # Update buy asset
        buy_asset = self.session.execute(
            select(PortfolioAsset).where(
                PortfolioAsset.portfolio_id == portfolio.id,
                PortfolioAsset.token_symbol == trade.buy_token
            )
        ).first()
        
        if buy_asset:
            buy_asset.balance += trade.buy_amount
            buy_asset.updated_at = datetime.utcnow()
        else:
            # Create new asset if it doesn't exist
            new_asset = PortfolioAsset(
                portfolio_id=portfolio.id,
                token_symbol=trade.buy_token,
                target_allocation=0.0,
                current_allocation=0.0,
                balance=trade.buy_amount,
                created_at=datetime.utcnow()
            )
            self.session.add(new_asset)
    
    async def _update_portfolio_metrics(self, portfolio: AgentPortfolio) -> None:
        """Update portfolio value and allocations"""
        
        portfolio_value = await self._calculate_portfolio_value(portfolio)
        
        # Update current allocations
        assets = self.session.execute(
            select(PortfolioAsset).where(
                PortfolioAsset.portfolio_id == portfolio.id
            )
        ).all()
        
        for asset in assets:
            if asset.balance > 0:
                price = await self.price_service.get_price(asset.token_symbol)
                asset_value = asset.balance * price
                asset.current_allocation = (asset_value / portfolio_value) * 100
                asset.updated_at = datetime.utcnow()
        
        portfolio.total_value = portfolio_value
        portfolio.updated_at = datetime.utcnow()
    
    async def _calculate_portfolio_value(self, portfolio: AgentPortfolio) -> float:
        """Calculate total portfolio value"""
        
        assets = self.session.execute(
            select(PortfolioAsset).where(
                PortfolioAsset.portfolio_id == portfolio.id
            )
        ).all()
        
        total_value = 0.0
        for asset in assets:
            if asset.balance > 0:
                price = await self.price_service.get_price(asset.token_symbol)
                total_value += asset.balance * price
        
        return total_value
    
    async def _needs_rebalancing(self, portfolio: AgentPortfolio) -> bool:
        """Check if portfolio needs rebalancing"""
        
        # Check time-based rebalancing
        strategy = self.session.get(PortfolioStrategy, portfolio.strategy_id)
        if not strategy:
            return False
        
        time_since_rebalance = datetime.utcnow() - portfolio.last_rebalance
        if time_since_rebalance > timedelta(seconds=strategy.rebalance_frequency):
            return True
        
        # Check threshold-based rebalancing
        assets = self.session.execute(
            select(PortfolioAsset).where(
                PortfolioAsset.portfolio_id == portfolio.id
            )
        ).all()
        
        for asset in assets:
            if asset.balance > 0:
                deviation = abs(asset.current_allocation - asset.target_allocation)
                if deviation > 5.0:  # 5% deviation threshold
                    return True
        
        return False
    
    async def _generate_rebalance_trades(
        self,
        portfolio: AgentPortfolio,
        optimal_allocations: Dict[str, float]
    ) -> List[TradeRequest]:
        """Generate rebalancing trades"""
        
        trades = []
        assets = self.session.execute(
            select(PortfolioAsset).where(
                PortfolioAsset.portfolio_id == portfolio.id
            )
        ).all()
        
        # Calculate current vs target allocations
        for asset in assets:
            target_allocation = optimal_allocations.get(asset.token_symbol, 0.0)
            current_allocation = asset.current_allocation
            
            if abs(current_allocation - target_allocation) > 1.0:  # 1% minimum deviation
                if current_allocation > target_allocation:
                    # Sell excess
                    excess_percentage = current_allocation - target_allocation
                    sell_amount = (asset.balance * excess_percentage) / 100
                    
                    # Find asset to buy
                    for other_asset in assets:
                        other_target = optimal_allocations.get(other_asset.token_symbol, 0.0)
                        other_current = other_asset.current_allocation
                        
                        if other_current < other_target:
                            trade = TradeRequest(
                                sell_token=asset.token_symbol,
                                buy_token=other_asset.token_symbol,
                                sell_amount=sell_amount,
                                min_buy_amount=0  # Will be calculated during execution
                            )
                            trades.append(trade)
                            break
        
        return trades
    
    async def _calculate_performance_metrics(
        self,
        portfolio: AgentPortfolio,
        period: str
    ) -> Dict:
        """Calculate portfolio performance metrics"""
        
        # Get historical trades
        trades = self.session.execute(
            select(PortfolioTrade)
            .where(PortfolioTrade.portfolio_id == portfolio.id)
            .order_by(PortfolioTrade.executed_at.desc())
        ).all()
        
        # Calculate returns, volatility, etc.
        # This is a simplified implementation
        current_value = await self._calculate_portfolio_value(portfolio)
        initial_value = portfolio.initial_capital
        
        total_return = ((current_value - initial_value) / initial_value) * 100
        
        return {
            "total_return": total_return,
            "current_value": current_value,
            "initial_value": initial_value,
            "total_trades": len(trades),
            "last_updated": datetime.utcnow().isoformat()
        }


class ValidationResult:
    """Validation result for trade requests"""
    
    def __init__(self, is_valid: bool, error_message: str = ""):
        self.is_valid = is_valid
        self.error_message = error_message
