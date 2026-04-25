#!/usr/bin/env python3
"""
Trading Surveillance System
Detects market manipulation, unusual trading patterns, and suspicious activities
"""

import asyncio
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from aitbc import get_logger

logger = get_logger(__name__)


class AlertLevel(StrEnum):
    """Alert severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ManipulationType(StrEnum):
    """Types of market manipulation"""

    PUMP_AND_DUMP = "pump_and_dump"
    WASH_TRADING = "wash_trading"
    SPOOFING = "spoofing"
    LAYERING = "layering"
    INSIDER_TRADING = "insider_trading"
    FRONT_RUNNING = "front_running"
    MARKET_TIMING = "market_timing"


class AnomalyType(StrEnum):
    """Types of trading anomalies"""

    VOLUME_SPIKE = "volume_spike"
    PRICE_ANOMALY = "price_anomaly"
    UNUSUAL_TIMING = "unusual_timing"
    CONCENTRATED_TRADING = "concentrated_trading"
    CROSS_MARKET_ARBITRAGE = "cross_market_arbitrage"


@dataclass
class TradingAlert:
    """Trading surveillance alert"""

    alert_id: str
    timestamp: datetime
    alert_level: AlertLevel
    manipulation_type: ManipulationType | None
    anomaly_type: AnomalyType | None
    description: str
    confidence: float  # 0.0 to 1.0
    affected_symbols: list[str]
    affected_users: list[str]
    evidence: dict[str, Any]
    risk_score: float
    status: str = "active"  # active, resolved, false_positive


@dataclass
class TradingPattern:
    """Trading pattern analysis"""

    pattern_id: str
    symbol: str
    timeframe: str  # 1m, 5m, 15m, 1h, 1d
    pattern_type: str
    confidence: float
    start_time: datetime
    end_time: datetime
    volume_data: list[float]
    price_data: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


class TradingSurveillance:
    """Main trading surveillance system"""

    def __init__(self):
        self.alerts: list[TradingAlert] = []
        self.patterns: list[TradingPattern] = []
        self.monitoring_symbols: dict[str, bool] = {}
        self.thresholds = {
            "volume_spike_multiplier": 3.0,  # 3x average volume
            "price_change_threshold": 0.15,  # 15% price change
            "wash_trade_threshold": 0.8,  # 80% of trades between same entities
            "spoofing_threshold": 0.9,  # 90% order cancellation rate
            "concentration_threshold": 0.6,  # 60% of volume from single user
        }
        self.is_monitoring = False
        self.monitoring_task = None

    async def start_monitoring(self, symbols: list[str]):
        """Start monitoring trading activities"""
        if self.is_monitoring:
            logger.warning("⚠️  Trading surveillance already running")
            return

        self.monitoring_symbols = dict.fromkeys(symbols, True)
        self.is_monitoring = True
        self.monitoring_task = asyncio.create_task(self._monitor_loop())
        logger.info(f"🔍 Trading surveillance started for {len(symbols)} symbols")

    async def stop_monitoring(self):
        """Stop trading surveillance"""
        self.is_monitoring = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("🔍 Trading surveillance stopped")

    async def _monitor_loop(self):
        """Main monitoring loop"""
        while self.is_monitoring:
            try:
                for symbol in list(self.monitoring_symbols.keys()):
                    if self.monitoring_symbols.get(symbol, False):
                        await self._analyze_symbol(symbol)

                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Monitoring error: {e}")
                await asyncio.sleep(10)

    async def _analyze_symbol(self, symbol: str):
        """Analyze trading patterns for a symbol"""
        try:
            # Get recent trading data (mock implementation)
            trading_data = await self._get_trading_data(symbol)

            # Analyze for different manipulation types
            await self._detect_pump_and_dump(symbol, trading_data)
            await self._detect_wash_trading(symbol, trading_data)
            await self._detect_spoofing(symbol, trading_data)
            await self._detect_volume_anomalies(symbol, trading_data)
            await self._detect_price_anomalies(symbol, trading_data)
            await self._detect_concentrated_trading(symbol, trading_data)

        except Exception as e:
            logger.error(f"❌ Analysis error for {symbol}: {e}")

    async def _get_trading_data(self, symbol: str) -> dict[str, Any]:
        """Get recent trading data (mock implementation)"""
        # In production, this would fetch real data from exchanges
        await asyncio.sleep(0.1)  # Simulate API call

        # Generate mock trading data
        base_volume = 1000000
        base_price = 50000

        # Add some randomness
        volume = base_volume * (1 + np.random.normal(0, 0.2))
        price = base_price * (1 + np.random.normal(0, 0.05))

        # Generate time series data
        timestamps = [datetime.now() - timedelta(minutes=i) for i in range(60, 0, -1)]
        volumes = [volume * (1 + np.random.normal(0, 0.3)) for _ in timestamps]
        prices = [price * (1 + np.random.normal(0, 0.02)) for _ in timestamps]

        # Generate user distribution
        users = [f"user_{i}" for i in range(100)]
        user_volumes = {}

        for user in users:
            user_volumes[user] = np.random.exponential(volume / len(users))

        # Normalize
        total_user_volume = sum(user_volumes.values())
        user_volumes = {k: v / total_user_volume for k, v in user_volumes.items()}

        return {
            "symbol": symbol,
            "current_volume": volume,
            "current_price": price,
            "volume_history": volumes,
            "price_history": prices,
            "timestamps": timestamps,
            "user_distribution": user_volumes,
            "trade_count": int(volume / 1000),
            "order_cancellations": int(np.random.poisson(100)),
            "total_orders": int(np.random.poisson(500)),
        }

    async def _detect_pump_and_dump(self, symbol: str, data: dict[str, Any]):
        """Detect pump and dump patterns"""
        try:
            # Look for rapid price increase followed by sharp decline
            prices = data["price_history"]
            volumes = data["volume_history"]

            if len(prices) < 20:
                return

            # Calculate price changes
            price_changes = [prices[i] / prices[i - 1] - 1 for i in range(1, len(prices))]

            # Look for pump phase (rapid increase)
            pump_threshold = 0.05  # 5% increase
            pump_detected = False
            pump_start = 0

            for i in range(10, len(price_changes) - 10):
                recent_changes = price_changes[i - 10 : i]
                if all(change > pump_threshold for change in recent_changes):
                    pump_detected = True
                    pump_start = i
                    break

            # Look for dump phase (sharp decline after pump)
            if pump_detected and pump_start < len(price_changes) - 10:
                dump_changes = price_changes[pump_start : pump_start + 10]
                if all(change < -pump_threshold for change in dump_changes):
                    # Pump and dump detected
                    confidence = min(0.9, sum(abs(c) for c in dump_changes[:5]) / 0.5)

                    alert = TradingAlert(
                        alert_id=f"pump_dump_{symbol}_{int(datetime.now().timestamp())}",
                        timestamp=datetime.now(),
                        alert_level=AlertLevel.HIGH,
                        manipulation_type=ManipulationType.PUMP_AND_DUMP,
                        anomaly_type=None,
                        description=f"Pump and dump pattern detected in {symbol}",
                        confidence=confidence,
                        affected_symbols=[symbol],
                        affected_users=[],
                        evidence={
                            "price_changes": price_changes[pump_start - 10 : pump_start + 10],
                            "volume_spike": max(volumes[pump_start - 10 : pump_start + 10]) / np.mean(volumes),
                            "pump_start": pump_start,
                            "dump_start": pump_start + 10,
                        },
                        risk_score=0.8,
                    )

                    self.alerts.append(alert)
                    logger.warning(f"🚨 Pump and dump detected: {symbol} (confidence: {confidence:.2f})")

        except Exception as e:
            logger.error(f"❌ Pump and dump detection error: {e}")

    async def _detect_wash_trading(self, symbol: str, data: dict[str, Any]):
        """Detect wash trading patterns"""
        try:
            # Look for circular trading patterns between same entities
            user_distribution = data["user_distribution"]

            # Check if any user dominates trading
            max_user_share = max(user_distribution.values())
            if max_user_share > self.thresholds["wash_trade_threshold"]:
                dominant_user = max(user_distribution, key=user_distribution.get)

                alert = TradingAlert(
                    alert_id=f"wash_trade_{symbol}_{int(datetime.now().timestamp())}",
                    timestamp=datetime.now(),
                    alert_level=AlertLevel.HIGH,
                    manipulation_type=ManipulationType.WASH_TRADING,
                    anomaly_type=AnomalyType.CONCENTRATED_TRADING,
                    description=f"Potential wash trading detected in {symbol}",
                    confidence=min(0.9, max_user_share),
                    affected_symbols=[symbol],
                    affected_users=[dominant_user],
                    evidence={
                        "user_share": max_user_share,
                        "user_distribution": user_distribution,
                        "total_volume": data["current_volume"],
                    },
                    risk_score=0.75,
                )

                self.alerts.append(alert)
                logger.warning(f"🚨 Wash trading detected: {symbol} (user share: {max_user_share:.2f})")

        except Exception as e:
            logger.error(f"❌ Wash trading detection error: {e}")

    async def _detect_spoofing(self, symbol: str, data: dict[str, Any]):
        """Detect order spoofing (placing large orders then cancelling)"""
        try:
            total_orders = data["total_orders"]
            cancellations = data["order_cancellations"]

            if total_orders > 0:
                cancellation_rate = cancellations / total_orders

                if cancellation_rate > self.thresholds["spoofing_threshold"]:
                    alert = TradingAlert(
                        alert_id=f"spoofing_{symbol}_{int(datetime.now().timestamp())}",
                        timestamp=datetime.now(),
                        alert_level=AlertLevel.MEDIUM,
                        manipulation_type=ManipulationType.SPOOFING,
                        anomaly_type=None,
                        description=f"High order cancellation rate detected in {symbol}",
                        confidence=min(0.8, cancellation_rate),
                        affected_symbols=[symbol],
                        affected_users=[],
                        evidence={
                            "cancellation_rate": cancellation_rate,
                            "total_orders": total_orders,
                            "cancellations": cancellations,
                        },
                        risk_score=0.6,
                    )

                    self.alerts.append(alert)
                    logger.warning(f"🚨 Spoofing detected: {symbol} (cancellation rate: {cancellation_rate:.2f})")

        except Exception as e:
            logger.error(f"❌ Spoofing detection error: {e}")

    async def _detect_volume_anomalies(self, symbol: str, data: dict[str, Any]):
        """Detect unusual volume spikes"""
        try:
            volumes = data["volume_history"]
            current_volume = data["current_volume"]

            if len(volumes) > 20:
                avg_volume = np.mean(volumes[:-10])  # Average excluding recent period
                recent_avg = np.mean(volumes[-10:])  # Recent average

                volume_multiplier = recent_avg / avg_volume

                if volume_multiplier > self.thresholds["volume_spike_multiplier"]:
                    alert = TradingAlert(
                        alert_id=f"volume_spike_{symbol}_{int(datetime.now().timestamp())}",
                        timestamp=datetime.now(),
                        alert_level=AlertLevel.MEDIUM,
                        manipulation_type=None,
                        anomaly_type=AnomalyType.VOLUME_SPIKE,
                        description=f"Unusual volume spike detected in {symbol}",
                        confidence=min(0.8, volume_multiplier / 5),
                        affected_symbols=[symbol],
                        affected_users=[],
                        evidence={
                            "volume_multiplier": volume_multiplier,
                            "current_volume": current_volume,
                            "avg_volume": avg_volume,
                            "recent_avg": recent_avg,
                        },
                        risk_score=0.5,
                    )

                    self.alerts.append(alert)
                    logger.warning(f"🚨 Volume spike detected: {symbol} (multiplier: {volume_multiplier:.2f})")

        except Exception as e:
            logger.error(f"❌ Volume anomaly detection error: {e}")

    async def _detect_price_anomalies(self, symbol: str, data: dict[str, Any]):
        """Detect unusual price movements"""
        try:
            prices = data["price_history"]

            if len(prices) > 10:
                price_changes = [prices[i] / prices[i - 1] - 1 for i in range(1, len(prices))]

                # Look for extreme price changes
                for i, change in enumerate(price_changes):
                    if abs(change) > self.thresholds["price_change_threshold"]:
                        alert = TradingAlert(
                            alert_id=f"price_anomaly_{symbol}_{int(datetime.now().timestamp())}_{i}",
                            timestamp=datetime.now(),
                            alert_level=AlertLevel.MEDIUM,
                            manipulation_type=None,
                            anomaly_type=AnomalyType.PRICE_ANOMALY,
                            description=f"Unusual price movement detected in {symbol}",
                            confidence=min(0.9, abs(change) / 0.2),
                            affected_symbols=[symbol],
                            affected_users=[],
                            evidence={
                                "price_change": change,
                                "price_before": prices[i],
                                "price_after": prices[i + 1] if i + 1 < len(prices) else None,
                                "timestamp_index": i,
                            },
                            risk_score=0.4,
                        )

                        self.alerts.append(alert)
                        logger.warning(f"🚨 Price anomaly detected: {symbol} (change: {change:.2%})")

        except Exception as e:
            logger.error(f"❌ Price anomaly detection error: {e}")

    async def _detect_concentrated_trading(self, symbol: str, data: dict[str, Any]):
        """Detect concentrated trading from few users"""
        try:
            user_distribution = data["user_distribution"]

            # Calculate concentration (Herfindahl-Hirschman Index)
            hhi = sum(share**2 for share in user_distribution.values())

            # High concentration indicates potential manipulation
            if hhi > self.thresholds["concentration_threshold"]:
                # Find top users
                sorted_users = sorted(user_distribution.items(), key=lambda x: x[1], reverse=True)
                top_users = sorted_users[:3]

                alert = TradingAlert(
                    alert_id=f"concentrated_{symbol}_{int(datetime.now().timestamp())}",
                    timestamp=datetime.now(),
                    alert_level=AlertLevel.MEDIUM,
                    manipulation_type=None,
                    anomaly_type=AnomalyType.CONCENTRATED_TRADING,
                    description=f"Concentrated trading detected in {symbol}",
                    confidence=min(0.8, hhi),
                    affected_symbols=[symbol],
                    affected_users=[user for user, _ in top_users],
                    evidence={"hhi": hhi, "top_users": top_users, "total_users": len(user_distribution)},
                    risk_score=0.5,
                )

                self.alerts.append(alert)
                logger.warning(f"🚨 Concentrated trading detected: {symbol} (HHI: {hhi:.2f})")

        except Exception as e:
            logger.error(f"❌ Concentrated trading detection error: {e}")

    def get_active_alerts(self, level: AlertLevel | None = None) -> list[TradingAlert]:
        """Get active alerts, optionally filtered by level"""
        alerts = [alert for alert in self.alerts if alert.status == "active"]

        if level:
            alerts = [alert for alert in alerts if alert.alert_level == level]

        return sorted(alerts, key=lambda x: x.timestamp, reverse=True)

    def get_alert_summary(self) -> dict[str, Any]:
        """Get summary of all alerts"""
        active_alerts = [alert for alert in self.alerts if alert.status == "active"]

        summary = {
            "total_alerts": len(self.alerts),
            "active_alerts": len(active_alerts),
            "by_level": {
                "critical": len([a for a in active_alerts if a.alert_level == AlertLevel.CRITICAL]),
                "high": len([a for a in active_alerts if a.alert_level == AlertLevel.HIGH]),
                "medium": len([a for a in active_alerts if a.alert_level == AlertLevel.MEDIUM]),
                "low": len([a for a in active_alerts if a.alert_level == AlertLevel.LOW]),
            },
            "by_type": {
                "pump_and_dump": len([a for a in active_alerts if a.manipulation_type == ManipulationType.PUMP_AND_DUMP]),
                "wash_trading": len([a for a in active_alerts if a.manipulation_type == ManipulationType.WASH_TRADING]),
                "spoofing": len([a for a in active_alerts if a.manipulation_type == ManipulationType.SPOOFING]),
                "volume_spike": len([a for a in active_alerts if a.anomaly_type == AnomalyType.VOLUME_SPIKE]),
                "price_anomaly": len([a for a in active_alerts if a.anomaly_type == AnomalyType.PRICE_ANOMALY]),
                "concentrated_trading": len([a for a in active_alerts if a.anomaly_type == AnomalyType.CONCENTRATED_TRADING]),
            },
            "risk_distribution": {
                "high_risk": len([a for a in active_alerts if a.risk_score > 0.7]),
                "medium_risk": len([a for a in active_alerts if 0.4 <= a.risk_score <= 0.7]),
                "low_risk": len([a for a in active_alerts if a.risk_score < 0.4]),
            },
        }

        return summary

    def resolve_alert(self, alert_id: str, resolution: str = "resolved") -> bool:
        """Mark an alert as resolved"""
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.status = resolution
                logger.info(f"✅ Alert {alert_id} marked as {resolution}")
                return True
        return False


# Global instance
surveillance = TradingSurveillance()


# CLI Interface Functions
async def start_surveillance(symbols: list[str]) -> bool:
    """Start trading surveillance"""
    await surveillance.start_monitoring(symbols)
    return True


async def stop_surveillance() -> bool:
    """Stop trading surveillance"""
    await surveillance.stop_monitoring()
    return True


def get_alerts(level: str | None = None) -> dict[str, Any]:
    """Get surveillance alerts"""
    alert_level = AlertLevel(level) if level else None
    alerts = surveillance.get_active_alerts(alert_level)

    return {
        "alerts": [
            {
                "alert_id": alert.alert_id,
                "timestamp": alert.timestamp.isoformat(),
                "level": alert.alert_level.value,
                "manipulation_type": alert.manipulation_type.value if alert.manipulation_type else None,
                "anomaly_type": alert.anomaly_type.value if alert.anomaly_type else None,
                "description": alert.description,
                "confidence": alert.confidence,
                "risk_score": alert.risk_score,
                "affected_symbols": alert.affected_symbols,
                "affected_users": alert.affected_users,
            }
            for alert in alerts
        ],
        "total": len(alerts),
    }


def get_surveillance_summary() -> dict[str, Any]:
    """Get surveillance summary"""
    return surveillance.get_alert_summary()


# Test function
async def test_trading_surveillance():
    """Test trading surveillance system"""
    print("🧪 Testing Trading Surveillance System...")

    # Start monitoring
    await start_surveillance(["BTC/USDT", "ETH/USDT"])
    print("✅ Surveillance started")

    # Let it run for a few seconds to generate alerts
    await asyncio.sleep(5)

    # Get alerts
    alerts = get_alerts()
    print(f"🚨 Generated {alerts['total']} alerts")

    # Get summary
    summary = get_surveillance_summary()
    print(f"📊 Alert Summary: {summary}")

    # Stop monitoring
    await stop_surveillance()
    print("🔍 Surveillance stopped")

    print("🎉 Trading surveillance test complete!")


if __name__ == "__main__":
    asyncio.run(test_trading_surveillance())
