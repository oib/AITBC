#!/usr/bin/env python3
"""
Advanced Analytics Platform - Comprehensive Trading Analytics
Real-time analytics dashboard, market insights, and performance metrics
"""

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd

from aitbc import get_logger

logger = get_logger(__name__)


class MetricType(StrEnum):
    """Types of analytics metrics"""

    PRICE_METRICS = "price_metrics"
    VOLUME_METRICS = "volume_metrics"
    VOLATILITY_METRICS = "volatility_metrics"
    PERFORMANCE_METRICS = "performance_metrics"
    RISK_METRICS = "risk_metrics"
    MARKET_SENTIMENT = "market_sentiment"
    LIQUIDITY_METRICS = "liquidity_metrics"


class Timeframe(StrEnum):
    """Analytics timeframes"""

    REAL_TIME = "real_time"
    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    ONE_HOUR = "1h"
    FOUR_HOURS = "4h"
    ONE_DAY = "1d"
    ONE_WEEK = "1w"
    ONE_MONTH = "1m"


@dataclass
class MarketMetric:
    """Market metric data point"""

    timestamp: datetime
    symbol: str
    metric_type: MetricType
    value: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalyticsAlert:
    """Analytics alert configuration"""

    alert_id: str
    name: str
    metric_type: MetricType
    symbol: str
    condition: str  # gt, lt, eq, change_percent
    threshold: float
    timeframe: Timeframe
    active: bool = True
    last_triggered: datetime | None = None
    trigger_count: int = 0


@dataclass
class PerformanceReport:
    """Performance analysis report"""

    report_id: str
    symbol: str
    start_date: datetime
    end_date: datetime
    total_return: float
    volatility: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    calmar_ratio: float
    var_95: float  # Value at Risk 95%
    beta: float | None = None
    alpha: float | None = None


