# Marketplace Analytics

## Overview

The MarketAnalytics service provides real-time market metrics, trend analysis, and forecasting.

## Features

### Real-Time Metrics
- Total/available/booked GPU counts
- Capacity utilization
- Average pricing
- Active bookings count

### Trend Analysis
- Booking trends over time
- Price trends
- Utilization trends
- Direction indicators

### Forecasting
- Booking forecasts
- Price forecasts
- Utilization forecasts
- Confidence intervals

## Usage Example

```python
from app.contexts.marketplace.services.market_analytics import MarketAnalytics

analytics = MarketAnalytics(session)

# Get real-time metrics
metrics = analytics.get_realtime_metrics()

# Analyze trends
trends = analytics.analyze_trends(hours=24)

# Generate forecasts
forecasts = analytics.generate_forecasts(hours_ahead=48)

# Track events
analytics.track_event(
    event_type="booking",
    resource_id="gpu-789",
    metadata={"user_id": "user-123", "duration": 4}
)
```
