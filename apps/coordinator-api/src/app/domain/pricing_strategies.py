"""
Pricing Strategies Domain Module
Defines various pricing strategies and their configurations for dynamic pricing
"""

from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import StrEnum
from typing import Any


class PricingStrategy(StrEnum):
    """Dynamic pricing strategy types"""

    AGGRESSIVE_GROWTH = "aggressive_growth"
    PROFIT_MAXIMIZATION = "profit_maximization"
    MARKET_BALANCE = "market_balance"
    COMPETITIVE_RESPONSE = "competitive_response"
    DEMAND_ELASTICITY = "demand_elasticity"
    PENETRATION_PRICING = "penetration_pricing"
    PREMIUM_PRICING = "premium_pricing"
    COST_PLUS = "cost_plus"
    VALUE_BASED = "value_based"
    COMPETITOR_BASED = "competitor_based"


class StrategyPriority(StrEnum):
    """Strategy priority levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskTolerance(StrEnum):
    """Risk tolerance levels for pricing strategies"""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass
class StrategyParameters:
    """Parameters for pricing strategy configuration"""

    # Base pricing parameters
    base_multiplier: float = 1.0
    min_price_margin: float = 0.1  # 10% minimum margin
    max_price_margin: float = 2.0  # 200% maximum margin

    # Market sensitivity parameters
    demand_sensitivity: float = 0.5  # 0-1, how much demand affects price
    supply_sensitivity: float = 0.3  # 0-1, how much supply affects price
    competition_sensitivity: float = 0.4  # 0-1, how much competition affects price

    # Time-based parameters
    peak_hour_multiplier: float = 1.2
    off_peak_multiplier: float = 0.8
    weekend_multiplier: float = 1.1

    # Performance parameters
    performance_bonus_rate: float = 0.1  # 10% bonus for high performance
    performance_penalty_rate: float = 0.05  # 5% penalty for low performance

    # Risk management parameters
    max_price_change_percent: float = 0.3  # Maximum 30% change per update
    volatility_threshold: float = 0.2  # Trigger for circuit breaker
    confidence_threshold: float = 0.7  # Minimum confidence for price changes

    # Strategy-specific parameters
    growth_target_rate: float = 0.15  # 15% growth target for growth strategies
    profit_target_margin: float = 0.25  # 25% profit target for profit strategies
    market_share_target: float = 0.1  # 10% market share target

    # Regional parameters
    regional_adjustments: dict[str, float] = field(default_factory=dict)

    # Custom parameters
    custom_parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyRule:
    """Individual rule within a pricing strategy"""

    rule_id: str
    name: str
    description: str
    condition: str  # Expression that evaluates to True/False
    action: str  # Action to take when condition is met
    priority: StrategyPriority
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now(datetime.UTC))

    # Rule execution tracking
    execution_count: int = 0
    last_executed: datetime | None = None
    success_rate: float = 1.0


@dataclass
class PricingStrategyConfig:
    """Complete configuration for a pricing strategy"""

    strategy_id: str
    name: str
    description: str
    strategy_type: PricingStrategy
    parameters: StrategyParameters
    rules: list[StrategyRule] = field(default_factory=list)

    # Strategy metadata
    risk_tolerance: RiskTolerance = RiskTolerance.MODERATE
    priority: StrategyPriority = StrategyPriority.MEDIUM
    auto_optimize: bool = True
    learning_enabled: bool = True

    # Strategy constraints
    min_price: float | None = None
    max_price: float | None = None
    resource_types: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)

    # Performance tracking
    created_at: datetime = field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = field(default_factory=datetime.now(datetime.UTC))
    last_applied: datetime | None = None

    # Strategy effectiveness metrics
    total_revenue_impact: float = 0.0
    market_share_impact: float = 0.0
    customer_satisfaction_impact: float = 0.0
    strategy_effectiveness_score: float = 0.0


class StrategyLibrary:
    """Library of predefined pricing strategies"""

    @staticmethod
    def get_aggressive_growth_strategy() -> PricingStrategyConfig:
        """Get aggressive growth strategy configuration"""

        parameters = StrategyParameters(
            base_multiplier=0.85,
            min_price_margin=0.05,  # Lower margins for growth
            max_price_margin=1.5,
            demand_sensitivity=0.3,  # Less sensitive to demand
            supply_sensitivity=0.2,
            competition_sensitivity=0.6,  # Highly competitive
            peak_hour_multiplier=1.1,
            off_peak_multiplier=0.7,
            weekend_multiplier=1.05,
            performance_bonus_rate=0.05,
            performance_penalty_rate=0.02,
            growth_target_rate=0.25,  # 25% growth target
            market_share_target=0.15,  # 15% market share target
        )

        rules = [
            StrategyRule(
                rule_id="growth_competitive_undercut",
                name="Competitive Undercutting",
                description="Undercut competitors by 5% to gain market share",
                condition="competitor_price > 0 and current_price > competitor_price * 0.95",
                action="set_price = competitor_price * 0.95",
                priority=StrategyPriority.HIGH,
            ),
            StrategyRule(
                rule_id="growth_volume_discount",
                name="Volume Discount",
                description="Offer discounts for high-volume customers",
                condition="customer_volume > threshold and customer_loyalty < 6_months",
                action="apply_discount = 0.1",
                priority=StrategyPriority.MEDIUM,
            ),
        ]

        return PricingStrategyConfig(
            strategy_id="aggressive_growth_v1",
            name="Aggressive Growth Strategy",
            description="Focus on rapid market share acquisition through competitive pricing",
            strategy_type=PricingStrategy.AGGRESSIVE_GROWTH,
            parameters=parameters,
            rules=rules,
            risk_tolerance=RiskTolerance.AGGRESSIVE,
            priority=StrategyPriority.HIGH,
        )

    @staticmethod
    def get_profit_maximization_strategy() -> PricingStrategyConfig:
        """Get profit maximization strategy configuration"""

        parameters = StrategyParameters(
            base_multiplier=1.25,
            min_price_margin=0.3,  # Higher margins for profit
            max_price_margin=3.0,
            demand_sensitivity=0.7,  # Highly sensitive to demand
            supply_sensitivity=0.4,
            competition_sensitivity=0.2,  # Less competitive focus
            peak_hour_multiplier=1.4,
            off_peak_multiplier=1.0,
            weekend_multiplier=1.2,
            performance_bonus_rate=0.15,
            performance_penalty_rate=0.08,
            profit_target_margin=0.35,  # 35% profit target
            max_price_change_percent=0.2,  # More conservative changes
        )

        rules = [
            StrategyRule(
                rule_id="profit_demand_premium",
                name="Demand Premium Pricing",
                description="Apply premium pricing during high demand periods",
                condition="demand_level > 0.8 and competitor_capacity < 0.7",
                action="set_price = current_price * 1.3",
                priority=StrategyPriority.CRITICAL,
            ),
            StrategyRule(
                rule_id="profit_performance_premium",
                name="Performance Premium",
                description="Charge premium for high-performance resources",
                condition="performance_score > 0.9 and customer_satisfaction > 0.85",
                action="apply_premium = 0.2",
                priority=StrategyPriority.HIGH,
            ),
        ]

        return PricingStrategyConfig(
            strategy_id="profit_maximization_v1",
            name="Profit Maximization Strategy",
            description="Maximize profit margins through premium pricing and demand capture",
            strategy_type=PricingStrategy.PROFIT_MAXIMIZATION,
            parameters=parameters,
            rules=rules,
            risk_tolerance=RiskTolerance.MODERATE,
            priority=StrategyPriority.HIGH,
        )

    @staticmethod
    def get_market_balance_strategy() -> PricingStrategyConfig:
        """Get market balance strategy configuration"""

        parameters = StrategyParameters(
            base_multiplier=1.0,
            min_price_margin=0.15,
            max_price_margin=2.0,
            demand_sensitivity=0.5,
            supply_sensitivity=0.3,
            competition_sensitivity=0.4,
            peak_hour_multiplier=1.2,
            off_peak_multiplier=0.8,
            weekend_multiplier=1.1,
            performance_bonus_rate=0.1,
            performance_penalty_rate=0.05,
            volatility_threshold=0.15,  # Lower volatility threshold
            confidence_threshold=0.8,  # Higher confidence requirement
        )

        rules = [
            StrategyRule(
                rule_id="balance_market_follow",
                name="Market Following",
                description="Follow market trends while maintaining stability",
                condition="market_trend == increasing and price_position < market_average",
                action="adjust_price = market_average * 0.98",
                priority=StrategyPriority.MEDIUM,
            ),
            StrategyRule(
                rule_id="balance_stability_maintain",
                name="Stability Maintenance",
                description="Maintain price stability during volatile periods",
                condition="volatility > 0.15 and confidence < 0.7",
                action="freeze_price = true",
                priority=StrategyPriority.HIGH,
            ),
        ]

        return PricingStrategyConfig(
            strategy_id="market_balance_v1",
            name="Market Balance Strategy",
            description="Maintain balanced pricing that follows market trends while ensuring stability",
            strategy_type=PricingStrategy.MARKET_BALANCE,
            parameters=parameters,
            rules=rules,
            risk_tolerance=RiskTolerance.MODERATE,
            priority=StrategyPriority.MEDIUM,
        )

    @staticmethod
    def get_competitive_response_strategy() -> PricingStrategyConfig:
        """Get competitive response strategy configuration"""

        parameters = StrategyParameters(
            base_multiplier=0.95,
            min_price_margin=0.1,
            max_price_margin=1.8,
            demand_sensitivity=0.4,
            supply_sensitivity=0.3,
            competition_sensitivity=0.8,  # Highly competitive
            peak_hour_multiplier=1.15,
            off_peak_multiplier=0.85,
            weekend_multiplier=1.05,
            performance_bonus_rate=0.08,
            performance_penalty_rate=0.03,
        )

        rules = [
            StrategyRule(
                rule_id="competitive_price_match",
                name="Price Matching",
                description="Match or beat competitor prices",
                condition="competitor_price < current_price * 0.95",
                action="set_price = competitor_price * 0.98",
                priority=StrategyPriority.CRITICAL,
            ),
            StrategyRule(
                rule_id="competitive_promotion_response",
                name="Promotion Response",
                description="Respond to competitor promotions",
                condition="competitor_promotion == true and market_share_declining",
                action="apply_promotion = competitor_promotion_rate * 1.1",
                priority=StrategyPriority.HIGH,
            ),
        ]

        return PricingStrategyConfig(
            strategy_id="competitive_response_v1",
            name="Competitive Response Strategy",
            description="Reactively respond to competitor pricing actions to maintain market position",
            strategy_type=PricingStrategy.COMPETITIVE_RESPONSE,
            parameters=parameters,
            rules=rules,
            risk_tolerance=RiskTolerance.MODERATE,
            priority=StrategyPriority.HIGH,
        )

    @staticmethod
    def get_demand_elasticity_strategy() -> PricingStrategyConfig:
        """Get demand elasticity strategy configuration"""

        parameters = StrategyParameters(
            base_multiplier=1.0,
            min_price_margin=0.12,
            max_price_margin=2.2,
            demand_sensitivity=0.8,  # Highly sensitive to demand
            supply_sensitivity=0.3,
            competition_sensitivity=0.4,
            peak_hour_multiplier=1.3,
            off_peak_multiplier=0.7,
            weekend_multiplier=1.1,
            performance_bonus_rate=0.1,
            performance_penalty_rate=0.05,
            max_price_change_percent=0.4,  # Allow larger changes for elasticity
        )

        rules = [
            StrategyRule(
                rule_id="elasticity_demand_capture",
                name="Demand Capture",
                description="Aggressively price to capture demand surges",
                condition="demand_growth_rate > 0.2 and supply_constraint == true",
                action="set_price = current_price * 1.25",
                priority=StrategyPriority.HIGH,
            ),
            StrategyRule(
                rule_id="elasticity_demand_stimulation",
                name="Demand Stimulation",
                description="Lower prices to stimulate demand during lulls",
                condition="demand_level < 0.4 and inventory_turnover < threshold",
                action="apply_discount = 0.15",
                priority=StrategyPriority.MEDIUM,
            ),
        ]

        return PricingStrategyConfig(
            strategy_id="demand_elasticity_v1",
            name="Demand Elasticity Strategy",
            description="Dynamically adjust prices based on demand elasticity to optimize revenue",
            strategy_type=PricingStrategy.DEMAND_ELASTICITY,
            parameters=parameters,
            rules=rules,
            risk_tolerance=RiskTolerance.AGGRESSIVE,
            priority=StrategyPriority.MEDIUM,
        )

    @staticmethod
    def get_penetration_pricing_strategy() -> PricingStrategyConfig:
        """Get penetration pricing strategy configuration"""

        parameters = StrategyParameters(
            base_multiplier=0.7,  # Low initial prices
            min_price_margin=0.05,
            max_price_margin=1.5,
            demand_sensitivity=0.3,
            supply_sensitivity=0.2,
            competition_sensitivity=0.7,
            peak_hour_multiplier=1.0,
            off_peak_multiplier=0.6,
            weekend_multiplier=0.9,
            growth_target_rate=0.3,  # 30% growth target
            market_share_target=0.2,  # 20% market share target
        )

        rules = [
            StrategyRule(
                rule_id="penetration_market_entry",
                name="Market Entry Pricing",
                description="Very low prices for new market entry",
                condition="market_share < 0.05 and time_in_market < 6_months",
                action="set_price = cost * 1.1",
                priority=StrategyPriority.CRITICAL,
            ),
            StrategyRule(
                rule_id="penetration_gradual_increase",
                name="Gradual Price Increase",
                description="Gradually increase prices after market penetration",
                condition="market_share > 0.1 and customer_loyalty > 12_months",
                action="increase_price = 0.05",
                priority=StrategyPriority.MEDIUM,
            ),
        ]

        return PricingStrategyConfig(
            strategy_id="penetration_pricing_v1",
            name="Penetration Pricing Strategy",
            description="Low initial prices to gain market share, followed by gradual increases",
            strategy_type=PricingStrategy.PENETRATION_PRICING,
            parameters=parameters,
            rules=rules,
            risk_tolerance=RiskTolerance.AGGRESSIVE,
            priority=StrategyPriority.HIGH,
        )

    @staticmethod
    def get_premium_pricing_strategy() -> PricingStrategyConfig:
        """Get premium pricing strategy configuration"""

        parameters = StrategyParameters(
            base_multiplier=1.8,  # High base prices
            min_price_margin=0.5,
            max_price_margin=4.0,
            demand_sensitivity=0.2,  # Less sensitive to demand
            supply_sensitivity=0.3,
            competition_sensitivity=0.1,  # Ignore competition
            peak_hour_multiplier=1.5,
            off_peak_multiplier=1.2,
            weekend_multiplier=1.4,
            performance_bonus_rate=0.2,
            performance_penalty_rate=0.1,
            profit_target_margin=0.4,  # 40% profit target
        )

        rules = [
            StrategyRule(
                rule_id="premium_quality_assurance",
                name="Quality Assurance Premium",
                description="Maintain premium pricing for quality assurance",
                condition="quality_score > 0.95 and brand_recognition > high",
                action="maintain_premium = true",
                priority=StrategyPriority.CRITICAL,
            ),
            StrategyRule(
                rule_id="premium_exclusivity",
                name="Exclusivity Pricing",
                description="Premium pricing for exclusive features",
                condition="exclusive_features == true and customer_segment == premium",
                action="apply_premium = 0.3",
                priority=StrategyPriority.HIGH,
            ),
        ]

        return PricingStrategyConfig(
            strategy_id="premium_pricing_v1",
            name="Premium Pricing Strategy",
            description="High-end pricing strategy focused on quality and exclusivity",
            strategy_type=PricingStrategy.PREMIUM_PRICING,
            parameters=parameters,
            rules=rules,
            risk_tolerance=RiskTolerance.CONSERVATIVE,
            priority=StrategyPriority.MEDIUM,
        )

    @staticmethod
    def get_all_strategies() -> dict[PricingStrategy, PricingStrategyConfig]:
        """Get all available pricing strategies"""

        return {
            PricingStrategy.AGGRESSIVE_GROWTH: StrategyLibrary.get_aggressive_growth_strategy(),
            PricingStrategy.PROFIT_MAXIMIZATION: StrategyLibrary.get_profit_maximization_strategy(),
            PricingStrategy.MARKET_BALANCE: StrategyLibrary.get_market_balance_strategy(),
            PricingStrategy.COMPETITIVE_RESPONSE: StrategyLibrary.get_competitive_response_strategy(),
            PricingStrategy.DEMAND_ELASTICITY: StrategyLibrary.get_demand_elasticity_strategy(),
            PricingStrategy.PENETRATION_PRICING: StrategyLibrary.get_penetration_pricing_strategy(),
            PricingStrategy.PREMIUM_PRICING: StrategyLibrary.get_premium_pricing_strategy(),
        }


class StrategyOptimizer:
    """Optimizes pricing strategies based on performance data"""

    def __init__(self):
        self.performance_history: dict[str, list[dict[str, Any]]] = {}
        self.optimization_rules = self._initialize_optimization_rules()

    def optimize_strategy(
        self, strategy_config: PricingStrategyConfig, performance_data: dict[str, Any]
    ) -> PricingStrategyConfig:
        """Optimize strategy parameters based on performance"""

        strategy_id = strategy_config.strategy_id

        # Store performance data
        if strategy_id not in self.performance_history:
            self.performance_history[strategy_id] = []

        self.performance_history[strategy_id].append({"timestamp": datetime.now(datetime.UTC), "performance": performance_data})

        # Apply optimization rules
        optimized_config = self._apply_optimization_rules(strategy_config, performance_data)

        # Update strategy effectiveness score
        optimized_config.strategy_effectiveness_score = self._calculate_effectiveness_score(performance_data)

        return optimized_config

    def _initialize_optimization_rules(self) -> list[dict[str, Any]]:
        """Initialize optimization rules"""

        return [
            {
                "name": "Revenue Optimization",
                "condition": "revenue_growth < target and price_elasticity > 0.5",
                "action": "decrease_base_multiplier",
                "adjustment": -0.05,
            },
            {
                "name": "Margin Protection",
                "condition": "profit_margin < minimum and demand_inelastic",
                "action": "increase_base_multiplier",
                "adjustment": 0.03,
            },
            {
                "name": "Market Share Growth",
                "condition": "market_share_declining and competitive_pressure_high",
                "action": "increase_competition_sensitivity",
                "adjustment": 0.1,
            },
            {
                "name": "Volatility Reduction",
                "condition": "price_volatility > threshold and customer_complaints_high",
                "action": "decrease_max_price_change",
                "adjustment": -0.1,
            },
            {
                "name": "Demand Capture",
                "condition": "demand_surge_detected and capacity_available",
                "action": "increase_demand_sensitivity",
                "adjustment": 0.15,
            },
        ]

    def _apply_optimization_rules(
        self, strategy_config: PricingStrategyConfig, performance_data: dict[str, Any]
    ) -> PricingStrategyConfig:
        """Apply optimization rules to strategy configuration"""

        # Create a copy to avoid modifying the original
        optimized_config = PricingStrategyConfig(
            strategy_id=strategy_config.strategy_id,
            name=strategy_config.name,
            description=strategy_config.description,
            strategy_type=strategy_config.strategy_type,
            parameters=StrategyParameters(
                base_multiplier=strategy_config.parameters.base_multiplier,
                min_price_margin=strategy_config.parameters.min_price_margin,
                max_price_margin=strategy_config.parameters.max_price_margin,
                demand_sensitivity=strategy_config.parameters.demand_sensitivity,
                supply_sensitivity=strategy_config.parameters.supply_sensitivity,
                competition_sensitivity=strategy_config.parameters.competition_sensitivity,
                peak_hour_multiplier=strategy_config.parameters.peak_hour_multiplier,
                off_peak_multiplier=strategy_config.parameters.off_peak_multiplier,
                weekend_multiplier=strategy_config.parameters.weekend_multiplier,
                performance_bonus_rate=strategy_config.parameters.performance_bonus_rate,
                performance_penalty_rate=strategy_config.parameters.performance_penalty_rate,
                max_price_change_percent=strategy_config.parameters.max_price_change_percent,
                volatility_threshold=strategy_config.parameters.volatility_threshold,
                confidence_threshold=strategy_config.parameters.confidence_threshold,
                growth_target_rate=strategy_config.parameters.growth_target_rate,
                profit_target_margin=strategy_config.parameters.profit_target_margin,
                market_share_target=strategy_config.parameters.market_share_target,
                regional_adjustments=strategy_config.parameters.regional_adjustments.copy(),
                custom_parameters=strategy_config.parameters.custom_parameters.copy(),
            ),
            rules=strategy_config.rules.copy(),
            risk_tolerance=strategy_config.risk_tolerance,
            priority=strategy_config.priority,
            auto_optimize=strategy_config.auto_optimize,
            learning_enabled=strategy_config.learning_enabled,
            min_price=strategy_config.min_price,
            max_price=strategy_config.max_price,
            resource_types=strategy_config.resource_types.copy(),
            regions=strategy_config.regions.copy(),
        )

        # Apply each optimization rule
        for rule in self.optimization_rules:
            if self._evaluate_rule_condition(rule["condition"], performance_data):
                self._apply_rule_action(optimized_config, rule["action"], rule["adjustment"])

        return optimized_config

    def _evaluate_rule_condition(self, condition: str, performance_data: dict[str, Any]) -> bool:
        """Evaluate optimization rule condition"""

        # Simple condition evaluation (in production, use a proper expression evaluator)
        try:
            # Replace variables with actual values
            condition_eval = condition

            # Common performance metrics
            metrics = {
                "revenue_growth": performance_data.get("revenue_growth", 0),
                "price_elasticity": performance_data.get("price_elasticity", 0.5),
                "profit_margin": performance_data.get("profit_margin", 0.2),
                "market_share_declining": performance_data.get("market_share_declining", False),
                "competitive_pressure_high": performance_data.get("competitive_pressure_high", False),
                "price_volatility": performance_data.get("price_volatility", 0.1),
                "customer_complaints_high": performance_data.get("customer_complaints_high", False),
                "demand_surge_detected": performance_data.get("demand_surge_detected", False),
                "capacity_available": performance_data.get("capacity_available", True),
            }

            # Simple condition parsing
            for key, value in metrics.items():
                condition_eval = condition_eval.replace(key, str(value))

            # Evaluate simple conditions
            if "and" in condition_eval:
                parts = condition_eval.split(" and ")
                return all(self._evaluate_simple_condition(part.strip()) for part in parts)
            else:
                return self._evaluate_simple_condition(condition_eval.strip())

        except Exception:
            return False

    def _evaluate_simple_condition(self, condition: str) -> bool:
        """Evaluate a simple condition"""

        try:
            # Handle common comparison operators
            if "<" in condition:
                left, right = condition.split("<", 1)
                return float(left.strip()) < float(right.strip())
            elif ">" in condition:
                left, right = condition.split(">", 1)
                return float(left.strip()) > float(right.strip())
            elif "==" in condition:
                left, right = condition.split("==", 1)
                return left.strip() == right.strip()
            elif "True" in condition:
                return True
            elif "False" in condition:
                return False
            else:
                return bool(condition)

        except Exception:
            return False

    def _apply_rule_action(self, config: PricingStrategyConfig, action: str, adjustment: float):
        """Apply optimization rule action"""

        if action == "decrease_base_multiplier":
            config.parameters.base_multiplier = max(0.5, config.parameters.base_multiplier + adjustment)
        elif action == "increase_base_multiplier":
            config.parameters.base_multiplier = min(2.0, config.parameters.base_multiplier + adjustment)
        elif action == "increase_competition_sensitivity":
            config.parameters.competition_sensitivity = min(1.0, config.parameters.competition_sensitivity + adjustment)
        elif action == "decrease_max_price_change":
            config.parameters.max_price_change_percent = max(0.1, config.parameters.max_price_change_percent + adjustment)
        elif action == "increase_demand_sensitivity":
            config.parameters.demand_sensitivity = min(1.0, config.parameters.demand_sensitivity + adjustment)

    def _calculate_effectiveness_score(self, performance_data: dict[str, Any]) -> float:
        """Calculate overall strategy effectiveness score"""

        # Weight different performance metrics
        weights = {
            "revenue_growth": 0.3,
            "profit_margin": 0.25,
            "market_share": 0.2,
            "customer_satisfaction": 0.15,
            "price_stability": 0.1,
        }

        score = 0.0
        total_weight = 0.0

        for metric, weight in weights.items():
            if metric in performance_data:
                value = performance_data[metric]
                # Normalize values to 0-1 scale
                if metric in ["revenue_growth", "profit_margin", "market_share", "customer_satisfaction"]:
                    normalized_value = min(1.0, max(0.0, value))
                else:  # price_stability (lower is better, so invert)
                    normalized_value = min(1.0, max(0.0, 1.0 - value))

                score += normalized_value * weight
                total_weight += weight

        return score / total_weight if total_weight > 0 else 0.5
