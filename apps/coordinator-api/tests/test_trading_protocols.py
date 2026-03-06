"""
Trading Protocols Test Suite

Comprehensive tests for agent portfolio management, AMM, and cross-chain bridge services.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from sqlmodel import Session, create_engine, SQLModel
from sqlmodel.pool import StaticPool

from ..services.agent_portfolio_manager import AgentPortfolioManager
from ..services.amm_service import AMMService
from ..services.cross_chain_bridge import CrossChainBridgeService
from ..domain.agent_portfolio import (
    AgentPortfolio, PortfolioStrategy, StrategyType, TradeStatus
)
from ..domain.amm import (
    LiquidityPool, SwapTransaction, PoolStatus, SwapStatus
)
from ..domain.cross_chain_bridge import (
    BridgeRequest, BridgeRequestStatus, ChainType
)
from ..schemas.portfolio import PortfolioCreate, TradeRequest
from ..schemas.amm import PoolCreate, SwapRequest
from ..schemas.cross_chain_bridge import BridgeCreateRequest


@pytest.fixture
def test_db():
    """Create test database"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture
def mock_contract_service():
    """Mock contract service"""
    service = AsyncMock()
    service.create_portfolio.return_value = "12345"
    service.execute_portfolio_trade.return_value = MagicMock(
        buy_amount=100.0,
        price=1.0,
        transaction_hash="0x123"
    )
    service.create_amm_pool.return_value = 67890
    service.add_liquidity.return_value = MagicMock(
        liquidity_received=1000.0
    )
    service.execute_swap.return_value = MagicMock(
        amount_out=95.0,
        price=1.05,
        fee_amount=0.5,
        transaction_hash="0x456"
    )
    service.initiate_bridge.return_value = 11111
    service.get_bridge_status.return_value = MagicMock(
        status="pending"
    )
    return service


@pytest.fixture
def mock_price_service():
    """Mock price service"""
    service = AsyncMock()
    service.get_price.side_effect = lambda token: {
        "AITBC": 1.0,
        "USDC": 1.0,
        "ETH": 2000.0,
        "WBTC": 50000.0
    }.get(token, 1.0)
    service.get_market_conditions.return_value = MagicMock(
        volatility=0.15,
        trend="bullish"
    )
    return service


@pytest.fixture
def mock_risk_calculator():
    """Mock risk calculator"""
    calculator = AsyncMock()
    calculator.calculate_portfolio_risk.return_value = MagicMock(
        volatility=0.12,
        max_drawdown=0.08,
        sharpe_ratio=1.5,
        var_95=0.05,
        overall_risk_score=35.0,
        risk_level="medium"
    )
    calculator.calculate_trade_risk.return_value = 25.0
    return calculator


@pytest.fixture
def mock_strategy_optimizer():
    """Mock strategy optimizer"""
    optimizer = AsyncMock()
    optimizer.calculate_optimal_allocations.return_value = {
        "AITBC": 40.0,
        "USDC": 30.0,
        "ETH": 20.0,
        "WBTC": 10.0
    }
    return optimizer


@pytest.fixture
def mock_volatility_calculator():
    """Mock volatility calculator"""
    calculator = AsyncMock()
    calculator.calculate_volatility.return_value = 0.15
    return calculator


@pytest.fixture
def mock_zk_proof_service():
    """Mock ZK proof service"""
    service = AsyncMock()
    service.generate_proof.return_value = MagicMock(
        proof="zk_proof_123"
    )
    return service


@pytest.fixture
def mock_merkle_tree_service():
    """Mock Merkle tree service"""
    service = AsyncMock()
    service.generate_proof.return_value = MagicMock(
        proof_hash="merkle_hash_456"
    )
    service.verify_proof.return_value = True
    return service


@pytest.fixture
def mock_bridge_monitor():
    """Mock bridge monitor"""
    monitor = AsyncMock()
    monitor.start_monitoring.return_value = None
    monitor.stop_monitoring.return_value = None
    return monitor


@pytest.fixture
def agent_portfolio_manager(
    test_db, mock_contract_service, mock_price_service,
    mock_risk_calculator, mock_strategy_optimizer
):
    """Create agent portfolio manager instance"""
    return AgentPortfolioManager(
        session=test_db,
        contract_service=mock_contract_service,
        price_service=mock_price_service,
        risk_calculator=mock_risk_calculator,
        strategy_optimizer=mock_strategy_optimizer
    )


@pytest.fixture
def amm_service(
    test_db, mock_contract_service, mock_price_service,
    mock_volatility_calculator
):
    """Create AMM service instance"""
    return AMMService(
        session=test_db,
        contract_service=mock_contract_service,
        price_service=mock_price_service,
        volatility_calculator=mock_volatility_calculator
    )


