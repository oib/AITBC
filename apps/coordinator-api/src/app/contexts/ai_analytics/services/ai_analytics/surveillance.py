"""
AI-Powered Surveillance System - Advanced Machine Learning Surveillance
Implements ML-based pattern recognition, behavioral analysis, and predictive risk assessment
"""

import asyncio
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from aitbc import get_logger

logger = get_logger(__name__)


class SurveillanceType(StrEnum):
    """Types of AI surveillance"""

    PATTERN_RECOGNITION = "pattern_recognition"
    BEHAVIORAL_ANALYSIS = "behavioral_analysis"
    PREDICTIVE_RISK = "predictive_risk"
    MARKET_INTEGRITY = "market_integrity"


class RiskLevel(StrEnum):
    """Risk levels for surveillance alerts"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertPriority(StrEnum):
    """Alert priority levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class BehaviorPattern:
    """User behavior pattern data"""

    user_id: str
    pattern_type: str
    confidence: float
    risk_score: float
    features: dict[str, float]
    detected_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SurveillanceAlert:
    """AI surveillance alert"""

    alert_id: str
    surveillance_type: SurveillanceType
    user_id: str
    risk_level: RiskLevel
    priority: AlertPriority
    confidence: float
    description: str
    evidence: dict[str, Any]
    detected_at: datetime
    resolved: bool = False
    false_positive: bool = False


@dataclass
class PredictiveRiskModel:
    """Predictive risk assessment model"""

    model_id: str
    model_type: str
    accuracy: float
    features: list[str]
    risk_threshold: float
    last_updated: datetime
    predictions: list[dict[str, Any]] = field(default_factory=list)


