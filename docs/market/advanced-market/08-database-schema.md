# Database Schema

## New Tables

### Pricing Tables

- `price_history`: Historical price data for ML training
- `price_forecasts`: Predicted prices with confidence intervals
  (migration `a0288b36720c` dropped the obsolete `price_forecast` table;
  the live model is `price_forecasts` in `trading/domain/pricing_models.py`)

### Auction Tables ~~(DEPRECATED v0.4.7)~~

~~- `auction_config`: Auction metadata and configuration~~ (REMOVED)
~~- `marketbid`: Extended with auction-specific fields~~ (REMOVED)

### Search & Recommendation Tables

- `search_history`: User search patterns
- `resource_embeddings`: Vector embeddings for similarity search
- `user_profiles`: User preferences and behavior

### Analytics Tables

- `market_metrics`: Real-time market statistics
- `trend_data`: Historical trend data
- `analytics_events`: Market event tracking

### External Provider Tables

- `external_providers`: Provider configurations
- `provider_mappings`: External to internal resource mapping
- `sync_status`: Synchronization status tracking

### Plugin Tables

- `plugins`: Plugin metadata and configuration
- `plugin_configs`: Plugin-specific configurations

## Migration

Run the migration script to create all tables:

```bash
python scripts/migration/create_advanced_market_tables.py
```

Verify tables:

```bash
python scripts/migration/create_advanced_market_tables.py --verify
```

Reset tables (WARNING: data loss):

```bash
python scripts/migration/create_advanced_market_tables.py --reset
```