@pytest.fixture
def cross_chain_bridge_service(
    test_db, mock_contract_service, mock_zk_proof_service,
    mock_merkle_tree_service, mock_bridge_monitor
):
    """Create cross-chain bridge service instance"""
    return CrossChainBridgeService(
        session=test_db,
        contract_service=mock_contract_service,
        zk_proof_service=mock_zk_proof_service,
        merkle_tree_service=mock_merkle_tree_service,
        bridge_monitor=mock_bridge_monitor
    )


@pytest.fixture
def sample_strategy(test_db):
    """Create sample portfolio strategy"""
    strategy = PortfolioStrategy(
        name="Balanced Strategy",
        strategy_type=StrategyType.BALANCED,
        target_allocations={
            "AITBC": 40.0,
            "USDC": 30.0,
            "ETH": 20.0,
            "WBTC": 10.0
        },
        max_drawdown=15.0,
        rebalance_frequency=86400,
        is_active=True
    )
    test_db.add(strategy)
    test_db.commit()
    test_db.refresh(strategy)
    return strategy


class TestAgentPortfolioManager:
    """Test cases for Agent Portfolio Manager"""
    
    def test_create_portfolio_success(
        self, agent_portfolio_manager, test_db, sample_strategy
    ):
        """Test successful portfolio creation"""
        portfolio_data = PortfolioCreate(
            strategy_id=sample_strategy.id,
            initial_capital=10000.0,
            risk_tolerance=50.0
        )
        agent_address = "0x1234567890123456789012345678901234567890"
        
        result = agent_portfolio_manager.create_portfolio(portfolio_data, agent_address)
        
        assert result.strategy_id == sample_strategy.id
        assert result.initial_capital == 10000.0
        assert result.risk_tolerance == 50.0
        assert result.is_active is True
        assert result.agent_address == agent_address
    
    def test_create_portfolio_invalid_address(self, agent_portfolio_manager, sample_strategy):
        """Test portfolio creation with invalid address"""
        portfolio_data = PortfolioCreate(
            strategy_id=sample_strategy.id,
            initial_capital=10000.0,
            risk_tolerance=50.0
        )
        invalid_address = "invalid_address"
        
        with pytest.raises(Exception) as exc_info:
            agent_portfolio_manager.create_portfolio(portfolio_data, invalid_address)
        
        assert "Invalid agent address" in str(exc_info.value)
    
    def test_create_portfolio_already_exists(
        self, agent_portfolio_manager, test_db, sample_strategy
    ):
        """Test portfolio creation when portfolio already exists"""
        portfolio_data = PortfolioCreate(
            strategy_id=sample_strategy.id,
            initial_capital=10000.0,
            risk_tolerance=50.0
        )
        agent_address = "0x1234567890123456789012345678901234567890"
        
        # Create first portfolio
        agent_portfolio_manager.create_portfolio(portfolio_data, agent_address)
        
        # Try to create second portfolio
        with pytest.raises(Exception) as exc_info:
            agent_portfolio_manager.create_portfolio(portfolio_data, agent_address)
        
        assert "Portfolio already exists" in str(exc_info.value)
    
    def test_execute_trade_success(self, agent_portfolio_manager, test_db, sample_strategy):
        """Test successful trade execution"""
        # Create portfolio first
        portfolio_data = PortfolioCreate(
            strategy_id=sample_strategy.id,
            initial_capital=10000.0,
            risk_tolerance=50.0
        )
        agent_address = "0x1234567890123456789012345678901234567890"
        portfolio = agent_portfolio_manager.create_portfolio(portfolio_data, agent_address)
        
        # Add some assets to portfolio
        from ..domain.agent_portfolio import PortfolioAsset
        asset = PortfolioAsset(
            portfolio_id=portfolio.id,
            token_symbol="AITBC",
            token_address="0xaitbc",
            balance=1000.0,
            target_allocation=40.0,
            current_allocation=40.0
        )
        test_db.add(asset)
        test_db.commit()
        
        # Execute trade
        trade_request = TradeRequest(
            sell_token="AITBC",
            buy_token="USDC",
            sell_amount=100.0,
            min_buy_amount=95.0
        )
        
        result = agent_portfolio_manager.execute_trade(trade_request, agent_address)
        
        assert result.sell_token == "AITBC"
        assert result.buy_token == "USDC"
        assert result.sell_amount == 100.0
        assert result.status == TradeStatus.EXECUTED
    
    def test_risk_assessment(self, agent_portfolio_manager, test_db, sample_strategy):
        """Test risk assessment"""
        # Create portfolio first
        portfolio_data = PortfolioCreate(
            strategy_id=sample_strategy.id,
            initial_capital=10000.0,
            risk_tolerance=50.0
        )
        agent_address = "0x1234567890123456789012345678901234567890"
        portfolio = agent_portfolio_manager.create_portfolio(portfolio_data, agent_address)
        
        # Perform risk assessment
        result = agent_portfolio_manager.risk_assessment(agent_address)
        
        assert result.volatility == 0.12
        assert result.max_drawdown == 0.08
        assert result.sharpe_ratio == 1.5
        assert result.var_95 == 0.05
        assert result.overall_risk_score == 35.0