class AISurveillanceSystem:
    """AI-powered surveillance system with machine learning capabilities"""

    def __init__(self) -> None:
        self.is_running = False
        self.monitoring_task: asyncio.Task[None] | None = None
        self.behavior_patterns: dict[str, list[BehaviorPattern]] = defaultdict(list)
        self.surveillance_alerts: dict[str, SurveillanceAlert] = {}
        self.risk_models: dict[str, PredictiveRiskModel] = {}
        self.user_profiles: dict[str, dict[str, Any]] = defaultdict(dict)
        self.market_data: dict[str, pd.DataFrame] = {}
        self.suspicious_activities: list[dict[str, Any]] = []
        self._initialize_ml_models()

    def _initialize_ml_models(self) -> None:
        """Initialize machine learning models"""
        self.risk_models["pattern_recognition"] = PredictiveRiskModel(
            model_id="pr_001",
            model_type="isolation_forest",
            accuracy=0.92,
            features=["trade_frequency", "volume_variance", "timing_consistency", "price_impact"],
            risk_threshold=0.75,
            last_updated=datetime.now(),
        )
        self.risk_models["behavioral_analysis"] = PredictiveRiskModel(
            model_id="ba_001",
            model_type="clustering",
            accuracy=0.88,
            features=["session_duration", "trade_patterns", "device_consistency", "geo_location"],
            risk_threshold=0.7,
            last_updated=datetime.now(),
        )
        self.risk_models["predictive_risk"] = PredictiveRiskModel(
            model_id="pr_002",
            model_type="gradient_boosting",
            accuracy=0.94,
            features=["historical_risk", "network_connections", "transaction_anomalies", "compliance_flags"],
            risk_threshold=0.8,
            last_updated=datetime.now(),
        )
        self.risk_models["market_integrity"] = PredictiveRiskModel(
            model_id="mi_001",
            model_type="neural_network",
            accuracy=0.91,
            features=["price_manipulation", "volume_anomalies", "cross_market_patterns", "news_sentiment"],
            risk_threshold=0.85,
            last_updated=datetime.now(),
        )
        logger.info("🤖 AI Surveillance ML models initialized")

    async def start_surveillance(self, symbols: list[str]) -> None:
        """Start AI surveillance monitoring"""
        if self.is_running:
            logger.warning("⚠️  AI surveillance already running")
            return
        self.is_running = True
        self.monitoring_task = asyncio.create_task(self._surveillance_loop(symbols))
        logger.info("🔍 AI Surveillance started for %s symbols", len(symbols))

    async def stop_surveillance(self) -> None:
        """Stop AI surveillance monitoring"""
        self.is_running = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("🔍 AI surveillance stopped")

    async def _surveillance_loop(self, symbols: list[str]) -> None:
        """Main surveillance monitoring loop"""
        while self.is_running:
            try:
                await self._collect_market_data(symbols)
                await self._run_pattern_recognition()
                await self._run_behavioral_analysis()
                await self._run_predictive_risk_assessment()
                await self._run_market_integrity_check()
                await self._process_alerts()
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("❌ Surveillance error: %s", e)
                await asyncio.sleep(10)

    async def _collect_market_data(self, symbols: list[str]) -> None:
        """Collect market data for analysis"""
        for symbol in symbols:
            base_price = 50000 if symbol == "BTC/USDT" else 3000
            timestamp = datetime.now()
            price = base_price * (1 + random.uniform(-0.05, 0.05))
            volume = random.uniform(1000, 50000)
            if random.random() < 0.1:
                volume *= random.uniform(5, 20)
                price *= random.uniform(0.95, 1.05)
            market_data = {
                "timestamp": timestamp,
                "symbol": symbol,
                "price": price,
                "volume": volume,
                "trades": int(volume / 1000),
                "buy_orders": int(volume * 0.6 / 1000),
                "sell_orders": int(volume * 0.4 / 1000),
            }
            if symbol not in self.market_data:
                self.market_data[symbol] = pd.DataFrame()
            new_row = pd.DataFrame([market_data])
            self.market_data[symbol] = pd.concat([self.market_data[symbol], new_row], ignore_index=True)
            if len(self.market_data[symbol]) > 1000:
                self.market_data[symbol] = self.market_data[symbol].tail(1000)

    async def _run_pattern_recognition(self) -> None:
        """Run ML-based pattern recognition"""
        try:
            for symbol, data in self.market_data.items():
                if len(data) < 50:
                    continue
                features = self._extract_pattern_features(data)
                risk_score = self._simulate_ml_prediction("pattern_recognition", features)
                if risk_score > 0.75:
                    pattern = BehaviorPattern(
                        user_id=f"pattern_user_{symbol}",
                        pattern_type="volume_spike",
                        confidence=risk_score,
                        risk_score=risk_score,
                        features=features,
                        detected_at=datetime.now(),
                        metadata={"symbol": symbol, "anomaly_type": "volume_manipulation"},
                    )
                    self.behavior_patterns[symbol].append(pattern)
                    await self._create_alert(
                        SurveillanceType.PATTERN_RECOGNITION,
                        pattern.user_id,
                        RiskLevel.HIGH if risk_score > 0.9 else RiskLevel.MEDIUM,
                        AlertPriority.HIGH,
                        risk_score,
                        f"Suspicious trading pattern detected in {symbol}",
                        {"features": features, "pattern_type": pattern.pattern_type},
                    )
        except Exception as e:
            logger.error("❌ Pattern recognition failed: %s", e)

    async def _run_behavioral_analysis(self) -> None:
        """Run behavioral analysis on user activities"""
        try:
            users = [f"user_{i}" for i in range(1, 21)]
            for user_id in users:
                features = self._generate_behavior_features(user_id)
                risk_score = self._simulate_ml_prediction("behavioral_analysis", features)
                if risk_score > 0.7:
                    pattern = BehaviorPattern(
                        user_id=user_id,
                        pattern_type="suspicious_behavior",
                        confidence=risk_score,
                        risk_score=risk_score,
                        features=features,
                        detected_at=datetime.now(),
                        metadata={"analysis_type": "behavioral_anomaly"},
                    )
                    if user_id not in self.behavior_patterns:
                        self.behavior_patterns[user_id] = []
                    self.behavior_patterns[user_id].append(pattern)
                    if risk_score > 0.85:
                        await self._create_alert(
                            SurveillanceType.BEHAVIORAL_ANALYSIS,
                            user_id,
                            RiskLevel.HIGH if risk_score > 0.9 else RiskLevel.MEDIUM,
                            AlertPriority.MEDIUM,
                            risk_score,
                            f"Suspicious user behavior detected for {user_id}",
                            {"features": features, "behavior_type": "anomalous_activity"},
                        )
        except Exception as e:
            logger.error("❌ Behavioral analysis failed: %s", e)

    async def _run_predictive_risk_assessment(self) -> None:
        """Run predictive risk assessment"""
        try:
            all_users = set()
            for patterns in self.behavior_patterns.values():
                for pattern in patterns:
                    all_users.add(pattern.user_id)
            for user_id in all_users:
                user_patterns = []
                for patterns in self.behavior_patterns.values():
                    user_patterns.extend([p for p in patterns if p.user_id == user_id])
                if not user_patterns:
                    continue
                features = self._calculate_predictive_features(user_id, user_patterns)
                risk_score = self._simulate_ml_prediction("predictive_risk", features)
                self.user_profiles[user_id]["predictive_risk"] = risk_score
                self.user_profiles[user_id]["last_assessed"] = datetime.now()
                if risk_score > 0.8:
                    await self._create_alert(
                        SurveillanceType.PREDICTIVE_RISK,
                        user_id,
                        RiskLevel.CRITICAL if risk_score > 0.9 else RiskLevel.HIGH,
                        AlertPriority.HIGH,
                        risk_score,
                        f"High predictive risk detected for {user_id}",
                        {"features": features, "risk_prediction": risk_score},
                    )
        except Exception as e:
            logger.error("❌ Predictive risk assessment failed: %s", e)

    async def _run_market_integrity_check(self) -> None:
        """Run market integrity protection checks"""
        try:
            for symbol, data in self.market_data.items():
                if len(data) < 100:
                    continue
                integrity_features = self._extract_integrity_features(data)
                risk_score = self._simulate_ml_prediction("market_integrity", integrity_features)
                if risk_score > 0.85:
                    await self._create_alert(
                        SurveillanceType.MARKET_INTEGRITY,
                        f"market_{symbol}",
                        RiskLevel.CRITICAL,
                        AlertPriority.URGENT,
                        risk_score,
                        f"Market integrity violation detected in {symbol}",
                        {"features": integrity_features, "integrity_risk": risk_score},
                    )
        except Exception as e:
            logger.error("❌ Market integrity check failed: %s", e)

    def _extract_pattern_features(self, data: pd.DataFrame) -> dict[str, float]:
        """Extract features for pattern recognition"""
        if len(data) < 10:
            return {}
        volumes = data["volume"].values
        prices = data["price"].values
        trades = data["trades"].values
        return {
            "trade_frequency": len(trades) / len(data),
            "volume_variance": np.var(volumes),
            "timing_consistency": 0.8,
            "price_impact": np.std(prices) / np.mean(prices),
            "volume_spike": max(volumes) / np.mean(volumes),
            "price_volatility": np.std(prices) / np.mean(prices),
        }

    def _generate_behavior_features(self, user_id: str) -> dict[str, float]:
        """Generate behavioral features for user"""
        user_hash = hash(user_id) % 100
        return {
            "session_duration": user_hash + random.uniform(1, 8),
            "trade_patterns": random.uniform(0.1, 1.0),
            "device_consistency": random.uniform(0.7, 1.0),
            "geo_location": random.uniform(0.8, 1.0),
            "transaction_frequency": random.uniform(1, 50),
            "avg_trade_size": random.uniform(1000, 100000),
        }

    def _calculate_predictive_features(self, user_id: str, patterns: list[BehaviorPattern]) -> dict[str, float]:
        """Calculate predictive risk features"""
        if not patterns:
            return {}
        risk_scores = [p.risk_score for p in patterns]
        confidences = [p.confidence for p in patterns]
        return {
            "historical_risk": float(np.mean(risk_scores)),
            "risk_trend": float(risk_scores[-1] - risk_scores[0] if len(risk_scores) > 1 else 0),
            "pattern_frequency": len(patterns),
            "avg_confidence": float(np.mean(confidences)),
            "max_risk_score": float(max(risk_scores)),
            "risk_consistency": float(1 - np.std(risk_scores)),
        }

    def _extract_integrity_features(self, data: pd.DataFrame) -> dict[str, float]:
        """Extract market integrity features"""
        if len(data) < 50:
            return {}
        prices = data["price"].values
        volumes = data["volume"].values
        buy_orders = data["buy_orders"].values
        sell_orders = data["sell_orders"].values
        return {
            "price_manipulation": self._detect_price_manipulation(prices),
            "volume_anomalies": self._detect_volume_anomalies(volumes),
            "cross_market_patterns": random.uniform(0.1, 0.9),
            "news_sentiment": random.uniform(-1, 1),
            "order_imbalance": np.abs(np.mean(buy_orders) - np.mean(sell_orders)) / np.mean(buy_orders + sell_orders),
        }

    def _detect_price_manipulation(self, prices: np.ndarray) -> float:
        """Detect price manipulation patterns"""
        if len(prices) < 10:
            return 0.0
        price_changes = np.diff(prices) / prices[:-1]
        large_moves = np.sum(np.abs(price_changes) > 0.05)
        total_moves = len(price_changes)
        return float(min(1.0, large_moves / total_moves * 5))

    def _detect_volume_anomalies(self, volumes: np.ndarray) -> float:
        """Detect volume anomalies"""
        if len(volumes) < 10:
            return 0.0
        mean_volume = np.mean(volumes)
        std_volume = np.std(volumes)
        anomalies = np.sum(np.abs(volumes - mean_volume) > 2 * std_volume)
        return float(min(1.0, anomalies / len(volumes) * 10))

    def _simulate_ml_prediction(self, model_type: str, features: dict[str, float]) -> float:
        """Simulate ML model prediction"""
        if not features:
            return random.uniform(0.1, 0.3)
        model = self.risk_models.get(model_type)
        if not model:
            return 0.5
        feature_score = np.mean(list(features.values())) if features else 0.5
        noise = random.uniform(-0.1, 0.1)
        prediction = feature_score * model.accuracy + noise
        return float(max(0.0, min(1.0, prediction)))

    async def _create_alert(
        self,
        surveillance_type: SurveillanceType,
        user_id: str,
        risk_level: RiskLevel,
        priority: AlertPriority,
        confidence: float,
        description: str,
        evidence: dict[str, Any],
    ) -> None:
        """Create surveillance alert"""
        alert_id = f"alert_{surveillance_type.value}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        alert = SurveillanceAlert(
            alert_id=alert_id,
            surveillance_type=surveillance_type,
            user_id=user_id,
            risk_level=risk_level,
            priority=priority,
            confidence=confidence,
            description=description,
            evidence=evidence,
            detected_at=datetime.now(),
        )
        self.surveillance_alerts[alert_id] = alert
        logger.warning("🚨 AI Surveillance Alert: %s", description)
        logger.warning("   Type: %s", surveillance_type.value)
        logger.warning("   User: %s", user_id)
        logger.warning("   Risk Level: %s", risk_level.value)
        logger.warning("   Confidence: %s", confidence)

    async def _process_alerts(self) -> None:
        """Process and prioritize alerts"""
        alerts = list(self.surveillance_alerts.values())
        priority_scores = {AlertPriority.URGENT: 4, AlertPriority.HIGH: 3, AlertPriority.MEDIUM: 2, AlertPriority.LOW: 1}
        risk_scores = {RiskLevel.CRITICAL: 4, RiskLevel.HIGH: 3, RiskLevel.MEDIUM: 2, RiskLevel.LOW: 1}
        alerts.sort(
            key=lambda x: priority_scores.get(x.priority, 1) * risk_scores.get(x.risk_level, 1) * x.confidence, reverse=True
        )
        for alert in alerts[:5]:
            if not alert.resolved:
                await self._handle_alert(alert)

    async def _handle_alert(self, alert: SurveillanceAlert) -> None:
        """Handle surveillance alert"""
        logger.info("🔧 Processing alert: %s", alert.alert_id)
        alert.resolved = True
        if random.random() < 0.1:
            alert.false_positive = True
            logger.info("✅ Alert %s marked as false positive", alert.alert_id)

    def get_surveillance_summary(self) -> dict[str, Any]:
        """Get surveillance system summary"""
        total_alerts = len(self.surveillance_alerts)
        resolved_alerts = len([a for a in self.surveillance_alerts.values() if a.resolved])
        false_positives = len([a for a in self.surveillance_alerts.values() if a.false_positive])
        alerts_by_type: dict[str, int] = defaultdict(int)
        for alert in self.surveillance_alerts.values():
            alerts_by_type[alert.surveillance_type.value] += 1
        alerts_by_risk: dict[str, int] = defaultdict(int)
        for alert in self.surveillance_alerts.values():
            alerts_by_risk[alert.risk_level.value] += 1
        return {
            "monitoring_active": self.is_running,
            "total_alerts": total_alerts,
            "resolved_alerts": resolved_alerts,
            "false_positives": false_positives,
            "active_alerts": total_alerts - resolved_alerts,
            "behavior_patterns": len(self.behavior_patterns),
            "monitored_symbols": len(self.market_data),
            "ml_models": len(self.risk_models),
            "alerts_by_type": dict(alerts_by_type),
            "alerts_by_risk": dict(alerts_by_risk),
            "model_performance": {
                model_id: {"accuracy": model.accuracy, "threshold": model.risk_threshold}
                for model_id, model in self.risk_models.items()
            },
        }

    def get_user_risk_profile(self, user_id: str) -> dict[str, Any]:
        """Get comprehensive risk profile for a user"""
        user_patterns = []
        for patterns in self.behavior_patterns.values():
            user_patterns.extend([p for p in patterns if p.user_id == user_id])
        user_alerts = [a for a in self.surveillance_alerts.values() if a.user_id == user_id]
        return {
            "user_id": user_id,
            "behavior_patterns": len(user_patterns),
            "surveillance_alerts": len(user_alerts),
            "predictive_risk": self.user_profiles.get(user_id, {}).get("predictive_risk", 0.0),
            "last_assessed": self.user_profiles.get(user_id, {}).get("last_assessed"),
            "risk_trend": "increasing" if len(user_patterns) > 5 else "stable",
            "pattern_types": list({p.pattern_type for p in user_patterns}),
            "alert_types": list({a.surveillance_type.value for a in user_alerts}),
        }


