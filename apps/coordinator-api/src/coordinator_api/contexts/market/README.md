# market

GPU and global compute market — offers, matching, analytics, and provider integration.

## Domain Models

- global_market.py
- gpu_market.py
- market.py

## Routes

- POST /offers
- GET /offers
- GET /offers/{offer_id}
- POST /transactions
- GET /transactions
- GET /transactions/{transaction_id}
- GET /regions
- GET /regions/{region_code}/health
- POST /regions/{region_code}/health
- GET /analytics
- GET /config
- GET /health
- POST /offers/create-cross-chain
- GET /offers/cross-chain
- GET /offers/{offer_id}/cross-chain-details
- POST /offers/{offer_id}/optimize-pricing
- POST /transactions/execute-cross-chain
- GET /transactions/cross-chain
- GET /analytics/cross-chain
- GET /analytics/market-integration
- GET /status
- GET /config
- POST /config/update
- GET /health
- POST /diagnostics/run
- GET /market/offers
- GET /market/stats
- GET /market/plugins
- POST /market/gpu/register
- GET /market/gpu/list
- GET /market/gpu/{gpu_id}
- POST /market/gpu/purchase
- POST /market/gpu/sell
- POST /market/gpu/{gpu_id}/book
- POST /market/gpu/{gpu_id}/release
- POST /market/gpu/{gpu_id}/confirm
- POST /tasks/ollama
- POST /payments/send
- DELETE /market/gpu/{gpu_id}
- GET /market/gpu/{gpu_id}/reviews
- POST /market/gpu/{gpu_id}/reviews
- GET /market/orders
- GET /market/pricing/{model}
- POST /market/gpu/bid
- POST /market/sync-offers
- GET /market/miner-offers
- GET /offers

## Services

- external_providers.py
- global_market.py
- global_market_integration.py
- market_analytics.py
- market.py
- market_enhanced.py
- market_enhanced_simple.py
- plugin_manager.py
- resource_matcher.py