class TestAMMService:
    """Test cases for AMM Service"""
    
    def test_create_pool_success(self, amm_service):
        """Test successful pool creation"""
        pool_data = PoolCreate(
            token_a="0xaitbc",
            token_b="0xusdc",
            fee_percentage=0.3
        )
        creator_address = "0x1234567890123456789012345678901234567890"
        
        result = amm_service.create_service_pool(pool_data, creator_address)
        
        assert result.token_a == "0xaitbc"
        assert result.token_b == "0xusdc"
        assert result.fee_percentage == 0.3
        assert result.is_active is True
    
    def test_create_pool_same_tokens(self, amm_service):
        """Test pool creation with same tokens"""
        pool_data = PoolCreate(
            token_a="0xaitbc",
            token_b="0xaitbc",
            fee_percentage=0.3
        )
        creator_address = "0x1234567890123456789012345678901234567890"
        
        with pytest.raises(Exception) as exc_info:
            amm_service.create_service_pool(pool_data, creator_address)
        
        assert "Token addresses must be different" in str(exc_info.value)
    
    def test_add_liquidity_success(self, amm_service):
        """Test successful liquidity addition"""
        # Create pool first
        pool_data = PoolCreate(
            token_a="0xaitbc",
            token_b="0xusdc",
            fee_percentage=0.3
        )
        creator_address = "0x1234567890123456789012345678901234567890"
        pool = amm_service.create_service_pool(pool_data, creator_address)
        
        # Add liquidity
        from ..schemas.amm import LiquidityAddRequest
        liquidity_request = LiquidityAddRequest(
            pool_id=pool.id,
            amount_a=1000.0,
            amount_b=1000.0,
            min_amount_a=950.0,
            min_amount_b=950.0
        )
        
        result = amm_service.add_liquidity(liquidity_request, creator_address)
        
        assert result.pool_id == pool.id
        assert result.liquidity_amount > 0
    
    def test_execute_swap_success(self, amm_service):
        """Test successful swap execution"""
        # Create pool first
        pool_data = PoolCreate(
            token_a="0xaitbc",
            token_b="0xusdc",
            fee_percentage=0.3
        )
        creator_address = "0x1234567890123456789012345678901234567890"
        pool = amm_service.create_service_pool(pool_data, creator_address)
        
        # Add liquidity first
        from ..schemas.amm import LiquidityAddRequest
        liquidity_request = LiquidityAddRequest(
            pool_id=pool.id,
            amount_a=10000.0,
            amount_b=10000.0,
            min_amount_a=9500.0,
            min_amount_b=9500.0
        )
        amm_service.add_liquidity(liquidity_request, creator_address)
        
        # Execute swap
        swap_request = SwapRequest(
            pool_id=pool.id,
            token_in="0xaitbc",
            token_out="0xusdc",
            amount_in=100.0,
            min_amount_out=95.0,
            deadline=datetime.utcnow() + timedelta(minutes=20)
        )
        
        result = amm_service.execute_swap(swap_request, creator_address)
        
        assert result.token_in == "0xaitbc"
        assert result.token_out == "0xusdc"
        assert result.amount_in == 100.0
        assert result.status == SwapStatus.EXECUTED
    
    def test_dynamic_fee_adjustment(self, amm_service):
        """Test dynamic fee adjustment"""
        # Create pool first
        pool_data = PoolCreate(
            token_a="0xaitbc",
            token_b="0xusdc",
            fee_percentage=0.3
        )
        creator_address = "0x1234567890123456789012345678901234567890"
        pool = amm_service.create_service_pool(pool_data, creator_address)
        
        # Adjust fee based on volatility
        volatility = 0.25  # High volatility
        result = amm_service.dynamic_fee_adjustment(pool.id, volatility)
        
        assert result.pool_id == pool.id
        assert result.current_fee_percentage > result.base_fee_percentage