class AdvancedAnalytics:
    """Advanced analytics platform for trading insights"""

    def __init__(self):
        self.metrics_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self.alerts: dict[str, AnalyticsAlert] = {}
        self.performance_cache: dict[str, PerformanceReport] = {}
        self.market_data: dict[str, pd.DataFrame] = {}
        self.is_monitoring = False
        self.monitoring_task = None

        # Initialize metrics storage
        self.current_metrics: dict[str, dict[MetricType, float]] = defaultdict(dict)

    async def start_monitoring(self, symbols: list[str]):
        """Start real-time analytics monitoring"""
        if self.is_monitoring:
            logger.warning("⚠️  Analytics monitoring already running")
            return

        self.is_monitoring = True
        self.monitoring_task = asyncio.create_task(self._monitor_loop(symbols))
        logger.info(f"📊 Analytics monitoring started for {len(symbols)} symbols")

    async def stop_monitoring(self):
        """Stop analytics monitoring"""
        self.is_monitoring = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("📊 Analytics monitoring stopped")

    async def _monitor_loop(self, symbols: list[str]):
        """Main monitoring loop"""
        while self.is_monitoring:
            try:
                for symbol in symbols:
                    await self._update_metrics(symbol)

                # Check alerts
                await self._check_alerts()

                await asyncio.sleep(60)  # Update every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Monitoring error: {e}")
                await asyncio.sleep(10)

    async def _update_metrics(self, symbol: str):
        """Update metrics for a symbol"""
        try:
            # Get current market data (mock implementation)
            current_data = await self._get_current_market_data(symbol)

            if not current_data:
                return

            timestamp = datetime.now()

            # Calculate price metrics
            price_metrics = self._calculate_price_metrics(current_data)
            for metric_type, value in price_metrics.items():
                self._store_metric(symbol, metric_type, value, timestamp)

            # Calculate volume metrics
            volume_metrics = self._calculate_volume_metrics(current_data)
            for metric_type, value in volume_metrics.items():
                self._store_metric(symbol, metric_type, value, timestamp)

            # Calculate volatility metrics
            volatility_metrics = self._calculate_volatility_metrics(symbol)
            for metric_type, value in volatility_metrics.items():
                self._store_metric(symbol, metric_type, value, timestamp)

            # Update current metrics
            self.current_metrics[symbol].update(price_metrics)
            self.current_metrics[symbol].update(volume_metrics)
            self.current_metrics[symbol].update(volatility_metrics)

        except Exception as e:
            logger.error(f"❌ Metrics update failed for {symbol}: {e}")

    def _store_metric(self, symbol: str, metric_type: MetricType, value: float, timestamp: datetime):
        """Store a metric value"""
        metric = MarketMetric(timestamp=timestamp, symbol=symbol, metric_type=metric_type, value=value)

        key = f"{symbol}_{metric_type.value}"
        self.metrics_history[key].append(metric)

    def _calculate_price_metrics(self, data: dict[str, Any]) -> dict[MetricType, float]:
        """Calculate price-related metrics"""
        current_price = data.get("price", 0)
        volume = data.get("volume", 0)

        # Get historical data for calculations
        key = f"{data['symbol']}_price_metrics"
        history = list(self.metrics_history.get(key, []))

        if len(history) < 2:
            return {}

        # Extract recent prices
        recent_prices = [m.value for m in history[-20:]] + [current_price]

        # Calculate metrics
        (current_price - recent_prices[0]) / recent_prices[0] if recent_prices[0] > 0 else 0
        self._calculate_change(recent_prices, 60) if len(recent_prices) >= 60 else 0
        self._calculate_change(recent_prices, 1440) if len(recent_prices) >= 1440 else 0

        # Moving averages
        sma_5 = np.mean(recent_prices[-5:]) if len(recent_prices) >= 5 else current_price
        sma_20 = np.mean(recent_prices[-20:]) if len(recent_prices) >= 20 else current_price

        # Price relative to moving averages
        (current_price / sma_5 - 1) if sma_5 > 0 else 0
        (current_price / sma_20 - 1) if sma_20 > 0 else 0

        # RSI calculation
        self._calculate_rsi(recent_prices)

        return {
            MetricType.PRICE_METRICS: current_price,
            MetricType.VOLUME_METRICS: volume,
            MetricType.VOLATILITY_METRICS: np.std(recent_prices) / np.mean(recent_prices) if np.mean(recent_prices) > 0 else 0,
        }

    def _calculate_volume_metrics(self, data: dict[str, Any]) -> dict[MetricType, float]:
        """Calculate volume-related metrics"""
        current_volume = data.get("volume", 0)

        # Get volume history
        key = f"{data['symbol']}_volume_metrics"
        history = list(self.metrics_history.get(key, []))

        if len(history) < 2:
            return {}

        recent_volumes = [m.value for m in history[-20:]] + [current_volume]

        # Volume metrics
        volume_ma = np.mean(recent_volumes)
        volume_ratio = current_volume / volume_ma if volume_ma > 0 else 1

        # Volume change
        (current_volume - recent_volumes[0]) / recent_volumes[0] if recent_volumes[0] > 0 else 0

        return {
            MetricType.VOLUME_METRICS: volume_ratio,
        }

    def _calculate_volatility_metrics(self, symbol: str) -> dict[MetricType, float]:
        """Calculate volatility metrics"""
        # Get price history
        key = f"{symbol}_price_metrics"
        history = list(self.metrics_history.get(key, []))

        if len(history) < 20:
            return {}

        prices = [m.value for m in history[-100:]]  # Last 100 data points

        # Calculate volatility
        returns = np.diff(np.log(prices))
        np.std(returns) * np.sqrt(252) if len(returns) > 0 else 0  # Annualized

        # Realized volatility (last 24 hours)
        recent_returns = returns[-1440:] if len(returns) >= 1440 else returns
        realized_vol = np.std(recent_returns) * np.sqrt(365) if len(recent_returns) > 0 else 0

        return {
            MetricType.VOLATILITY_METRICS: realized_vol,
        }

    def _calculate_change(self, values: list[float], periods: int) -> float:
        """Calculate percentage change over specified periods"""
        if len(values) < periods + 1:
            return 0

        current = values[-1]
        past = values[-(periods + 1)]

        return (current - past) / past if past > 0 else 0

    def _calculate_rsi(self, prices: list[float], period: int = 14) -> float:
        """Calculate RSI indicator"""
        if len(prices) < period + 1:
            return 50  # Neutral

        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    async def _get_current_market_data(self, symbol: str) -> dict[str, Any] | None:
        """Get current market data (mock implementation)"""
        # In production, this would fetch real market data
        import random

        # Generate mock data with some randomness
        base_price = 50000 if symbol == "BTC/USDT" else 3000
        price = base_price * (1 + random.uniform(-0.02, 0.02))
        volume = random.uniform(1000, 10000)

        return {"symbol": symbol, "price": price, "volume": volume, "timestamp": datetime.now()}

    async def _check_alerts(self):
        """Check configured alerts"""
        for alert_id, alert in self.alerts.items():
            if not alert.active:
                continue

            try:
                current_value = self.current_metrics.get(alert.symbol, {}).get(alert.metric_type)
                if current_value is None:
                    continue

                triggered = self._evaluate_alert_condition(alert, current_value)

                if triggered:
                    await self._trigger_alert(alert, current_value)

            except Exception as e:
                logger.error(f"❌ Alert check failed for {alert_id}: {e}")

    def _evaluate_alert_condition(self, alert: AnalyticsAlert, current_value: float) -> bool:
        """Evaluate if alert condition is met"""
        if alert.condition == "gt":
            return current_value > alert.threshold
        elif alert.condition == "lt":
            return current_value < alert.threshold
        elif alert.condition == "eq":
            return abs(current_value - alert.threshold) < 0.001
        elif alert.condition == "change_percent":
            # Calculate percentage change (simplified)
            key = f"{alert.symbol}_{alert.metric_type.value}"
            history = list(self.metrics_history.get(key, []))
            if len(history) >= 2:
                old_value = history[-1].value
                change = (current_value - old_value) / old_value if old_value != 0 else 0
                return abs(change) > alert.threshold

        return False

    async def _trigger_alert(self, alert: AnalyticsAlert, current_value: float):
        """Trigger an alert"""
        alert.last_triggered = datetime.now()
        alert.trigger_count += 1

        logger.warning(f"🚨 Alert triggered: {alert.name}")
        logger.warning(f"   Symbol: {alert.symbol}")
        logger.warning(f"   Metric: {alert.metric_type.value}")
        logger.warning(f"   Current Value: {current_value}")
        logger.warning(f"   Threshold: {alert.threshold}")
        logger.warning(f"   Trigger Count: {alert.trigger_count}")

    def create_alert(
        self, name: str, symbol: str, metric_type: MetricType, condition: str, threshold: float, timeframe: Timeframe
    ) -> str:
        """Create a new analytics alert"""
        alert_id = f"alert_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        alert = AnalyticsAlert(
            alert_id=alert_id,
            name=name,
            metric_type=metric_type,
            symbol=symbol,
            condition=condition,
            threshold=threshold,
            timeframe=timeframe,
        )

        self.alerts[alert_id] = alert
        logger.info(f"✅ Alert created: {name}")

        return alert_id

    def get_real_time_dashboard(self, symbol: str) -> dict[str, Any]:
        """Get real-time dashboard data for a symbol"""
        current_metrics = self.current_metrics.get(symbol, {})

        # Get recent history for charts
        price_history = []
        volume_history = []

        price_key = f"{symbol}_price_metrics"
        volume_key = f"{symbol}_volume_metrics"

        for metric in list(self.metrics_history.get(price_key, []))[-100:]:
            price_history.append({"timestamp": metric.timestamp.isoformat(), "value": metric.value})

        for metric in list(self.metrics_history.get(volume_key, []))[-100:]:
            volume_history.append({"timestamp": metric.timestamp.isoformat(), "value": metric.value})

        # Calculate technical indicators
        indicators = self._calculate_technical_indicators(symbol)

        return {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "current_metrics": current_metrics,
            "price_history": price_history,
            "volume_history": volume_history,
            "technical_indicators": indicators,
            "alerts": [a for a in self.alerts.values() if a.symbol == symbol and a.active],
            "market_status": self._get_market_status(symbol),
        }

    def _calculate_technical_indicators(self, symbol: str) -> dict[str, Any]:
        """Calculate technical indicators"""
        # Get price history
        price_key = f"{symbol}_price_metrics"
        history = list(self.metrics_history.get(price_key, []))

        if len(history) < 20:
            return {}

        prices = [m.value for m in history[-100:]]

        indicators = {}

        # Moving averages
        if len(prices) >= 5:
            indicators["sma_5"] = np.mean(prices[-5:])
        if len(prices) >= 20:
            indicators["sma_20"] = np.mean(prices[-20:])
        if len(prices) >= 50:
            indicators["sma_50"] = np.mean(prices[-50:])

        # RSI
        indicators["rsi"] = self._calculate_rsi(prices)

        # Bollinger Bands
        if len(prices) >= 20:
            sma_20 = indicators["sma_20"]
            std_20 = np.std(prices[-20:])
            indicators["bb_upper"] = sma_20 + (2 * std_20)
            indicators["bb_lower"] = sma_20 - (2 * std_20)
            indicators["bb_width"] = (indicators["bb_upper"] - indicators["bb_lower"]) / sma_20

        # MACD (simplified)
        if len(prices) >= 26:
            ema_12 = self._calculate_ema(prices, 12)
            ema_26 = self._calculate_ema(prices, 26)
            indicators["macd"] = ema_12 - ema_26
            indicators["macd_signal"] = self._calculate_ema([indicators["macd"]], 9)

        return indicators

    def _calculate_ema(self, values: list[float], period: int) -> float:
        """Calculate Exponential Moving Average"""
        if len(values) < period:
            return np.mean(values)

        multiplier = 2 / (period + 1)
        ema = values[0]

        for value in values[1:]:
            ema = (value * multiplier) + (ema * (1 - multiplier))

        return ema

    def _get_market_status(self, symbol: str) -> str:
        """Get overall market status"""
        current_metrics = self.current_metrics.get(symbol, {})

        # Simple market status logic
        rsi = current_metrics.get("rsi", 50)

        if rsi > 70:
            return "overbought"
        elif rsi < 30:
            return "oversold"
        else:
            return "neutral"

    def generate_performance_report(self, symbol: str, start_date: datetime, end_date: datetime) -> PerformanceReport:
        """Generate comprehensive performance report"""
        # Get historical data for the period
        price_key = f"{symbol}_price_metrics"
        history = [m for m in self.metrics_history.get(price_key, []) if start_date <= m.timestamp <= end_date]

        if len(history) < 2:
            raise ValueError("Insufficient data for performance analysis")

        prices = [m.value for m in history]
        returns = np.diff(prices) / prices[:-1]

        # Calculate performance metrics
        total_return = (prices[-1] - prices[0]) / prices[0]
        volatility = np.std(returns) * np.sqrt(252)
        sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0

        # Maximum drawdown
        peak = np.maximum.accumulate(prices)
        drawdown = (peak - prices) / peak
        max_drawdown = np.max(drawdown)

        # Win rate (simplified - assuming 50% for random data)
        win_rate = 0.5

        # Value at Risk (95%)
        var_95 = np.percentile(returns, 5)

        report = PerformanceReport(
            report_id=f"perf_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            total_return=total_return,
            volatility=volatility,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=1.5,  # Mock value
            calmar_ratio=total_return / max_drawdown if max_drawdown > 0 else 0,
            var_95=var_95,
        )

        # Cache the report
        self.performance_cache[report.report_id] = report

        return report

    def get_analytics_summary(self) -> dict[str, Any]:
        """Get overall analytics summary"""
        summary = {
            "monitoring_active": self.is_monitoring,
            "total_alerts": len(self.alerts),
            "active_alerts": len([a for a in self.alerts.values() if a.active]),
            "tracked_symbols": len(self.current_metrics),
            "total_metrics_stored": sum(len(history) for history in self.metrics_history.values()),
            "performance_reports": len(self.performance_cache),
        }

        # Add symbol-specific metrics
        for symbol, metrics in self.current_metrics.items():
            summary[f"{symbol}_metrics"] = len(metrics)

        return summary