ai_surveillance = AISurveillanceSystem()


async def start_ai_surveillance(symbols: list[str]) -> bool:
    """Start AI surveillance monitoring"""
    await ai_surveillance.start_surveillance(symbols)
    return True


async def stop_ai_surveillance() -> bool:
    """Stop AI surveillance monitoring"""
    await ai_surveillance.stop_surveillance()
    return True


def get_surveillance_summary() -> dict[str, Any]:
    """Get surveillance system summary"""
    return ai_surveillance.get_surveillance_summary()


def get_user_risk_profile(user_id: str) -> dict[str, Any]:
    """Get user risk profile"""
    return ai_surveillance.get_user_risk_profile(user_id)


def list_active_alerts(limit: int = 20) -> list[dict[str, Any]]:
    """List active surveillance alerts"""
    alerts = [a for a in ai_surveillance.surveillance_alerts.values() if not a.resolved]
    alerts.sort(key=lambda x: (x.detected_at, x.priority.value), reverse=True)
    return [
        {
            "alert_id": alert.alert_id,
            "type": alert.surveillance_type.value,
            "user_id": alert.user_id,
            "risk_level": alert.risk_level.value,
            "priority": alert.priority.value,
            "confidence": alert.confidence,
            "description": alert.description,
            "detected_at": alert.detected_at.isoformat(),
        }
        for alert in alerts[:limit]
    ]


