# API Endpoints

> **Planned-surface document.** Most routes below are **not implemented** —
> the market service only mounts `/v1/market/plugins` (GET/POST),
> `/v1/market/dynamic-pricing`, `/v1/market/pricing/{model}`,
> `/v1/market/analytics`, etc. The `gpu/{id}/pricing/*`, `gpu/search`,
> `recommendations/*`, `gpu/{id}/similar`, `analytics/realtime|trends|forecast`,
> `external/*`, and `plugins/install|enable|disable` routes do not exist;
> the underlying `ResourceMatcher`/`MarketAnalytics`/`ExternalProviderService`
> are service-layer Python APIs only.

## Pricing Endpoints

### Get Price Forecast

```
GET /v1/market/gpu/{gpu_id}/pricing/forecast
```

### Get Price History

```
GET /v1/market/gpu/{gpu_id}/pricing/history
```

## Auction Endpoints ~~(DEPRECATED v0.4.7)~~

> **⚠️ DEPRECATED (v0.4.7)**: All auction endpoints have been removed. GPU-only market auctions are no longer supported.

~~### Create Auction~~
~~```
POST /v1/market/gpu/{gpu_id}/auction

```~~

~~### Submit Auction Bid~~
~~```
POST /v1/market/auctions/{id}/bid
```~~

~~### Reveal Sealed Bids~~
~~```
POST /v1/market/auctions/{id}/reveal
```~~

~~### Get Auction Status~~
~~```
GET /v1/market/auctions/{id}
```~~

**Current Implementation:** Use `POST /v1/market/offers/{offer_id}/book` for booking hardware+software bundle offers with fixed pricing.

## Search & Recommendation Endpoints

### Advanced Search
```

POST /v1/market/gpu/search

```

### Get Recommendations
```

GET /v1/market/recommendations/{user_id}

```

### Find Similar Resources
```

GET /v1/market/gpu/{gpu_id}/similar

```

## Analytics Endpoints

### Real-Time Metrics
```

GET /v1/market/analytics/realtime

```

### Market Trends
```

GET /v1/market/analytics/trends

```

### Market Forecasts
```

GET /v1/market/analytics/forecast

```

## External Provider Endpoints

### Register Provider
```

POST /v1/market/external/providers

```

### List External Resources
```

GET /v1/market/external/resources

```

### Trigger Synchronization
```

POST /v1/market/external/sync

```

### Sync Status
```

GET /v1/market/external/sync/status

```

## Plugin Endpoints

### Install Plugin
```

POST /v1/market/plugins/install

```

### List Plugins
```

GET /v1/market/plugins

```

### Enable Plugin
```

POST /v1/market/plugins/{id}/enable

```

### Disable Plugin
```

POST /v1/market/plugins/{id}/disable

```
