"""
Economic Attack Prevention
Detects and prevents various economic attacks on the network
"""

import asyncio
import time
import json
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum

from .staking import StakingManager
from .rewards import RewardDistributor
from .gas import GasManager

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
    evidence: Dict
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
    
    def __init__(self, staking_manager: StakingManager, reward_distributor: RewardDistributor,
                 gas_manager: GasManager):
        self.staking_manager = staking_manager
        self.reward_distributor = reward_distributor
        self.gas_manager = gas_manager
        
        self.detection_rules = self._initialize_detection_rules()
        self.attack_detections: List[AttackDetection] = []
        self.security_metrics: Dict[str, SecurityMetric] = {}
        self.blacklisted_addresses: Set[str] = set()
        
        # Monitoring parameters
        self.monitoring_interval = 60  # seconds
        self.detection_history_window = 3600  # 1 hour
        self.max_false_positive_rate = 0.05  # 5%
        
        # Initialize security metrics
        self._initialize_security_metrics()
    
    def _initialize_detection_rules(self) -> Dict[AttackType, Dict]:
        """Initialize detection rules for different attack types"""
        return {
            AttackType.SYBIL: {
                'threshold': 0.1,  # 10% of validators from same entity
                'min_stake': 1000.0,
                'time_window': 86400,  # 24 hours
                'max_similar_addresses': 5
            },
            AttackType.STAKE_GRINDING: {
                'threshold': 0.3,  # 30% stake variation
                'min_operations': 10,
                'time_window': 3600,  # 1 hour
                'max_withdrawal_frequency': 5
            },
            AttackType.NOTHING_AT_STAKE: {
                'threshold': 0.5,  # 50% abstention rate
                'min_validators': 10,
                'time_window': 7200,  # 2 hours
                'max_abstention_periods': 3
            },
            AttackType.LONG_RANGE: {
                'threshold': 0.8,  # 80% stake from old keys
                'min_history_depth': 1000,
                'time_window': 604800,  # 1 week
                'max_key_reuse': 2
            },
            AttackType.FRONT_RUNNING: {
                'threshold': 0.1,  # 10% transaction front-running
                'min_transactions': 100,
                'time_window': 3600,  # 1 hour
                'max_mempool_advantage': 0.05
            },
            AttackType.GAS_MANIPULATION: {
                'threshold': 2.0,  # 2x price manipulation
                'min_price_changes': 5,
                'time_window': 1800,  # 30 minutes
                'max_spikes_per_hour': 3
            }
        }
    
    def _initialize_security_metrics(self):
        """Initialize security monitoring metrics"""
        self.security_metrics = {
            'validator_diversity': SecurityMetric(
                metric_name='validator_diversity',
                current_value=0.0,
                threshold=0.7,
                status='healthy',
                last_updated=time.time()
            ),
            'stake_distribution': SecurityMetric(
                metric_name='stake_distribution',
                current_value=0.0,
                threshold=0.8,
                status='healthy',
                last_updated=time.time()
            ),
            'reward_distribution': SecurityMetric(
                metric_name='reward_distribution',
                current_value=0.0,
                threshold=0.9,
                status='healthy',
                last_updated=time.time()
            ),
            'gas_price_stability': SecurityMetric(
                metric_name='gas_price_stability',
                current_value=0.0,
                threshold=0.3,
                status='healthy',
                last_updated=time.time()
            )
        }
    
    async def start_monitoring(self):
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
    
    async def _monitor_security_metrics(self):
        """Monitor security metrics"""
        current_time = time.time()
        
        # Update validator diversity
        await self._update_validator_diversity(current_time)
        
        # Update stake distribution
        await self._update_stake_distribution(current_time)
        
        # Update reward distribution
        await self._update_reward_distribution(current_time)
        
        # Update gas price stability
        await self._update_gas_price_stability(current_time)
    
    async def _update_validator_diversity(self, current_time: float):
        """Update validator diversity metric"""
        validators = self.staking_manager.get_active_validators()
        
        if len(validators) < 10:
            diversity_score = 0.0
        else:
            # Calculate diversity based on stake distribution
            total_stake = sum(v.total_stake for v in validators)
            if total_stake == 0:
                diversity_score = 0.0
            else:
                # Use Herfindahl-Hirschman Index
                stake_shares = [float(v.total_stake / total_stake) for v in validators]
                hhi = sum(share ** 2 for share in stake_shares)
                diversity_score = 1.0 - hhi
        
        metric = self.security_metrics['validator_diversity']
        metric.current_value = diversity_score
        metric.last_updated = current_time
        
        if diversity_score < metric.threshold:
            metric.status = 'warning'
        else:
            metric.status = 'healthy'
    
    async def _update_stake_distribution(self, current_time: float):
        """Update stake distribution metric"""
        validators = self.staking_manager.get_active_validators()
        
        if not validators:
            distribution_score = 0.0
        else:
            # Check for concentration (top 3 validators)
            stakes = [float(v.total_stake) for v in validators]
            stakes.sort(reverse=True)
            
            total_stake = sum(stakes)
            if total_stake == 0:
                distribution_score = 0.0
            else:
                top3_share = sum(stakes[:3]) / total_stake
                distribution_score = 1.0 - top3_share
        
        metric = self.security_metrics['stake_distribution']
        metric.current_value = distribution_score
        metric.last_updated = current_time
        
        if distribution_score < metric.threshold:
            metric.status = 'warning'
        else:
            metric.status = 'healthy'
    
    async def _update_reward_distribution(self, current_time: float):
        """Update reward distribution metric"""
        distributions = self.reward_distributor.get_distribution_history(limit=10)
        
        if len(distributions) < 5:
            distribution_score = 1.0  # Not enough data
        else:
            # Check for reward concentration
            total_rewards = sum(dist.total_rewards for dist in distributions)
            if total_rewards == 0:
                distribution_score = 0.0
            else:
                # Calculate variance in reward distribution
                validator_rewards = []
                for dist in distributions:
                    validator_rewards.extend(dist.validator_rewards.values())
                
                if not validator_rewards:
                    distribution_score = 0.0
                else:
                    avg_reward = sum(validator_rewards) / len(validator_rewards)
                    variance = sum((r - avg_reward) ** 2 for r in validator_rewards) / len(validator_rewards)
                    cv = (variance ** 0.5) / avg_reward if avg_reward > 0 else 0
                    distribution_score = max(0.0, 1.0 - cv)
        
        metric = self.security_metrics['reward_distribution']
        metric.current_value = distribution_score
        metric.last_updated = current_time
        
        if distribution_score < metric.threshold:
            metric.status = 'warning'
        else:
            metric.status = 'healthy'
    
    async def _update_gas_price_stability(self, current_time: float):
        """Update gas price stability metric"""
        gas_stats = self.gas_manager.get_gas_statistics()
        
        if gas_stats['price_history_length'] < 10:
            stability_score = 1.0  # Not enough data
        else:
            stability_score = 1.0 - gas_stats['price_volatility']
        
        metric = self.security_metrics['gas_price_stability']
        metric.current_value = stability_score
        metric.last_updated = current_time
        
        if stability_score < metric.threshold:
            metric.status = 'warning'
        else:
            metric.status = 'healthy'
    
    async def _detect_attacks(self):
        """Detect potential economic attacks"""
        current_time = time.time()
        
        # Detect Sybil attacks
        await self._detect_sybil_attacks(current_time)
        
        # Detect stake grinding
        await self._detect_stake_grinding(current_time)
        
        # Detect nothing-at-stake
        await self._detect_nothing_at_stake(current_time)
        
        # Detect long-range attacks
        await self._detect_long_range_attacks(current_time)
        
        # Detect front-running
        await self._detect_front_running(current_time)
        
        # Detect gas manipulation
        await self._detect_gas_manipulation(current_time)
    
    async def _detect_sybil_attacks(self, current_time: float):
        """Detect Sybil attacks (multiple identities)"""
        rule = self.detection_rules[AttackType.SYBIL]
        validators = self.staking_manager.get_active_validators()
        
        # Group validators by similar characteristics
        address_groups = {}
        for validator in validators:
            # Simple grouping by address prefix (more sophisticated in real implementation)
            prefix = validator.validator_address[:8]
            if prefix not in address_groups:
                address_groups[prefix] = []
            address_groups[prefix].append(validator)
        
        # Check for suspicious groups
        for prefix, group in address_groups.items():
            if len(group) >= rule['max_similar_addresses']:
                # Calculate threat level
                group_stake = sum(v.total_stake for v in group)
                total_stake = sum(v.total_stake for v in validators)
                stake_ratio = float(group_stake / total_stake) if total_stake > 0 else 0
                
                if stake_ratio > rule['threshold']:
                    threat_level = ThreatLevel.HIGH
                elif stake_ratio > rule['threshold'] * 0.5:
                    threat_level = ThreatLevel.MEDIUM
                else:
                    threat_level = ThreatLevel.LOW
                
                # Create detection
                detection = AttackDetection(
                    attack_type=AttackType.SYBIL,
                    threat_level=threat_level,
                    attacker_address=prefix,
                    evidence={
                        'similar_addresses': [v.validator_address for v in group],
                        'group_size': len(group),
                        'stake_ratio': stake_ratio,
                        'common_prefix': prefix
                    },
                    detected_at=current_time,
                    confidence=0.8,
                    recommended_action='Investigate validator identities'
                )
                
                self.attack_detections.append(detection)
    
    async def _detect_stake_grinding(self, current_time: float):
        """Detect stake grinding attacks"""
        rule = self.detection_rules[AttackType.STAKE_GRINDING]
        
        # Check for frequent stake changes
        recent_detections = [
            d for d in self.attack_detections
            if d.attack_type == AttackType.STAKE_GRINDING and
            current_time - d.detected_at < rule['time_window']
        ]
        
        # This would analyze staking patterns (simplified here)
        # In real implementation, would track stake movements over time
        
        pass  # Placeholder for stake grinding detection
    
    async def _detect_nothing_at_stake(self, current_time: float):
        """Detect nothing-at-stake attacks"""
        rule = self.detection_rules[AttackType.NOTHING_AT_STAKE]
        
        # Check for validator participation rates
        # This would require consensus participation data
        
        pass  # Placeholder for nothing-at-stake detection
    
    async def _detect_long_range_attacks(self, current_time: float):
        """Detect long-range attacks"""
        rule = self.detection_rules[AttackType.LONG_RANGE]
        
        # Check for key reuse from old blockchain states
        # This would require historical blockchain data
        
        pass  # Placeholder for long-range attack detection
    
    async def _detect_front_running(self, current_time: float):
        """Detect front-running attacks"""
        rule = self.detection_rules[AttackType.FRONT_RUNNING]
        
        # Check for transaction ordering patterns
        # This would require mempool and transaction ordering data
        
        pass  # Placeholder for front-running detection
    
    async def _detect_gas_manipulation(self, current_time: float):
        """Detect gas price manipulation"""
        rule = self.detection_rules[AttackType.GAS_MANIPULATION]
        
        gas_stats = self.gas_manager.get_gas_statistics()
        
        # Check for unusual gas price spikes
        if gas_stats['price_history_length'] >= 10:
            recent_prices = [p.price_per_gas for p in self.gas_manager.price_history[-10:]]
            avg_price = sum(recent_prices) / len(recent_prices)
            
            # Look for significant spikes
            for price in recent_prices:
                if float(price / avg_price) > rule['threshold']:
                    detection = AttackDetection(
                        attack_type=AttackType.GAS_MANIPULATION,
                        threat_level=ThreatLevel.MEDIUM,
                        attacker_address="unknown",  # Would need more sophisticated detection
                        evidence={
                            'spike_ratio': float(price / avg_price),
                            'current_price': float(price),
                            'average_price': float(avg_price)
                        },
                        detected_at=current_time,
                        confidence=0.6,
                        recommended_action='Monitor gas price patterns'
                    )
                    
                    self.attack_detections.append(detection)
                    break
    
    async def _update_blacklist(self):
        """Update blacklist based on detections"""
        current_time = time.time()
        
        # Remove old detections from history
        self.attack_detections = [
            d for d in self.attack_detections
            if current_time - d.detected_at < self.detection_history_window
        ]
        
        # Add high-confidence, high-threat attackers to blacklist
        for detection in self.attack_detections:
            if (detection.threat_level in [ThreatLevel.HIGH, ThreatLevel.CRITICAL] and
                detection.confidence > 0.8 and
                detection.attacker_address not in self.blacklisted_addresses):
                
                self.blacklisted_addresses.add(detection.attacker_address)
                log_warn(f"Added {detection.attacker_address} to blacklist due to {detection.attack_type.value} attack")
    
    def is_address_blacklisted(self, address: str) -> bool:
        """Check if address is blacklisted"""
        return address in self.blacklisted_addresses
    
    def get_attack_summary(self) -> Dict:
        """Get summary of detected attacks"""
        current_time = time.time()
        recent_detections = [
            d for d in self.attack_detections
            if current_time - d.detected_at < 3600  # Last hour
        ]
        
        attack_counts = {}
        threat_counts = {}
        
        for detection in recent_detections:
            attack_type = detection.attack_type.value
            threat_level = detection.threat_level.value
            
            attack_counts[attack_type] = attack_counts.get(attack_type, 0) + 1
            threat_counts[threat_level] = threat_counts.get(threat_level, 0) + 1
        
        return {
            'total_detections': len(recent_detections),
            'attack_types': attack_counts,
            'threat_levels': threat_counts,
            'blacklisted_addresses': len(self.blacklisted_addresses),
            'security_metrics': {
                name: {
                    'value': metric.current_value,
                    'threshold': metric.threshold,
                    'status': metric.status
                }
                for name, metric in self.security_metrics.items()
            }
        }

# Global security monitor
security_monitor: Optional[EconomicSecurityMonitor] = None

def get_security_monitor() -> Optional[EconomicSecurityMonitor]:
    """Get global security monitor"""
    return security_monitor

def create_security_monitor(staking_manager: StakingManager, reward_distributor: RewardDistributor,
                           gas_manager: GasManager) -> EconomicSecurityMonitor:
    """Create and set global security monitor"""
    global security_monitor
    security_monitor = EconomicSecurityMonitor(staking_manager, reward_distributor, gas_manager)
    return security_monitor