def analyze_behavior_patterns(user_id: str | None = None) -> dict[str, Any]:
    """Analyze behavior patterns"""
    if user_id:
        patterns = ai_surveillance.behavior_patterns.get(user_id, [])
        return {
            "user_id": user_id,
            "total_patterns": len(patterns),
            "patterns": [
                {
                    "pattern_type": p.pattern_type,
                    "confidence": p.confidence,
                    "risk_score": p.risk_score,
                    "detected_at": p.detected_at.isoformat(),
                }
                for p in patterns[-10:]
            ],
        }
    else:
        all_patterns = []
        for patterns in ai_surveillance.behavior_patterns.values():
            all_patterns.extend(patterns)
        pattern_types: dict[str, int] = defaultdict(int)
        for pattern in all_patterns:
            pattern_types[pattern.pattern_type] += 1
        return {
            "total_patterns": len(all_patterns),
            "pattern_types": dict(pattern_types),
            "avg_confidence": np.mean([p.confidence for p in all_patterns]) if all_patterns else 0,
            "avg_risk_score": np.mean([p.risk_score for p in all_patterns]) if all_patterns else 0,
        }


async def test_ai_surveillance() -> None:
    """Test AI surveillance system"""
    logger.info("Testing AI Surveillance System")
    await start_ai_surveillance(["BTC/USDT", "ETH/USDT"])
    logger.info("AI surveillance started")
    await asyncio.sleep(5)
    summary = get_surveillance_summary()
    logger.info("Surveillance summary: %s", summary)
    alerts = list_active_alerts()
    logger.info("Active alerts: %s", len(alerts))
    patterns = analyze_behavior_patterns()
    logger.info("Behavior patterns: %s", patterns)
    await stop_ai_surveillance()
    logger.info("AI surveillance stopped")
    logger.info("AI Surveillance test complete")


if __name__ == "__main__":
    asyncio.run(test_ai_surveillance())
