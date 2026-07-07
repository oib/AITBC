# marketplace

GPU and global compute marketplace — offers, matching, analytics, and provider integration.

## Domain Models

- global_marketplace.py
- gpu_marketplace.py
- marketplace.py

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
- GET /analytics/marketplace-integration
- GET /status
- GET /config
- POST /config/update
- GET /health
- POST /diagnostics/run
- GET /marketplace/offers
- GET /marketplace/stats
- GET /marketplace/plugins
- POST /marketplace/gpu/register
- GET /marketplace/gpu/list
- GET /marketplace/gpu/{gpu_id}
- POST /marketplace/gpu/purchase
- POST /marketplace/gpu/sell
- POST /marketplace/gpu/{gpu_id}/book
- POST /marketplace/gpu/{gpu_id}/release
- POST /marketplace/gpu/{gpu_id}/confirm
- POST /tasks/ollama
- POST /payments/send
- DELETE /marketplace/gpu/{gpu_id}
- GET /marketplace/gpu/{gpu_id}/reviews
- POST /marketplace/gpu/{gpu_id}/reviews
- GET /marketplace/orders
- GET /marketplace/pricing/{model}
- POST /marketplace/gpu/bid
- POST /marketplace/sync-offers
- GET /marketplace/miner-offers
- GET /offers

## Services

- external_providers.py
- global_marketplace.py
- global_marketplace_integration.py
- market_analytics.py
- marketplace.py
- marketplace_enhanced.py
- marketplace_enhanced_simple.py
- plugin_manager.py
- resource_matcher.py
