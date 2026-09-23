# trading

Trading — order management, matching, and trading market integration.

## Domain Models

- `trading.py` — `TradeRequest`, `TradeMatch`, `TradeNegotiation`, `TradeAgreement`, `TradeSettlement`, `TradeFeedback`, `TradingAnalytics`
- `pricing_models.py` — `PricingHistory`, `ProviderPricingStrategy`, `MarketMetrics`, `PriceForecast`, `PricingAuditLog`, `PricingSummaryView`, `MarketHeatmapView`
- `pricing_strategies.py` — pricing strategy definitions and configurations

## Routes

- POST /requests
- GET /requests/{request_id}
- POST /requests/{request_id}/matches
- GET /requests/{request_id}/matches
- POST /negotiations
- GET /negotiations/{negotiation_id}
- GET /matches/{match_id}
- GET /agents/{agent_id}/summary
- GET /requests
- GET /matches
- GET /negotiations
- GET /analytics
- POST /simulate-match

## Services

- `market_data_collector.py` — `MarketDataCollector`: collects real-time market data for pricing calculations
- `trading_market/trading.py` — `MatchingEngine`: order matching logic
- `trading_market/dynamic_pricing.py` — `DynamicPricingEngine`: dynamic pricing engine
- `trading_market/bid_strategy.py` — `BidStrategyEngine`: bid strategy engine
- `trading_market/gpu_optimizer.py` — GPU optimization for trading workloads
