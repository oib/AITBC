#!/usr/bin/env python3
"""
AI Trading Engine - Advanced Machine Learning Trading System
Implements AI-powered trading algorithms, predictive analytics, and portfolio optimization
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd

from aitbc import get_logger

logger = get_logger(__name__)


class TradingStrategy(StrEnum):
    """AI trading strategies"""

    MEAN_REVERSION = "mean_reversion"
    MOMENTUM = "momentum"
    ARBITRAGE = "arbitrage"
    MARKET_MAKING = "market_making"
    SENTIMENT_BASED = "sentiment_based"
    TREND_FOLLOWING = "trend_following"
    STATISTICAL_ARBITRAGE = "statistical_arbitrage"


class SignalType(StrEnum):
    """Trading signal types"""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    CLOSE = "close"


class RiskLevel(StrEnum):
    """Risk levels for trading"""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"
    SPECULATIVE = "speculative"


@dataclass
class TradingSignal:
    """AI-generated trading signal"""

    signal_id: str
    timestamp: datetime
    strategy: TradingStrategy
    symbol: str
    signal_type: SignalType
    confidence: float  # 0.0 to 1.0
    predicted_return: float
    risk_score: float
    time_horizon: str  # short, medium, long
    reasoning: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Portfolio:
    """AI-managed portfolio"""

    portfolio_id: str
    assets: dict[str, float]  # symbol -> quantity
    cash_balance: float
    total_value: float
    last_updated: datetime
    risk_level: RiskLevel
    performance_metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class BacktestResult:
    """Backtesting results"""

    strategy: TradingStrategy
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    profitable_trades: int
    trades: list[dict[str, Any]] = field(default_factory=dict)


class AITradingStrategy(ABC):
    """Abstract base class for AI trading strategies"""

    def __init__(self, name: str, parameters: dict[str, Any]):
        self.name = name
        self.parameters = parameters
        self.is_trained = False
        self.model = None

    @abstractmethod
    async def train(self, data: pd.DataFrame) -> bool:
        """Train the AI model with historical data"""
        pass

    @abstractmethod
    async def generate_signal(self, current_data: pd.DataFrame, market_data: dict[str, Any]) -> TradingSignal:
        """Generate trading signal based on current data"""
        pass

    @abstractmethod
    async def update_model(self, new_data: pd.DataFrame) -> bool:
        """Update model with new data"""
        pass


class MeanReversionStrategy(AITradingStrategy):
    """Mean reversion trading strategy using statistical analysis"""

    def __init__(self, parameters: dict[str, Any] = None):
        default_params = {
            "lookback_period": 20,
            "entry_threshold": 2.0,  # Standard deviations
            "exit_threshold": 0.5,
            "risk_level": "moderate",
        }
        if parameters:
            default_params.update(parameters)
        super().__init__("Mean Reversion", default_params)

    async def train(self, data: pd.DataFrame) -> bool:
        """Train mean reversion model"""
        try:
            # Calculate rolling statistics
            data["rolling_mean"] = data["close"].rolling(window=self.parameters["lookback_period"]).mean()
            data["rolling_std"] = data["close"].rolling(window=self.parameters["lookback_period"]).std()
            data["z_score"] = (data["close"] - data["rolling_mean"]) / data["rolling_std"]

            # Store training statistics
            self.training_stats = {
                "mean_reversion_frequency": len(data[data["z_score"].abs() > self.parameters["entry_threshold"]]) / len(data),
                "avg_reversion_time": 5,  # Mock calculation
                "volatility": data["close"].pct_change().std(),
            }

            self.is_trained = True
            logger.info(f"✅ Mean reversion strategy trained on {len(data)} data points")
            return True

        except Exception as e:
            logger.error(f"❌ Mean reversion training failed: {e}")
            return False

    async def generate_signal(self, current_data: pd.DataFrame, market_data: dict[str, Any]) -> TradingSignal:
        """Generate mean reversion trading signal"""
        if not self.is_trained:
            raise ValueError("Strategy not trained")

        try:
            # Calculate current z-score
            latest_data = current_data.iloc[-1]
            current_price = latest_data["close"]
            rolling_mean = latest_data["rolling_mean"]
            rolling_std = latest_data["rolling_std"]
            z_score = (current_price - rolling_mean) / rolling_std

            # Generate signal based on z-score
            if z_score < -self.parameters["entry_threshold"]:
                signal_type = SignalType.BUY
                confidence = min(0.9, abs(z_score) / 3.0)
                predicted_return = abs(z_score) * 0.02  # Predict 2% per std dev
                reasoning = f"Price is {z_score:.2f} std below mean - oversold condition"
            elif z_score > self.parameters["entry_threshold"]:
                signal_type = SignalType.SELL
                confidence = min(0.9, abs(z_score) / 3.0)
                predicted_return = -abs(z_score) * 0.02
                reasoning = f"Price is {z_score:.2f} std above mean - overbought condition"
            else:
                signal_type = SignalType.HOLD
                confidence = 0.5
                predicted_return = 0.0
                reasoning = f"Price is {z_score:.2f} std from mean - no clear signal"

            # Calculate risk score
            risk_score = abs(z_score) / 4.0  # Normalize to 0-1

            return TradingSignal(
                signal_id=f"mean_rev_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                timestamp=datetime.now(),
                strategy=TradingStrategy.MEAN_REVERSION,
                symbol=market_data.get("symbol", "UNKNOWN"),
                signal_type=signal_type,
                confidence=confidence,
                predicted_return=predicted_return,
                risk_score=min(1.0, risk_score),
                time_horizon="short",
                reasoning=reasoning,
                metadata={
                    "z_score": z_score,
                    "current_price": current_price,
                    "rolling_mean": rolling_mean,
                    "entry_threshold": self.parameters["entry_threshold"],
                },
            )

        except Exception as e:
            logger.error(f"❌ Signal generation failed: {e}")
            raise

    async def update_model(self, new_data: pd.DataFrame) -> bool:
        """Update model with new data"""
        return await self.train(new_data)


class MomentumStrategy(AITradingStrategy):
    """Momentum trading strategy using trend analysis"""

    def __init__(self, parameters: dict[str, Any] = None):
        default_params = {"momentum_period": 10, "signal_threshold": 0.02, "risk_level": "moderate"}  # 2% momentum threshold
        if parameters:
            default_params.update(parameters)
        super().__init__("Momentum", default_params)

    async def train(self, data: pd.DataFrame) -> bool:
        """Train momentum model"""
        try:
            # Calculate momentum indicators
            data["returns"] = data["close"].pct_change()
            data["momentum"] = data["close"].pct_change(self.parameters["momentum_period"])
            data["volatility"] = data["returns"].rolling(window=20).std()

            # Store training statistics
            self.training_stats = {
                "avg_momentum": data["momentum"].mean(),
                "momentum_volatility": data["momentum"].std(),
                "trend_persistence": len(data[data["momentum"] > 0]) / len(data),
            }

            self.is_trained = True
            logger.info(f"✅ Momentum strategy trained on {len(data)} data points")
            return True

        except Exception as e:
            logger.error(f"❌ Momentum training failed: {e}")
            return False

    async def generate_signal(self, current_data: pd.DataFrame, market_data: dict[str, Any]) -> TradingSignal:
        """Generate momentum trading signal"""
        if not self.is_trained:
            raise ValueError("Strategy not trained")

        try:
            latest_data = current_data.iloc[-1]
            momentum = latest_data["momentum"]
            volatility = latest_data["volatility"]

            # Generate signal based on momentum
            if momentum > self.parameters["signal_threshold"]:
                signal_type = SignalType.BUY
                confidence = min(0.9, momentum / 0.05)
                predicted_return = momentum * 0.8  # Conservative estimate
                reasoning = f"Strong positive momentum: {momentum:.3f}"
            elif momentum < -self.parameters["signal_threshold"]:
                signal_type = SignalType.SELL
                confidence = min(0.9, abs(momentum) / 0.05)
                predicted_return = momentum * 0.8
                reasoning = f"Strong negative momentum: {momentum:.3f}"
            else:
                signal_type = SignalType.HOLD
                confidence = 0.5
                predicted_return = 0.0
                reasoning = f"Weak momentum: {momentum:.3f}"

            # Calculate risk score based on volatility
            risk_score = min(1.0, volatility / 0.05)  # Normalize volatility

            return TradingSignal(
                signal_id=f"momentum_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                timestamp=datetime.now(),
                strategy=TradingStrategy.MOMENTUM,
                symbol=market_data.get("symbol", "UNKNOWN"),
                signal_type=signal_type,
                confidence=confidence,
                predicted_return=predicted_return,
                risk_score=risk_score,
                time_horizon="medium",
                reasoning=reasoning,
                metadata={
                    "momentum": momentum,
                    "volatility": volatility,
                    "signal_threshold": self.parameters["signal_threshold"],
                },
            )

        except Exception as e:
            logger.error(f"❌ Signal generation failed: {e}")
            raise

    async def update_model(self, new_data: pd.DataFrame) -> bool:
        """Update model with new data"""
        return await self.train(new_data)


class AITradingEngine:
    """Main AI trading engine orchestrator"""

    def __init__(self):
        self.strategies: dict[TradingStrategy, AITradingStrategy] = {}
        self.active_signals: list[TradingSignal] = []
        self.portfolios: dict[str, Portfolio] = {}
        self.market_data: dict[str, pd.DataFrame] = {}
        self.is_running = False
        self.performance_metrics: dict[str, float] = {}

    def add_strategy(self, strategy: AITradingStrategy):
        """Add a trading strategy to the engine"""
        self.strategies[TradingStrategy(strategy.name.lower().replace(" ", "_"))] = strategy
        logger.info(f"✅ Added strategy: {strategy.name}")

    async def train_all_strategies(self, symbol: str, historical_data: pd.DataFrame) -> bool:
        """Train all strategies with historical data"""
        try:
            logger.info(f"🧠 Training {len(self.strategies)} strategies for {symbol}")

            # Store market data
            self.market_data[symbol] = historical_data

            # Train each strategy
            training_results = {}
            for strategy_name, strategy in self.strategies.items():
                try:
                    success = await strategy.train(historical_data)
                    training_results[strategy_name] = success
                    if success:
                        logger.info(f"✅ {strategy_name} trained successfully")
                    else:
                        logger.warning(f"⚠️  {strategy_name} training failed")
                except Exception as e:
                    logger.error(f"❌ {strategy_name} training error: {e}")
                    training_results[strategy_name] = False

            # Calculate overall success rate
            success_rate = sum(training_results.values()) / len(training_results)
            logger.info(f"📊 Training success rate: {success_rate:.1%}")

            return success_rate > 0.5

        except Exception as e:
            logger.error(f"❌ Strategy training failed: {e}")
            return False

    async def generate_signals(self, symbol: str, current_data: pd.DataFrame) -> list[TradingSignal]:
        """Generate trading signals from all strategies"""
        try:
            signals = []
            market_data = {"symbol": symbol, "timestamp": datetime.now()}

            for strategy_name, strategy in self.strategies.items():
                if strategy.is_trained:
                    try:
                        signal = await strategy.generate_signal(current_data, market_data)
                        signals.append(signal)
                        logger.info(
                            f"📈 {strategy_name} signal: {signal.signal_type.value} (confidence: {signal.confidence:.2f})"
                        )
                    except Exception as e:
                        logger.error(f"❌ {strategy_name} signal generation failed: {e}")

            # Store signals
            self.active_signals.extend(signals)

            # Keep only last 1000 signals
            if len(self.active_signals) > 1000:
                self.active_signals = self.active_signals[-1000:]

            return signals

        except Exception as e:
            logger.error(f"❌ Signal generation failed: {e}")
            return []

    async def backtest_strategy(
        self, strategy_name: str, symbol: str, start_date: datetime, end_date: datetime, initial_capital: float = 10000
    ) -> BacktestResult:
        """Backtest a trading strategy"""
        try:
            strategy = self.strategies.get(TradingStrategy(strategy_name))
            if not strategy:
                raise ValueError(f"Strategy {strategy_name} not found")

            # Get historical data for the period
            data = self.market_data.get(symbol)
            if data is None:
                raise ValueError(f"No data available for {symbol}")

            # Filter data for backtesting period
            mask = (data.index >= start_date) & (data.index <= end_date)
            backtest_data = data[mask]

            if len(backtest_data) < 50:
                raise ValueError("Insufficient data for backtesting")

            # Simulate trading
            capital = initial_capital
            position = 0
            trades = []

            for i in range(len(backtest_data) - 1):
                current_slice = backtest_data.iloc[: i + 1]
                market_data = {"symbol": symbol, "timestamp": current_slice.index[-1]}

                try:
                    signal = await strategy.generate_signal(current_slice, market_data)

                    if signal.signal_type == SignalType.BUY and position == 0:
                        # Buy
                        position = capital / current_slice.iloc[-1]["close"]
                        capital = 0
                        trades.append(
                            {
                                "type": "buy",
                                "timestamp": signal.timestamp,
                                "price": current_slice.iloc[-1]["close"],
                                "quantity": position,
                                "signal_confidence": signal.confidence,
                            }
                        )
                    elif signal.signal_type == SignalType.SELL and position > 0:
                        # Sell
                        capital = position * current_slice.iloc[-1]["close"]
                        trades.append(
                            {
                                "type": "sell",
                                "timestamp": signal.timestamp,
                                "price": current_slice.iloc[-1]["close"],
                                "quantity": position,
                                "signal_confidence": signal.confidence,
                            }
                        )
                        position = 0

                except Exception as e:
                    logger.warning(f"⚠️  Signal generation error at {i}: {e}")
                    continue

            # Final portfolio value
            final_value = capital + (position * backtest_data.iloc[-1]["close"] if position > 0 else 0)

            # Calculate metrics
            total_return = (final_value - initial_capital) / initial_capital

            # Calculate daily returns for Sharpe ratio
            daily_returns = backtest_data["close"].pct_change().dropna()
            sharpe_ratio = daily_returns.mean() / daily_returns.std() * np.sqrt(252) if daily_returns.std() > 0 else 0

            # Calculate max drawdown
            portfolio_values = []
            running_capital = initial_capital
            running_position = 0

            for trade in trades:
                if trade["type"] == "buy":
                    running_position = running_capital / trade["price"]
                    running_capital = 0
                else:
                    running_capital = running_position * trade["price"]
                    running_position = 0

                portfolio_values.append(running_capital + (running_position * trade["price"]))

            if portfolio_values:
                peak = np.maximum.accumulate(portfolio_values)
                drawdown = (peak - portfolio_values) / peak
                max_drawdown = np.max(drawdown)
            else:
                max_drawdown = 0

            # Calculate win rate
            profitable_trades = 0
            for i in range(0, len(trades) - 1, 2):
                if i + 1 < len(trades):
                    buy_price = trades[i]["price"]
                    sell_price = trades[i + 1]["price"]
                    if sell_price > buy_price:
                        profitable_trades += 1

            win_rate = profitable_trades / (len(trades) // 2) if len(trades) > 1 else 0

            result = BacktestResult(
                strategy=TradingStrategy(strategy_name),
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                final_capital=final_value,
                total_return=total_return,
                sharpe_ratio=sharpe_ratio,
                max_drawdown=max_drawdown,
                win_rate=win_rate,
                total_trades=len(trades),
                profitable_trades=profitable_trades,
                trades=trades,
            )

            logger.info(f"✅ Backtest completed for {strategy_name}")
            logger.info(f"   Total Return: {total_return:.2%}")
            logger.info(f"   Sharpe Ratio: {sharpe_ratio:.2f}")
            logger.info(f"   Max Drawdown: {max_drawdown:.2%}")
            logger.info(f"   Win Rate: {win_rate:.2%}")
            logger.info(f"   Total Trades: {len(trades)}")

            return result

        except Exception as e:
            logger.error(f"❌ Backtesting failed: {e}")
            raise

    def get_active_signals(
        self, symbol: str | None = None, strategy: TradingStrategy | None = None
    ) -> list[TradingSignal]:
        """Get active trading signals"""
        signals = self.active_signals

        if symbol:
            signals = [s for s in signals if s.symbol == symbol]

        if strategy:
            signals = [s for s in signals if s.strategy == strategy]

        return sorted(signals, key=lambda x: x.timestamp, reverse=True)

    def get_performance_metrics(self) -> dict[str, float]:
        """Get overall performance metrics"""
        if not self.active_signals:
            return {}

        # Calculate metrics from recent signals
        recent_signals = self.active_signals[-100:]  # Last 100 signals

        return {
            "total_signals": len(self.active_signals),
            "recent_signals": len(recent_signals),
            "avg_confidence": np.mean([s.confidence for s in recent_signals]),
            "avg_risk_score": np.mean([s.risk_score for s in recent_signals]),
            "buy_signals": len([s for s in recent_signals if s.signal_type == SignalType.BUY]),
            "sell_signals": len([s for s in recent_signals if s.signal_type == SignalType.SELL]),
            "hold_signals": len([s for s in recent_signals if s.signal_type == SignalType.HOLD]),
        }


# Global instance
ai_trading_engine = AITradingEngine()


# CLI Interface Functions
async def initialize_ai_engine():
    """Initialize AI trading engine with default strategies"""
    # Add default strategies
    ai_trading_engine.add_strategy(MeanReversionStrategy())
    ai_trading_engine.add_strategy(MomentumStrategy())

    logger.info("🤖 AI Trading Engine initialized with 2 strategies")
    return True


async def train_strategies(symbol: str, days: int = 90) -> bool:
    """Train AI strategies with historical data"""
    # Generate mock historical data
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    # Create mock price data
    dates = pd.date_range(start=start_date, end=end_date, freq="1h")
    prices = [50000 + np.cumsum(np.random.normal(0, 100, len(dates)))[-1] for _ in range(len(dates))]

    # Create DataFrame
    data = pd.DataFrame({"timestamp": dates, "close": prices, "volume": np.random.randint(1000, 10000, len(dates))})
    data.set_index("timestamp", inplace=True)

    return await ai_trading_engine.train_all_strategies(symbol, data)


async def generate_trading_signals(symbol: str) -> list[dict[str, Any]]:
    """Generate trading signals for symbol"""
    # Get current market data (mock)
    current_data = ai_trading_engine.market_data.get(symbol)
    if current_data is None:
        raise ValueError(f"No data available for {symbol}")

    # Get last 50 data points
    recent_data = current_data.tail(50)

    signals = await ai_trading_engine.generate_signals(symbol, recent_data)

    return [
        {
            "signal_id": signal.signal_id,
            "strategy": signal.strategy.value,
            "symbol": signal.symbol,
            "signal_type": signal.signal_type.value,
            "confidence": signal.confidence,
            "predicted_return": signal.predicted_return,
            "risk_score": signal.risk_score,
            "reasoning": signal.reasoning,
            "timestamp": signal.timestamp.isoformat(),
        }
        for signal in signals
    ]


def get_engine_status() -> dict[str, Any]:
    """Get AI trading engine status"""
    return {
        "strategies_count": len(ai_trading_engine.strategies),
        "trained_strategies": len([s for s in ai_trading_engine.strategies.values() if s.is_trained]),
        "active_signals": len(ai_trading_engine.active_signals),
        "market_data_symbols": list(ai_trading_engine.market_data.keys()),
        "performance_metrics": ai_trading_engine.get_performance_metrics(),
    }


# Test function
async def test_ai_trading_engine():
    """Test AI trading engine"""
    print("🤖 Testing AI Trading Engine...")

    # Initialize engine
    await initialize_ai_engine()

    # Train strategies
    success = await train_strategies("BTC/USDT", 30)
    print(f"✅ Training successful: {success}")

    # Generate signals
    signals = await generate_trading_signals("BTC/USDT")
    print(f"📈 Generated {len(signals)} signals")

    for signal in signals:
        print(f"   {signal['strategy']}: {signal['signal_type']} (confidence: {signal['confidence']:.2f})")

    # Get status
    status = get_engine_status()
    print(f"📊 Engine Status: {status}")

    print("🎉 AI Trading Engine test complete!")


if __name__ == "__main__":
    asyncio.run(test_ai_trading_engine())