# Global instance
advanced_analytics = AdvancedAnalytics()


# CLI Interface Functions
async def start_analytics_monitoring(symbols: list[str]) -> bool:
    """Start analytics monitoring"""
    await advanced_analytics.start_monitoring(symbols)
    return True


async def stop_analytics_monitoring() -> bool:
    """Stop analytics monitoring"""
    await advanced_analytics.stop_monitoring()
    return True


def get_dashboard_data(symbol: str) -> dict[str, Any]:
    """Get dashboard data for symbol"""
    return advanced_analytics.get_real_time_dashboard(symbol)


def create_analytics_alert(name: str, symbol: str, metric_type: str, condition: str, threshold: float, timeframe: str) -> str:
    """Create analytics alert"""
    from advanced_analytics import MetricType, Timeframe

    return advanced_analytics.create_alert(
        name=name,
        symbol=symbol,
        metric_type=MetricType(metric_type),
        condition=condition,
        threshold=threshold,
        timeframe=Timeframe(timeframe),
    )


def get_analytics_summary() -> dict[str, Any]:
    """Get analytics summary"""
    return advanced_analytics.get_analytics_summary()


# Test function
async def test_advanced_analytics():
    """Test advanced analytics platform"""
    print("📊 Testing Advanced Analytics Platform...")

    # Start monitoring
    await start_analytics_monitoring(["BTC/USDT", "ETH/USDT"])
    print("✅ Analytics monitoring started")

    # Let it run for a few seconds to generate data
    await asyncio.sleep(5)

    # Get dashboard data
    dashboard = get_dashboard_data("BTC/USDT")
    print(f"📈 Dashboard data: {len(dashboard)} fields")

    # Get summary
    summary = get_analytics_summary()
    print(f"📊 Analytics summary: {summary}")

    # Stop monitoring
    await stop_analytics_monitoring()
    print("📊 Analytics monitoring stopped")

    print("🎉 Advanced Analytics test complete!")


if __name__ == "__main__":
    asyncio.run(test_advanced_analytics())
