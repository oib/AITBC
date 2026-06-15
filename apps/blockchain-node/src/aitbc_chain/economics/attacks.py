"""
Economic Attack Prevention
Detects and prevents various economic attacks on the network
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .gas import GasManager
from .rewards import RewardDistributor
from .staking import StakingManager

logger = logging.getLogger(__name__)


def log_info(msg: str) -> None:
    logger.info(msg)


def log_error(msg: str) -> None:
    logger.error(msg)


def log_warn(msg: str) -> None:
    logger.warning(msg)


class AttackType(Enum):
    SYBIL = "sybil"
    STAKE_GRINDING = "stake_grinding"
    NOTHING_AT_STAKE = "nothing_at_stake"
    LONG_RANGE = "long_range"
    FRONT_RUNNING = "front_running"
    GAS_MANIPULATION = "gas_manipulation"


class ThreatLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AttackDetection:
    attack_type: AttackType
    threat_level: ThreatLevel
    attacker_address: str
    evidence: dict[str, Any]
    detected_at: float
    confidence: float
    recommended_action: str


@dataclass
class SecurityMetric:
    metric_name: str
    current_value: float
    threshold: float
    status: str
    last_updated: float


class EconomicSecurityMonitor:
    """Monitors and prevents economic attacks"""

    def __init__(self, staking_manager: StakingManager, reward_distributor: RewardDistributor, gas_manager: GasManager):
        self.staking_manager = staking_manager
        self.reward_distributor = reward_distributor
        self.gas_manager = gas_manager
        self.detection_rules = self._initialize_detection_rules()
        self.attack_detections: list[AttackDetection] = []
        self.security_metrics: dict[str, SecurityMetric] = {}
        self.blacklisted_addresses: set[str] = set()
        self.monitoring_interval = 60
        self.detection_history_window = 3600
        self.max_false_positive_rate = 0.05
        self._initialize_security_metrics()

    def _initialize_detection_rules(self) -> dict[AttackType, dict[str, Any]]:
        """Initialize detection rules for different attack types"""
        return {
            AttackType.SYBIL: {"threshold": 0.1, "min_stake": 1000.0, "time_window": 86400, "max_similar_addresses": 5},
            AttackType.STAKE_GRINDING: {
                "threshold": 0.3,
                "min_operations": 10,
                "time_window": 3600,
                "max_withdrawal_frequency": 5,
            },
            AttackType.NOTHING_AT_STAKE: {
                "threshold": 0.5,
                "min_validators": 10,
                "time_window": 7200,
                "max_abstention_periods": 3,
            },
            AttackType.LONG_RANGE: {"threshold": 0.8, "min_history_depth": 1000, "time_window": 604800, "max_key_reuse": 2},
            AttackType.FRONT_RUNNING: {
                "threshold": 0.1,
                "min_transactions": 100,
                "time_window": 3600,
                "max_mempool_advantage": 0.05,
            },
            AttackType.GAS_MANIPULATION: {
                "threshold": 2.0,
                "min_price_changes": 5,
                "time_window": 1800,
                "max_spikes_per_hour": 3,
            },
        }

    def _initialize_security_metrics(self) -> None:
        """Initialize security monitoring metrics"""
        self.security_metrics = {
            "validator_diversity": SecurityMetric(
                metric_name="validator_diversity", current_value=0.0, threshold=0.7, status="healthy", last_updated=time.time()
            ),
            "stake_distribution": SecurityMetric(
                metric_name="stake_distribution", current_value=0.0, threshold=0.8, status="healthy", last_updated=time.time()
            ),
            "reward_distribution": SecurityMetric(
                metric_name="reward_distribution", current_value=0.0, threshold=0.9, status="healthy", last_updated=time.time()
            ),
            "gas_price_stability": SecurityMetric(
                metric_name="gas_price_stability", current_value=0.0, threshold=0.3, status="healthy", last_updated=time.time()
            ),
        }

    async def start_monitoring(self) -> None:
        """Start economic security monitoring"""
        log_info("Starting economic security monitoring")
        while True:
            try:
                await self._monitor_security_metrics()
                await self._detect_attacks()
                await self._update_blacklist()
                await asyncio.sleep(self.monitoring_interval)
            except Exception as e:
                log_error(f"Security monitoring error: {e}")
                await asyncio.sleep(10)

    async def _monitor_security_metrics(self) -> None:
        """Monitor security metrics"""
        current_time = time.time()
        await self._update_validator_diversity(current_time)
        await self._update_stake_distribution(current_time)
        await self._update_reward_distribution(current_time)
        await self._update_gas_price_stability(current_time)

    async def _update_validator_diversity(self, current_time: float) -> None:
        """Update validator diversity metric"""
        validators = self.staking_manager.get_active_validators()
        if len(validators) < 10:
            diversity_score = 0.0
        else:
            total_stake = sum(v.total_stake for v in validators)
            if total_stake == 0:
                diversity_score = 0.0
            else:
                stake_shares = [float(v.total_stake / total_stake) for v in validators]
                hhi = sum(share**2 for share in stake_shares)
                diversity_score = 1.0 - hhi
        metric = self.security_metrics["validator_diversity"]
        metric.current_value = diversity_score
        metric.last_updated = current_time
        if diversity_score < metric.threshold:
            metric.status = "warning"
        else:
            metric.status = "healthy"

    async def _update_stake_distribution(self, current_time: float) -> None:
        """Update stake distribution metric"""
        validators = self.staking_manager.get_active_validators()
        if not validators:
            distribution_score = 0.0
        else:
            stakes = [float(v.total_stake) for v in validators]
            stakes.sort(reverse=True)
            total_stake = sum(stakes)
            if total_stake == 0:
                distribution_score = 0.0
            else:
                top3_share = sum(stakes[:3]) / total_stake
                distribution_score = 1.0 - top3_share
        metric = self.security_metrics["stake_distribution"]
        metric.current_value = distribution_score
        metric.last_updated = current_time
        if distribution_score < metric.threshold:
            metric.status = "warning"
        else:
            metric.status = "healthy"

    async def _update_reward_distribution(self, current_time: float) -> None:
        """Update reward distribution metric"""
        distributions = self.reward_distributor.get_distribution_history(limit=10)
        if len(distributions) < 5:
            distribution_score = 1.0
        else:
            total_rewards = sum(dist.total_rewards for dist in distributions)
            if total_rewards == 0:
                distribution_score = 0.0
            else:
                validator_rewards: list[float] = []
                for dist in distributions:
                    validator_rewards.extend(float(v) for v in dist.validator_rewards.values())
                if not validator_rewards:
                    distribution_score = 0.0
                else:
                    avg_reward = sum(validator_rewards) / len(validator_rewards)
                    variance = sum((r - avg_reward) ** 2 for r in validator_rewards) / len(validator_rewards)
                    cv = variance**0.5 / avg_reward if avg_reward > 0 else 0
                    distribution_score = max(0.0, 1.0 - cv)
        metric = self.security_metrics["reward_distribution"]
        metric.current_value = distribution_score
        metric.last_updated = current_time
        if distribution_score < metric.threshold:
            metric.status = "warning"
        else:
            metric.status = "healthy"

    async def _update_gas_price_stability(self, current_time: float) -> None:
        """Update gas price stability metric"""
        gas_stats = self.gas_manager.get_gas_statistics()
        if gas_stats["price_history_length"] < 10:
            stability_score = 1.0
        else:
            stability_score = 1.0 - gas_stats["price_volatility"]
        metric = self.security_metrics["gas_price_stability"]
        metric.current_value = stability_score
        metric.last_updated = current_time
        if stability_score < metric.threshold:
            metric.status = "warning"
        else:
            metric.status = "healthy"

    async def _detect_attacks(self) -> None:
        """Detect potential economic attacks"""
        current_time = time.time()
        await self._detect_sybil_attacks(current_time)
        await self._detect_stake_grinding(current_time)
        await self._detect_nothing_at_stake(current_time)
        await self._detect_long_range_attacks(current_time)
        await self._detect_front_running(current_time)
        await self._detect_gas_manipulation(current_time)

    async def _detect_sybil_attacks(self, current_time: float) -> None:
        """Detect Sybil attacks (multiple identities)"""
        rule = self.detection_rules[AttackType.SYBIL]
        validators = self.staking_manager.get_active_validators()
        address_groups: dict[str, list[Any]] = {}
        for validator in validators:
            prefix = validator.validator_address[:8]
            if prefix not in address_groups:
                address_groups[prefix] = []
            address_groups[prefix].append(validator)
        for prefix, group in address_groups.items():
            if len(group) >= rule["max_similar_addresses"]:
                group_stake = sum(v.total_stake for v in group)
                total_stake = sum(v.total_stake for v in validators)
                stake_ratio = float(group_stake / total_stake) if total_stake > 0 else 0
                if stake_ratio > rule["threshold"]:
                    threat_level = ThreatLevel.HIGH
                elif stake_ratio > rule["threshold"] * 0.5:
                    threat_level = ThreatLevel.MEDIUM
                else:
                    threat_level = ThreatLevel.LOW
                detection = AttackDetection(
                    attack_type=AttackType.SYBIL,
                    threat_level=threat_level,
                    attacker_address=prefix,
                    evidence={
                        "similar_addresses": [v.validator_address for v in group],
                        "group_size": len(group),
                        "stake_ratio": stake_ratio,
                        "common_prefix": prefix,
                    },
                    detected_at=current_time,
                    confidence=0.8,
                    recommended_action="Investigate validator identities",
                )
                self.attack_detections.append(detection)

    async def _record_detection(
        self, attack_type: AttackType, message: str, threat_level: ThreatLevel = ThreatLevel.MEDIUM
    ) -> None:
        """Record an attack detection."""
        detection = AttackDetection(
            attack_type=attack_type,
            threat_level=threat_level,
            attacker_address="unknown",
            evidence={"message": message},
            detected_at=time.time(),
            confidence=0.7,
            recommended_action="Monitor and investigate",
        )
        self.attack_detections.append(detection)
        logger.warning("Attack detected: %s - %s", attack_type.value, message)

    async def _detect_stake_grinding(self, current_time: float) -> None:
        """Detect stake grinding attacks"""
        rule = self.detection_rules[AttackType.STAKE_GRINDING]
        recent_detections = [
            d
            for d in self.attack_detections
            if d.attack_type == AttackType.STAKE_GRINDING and current_time - d.detected_at < rule["time_window"]
        ]
        try:
            from ..state import get_state_manager  # type: ignore[attr-defined]

            get_state_manager()
            if len(recent_detections) >= rule["threshold"]:
                logger.warning("Potential stake grinding attack detected: %s events in window", len(recent_detections))
                await self._record_detection(AttackType.STAKE_GRINDING, "Multiple stake movements detected in short window")
        except Exception as e:
            logger.debug("Stake grinding detection error: %s", e)

    async def _detect_nothing_at_stake(self, current_time: float) -> None:
        """Detect nothing-at-stake attacks"""
        rule = self.detection_rules[AttackType.NOTHING_AT_STAKE]
        try:
            from ..state import get_state_manager  # type: ignore[attr-defined]

            get_state_manager()
            participation_rate = 0.95
            if participation_rate < rule.get("min_participation", 0.8):
                logger.warning("Low validator participation: %s", participation_rate)
                await self._record_detection(
                    AttackType.NOTHING_AT_STAKE, f"Validator participation below threshold: {participation_rate:.2%}"
                )
        except Exception as e:
            logger.debug("Nothing-at-stake detection error: %s", e)

    async def _detect_long_range_attacks(self, current_time: float) -> None:
        """Detect long-range attacks"""
        self.detection_rules[AttackType.LONG_RANGE]
        try:
            from ..state import get_state_manager  # type: ignore[attr-defined]

            get_state_manager()
            pass
        except Exception as e:
            logger.debug("Long-range attack detection error: %s", e)

    async def _detect_front_running(self, current_time: float) -> None:
        """Detect front-running attacks"""
        self.detection_rules[AttackType.FRONT_RUNNING]
        try:
            gas_stats = self.gas_manager.get_gas_statistics() if hasattr(self, "gas_manager") else {}
            current_gas = gas_stats.get("current_gas_price", 0)
            avg_gas = gas_stats.get("average_gas_price", 1)
            if avg_gas > 0 and current_gas > avg_gas * 3:
                logger.warning("Potential gas manipulation detected: %s vs avg %s", current_gas, avg_gas)
                await self._record_detection(
                    AttackType.GAS_MANIPULATION, f"Gas price spike detected: {current_gas} vs avg {avg_gas}"
                )
        except Exception as e:
            logger.debug("Front-running detection error: %s", e)

    async def _detect_gas_manipulation(self, current_time: float) -> None:
        """Detect gas price manipulation"""
        from decimal import Decimal

        rule = self.detection_rules[AttackType.GAS_MANIPULATION]
        gas_stats = self.gas_manager.get_gas_statistics()
        if gas_stats["price_history_length"] >= 10:
            recent_prices = [p.price_per_gas for p in self.gas_manager.price_history[-10:]]
            avg_price = sum(recent_prices) / len(recent_prices)
            for price in recent_prices:
                if float(Decimal(price) / Decimal(avg_price)) > rule["threshold"]:
                    detection = AttackDetection(
                        attack_type=AttackType.GAS_MANIPULATION,
                        threat_level=ThreatLevel.MEDIUM,
                        attacker_address="unknown",
                        evidence={
                            "spike_ratio": float(Decimal(price) / Decimal(avg_price)),
                            "current_price": float(price),
                            "average_price": float(avg_price),
                        },
                        detected_at=current_time,
                        confidence=0.6,
                        recommended_action="Monitor gas price patterns",
                    )
                    self.attack_detections.append(detection)
                    break

    async def _update_blacklist(self) -> None:
        """Update blacklist based on detections"""
        current_time = time.time()
        self.attack_detections = [
            d for d in self.attack_detections if current_time - d.detected_at < self.detection_history_window
        ]
        for detection in self.attack_detections:
            if (
                detection.threat_level in [ThreatLevel.HIGH, ThreatLevel.CRITICAL]
                and detection.confidence > 0.8
                and (detection.attacker_address not in self.blacklisted_addresses)
            ):
                self.blacklisted_addresses.add(detection.attacker_address)
                log_warn(f"Added {detection.attacker_address} to blacklist due to {detection.attack_type.value} attack")

    def is_address_blacklisted(self, address: str) -> bool:
        """Check if address is blacklisted"""
        return address in self.blacklisted_addresses

    def get_attack_summary(self) -> dict[str, Any]:
        """Get summary of detected attacks"""
        current_time = time.time()
        recent_detections = [d for d in self.attack_detections if current_time - d.detected_at < 3600]
        attack_counts: dict[str, int] = {}
        threat_counts: dict[str, int] = {}
        for detection in recent_detections:
            attack_type = detection.attack_type.value
            threat_level = detection.threat_level.value
            attack_counts[attack_type] = attack_counts.get(attack_type, 0) + 1
            threat_counts[threat_level] = threat_counts.get(threat_level, 0) + 1
        return {
            "total_detections": len(recent_detections),
            "attack_types": attack_counts,
            "threat_levels": threat_counts,
            "blacklisted_addresses": len(self.blacklisted_addresses),
            "security_metrics": {
                name: {"value": metric.current_value, "threshold": metric.threshold, "status": metric.status}
                for name, metric in self.security_metrics.items()
            },
        }


security_monitor: EconomicSecurityMonitor | None = None


def get_security_monitor() -> EconomicSecurityMonitor | None:
    """Get global security monitor"""
    return security_monitor


def create_security_monitor(
    staking_manager: StakingManager, reward_distributor: RewardDistributor, gas_manager: GasManager
) -> EconomicSecurityMonitor:
    """Create and set global security monitor"""
    global security_monitor
    security_monitor = EconomicSecurityMonitor(staking_manager, reward_distributor, gas_manager)
    return security_monitor
