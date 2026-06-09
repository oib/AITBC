# API Endpoints

## Pricing Endpoints

### Get Price Forecast
```
GET /v1/marketplace/gpu/{gpu_id}/pricing/forecast
```

### Get Price History
```
GET /v1/marketplace/gpu/{gpu_id}/pricing/history
```

## Auction Endpoints ~~(DEPRECATED v0.4.7)~~

> **⚠️ DEPRECATED (v0.4.7)**: All auction endpoints have been removed. GPU-only marketplace auctions are no longer supported.

~~### Create Auction~~
~~```
POST /v1/marketplace/gpu/{gpu_id}/auction
```~~

~~### Submit Auction Bid~~
~~```
POST /v1/marketplace/auctions/{id}/bid
```~~

~~### Reveal Sealed Bids~~
~~```
POST /v1/marketplace/auctions/{id}/reveal
```~~

~~### Get Auction Status~~
~~```
GET /v1/marketplace/auctions/{id}
```~~

**Current Implementation:** Use `POST /v1/marketplace/offers/{offer_id}/book` for booking hardware+software bundle offers with fixed pricing.

## Search & Recommendation Endpoints

### Advanced Search
```
POST /v1/marketplace/gpu/search
```

### Get Recommendations
```
GET /v1/marketplace/recommendations/{user_id}
```

### Find Similar Resources
```
GET /v1/marketplace/gpu/{gpu_id}/similar
```

## Analytics Endpoints

### Real-Time Metrics
```
GET /v1/marketplace/analytics/realtime
```

### Market Trends
```
GET /v1/marketplace/analytics/trends
```

### Market Forecasts
```
GET /v1/marketplace/analytics/forecast
```

## External Provider Endpoints

### Register Provider
```
POST /v1/marketplace/external/providers
```

### List External Resources
```
GET /v1/marketplace/external/resources
```

### Trigger Synchronization
```
POST /v1/marketplace/external/sync
```

### Sync Status
```
GET /v1/marketplace/external/sync/status
```

## Plugin Endpoints

### Install Plugin
```
POST /v1/marketplace/plugins/install
```

### List Plugins
```
GET /v1/marketplace/plugins
```

### Enable Plugin
```
POST /v1/marketplace/plugins/{id}/enable
```

### Disable Plugin
```
POST /v1/marketplace/plugins/{id}/disable
```
