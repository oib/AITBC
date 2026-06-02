# Advanced GPU Marketplace Features Documentation

**Last Updated:** June 2, 2026  
**Version:** v0.5.0

## Overview

This document describes the advanced marketplace features implemented for the AITBC GPU marketplace, including advanced pricing strategies, auction types, ML-based search, analytics, external integrations, and a plugin system.

## Table of Contents

1. [Advanced Pricing Strategies](#advanced-pricing-strategies)
2. [Advanced Auction Types](#advanced-auction-types)
3. [ML-Based Search and Recommendations](#ml-based-search-and-recommendations)
4. [Marketplace Analytics](#marketplace-analytics)
5. [External Provider Integrations](#external-provider-integrations)
6. [Plugin System](#plugin-system)
7. [Database Schema](#database-schema)
8. [API Endpoints](#api-endpoints)

## Advanced Pricing Strategies

### Overview

The DynamicPricingEngine has been extended with four new pricing strategies in addition to the existing five strategies:

### New Strategies

#### TIME_BASED
- **Description:** Peak/off-peak pricing with time-based adjustments
- **Configuration:**
  - `peak_hours_multiplier`: 1.3 (default)
  - `off_peak_multiplier`: 0.8 (default)
  - `weekend_multiplier`: 0.9 (default)
  - `hourly_sensitivity`: 0.5 (default)
- **Use Case:** Adjust prices based on time of day and day of week

#### REPUTATION_BASED
- **Description:** Pricing adjusted based on provider reputation and performance
- **Configuration:**
  - `reputation_weight`: 0.6 (default)
  - `performance_weight`: 0.3 (default)
  - `history_weight`: 0.1 (default)
- **Use Case:** Reward high-reputation providers with premium pricing

#### MULTI_FACTOR
- **Description:** Weighted combination of multiple pricing factors
- **Configuration:**
  - `demand_weight`: 0.25
  - `supply_weight`: 0.20
  - `time_weight`: 0.15
  - `reputation_weight`: 0.15
  - `competition_weight`: 0.15
  - `regional_weight`: 0.10
- **Use Case:** Balanced pricing considering all market factors

#### PREDICTIVE
- **Description:** ML-based price forecasting with confidence intervals
- **Configuration:**
  - `forecast_weight`: 0.5
  - `current_weight`: 0.3
  - `trend_weight`: 0.2
  - `ml_confidence_threshold`: 0.7
- **Use Case:** Predictive pricing based on market trends

### Usage Example

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

## Advanced Auction Types

### Overview

The marketplace now supports three advanced auction types in addition to standard bidding:

### Auction Types

#### Dutch Auction
- **Description:** Price decreases over time until a bid is accepted
- **Configuration:**
  - `start_price`: Initial high price
  - `decrement_rate`: Price decrease per interval
  - `decrement_interval`: Time between decrements (seconds)
  - `reserve_price`: Minimum acceptable price
- **Use Case:** Quick resource liquidation

#### Sealed-Bid Auction
- **Description:** Bids are encrypted until reveal time
- **Configuration:**
  - `reveal_timestamp`: When bids are revealed
  - `reserve_price`: Minimum acceptable price
- **Use Case:** Private competitive bidding

#### Reverse Auction
- **Description:** Providers compete to offer lowest price
- **Configuration:**
  - `reserve_price`: Maximum acceptable price
- **Use Case:** Cost optimization for buyers

### Usage Example

```python
from app.contexts.marketplace.services.marketplace import MarketplaceService

service = MarketplaceService(session)

# Create Dutch auction
auction = service.create_auction(
    resource_id="gpu-789",
    auction_type="dutch",
    start_price=1.0,
    decrement_rate=0.05,
    decrement_interval=60,
    reserve_price=0.30,
    duration_hours=4
)

# Submit bid
bid = service.submit_auction_bid(
    auction_id=auction.auction_id,
    provider="provider-123",
    price=0.45
)

# Update Dutch price
current_price = service.update_dutch_price(auction.auction_id)
```

## ML-Based Search and Recommendations

### Overview

The ResourceMatcher service provides intelligent resource matching with ML-based ranking and personalized recommendations.

### Features

#### Advanced Search
- Multi-factor filtering (memory, model, region, price, capabilities)
- ML-based ranking of results
- Search history tracking for personalization

#### Recommendations
- Personalized GPU recommendations based on user profile
- Popular GPUs fallback for new users
- Preference learning from search history

#### Similarity Search
- Vector embeddings for GPU resources
- Cosine similarity-based recommendations
- Real-time embedding generation

### Usage Example

```python
from app.contexts.marketplace.services.resource_matcher import ResourceMatcher

matcher = ResourceMatcher(session)

# Advanced search with ML ranking
results = matcher.advanced_search(
    filters={
        "gpu_memory_min": 16,
        "model": "A100",
        "region": "us-east",
        "price_max": 1.0
    },
    user_id="user-123",
    limit=10
)

# Get personalized recommendations
recommendations = matcher.get_recommendations(
    user_id="user-123",
    limit=5
)

# Find similar GPUs
similar = matcher.find_similar_resources(
    resource_id="gpu-456",
    limit=3
)
```

## Marketplace Analytics

### Overview

The MarketAnalytics service provides real-time market metrics, trend analysis, and forecasting.

### Features

#### Real-Time Metrics
- Total/available/booked GPU counts
- Capacity utilization
- Average pricing
- Active bookings count

#### Trend Analysis
- Booking trends over time
- Price trends
- Utilization trends
- Direction indicators

#### Forecasting
- Booking forecasts
- Price forecasts
- Utilization forecasts
- Confidence intervals

### Usage Example

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

## External Provider Integrations

### Overview

The ExternalProviderService enables integration with external GPU providers (AWS, GCP, Azure).

### Features

#### Provider Registration
- Register AWS, GCP, or Azure providers
- API key/secret management
- Sync interval configuration

#### Resource Synchronization
- Fetch external GPU resources
- Map to internal GPU registry
- Sync status tracking

#### Resource Mapping
- Bidirectional resource mapping
- Automatic internal resource creation
- Mapping persistence

### Usage Example

```python
from app.contexts.marketplace.services.external_providers import ExternalProviderService

service = ExternalProviderService(session)

# Register provider
provider = service.register_provider(
    provider_name="aws-us-east",
    provider_type="aws",
    api_key="AKIA...",
    api_secret="...",
    region="us-east-1",
    sync_interval_minutes=60
)

# Sync resources
sync_status = service.sync_resources(provider_id=provider.id)

# Map external resource
internal_gpu = service.map_to_internal(
    provider_id=provider.id,
    external_resource_id="i-12345"
)

# Check sync status
status = service.get_sync_status(provider_id=provider.id)
```

## Plugin System

### Overview

The PluginManager provides a production-ready plugin system for marketplace extensions.

### Features

#### Plugin Registration
- Register plugins with metadata
- Enable/disable plugins
- Plugin configuration management

#### Plugin Hooks
- `before_booking`: Pre-booking hook
- `after_booking`: Post-booking hook
- `before_pricing`: Pre-pricing hook
- `after_pricing`: Post-pricing hook
- `before_auction`: Pre-auction hook
- `after_auction`: Post-auction hook

#### Hook Execution
- Sequential hook execution
- Context passing
- Error handling

### Usage Example

```python
from app.contexts.marketplace.services.plugin_manager import get_plugin_manager

# Get plugin manager
plugin_manager = get_plugin_manager()

# Register plugin
plugin = plugin_manager.register_plugin(
    plugin_name="custom-pricing",
    plugin_version="1.0.0",
    plugin_type="extension",
    description="Custom pricing algorithm",
    author="AITBC"
)

# Register hook
def custom_pricing_hook(context):
    # Custom pricing logic
    context["custom_price"] = context["base_price"] * 1.1
    return context

plugin_manager.register_hook("before_pricing", custom_pricing_hook)

# Enable plugin
plugin_manager.enable_plugin("custom-pricing")

# Execute hooks in service
service = MarketplaceService(session)
context = service.before_pricing(
    resource_id="gpu-789",
    base_price=0.50
)
```

## Database Schema

### New Tables

#### Pricing Tables
- `price_history`: Historical price data for ML training
- `price_forecast`: Predicted prices with confidence intervals

#### Auction Tables
- `auction_config`: Auction metadata and configuration
- `marketplacebid`: Extended with auction-specific fields

#### Search & Recommendation Tables
- `search_history`: User search patterns
- `resource_embeddings`: Vector embeddings for similarity search
- `user_profiles`: User preferences and behavior

#### Analytics Tables
- `market_metrics`: Real-time market statistics
- `trend_data`: Historical trend data
- `analytics_events`: Marketplace event tracking

#### External Provider Tables
- `external_providers`: Provider configurations
- `provider_mappings`: External to internal resource mapping
- `sync_status`: Synchronization status tracking

#### Plugin Tables
- `plugins`: Plugin metadata and configuration
- `plugin_configs`: Plugin-specific configurations

### Migration

Run the migration script to create all tables:

```bash
python scripts/migration/create_advanced_marketplace_tables.py
```

Verify tables:
```bash
python scripts/migration/create_advanced_marketplace_tables.py --verify
```

Reset tables (WARNING: data loss):
```bash
python scripts/migration/create_advanced_marketplace_tables.py --reset
```

## API Endpoints

### Pricing Endpoints

#### Get Price Forecast
```
GET /v1/marketplace/gpu/{gpu_id}/pricing/forecast
```

#### Get Price History
```
GET /v1/marketplace/gpu/{gpu_id}/pricing/history
```

### Auction Endpoints

#### Create Auction
```
POST /v1/marketplace/gpu/{gpu_id}/auction
```

#### Submit Auction Bid
```
POST /v1/marketplace/auctions/{id}/bid
```

#### Reveal Sealed Bids
```
POST /v1/marketplace/auctions/{id}/reveal
```

#### Get Auction Status
```
GET /v1/marketplace/auctions/{id}
```

### Search & Recommendation Endpoints

#### Advanced Search
```
POST /v1/marketplace/gpu/search
```

#### Get Recommendations
```
GET /v1/marketplace/recommendations/{user_id}
```

#### Find Similar Resources
```
GET /v1/marketplace/gpu/{gpu_id}/similar
```

### Analytics Endpoints

#### Real-Time Metrics
```
GET /v1/marketplace/analytics/realtime
```

#### Market Trends
```
GET /v1/marketplace/analytics/trends
```

#### Market Forecasts
```
GET /v1/marketplace/analytics/forecast
```

### External Provider Endpoints

#### Register Provider
```
POST /v1/marketplace/external/providers
```

#### List External Resources
```
GET /v1/marketplace/external/resources
```

#### Trigger Synchronization
```
POST /v1/marketplace/external/sync
```

#### Sync Status
```
GET /v1/marketplace/external/sync/status
```

### Plugin Endpoints

#### Install Plugin
```
POST /v1/marketplace/plugins/install
```

#### List Plugins
```
GET /v1/marketplace/plugins
```

#### Enable Plugin
```
POST /v1/marketplace/plugins/{id}/enable
```

#### Disable Plugin
```
POST /v1/marketplace/plugins/{id}/disable
```

## Architecture

### Service Layer

All services follow the session injection pattern:

```python
class Service:
    def __init__(self, session: Session) -> None:
        self.session = session
```

### Singleton Pattern

Shared services use the singleton pattern:

```python
# DynamicPricingEngine
pricing_engine = get_pricing_engine()

# PluginManager
plugin_manager = get_plugin_manager()
```

### Database Models

All models use SQLModel with proper indexing:

```python
class Model(SQLModel, table=True):
    __tablename__ = "table_name"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"prefix_{uuid4().hex[:8]}", primary_key=True)
```

## Dependencies

### Required
- scikit-learn (ML models for recommendations)
- numpy (numerical computing)
- cryptography (sealed bid encryption)

### Optional
- redis (caching for analytics)
- celery (async task processing)
- boto3 (AWS integration)
- google-cloud-compute (GCP integration)
- azure-mgmt-compute (Azure integration)

## Security Considerations

### API Keys
- External provider API keys stored in database
- Encryption recommended for production

### Plugin Security
- Plugins run in same process
- Implement sandboxing for untrusted plugins
- Permission system for plugin access

### Auction Security
- Sealed bids encrypted until reveal
- Bid validation before acceptance
- Reserve price enforcement

## Performance

### Indexing
All tables have appropriate indexes for:
- Foreign keys
- Timestamps
- Status fields
- User IDs

### Caching
- Plugin manager uses singleton pattern
- Pricing engine uses singleton pattern
- Consider Redis for distributed caching

### Async Operations
- Pricing calculations are async
- External provider sync is async
- Analytics calculations are async

## Troubleshooting

### Common Issues

#### Database Migration Fails
- Check database path in migration script
- Ensure write permissions on database directory
- Use `--reset` flag to recreate tables

#### Plugin Hooks Not Executing
- Verify plugin is enabled
- Check hook registration
- Review plugin manager logs

#### External Sync Fails
- Verify API credentials
- Check network connectivity
- Review sync status for error messages

## Future Enhancements

### Planned Features
- Real ML model training for pricing
- Advanced auction types (combinatorial, Vickrey)
- More sophisticated recommendation algorithms
- Real-time analytics dashboard
- Additional external provider integrations
- Plugin marketplace

### Contributions
Contributions are welcome. Please follow the existing architectural patterns:
- SQLModel for database models
- Session injection for services
- Singleton pattern for shared services
- FastAPI for endpoints