class TestCrossChainBridgeService:
    """Test cases for Cross-Chain Bridge Service"""
    
    def test_initiate_transfer_success(self, cross_chain_bridge_service):
        """Test successful bridge transfer initiation"""
        transfer_request = BridgeCreateRequest(
            source_token="0xaitbc",
            target_token="0xaitbc_polygon",
            amount=1000.0,
            source_chain_id=1,  # Ethereum
            target_chain_id=137,  # Polygon
            recipient_address="0x9876543210987654321098765432109876543210"
        )
        sender_address = "0x1234567890123456789012345678901234567890"
        
        result = cross_chain_bridge_service.initiate_transfer(transfer_request, sender_address)
        
        assert result.sender_address == sender_address
        assert result.amount == 1000.0
        assert result.source_chain_id == 1
        assert result.target_chain_id == 137
        assert result.status == BridgeRequestStatus.PENDING
    
    def test_initiate_transfer_invalid_amount(self, cross_chain_bridge_service):
        """Test bridge transfer with invalid amount"""
        transfer_request = BridgeCreateRequest(
            source_token="0xaitbc",
            target_token="0xaitbc_polygon",
            amount=0.0,  # Invalid amount
            source_chain_id=1,
            target_chain_id=137,
            recipient_address="0x9876543210987654321098765432109876543210"
        )
        sender_address = "0x1234567890123456789012345678901234567890"
        
        with pytest.raises(Exception) as exc_info:
            cross_chain_bridge_service.initiate_transfer(transfer_request, sender_address)
        
        assert "Amount must be greater than 0" in str(exc_info.value)
    
    def test_monitor_bridge_status(self, cross_chain_bridge_service):
        """Test bridge status monitoring"""
        # Initiate transfer first
        transfer_request = BridgeCreateRequest(
            source_token="0xaitbc",
            target_token="0xaitbc_polygon",
            amount=1000.0,
            source_chain_id=1,
            target_chain_id=137,
            recipient_address="0x9876543210987654321098765432109876543210"
        )
        sender_address = "0x1234567890123456789012345678901234567890"
        bridge = cross_chain_bridge_service.initiate_transfer(transfer_request, sender_address)
        
        # Monitor status
        result = cross_chain_bridge_service.monitor_bridge_status(bridge.id)
        
        assert result.request_id == bridge.id
        assert result.status == BridgeRequestStatus.PENDING
        assert result.source_chain_id == 1
        assert result.target_chain_id == 137


class TestIntegration:
    """Integration tests for trading protocols"""
    
    def test_portfolio_to_amm_integration(
        self, agent_portfolio_manager, amm_service, test_db, sample_strategy
    ):
        """Test integration between portfolio management and AMM"""
        # Create portfolio
        portfolio_data = PortfolioCreate(
            strategy_id=sample_strategy.id,
            initial_capital=10000.0,
            risk_tolerance=50.0
        )
        agent_address = "0x1234567890123456789012345678901234567890"
        portfolio = agent_portfolio_manager.create_portfolio(portfolio_data, agent_address)
        
        # Create AMM pool
        from ..schemas.amm import PoolCreate
        pool_data = PoolCreate(
            token_a="0xaitbc",
            token_b="0xusdc",
            fee_percentage=0.3
        )
        pool = amm_service.create_service_pool(pool_data, agent_address)
        
        # Add liquidity to pool
        from ..schemas.amm import LiquidityAddRequest
        liquidity_request = LiquidityAddRequest(
            pool_id=pool.id,
            amount_a=5000.0,
            amount_b=5000.0,
            min_amount_a=4750.0,
            min_amount_b=4750.0
        )
        amm_service.add_liquidity(liquidity_request, agent_address)
        
        # Execute trade through portfolio
        from ..schemas.portfolio import TradeRequest
        trade_request = TradeRequest(
            sell_token="AITBC",
            buy_token="USDC",
            sell_amount=100.0,
            min_buy_amount=95.0
        )
        
        result = agent_portfolio_manager.execute_trade(trade_request, agent_address)
        
        assert result.status == TradeStatus.EXECUTED
        assert result.sell_amount == 100.0
    
    def test_bridge_to_portfolio_integration(
        self, agent_portfolio_manager, cross_chain_bridge_service, test_db, sample_strategy
    ):
        """Test integration between bridge and portfolio management"""
        # Create portfolio
        portfolio_data = PortfolioCreate(
            strategy_id=sample_strategy.id,
            initial_capital=10000.0,
            risk_tolerance=50.0
        )
        agent_address = "0x1234567890123456789012345678901234567890"
        portfolio = agent_portfolio_manager.create_portfolio(portfolio_data, agent_address)
        
        # Initiate bridge transfer
        from ..schemas.cross_chain_bridge import BridgeCreateRequest
        transfer_request = BridgeCreateRequest(
            source_token="0xeth",
            target_token="0xeth_polygon",
            amount=2000.0,
            source_chain_id=1,
            target_chain_id=137,
            recipient_address=agent_address
        )
        
        bridge = cross_chain_bridge_service.initiate_transfer(transfer_request, agent_address)
        
        # Monitor bridge status
        status = cross_chain_bridge_service.monitor_bridge_status(bridge.id)
        
        assert status.request_id == bridge.id
        assert status.status == BridgeRequestStatus.PENDING


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
