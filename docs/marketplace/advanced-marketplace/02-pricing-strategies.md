# Advanced Pricing Strategies

## Overview

The DynamicPricingEngine has been extended with four new pricing strategies in addition to the existing five strategies.

## New Strategies

### TIME_BASED
- **Description:** Peak/off-peak pricing with time-based adjustments
- **Configuration:**
  - `peak_hours_multiplier`: 1.3 (default)
  - `off_peak_multiplier`: 0.8 (default)
  - `weekend_multiplier`: 0.9 (default)
  - `hourly_sensitivity`: 0.5 (default)
- **Use Case:** Adjust prices based on time of day and day of week

### REPUTATION_BASED
- **Description:** Pricing adjusted based on provider reputation and performance
- **Configuration:**
  - `reputation_weight`: 0.6 (default)
  - `performance_weight`: 0.3 (default)
  - `history_weight`: 0.1 (default)
- **Use Case:** Reward high-reputation providers with premium pricing

### MULTI_FACTOR
- **Description:** Weighted combination of multiple pricing factors
- **Configuration:**
  - `demand_weight`: 0.25
  - `supply_weight`: 0.20
  - `time_weight`: 0.15
  - `reputation_weight`: 0.15
  - `competition_weight`: 0.15
  - `regional_weight`: 0.10
- **Use Case:** Balanced pricing considering all market factors

### PREDICTIVE
- **Description:** ML-based price forecasting with confidence intervals
- **Configuration:**
  - `forecast_weight`: 0.5
  - `current_weight`: 0.3
  - `trend_weight`: 0.2
  - `ml_confidence_threshold`: 0.7
- **Use Case:** Predictive pricing based on market trends

## Usage Example

```python
from app.contexts.trading.services.trading_marketplace.dynamic_pricing import DynamicPricingEngine, PricingStrategy

# Initialize engine
engine = DynamicPricingEngine({
    "min_price": 0.001,
    "max_price": 1000.0,
    "update_interval": 300,
    "forecast_horizon": 72
})

# Set strategy for a provider
await engine.set_provider_strategy(
    provider_id="provider-123",
    strategy=PricingStrategy.TIME_BASED
)

# Calculate dynamic price
result = await engine.calculate_dynamic_price(
    resource_id="gpu-456",
    resource_type=ResourceType.GPU,
    base_price=0.50,
    strategy=PricingStrategy.TIME_BASED
)
```
